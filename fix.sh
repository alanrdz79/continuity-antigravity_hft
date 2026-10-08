cd /app && for f in *\\*; do dir="${f%\\*}"; mkdir -p "$dir"; mv "$f" "${f//\\//}"; done && systemctl restart continuity-hft.service
