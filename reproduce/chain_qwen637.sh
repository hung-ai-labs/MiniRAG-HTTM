#!/bin/zsh
# Chờ biến thể FIX=1 xong 637 câu rồi mới chạy FIX=0.
#
# Vì sao NỐI TIẾP chứ không song song: đã thử song song lúc 17:37 và hỏng.
# Máy có 16 GB RAM và đang dùng 4,7/6 GB swap; thêm tiến trình Python thứ ba
# (mỗi cái RSS ~450 MB, cộng đồ thị networkx + nano-vectordb nạp vào RAM) đẩy
# máy vào thrashing. Nhịp đo được:
#
#     một mình  (17:20)   13,7 s/câu     -> 4,4 câu/phút
#     song song (18:16)   31 và 51 s/câu -> 0,8 câu/phút  (chậm hơn 5 lần)
#
# Nút thắt là bộ nhớ, không phải 8 nhân CPU. Đừng chạy hai biến thể cùng lúc
# trên máy này.
cd /Users/hunggoodboy/Documents/HTTM-TK/MiniRAG-HTTM
lines () { echo $(( $(wc -l < "$1" 2>/dev/null || echo 1) - 1 )); }
while [ "$(lines ./logs/qwen637_fix.csv)" -lt 637 ]; do sleep 180; done
echo "=== FIX=1 xong 637 câu === $(date '+%d/%m %H:%M')"
exec ./reproduce/run_qwen637_one.sh 0
