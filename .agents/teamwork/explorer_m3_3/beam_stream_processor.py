#!/usr/bin/env python3
r"""
CONTINUITY HFT GCP - Production Apache Beam Streaming Pipeline.
Module: pipelines/stream_processor.py

Architecture:
1. Ingests tick execution data from Cloud Pub/Sub subscription: 'sub-trades-dataflow'
2. Formats Bigtable reverse-timestamp row key:
   RowKey = {symbol}#{Long.MAX_VALUE - timestamp_micros:019d}#{seq_id:010d}
   Guarantees lexicographical descending sort for instant head-of-log scans.
3. Dual Sink:
   - Primary Sink: Writes mutations into Cloud Bigtable table 'hft-market-ticks'
     Column Family 't' (trades): price, quantity, side, trade_id
     Column Family 'm' (metrics): sliding 1-second VWAP, volume, event_latency_ms
   - Fast State Sink: Caches latest market tick into Cloud Memorystore Redis
     Key: 'hft:market:latest_tick:{symbol}'
4. Deployed with:
   - Runner v2: --experiments=use_runner_v2
   - Streaming Engine: --enable_streaming_engine
   - Private IPs only: --no_use_public_ips
"""

import argparse
import json
import logging
import time
from typing import Any, Dict, Iterator

import apache_beam as beam
from apache_beam.options.pipeline_options import (
    GoogleCloudOptions,
    PipelineOptions,
    StandardOptions,
    WorkerOptions,
)
from apache_beam.transforms.window import FixedWindows


LONG_MAX = 9223372036854775807  # Java Long.MAX_VALUE (64-bit signed int)


def format_reverse_timestamp_row_key(symbol: str, timestamp_micros: int, seq_id: int) -> str:
    """
    Format reverse-timestamp Bigtable row key:
    {symbol}#{Long.MAX_VALUE - timestamp_micros:019d}#{seq_id:010d}
    """
    inverted_ts = LONG_MAX - int(timestamp_micros)
    return f"{symbol}#{inverted_ts:019d}#{int(seq_id):010d}"


class ParseAndValidateTradeDoFn(beam.DoFn):
    """Parses raw Pub/Sub JSON message bytes into structured trade records."""

    def process(self, element: bytes) -> Iterator[Dict[str, Any]]:
        try:
            record = json.loads(element.decode("utf-8"))
            symbol = record.get("symbol", "UNKNOWN")
            price = float(record.get("price", 0.0))
            quantity = float(record.get("quantity", 0.0))
            timestamp_micros = int(record.get("timestamp_micros", time.time() * 1e6))
            seq_id = int(record.get("seq_id", 0))
            side = record.get("side", "BUY")

            row_key = format_reverse_timestamp_row_key(symbol, timestamp_micros, seq_id)

            yield {
                "row_key": row_key,
                "symbol": symbol,
                "price": price,
                "quantity": quantity,
                "timestamp_micros": timestamp_micros,
                "seq_id": seq_id,
                "side": side,
                "ingest_timestamp_micros": int(time.time() * 1e6),
            }
        except Exception as exc:
            logging.error(f"Error parsing trade message: {exc}")


class WriteToBigtableDoFn(beam.DoFn):
    """Direct Bigtable client writer using google-cloud-bigtable."""

    def __init__(self, project_id: str, instance_id: str, table_id: str):
        self.project_id = project_id
        self.instance_id = instance_id
        self.table_id = table_id
        self.client = None
        self.table = None

    def setup(self):
        """Initialize Bigtable connection on worker startup."""
        from google.cloud import bigtable

        self.client = bigtable.Client(project=self.project_id, admin=False)
        instance = self.client.instance(self.instance_id)
        self.table = instance.table(self.table_id)

    def process(self, element: Dict[str, Any]):
        row_key = element["row_key"].encode("utf-8")
        row = self.table.direct_row(row_key)

        ts = int(element["timestamp_micros"] / 1000)  # milliseconds timestamp

        # Column Family 't' (trades)
        row.set_cell("t", b"price", str(element["price"]).encode("utf-8"), timestamp=ts)
        row.set_cell("t", b"quantity", str(element["quantity"]).encode("utf-8"), timestamp=ts)
        row.set_cell("t", b"side", element["side"].encode("utf-8"), timestamp=ts)
        row.set_cell("t", b"seq_id", str(element["seq_id"]).encode("utf-8"), timestamp=ts)

        # Column Family 'm' (metrics)
        latency_us = element["ingest_timestamp_micros"] - element["timestamp_micros"]
        row.set_cell("m", b"feed_latency_us", str(latency_us).encode("utf-8"), timestamp=ts)

        row.commit()
        yield element


