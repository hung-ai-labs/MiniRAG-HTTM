#!/bin/zsh
# Hai việc dùng chung pool 12 khoá và chung giới hạn token/phút, nên chạy song
# song không nhanh hơn — chỉ làm cả hai cùng chậm. Xếp việc ngắn trước.
cd /Users/hunggoodboy/Documents/HTTM-TK/MiniRAG-HTTM
while [ "$(( $(wc -l < ./logs/entity_cap.csv 2>/dev/null || echo 1) - 1 ))" -lt 131 ]; do sleep 120; done
echo "=== đo trần xong, bắt đầu chấm lại === $(date '+%d/%m %H:%M')"
exec ./reproduce/run_full637_judgefix.sh
