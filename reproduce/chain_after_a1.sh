#!/bin/zsh
# Đợi A1 quét xong rồi mới chạy Qwen 637 — tránh hai việc tranh cùng hạn mức Gemini.
cd /Users/hunggoodboy/Documents/HTTM-TK/MiniRAG-HTTM
while [ "$(( $(wc -l < ./logs/sources_cap.csv 2>/dev/null || echo 1) - 1 ))" -lt 800 ]; do sleep 180; done
echo "=== A1 xong, bắt đầu Qwen 637 === $(date '+%d/%m %H:%M')"
exec ./reproduce/run_qwen637.sh