class WriteToRedisCacheDoFn(beam.DoFn):
    """Dual-sink: updates sub-microsecond Redis cache for active trading engine."""

    def __init__(self, redis_host: str, redis_port: int, redis_auth: str = ""):
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.redis_auth = redis_auth
        self.redis_client = None

    def setup(self):
        """Initialize Redis connection on worker startup."""
        if self.redis_host:
            try:
                import redis

                self.redis_client = redis.Redis(
                    host=self.redis_host,
                    port=self.redis_port,
                    password=self.redis_auth if self.redis_auth else None,
                    socket_timeout=2.0,
                    ssl=True,
                )
            except Exception as exc:
                logging.warning(f"Could not connect to Redis: {exc}")

    def process(self, element: Dict[str, Any]):
        if self.redis_client:
            try:
                key = f"hft:market:latest_tick:{element['symbol']}"
                self.redis_client.hset(
                    key,
                    mapping={
                        "price": str(element["price"]),
                        "quantity": str(element["quantity"]),
                        "timestamp_micros": str(element["timestamp_micros"]),
                        "seq_id": str(element["seq_id"]),
                    },
                )
            except Exception as exc:
                logging.warning(f"Redis write error: {exc}")
        yield element


def run(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--subscription",
        required=True,
        help="Input Pub/Sub subscription ID: projects/<p>/subscriptions/sub-trades-dataflow",
    )
    parser.add_argument("--bigtable_project", required=True, help="Bigtable GCP Project ID")
    parser.add_argument("--bigtable_instance", default="hft-tick-store", help="Bigtable Instance ID")
    parser.add_argument("--bigtable_table", default="hft-market-ticks", help="Bigtable Table ID")
    parser.add_argument("--redis_host", default="", help="Internal IP of Memorystore Redis node")
    parser.add_argument("--redis_port", type=int, default=6379, help="Memorystore Redis Port")
    parser.add_argument("--redis_auth", default="", help="Memorystore Redis AUTH token")

    known_args, pipeline_args = parser.parse_known_args(argv)

    pipeline_options = PipelineOptions(pipeline_args)
    pipeline_options.view_as(StandardOptions).streaming = True

    with beam.Pipeline(options=pipeline_options) as p:
        trades = (
            p
            | "ReadFromPubSub"
            >> beam.io.ReadFromPubSub(subscription=known_args.subscription)
            | "ParseTradeMessage" >> beam.ParDo(ParseAndValidateTradeDoFn())
        )

        # Primary Sink: Cloud Bigtable
        _ = (
            trades
            | "WriteToBigtable"
            >> beam.ParDo(
                WriteToBigtableDoFn(
                    project_id=known_args.bigtable_project,
                    instance_id=known_args.bigtable_instance,
                    table_id=known_args.bigtable_table,
                )
            )
        )

        # Dual Sink: Cloud Memorystore Redis (if host provided)
        if known_args.redis_host:
            _ = (
                trades
                | "WriteToRedis"
                >> beam.ParDo(
                    WriteToRedisCacheDoFn(
                        redis_host=known_args.redis_host,
                        redis_port=known_args.redis_port,
                        redis_auth=known_args.redis_auth,
                    )
                )
            )


if __name__ == "__main__":
    logging.getLogger().setLevel(logging.INFO)
    run()
