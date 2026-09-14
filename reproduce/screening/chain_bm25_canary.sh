#!/bin/zsh
# Chuỗi sàng lọc BM25 theo ROADMAP: tầng A (offline) cho B1, B2 → đông lạnh V3 canary → tầng B (canary)
# chỉ cho biến thể qua tầng A. DỪNG ở canary: dev 200 và tầng D cần duyệt riêng.
# Chạy lại được: tầng A đã có báo cáo và V3 đã FROZEN thì dùng lại, không rút parser lại, không ghi đè.
cd /Users/hunggoodboy/Documents/HTTM-TK/MiniRAG-HTTM
R=reproduce/screening/run_screen.sh
LOG=logs/screening/chain_bm25.log
mkdir -p logs/screening
stage () { echo "=== STAGE: $1 === $(date '+%d/%m %H:%M')" | tee -a $LOG; }
decision () { .venv/bin/python -c "import json,sys; print(json.load(open(sys.argv[1])).get('decision',''))" "$1" 2>/dev/null; }

for v in b1 b2; do
  if [ -n "$(decision logs/screening/$v/offline_report.json)" ]; then
    stage "OFFLINE_$v (đã có báo cáo — dùng lại)"
  else
    stage "OFFLINE_$v"
    $R --variant $v --stage offline || { stage "OFFLINE_${v}_FAILED"; exit 1; }
  fi
done
if [ "$(decision logs/screening/v3/canary_report.json)" = "FROZEN" ]; then
  stage "FREEZE_V3_CANARY (đã FROZEN — dùng lại)"
else
  stage FREEZE_V3_CANARY
  $R --variant v3 --stage canary || { stage FREEZE_V3_FAILED; exit 1; }
  [ "$(decision logs/screening/v3/canary_report.json)" = "FROZEN" ] || { stage FREEZE_V3_INCOMPLETE; exit 1; }
fi
for v in b1 b2; do
  if [ "$(decision logs/screening/$v/offline_report.json)" = "CONTINUE TO CANARY" ]; then
    stage "CANARY_$v"
    $R --variant $v --stage canary || stage "CANARY_${v}_FAILED"
  else
    stage "SKIP_CANARY_$v (tầng A: STOP)"
  fi
done
stage ALL_DONE
