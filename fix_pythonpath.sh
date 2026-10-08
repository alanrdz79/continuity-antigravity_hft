sed -i "/Environment=\"GCP_REGION/a Environment=\"PYTHONPATH=/app\"" /etc/systemd/system/continuity-hft.service && systemctl daemon-reload && systemctl restart continuity-hft.service
