#!/usr/bin/env bash
# 一键跑全套测试。现有断言只打印 PASS/FAIL 不产生退出码，
# 所以这里 grep 输出里的 FAIL 作为唯一失败信号，任一失败 exit 1。
cd "$(dirname "$0")"
FAILED=0
LOG=/tmp/sheetplayer-tests.log
: > "$LOG"

echo "=== 纯逻辑测试 (t*.js) ===" | tee -a "$LOG"
for f in t.js t2.js t3.js t4.js t6.js t7.js t8.js t9.js; do
  out=$(node "$f" 2>&1)
  echo "--- $f ---" >> "$LOG"; echo "$out" >> "$LOG"
  npass=$(echo "$out" | grep -cE '^PASS |^OK   ')
  nfail=$(echo "$out" | grep -cE '^FAIL')
  printf "%-10s %s pass / %s fail\n" "$f" "$npass" "$nfail" | tee -a "$LOG"
  if [ "$nfail" != "0" ]; then FAILED=1; fi
done

echo "=== 浏览器端到端 (pw_*.py) ===" | tee -a "$LOG"
for f in pw_*.py; do
  out=$(timeout 300 python3 "$f" 2>&1)
  echo "--- $f ---" >> "$LOG"; echo "$out" >> "$LOG"
  nok=$(echo "$out" | grep -cE '^OK   ')
  nfail=$(echo "$out" | grep -cE '^FAIL|Traceback|page errors: \[.+\]')
  printf "%-28s %s ok / %s fail\n" "$f" "$nok" "$nfail" | tee -a "$LOG"
  if [ "$nfail" != "0" ]; then FAILED=1; fi
done

echo "" | tee -a "$LOG"
if [ "$FAILED" = "0" ]; then echo "全部通过 ✓（详细日志：$LOG）" | tee -a "$LOG"
else echo "有测试失败 ✗（详细日志：$LOG）" | tee -a "$LOG"; fi
exit "$FAILED"
