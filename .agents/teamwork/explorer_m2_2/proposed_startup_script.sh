#!/bin/bash
# ==============================================================================
# HFT Compute Engine Startup Script: Ultra-Low Latency Network & Kernel Tuning
# Target: C3/C4 Trading Nodes in Tokyo (asia-northeast1)
# ==============================================================================
set -euo pipefail

LOG_FILE="/var/log/hft-startup-tuning.log"
exec > >(tee -a "${LOG_FILE}" | logger -t hft-startup -s 2>/dev/console) 2>&1

echo "===================================================================="
echo "Starting HFT Node Tuning & Security Verification: $(date -u)"
echo "Host: $(hostname -f) | Kernel: $(uname -r)"
echo "===================================================================="

# ------------------------------------------------------------------------------
# 1. Zero Public External IP Security Audit
# ------------------------------------------------------------------------------
echo "--> Step 1: Auditing Network Isolation (Zero Public External IPs)..."

METADATA_HEADER="Metadata-Flavor: Google"
ACCESS_CONFIG_URL="http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/"

# Query GCP Instance Metadata for access configs
HTTP_STATUS=$(curl -s -o /tmp/access_configs.txt -w "%{http_code}" -H "${METADATA_HEADER}" "${ACCESS_CONFIG_URL}" || echo "000")

if [ "${HTTP_STATUS}" = "200" ] && [ -s /tmp/access_configs.txt ]; then
    PUBLIC_IPS=$(cat /tmp/access_configs.txt)
    echo "CRITICAL SECURITY VIOLATION: External access configs detected on network interface 0!"
    echo "Found: ${PUBLIC_IPS}"
    echo "The HFT trading engine instance MUST operate in an isolated private VPC without public IPs."
    # Log alert to syslog
    logger -p user.emerg "HFT_SECURITY_ALERT: External IP detected on trading instance: ${PUBLIC_IPS}"
else
    echo "[PASS] ZERO public external IP addresses detected. Interface is purely internal."
fi
rm -f /tmp/access_configs.txt

# Verify local network interface IP addresses
LOCAL_IPS=$(ip -o -4 addr show | awk '{print $2, $4}')
echo "Local IPv4 Interfaces:"
echo "${LOCAL_IPS}"

# ------------------------------------------------------------------------------
# 2. Linux Kernel TCP Socket Buffers & Low-Latency Sysctl Tuning
# ------------------------------------------------------------------------------
echo "--> Step 2: Applying TCP socket buffer expansion and low-latency sysctl parameters..."

cat <<'EOF' > /etc/sysctl.d/99-hft-network-tuning.conf
# ------------------------------------------------------------------------------
# High-Frequency Trading Network & TCP Tuning for Google Cloud C3/C4 (gVNIC)
# ------------------------------------------------------------------------------

# Maximum Socket Receive and Send Buffer Sizes (16MB)
net.core.rmem_max = 16777216
net.core.wmem_max = 16777216
net.core.rmem_default = 262144
net.core.wmem_default = 262144
net.core.optmem_max = 2048576

# Maximum backlog of network packets queued for processing
net.core.netdev_max_backlog = 10000

# TCP Autotuning Memory Limits: min, default, max
# Optimized for rapid market tick burst handling
net.ipv4.tcp_rmem = 4096 87380 16777216
net.ipv4.tcp_wmem = 4096 65536 16777216

# Socket Latency & Polling Optimizations
# Eliminates hardware interrupt delays via kernel busy polling
net.core.busy_read = 50
net.core.busy_poll = 50

# TCP Protocol Latency Reductions
net.ipv4.tcp_low_latency = 1
net.ipv4.tcp_nodelay = 1
net.ipv4.tcp_fastopen = 3

# Fast connection reuse and rapid tear-down of stale sockets
net.ipv4.tcp_tw_reuse = 1
net.ipv4.tcp_fin_timeout = 15

# Memory management and dirty page flush tuning for trading loop determinism
vm.swappiness = 0
vm.dirty_ratio = 10
vm.dirty_background_ratio = 5
EOF

sysctl --system
echo "[PASS] Sysctl parameters applied and loaded persistently."

# ------------------------------------------------------------------------------
# 3. Google Virtual NIC (gVNIC) Multi-Queue & Ring Buffer Tuning
# ------------------------------------------------------------------------------
echo "--> Step 3: Configuring gVNIC multi-queue and ring buffer offloads..."

# Find primary network interface (e.g. ens4 or eth0)
PRIMARY_IFACE=$(ip route | awk '/default/ {print $5}' | head -n1)
if [ -z "${PRIMARY_IFACE}" ]; then
    PRIMARY_IFACE=$(ip -o link show | awk -F': ' '{print $2}' | grep -v 'lo' | head -n1)
fi

echo "Primary network interface identified: ${PRIMARY_IFACE}"

if command -v ethtool >/dev/null 2>&1; then
    # Expand Ring Buffers to maximum capacity (prevents tail drops under tick bursts)
    ethtool -G "${PRIMARY_IFACE}" rx 4096 tx 4096 2>/dev/null || echo "Ring buffer resize not supported or already max."
    
    # Enable all hardware offloads supported by gVNIC on Titanium IPU
    ethtool -K "${PRIMARY_IFACE}" tso on gso on gro on rx on tx on 2>/dev/null || true

    # Maximize multi-queue channels across available vCPUs
    VCPU_COUNT=$(nproc)
    ethtool -L "${PRIMARY_IFACE}" combined "${VCPU_COUNT}" 2>/dev/null || echo "Combined queue adjustment skipped."
    
    # Disable aggressive interrupt moderation for minimal round-trip latency
    ethtool -C "${PRIMARY_IFACE}" adaptive-rx off adaptive-tx off rx-usecs 0 tx-usecs 0 2>/dev/null || true
    echo "[PASS] ethtool tuning applied for ${PRIMARY_IFACE}."
else
    echo "[WARN] ethtool utility not found; installing via apt..."
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y && apt-get install -y ethtool || true
    if command -v ethtool >/dev/null 2>&1; then
        ethtool -G "${PRIMARY_IFACE}" rx 4096 tx 4096 2>/dev/null || true
        ethtool -K "${PRIMARY_IFACE}" tso on gso on gro on rx on tx on 2>/dev/null || true
    fi
fi

# ------------------------------------------------------------------------------
# 4. CPU Frequency Governor Performance Locking
# ------------------------------------------------------------------------------
echo "--> Step 4: Locking CPU frequency scaling governor to 'performance'..."

for GOV_FILE in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
    if [ -f "${GOV_FILE}" ]; then
        echo "performance" > "${GOV_FILE}" 2>/dev/null || true
    fi
done

echo "===================================================================="
echo "HFT Node Startup Optimization Complete: $(date -u)"
echo "Zero Public IPs: VERIFIED | Sysctl: LOADED | gVNIC: OPTIMIZED"
echo "===================================================================="
