#!/bin/bash
# K904 範例 S3 互動演練：官方 autonomous-coding 縮小版——初始化代理切 5 項功能寫測試，寫程式代理一個 session 做一項，
#   每個 session 先重測已通過的功能，中斷後接著做；題材是官方 claude.ai 複製品的「對話管理」資料層。一次跑一步。
# 用法：bash s3.sh <步驟 1-8>；第 8 步分兩半：bash s3.sh 8（先出題）→ bash s3.sh 8b（範例答案＋還原 workdir）
#       bash s3.sh restore：把 workdir 還原成演練前 5/5 完成的備份（8b 也會問要不要還原）
#       bash s3.sh seed：新電腦用，從 s3-long-running/snapshot-5of5 重建 workdir（不呼叫模型）；
#       第 3、4、7 步和 restore 發現 workdir 與備份都不存在時也會自動重建
# 呼叫模型：只有第 5、6 步會呼叫模型，各最多 2 次（harness.py 走 shared/llm_agent.py 的 claude -p，--max-calls 2），
#       整章最多 4 次；其餘步驟全部離線
# 乾跑：bash s3.sh 5 --dry-run／bash s3.sh 6 --dry-run 改跑 harness.py --dry-run（假回覆取自 snapshot-5of5），
#       產出寫到 s3-long-running/logs/dry-run-workdir（已被 .gitignore 排除），不動真正的 workdir，只檢查腳本路徑，不算演練
# 不設任何 API 金鑰
set -u
STEP="${1:-1}"
MODE="${2:-}"
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
S3="$ROOT/s3-long-running"
WD="$S3/workdir"
BAK="$S3/workdir.bak-5of5"
DRYWD="$S3/logs/dry-run-workdir"
SNAP="$S3/snapshot-5of5"
G=$'\e[32m'; Y=$'\e[33m'; C=$'\e[36m'; R=$'\e[31m'; B=$'\e[1m'; N=$'\e[0m'

banner() { clear 2>/dev/null || true; printf '%s╔══════════════════════════════════════════════════════╗%s\n' "$C" "$N"; printf '%s  K904 範例 S3｜官方 autonomous-coding 縮小版　第 %s / 8 步%s\n' "$B" "${STEP%b}" "$N"; printf '%s  %s%s\n' "$B" "$1" "$N"; printf '%s╚══════════════════════════════════════════════════════╝%s\n\n' "$C" "$N"; }
tip() { printf '%s💡 %s%s\n\n' "$Y" "$1" "$N"; }
warn() { printf '%s⚠ %s%s\n' "$R" "$1" "$N"; }
show() { printf '%s▶ 要執行的程式：%s\n' "$G" "$N"; printf '%s' "$1" | sed "s/^/${G}  │ ${N}/"; printf '\n%s▶ 執行結果：%s\n' "$G" "$N"; }
done_step() { printf '\n%s👉 第 %s 步完成%s\n' "$C" "$STEP" "$N"; }
# 在 s3-long-running/ 底下跑一段 Python；P 用單引號包住，所以 Python 程式碼裡不能出現單引號與錢字號
run() { (cd "$S3" && PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 S3_BAK="$(basename "$BAK")" python - <<PY
import sys
sys.path.insert(0, ".")
sys.path.insert(0, "../shared")
$1
PY
); local rc=$?; done_step; return $rc; }
# 在 s3-long-running/ 底下跑一行 shell 指令
runcmd() { (cd "$S3" && eval "$1"); local rc=$?; done_step; return $rc; }
# 印出某個 workdir 的完成數，例如 5/5；沒有清單就印 none
# 傳相對於 s3-long-running/ 的名稱給 Windows 的 Python（/c/... 這種 MSYS 路徑它看不懂）
progress_of() { (cd "$S3" && PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 python -c "
import json, sys
from pathlib import Path
p = Path(sys.argv[1]) / 'feature_list.json'
if not p.exists():
    print('none'); sys.exit(0)
try:
    fs = json.loads(p.read_text(encoding='utf-8'))
    print('{}/{}'.format(sum(1 for f in fs if f.get('passes')), len(fs)))
except (ValueError, TypeError, AttributeError):
    print('broken')
" "${1#"$S3"/}"); }
# 給人看的版本：5/5 完成、沒有功能清單、清單讀不懂
label_of() { local p; p="$(progress_of "$1")"; case "$p" in none) echo 沒有功能清單 ;; broken) echo 清單讀不懂 ;; *) echo "$p 完成" ;; esac; }
is_full() { local p; p="$(progress_of "$1")"; [ "$p" != none ] && [ "$p" != broken ] && [ "${p%/*}" = "${p#*/}" ]; }

restore() {
  rm -rf "$DRYWD"
  if [ -d "$BAK" ]; then
    if ! is_full "$BAK"; then warn "備份 $(basename "$BAK") 不是全部完成（$(label_of "$BAK")），不自動還原，請手動檢查"; return 1; fi
    rm -rf "$WD" && mv "$BAK" "$WD" || { warn "還原失敗：mv 不成功（可能有檔案被其他程式開著）"; return 1; }
    printf '%s已還原：workdir.bak-5of5 → workdir%s\n' "$G" "$N"
  elif is_full "$WD"; then
    printf 'workdir 本來就是全部完成的狀態，不需要還原。\n'
  else
    warn "找不到備份 workdir.bak-5of5，workdir 目前是 $(label_of "$WD")；要回到 5/5 完成版：rm -rf s3-long-running/workdir && bash s3.sh seed（或照 s3-long-running/README.md 重跑 harness）"
    return 1
  fi
  printf 'workdir 現在：%s｜git HEAD %s\n' "$(label_of "$WD")" "$(cd "$WD" && git log -1 --format=%h 2>/dev/null)"
}

# 從 snapshot-5of5 重建 workdir：複製檔案 → git init → 一個 commit（原本的 6 個 commit 只留在 git-log.txt）
seed() {
  if [ -d "$WD" ]; then
    printf 'workdir 已經存在（%s），不重建。要從快照重來，先刪掉 s3-long-running/workdir 再跑 bash s3.sh seed。\n' "$(label_of "$WD")"
    return 0
  fi
  if [ -d "$BAK" ]; then
    printf '有 workdir.bak-5of5 備份（演練中），不從快照重建；要還原請跑 bash s3.sh restore。\n'
    return 0
  fi
  if [ ! -f "$SNAP/feature_list.json" ]; then warn "找不到快照 $SNAP/feature_list.json，無法重建"; return 1; fi
  mkdir -p "$WD" && cp -R "$SNAP"/. "$WD"/ && rm -f "$WD/README.md" "$WD/git-log.txt" \
    || { warn "複製快照失敗"; rm -rf "$WD"; return 1; }
  if ! (cd "$WD" && git init -q && git add -A \
        && git -c user.name=k904-harness -c user.email=harness@localhost commit -q \
             -m "從 snapshot-5of5 重建：5/5 完成版（原本的 git log 見 snapshot-5of5/git-log.txt）"); then
    warn "git init／commit 失敗，已刪掉重建到一半的 workdir"; rm -rf "$WD"; return 1
  fi
  printf '%s已從 snapshot-5of5 重建 workdir：%s｜git HEAD %s%s\n' "$G" "$(label_of "$WD")" "$(cd "$WD" && git log -1 --format=%h)" "$N"
}
# 第 3、4、7 步和 restore 用：workdir 與備份都不存在（例如新電腦剛 clone）就自動重建
ensure_wd() {
  if [ ! -d "$WD" ] && [ ! -d "$BAK" ]; then
    printf '%s找不到 workdir 也沒有備份（新電腦剛 clone？），先從 snapshot-5of5 自動重建。%s\n' "$Y" "$N"
    seed || exit 1
    echo
  fi
}

if [ ! -d "$S3" ]; then echo "找不到範例資料夾：$S3"; exit 1; fi

case "$STEP" in
seed) STEP=0; seed ;;

1) banner "長時間工作的難處，以及官方 autonomous-coding 的解法"
   tip "官方 autonomous-coding 是整個 quickstarts 唯一為「長時間運行」設計的專案，原題材是 claude.ai 複製品、200 項功能、要跑好幾個小時。S3 只取官方規格自己切好的第 3 步「對話管理」，5 項功能。先把三個難處對到官方與 S3 的做法。本步不呼叫模型。"
   P='from pathlib import Path

rows = [
    ("context 會滿", "一個對話做到底，前面的事被擠掉",
     "兩種角色輪流開新 session，每次全新 context", "每次 claude -p 都是新行程；提示詞只帶規格、清單、進度、git log、現有檔案"),
    ("會中斷", "當機、限流、關機，狀態全丟",
     "交接檔：feature_list.json、claude-progress.txt、git", "同上三樣＋harness_state.json；session 編號從 claude-progress.txt 數出來"),
    ("會自我放水", "自己說做好了，或改清單、改測試過關",
     "提示詞叮嚀「只能改 passes」（講義陷阱 2）", "清單只有 harness 能寫；tests/ 由初始化代理寫好就鎖住；passes 只看測試結束碼"),
    ("改壞舊功能", "做新功能時把已通過的弄壞",
     "coding_prompt 第 3 步：先重測 1～2 條已通過的", "每個 session 先重測全部已通過的，壞了就把 passes 改回 false"),
]
print("{:<10} | {:<28} | {:<40} | {}".format("難處", "會發生什麼", "官方解法", "S3 怎麼做"))
print("-" * 150)
for r in rows:
    print("{:<10} | {:<28} | {:<40} | {}".format(*r))
print()
print("兩種角色（照官方）：")
print("  初始化代理 initializer：只跑第 1 個 session（看 feature_list.json 存不存在）→ 切 5 項功能、寫 tests/ 與 init.sh")
print("  寫程式代理 coding agent：每個 session 跑 init.sh → 重測已通過 → 挑一項 → 寫 → 驗收 → 只改 passes → commit → 交接")
print()
print("縮小對照：官方 200 項網頁應用、瀏覽器驗證、要 API 金鑰 → S3 是 5 項 SQLite 資料層、unittest 驗證、claude -p 不設金鑰")
src = Path.home() / "workspace" / "claude-quickstarts" / "autonomous-coding" / "prompts" / "app_spec.txt"
lesson = Path.home() / "workspace" / "kindle-902-claude-quickstarts" / "lessons" / "ch10-autonomous-coding.md"
print("官方原始碼：~/workspace/claude-quickstarts/autonomous-coding（{}）".format("在" if src.exists() else "這台沒有"))
print("官方導讀：~/workspace/kindle-902-claude-quickstarts/lessons/ch10-autonomous-coding.md（{}）".format("在" if lesson.exists() else "這台沒有"))'
   show "$P"; run "$P" ;;

2) banner "看縮小版 app_spec.txt 和 harness 的兩階段結構"
   tip "app_spec.txt 沿用官方的 XML 標籤（project_name、overview、technology_stack…），多加一段 interface：方法名、回傳的 dict 鍵、例外型別、排序都寫死，因為測試和程式由不同 session 寫，靠它對齊。再看 harness.py 外層 run() 的判斷：沒有清單就初始化，有就跑寫程式 session，全部通過就停。本步只讀檔，不呼叫模型。"
   P='import inspect, re
from pathlib import Path
import harness

spec = Path("app_spec.txt").read_text(encoding="utf-8")
print("=== app_spec.txt（{} 行）的 XML 標籤，跟官方同名 ===".format(len(spec.splitlines())))
tags = re.findall(r"^  <([a-z_]+)>", spec, re.MULTILINE)
print("  " + "、".join(tags))
print()
print("=== 縮小的那一段：官方 implementation_steps 第 3 步 ===")
step = spec.split("<implementation_steps>")[1].split("</implementation_steps>")[0]
for line in step.strip().splitlines():
    print("  " + line.strip())
print()
print("=== interface 裡的方法簽名（實作與測試都照這個） ===")
for line in spec.split("<interface>")[1].split("</interface>")[0].splitlines():
    s = line.strip()
    if re.match(r"^(class |def |[a-z_]+\(self)", s):
        print("  " + s)
print()
print("=== harness.py 的兩階段（函式與行號） ===")
parts = [
    ("第 1 階段", harness.run_initializer, "INIT_PROMPT；validate_features 要剛好 5 項；不合格在上限內重要求 1 次；最後才寫清單"),
    ("第 2 階段", harness.regression_check, "官方第 3 步：重測已通過的功能，壞了 passes 改回 false"),
    ("第 2 階段", harness.pick_feature, "先修回歸壞掉的，再挑第一項沒過、嘗試少於 {} 次的".format(harness.MAX_ATTEMPTS)),
    ("第 2 階段", harness.run_coding, "跑 init.sh → 回歸 → 挑一項 → 模型回 JSON → 寫檔、驗收、commit"),
    ("外層", harness.run, "跑 --max-sessions 圈；全部通過就停（官方沒有這個判斷）"),
]
for stage, fn, desc in parts:
    lines, start = inspect.getsourcelines(fn)
    print("  {:<6} {:<18} 第 {:>3}～{:>3} 行｜{}".format(stage, fn.__name__, start, start + len(lines) - 1, desc))
print()
lines, start = inspect.getsourcelines(harness.run)
print("=== run() 原始碼 ===")
for i, line in enumerate(lines, start):
    print("{:>4} | {}".format(i, line.rstrip()))'
   show "$P"; run "$P" ;;

3) banner "交接檔：feature_list.json、claude-progress.txt、git log（＋harness_state.json）"
   tip "寫程式代理每次都是全新 context。它知道進度，全靠 harness 把官方的三樣交接檔塞進提示詞。feature_list.json 照官方欄位 category／description／steps／passes；嘗試次數和錯誤另外放 harness_state.json，讓清單維持「只改 passes」。本步讀現在的 workdir（演練前是 5/5 完成版），不呼叫模型。"
   P='import json, subprocess
from pathlib import Path
import harness

wd = Path("workdir")
if not (wd / "feature_list.json").exists():
    print("workdir 還沒有 feature_list.json（第 5 步會把它改名備份、從空的 workdir 重來）。執行 bash s3.sh restore 還原後再看。")
    raise SystemExit(0)
feats, state = harness.load_features(wd), harness.load_state(wd)
print("【1】feature_list.json：官方格式是 JSON 陣列，每項 {} 個欄位".format(len(feats[0])))
print("    欄位：" + "、".join(feats[0].keys()) + "（id、test_command 是本範例加的）")
for f in feats:
    print("  {:<3} {:<8} {:<10} steps {} 條｜{}".format(f["id"], harness.mark_of(f, state), f["category"], len(f["steps"]), f["description"][:46] + "…"))
print("  F1 的 steps：")
for s in feats[0]["steps"][:4]:
    print("    - " + s[:90])
print()
print("【2】harness_state.json：每項的嘗試次數與上次錯誤（不放清單裡）")
for fid, st in state["features"].items():
    print("  {} 嘗試 {} 次｜last_error：{}".format(fid, st["attempts"], "無" if st["last_error"] is None else st["last_error"][:40]))
print()
text = (wd / "claude-progress.txt").read_text(encoding="utf-8")
print("【3】claude-progress.txt：每個 session 的交接（harness 追加，{} 字）".format(len(text)))
for block in text.split("\n## ")[1:]:
    head, _, body = block.partition("\n")
    first = next((l for l in body.splitlines() if l.strip() and not l.startswith("寫入：")), "")
    print("  ## " + head)
    if first:
        print("     " + first[:80] + ("…" if len(first) > 80 else ""))
print()
print("【4】git log --oneline：初始化＋每通過一項 commit 一次")
log = subprocess.run(["git", "log", "--oneline"], cwd=wd, capture_output=True, text=True, encoding="utf-8")
lines = log.stdout.splitlines()
if len(lines) == 1 and "snapshot-5of5" in lines[0]:
    print("  " + lines[0][:90])
    print("  ↑ 這個 workdir 是從 snapshot-5of5 重建的，所以只有 1 個 commit。原本逐項 commit 的歷史在 snapshot-5of5/git-log.txt：")
    lines = Path("snapshot-5of5/git-log.txt").read_text(encoding="utf-8").splitlines()
for line in lines:
    print("  " + line[:90])
print()
nxt = harness.pick_feature(feats, state, [])
print("harness 據此推算：下一個是 Session {}，要做的功能：{}".format(
    harness.next_session_no(wd), nxt["id"] if nxt else "沒有（全部完成，重跑也不會呼叫模型）"))
print("CODE_PROMPT 帶給模型的段落：", [l for l in harness.CODE_PROMPT.splitlines() if l.startswith("=== ")])'
   show "$P"; ensure_wd; run "$P" ;;

4) banner "權限護欄：寫檔路徑、驗收指令白名單、init.sh 逐行檢查"
   tip "模型沒有任何工具（claude -p --tools \"\"），只能回 JSON。寫檔、跑測試、跑 init.sh 都由 harness 代做，所以護欄全部寫在 harness 裡。對照官方的安全三層：沙箱、檔案限專案資料夾、Bash 允許清單（init.sh 另有檢查）。先跑 --selftest，再逐項測給你看。本步不呼叫模型。"
   CMD='PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 python harness.py --selftest; echo "結束碼：$?（0＝全部規則都正常擋下）"'
   ensure_wd
   show "$CMD"; (cd "$S3" && eval "$CMD")
   echo
   P='import harness
from harness import HarnessError

def verdict(fn):
    try:
        fn()
        return "放行"
    except HarnessError as exc:
        return "擋下：" + str(exc).split("：")[0]

wd = harness.DEFAULT_WORKDIR
print("【表 1】safe_target：寫程式代理（coding）說要寫的檔案")
for rel in ["chat_store.py", "lib/util.py", "../harness.py", "C:/Windows/x.py", "/etc/passwd", ".git/config",
            "feature_list.json", "claude-progress.txt", "harness_state.json", "tests/test_f1.py", "init.sh"]:
    print("  {:<22} {}".format(rel, verdict(lambda r=rel: harness.safe_target(wd, r, "coding"))))
print("  初始化代理（init）寫 chat_store.py →", verdict(lambda: harness.safe_target(wd, "chat_store.py", "init")))
print()
print("【表 2】parse_test_command：驗收指令白名單（不經 shell，60 秒 timeout）")
for cmd in ["python -m unittest tests.test_f1", "python chat_store.py", "python -m pip install requests",
            "python -c \"import os\"", "python -m unittest tests.test_f1;rm", "bash -c ls"]:
    print("  {:<38} {}".format(cmd, verdict(lambda c=cmd: harness.parse_test_command(c))))
print()
print("【表 3】check_init_sh：init.sh 每一行都要過白名單才執行（官方 init.sh 也要額外檢查）")
for line in ["echo 檢查 Python 版本", "python --version", "python -m unittest discover -s tests",
             "npm install", "rm -rf node_modules", "curl http://example.com", "echo hi > log.txt"]:
    print("  {:<38} {}".format(line, verdict(lambda l=line: harness.check_init_sh(l))))
print()
print("【其他護欄】")
print("  harness 專屬檔：", sorted(harness.HARNESS_OWNED))
print("  功能數：剛好", harness.FEATURE_COUNT, "項；官方要 200 項，模型照官方習慣多切也會被拒收")
print("  同一項最多嘗試：", harness.MAX_ATTEMPTS, "次，用完標成 GAVE-UP（官方重試無上限）")
print("  失敗的嘗試：寫入的檔還原成 HEAD，不留在工作區；整次執行有 --max-calls 呼叫上限（預設 10）")'
   show "$P"; run "$P" ;;

5) banner "實跑示範：從空的 workdir 跑 2 個 session，看到初始化和 F1"
   tip "先把現在 5/5 完成的 workdir 改名成 workdir.bak-5of5 備份（不刪），再從空的 workdir 跑 2 個 session：Session 1 初始化代理切 5 項、寫 tests/ 與 init.sh，Session 2 寫程式代理做 F1。會呼叫模型 2 次，約 2～3 分鐘。結束碼 0＝正常，1＝harness 停止（例如 claude -p 失敗或呼叫上限用完還沒做完初始化），要照實說明。"
   if [ "$MODE" = "--dry-run" ]; then
     rm -rf "$DRYWD"
     CMD='PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 python harness.py --dry-run --workdir logs/dry-run-workdir --max-sessions 2 --max-calls 2; echo "乾跑結束碼：$?｜產出在 logs/dry-run-workdir（真正的 workdir 沒動）"'
     show "$CMD"; runcmd "$CMD"
   else
     if [ -d "$BAK" ]; then
       if ! is_full "$BAK"; then warn "已有備份但不是全部完成（$(label_of "$BAK")），為了不弄丟成果先停下，請手動檢查 $BAK"; exit 1; fi
       printf '已有 5/5 完成的備份 workdir.bak-5of5；現在的 workdir（%s）是之前演練的產物，清掉重來。\n' "$(label_of "$WD")"
       rm -rf "$WD"
     elif [ -d "$WD" ]; then
       mv "$WD" "$BAK" || { warn "改名失敗（可能有檔案被其他程式開著），停止"; exit 1; }
       printf '%s已備份：workdir（%s）→ workdir.bak-5of5%s\n' "$G" "$(label_of "$BAK")" "$N"
     fi
     printf '現在 workdir 存在嗎？%s\n\n' "$([ -d "$WD" ] && echo 是 || echo 否，從零開始)"
     CMD='PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 python harness.py --max-sessions 2 --max-calls 2; echo "結束碼：$?（0＝正常、1＝harness 停止）"'
     show "$CMD"; runcmd "$CMD"
   fi ;;

6) banner "中斷後續跑：同一條指令再跑一次，先重測 F1，再接著做 F2、F3"
   tip "上一步跑完 2 個 session 就停了，等於被中斷。什麼都不用改，同一條指令再跑一次：harness 從 claude-progress.txt 數出下一個是 Session 3，先跑 init.sh、重測已通過的 F1（官方第 3 步），再挑 F2；最多再呼叫模型 2 次（F2、F3）。F4、F5 留著沒做，正好示範「下次再跑就會接著做」。"
   if [ "$MODE" = "--dry-run" ]; then
     if [ "$(progress_of "$DRYWD")" = none ]; then
       printf 'logs/dry-run-workdir 還沒有清單，請先跑 bash s3.sh 5 --dry-run。\n'; done_step
     else
       CMD='PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 python harness.py --dry-run --workdir logs/dry-run-workdir --max-sessions 2 --max-calls 2; echo "乾跑結束碼：$?｜產出在 logs/dry-run-workdir（真正的 workdir 沒動）"'
       show "$CMD"; runcmd "$CMD"
     fi
   else
     if [ ! -d "$BAK" ]; then warn "還沒有 workdir.bak-5of5 備份，代表第 5 步還沒跑；先跑 bash s3.sh 5"; exit 1; fi
     printf '續跑前：workdir %s\n' "$(label_of "$WD")"
     if [ "$(progress_of "$WD")" = none ]; then warn "workdir 還沒有清單：第 5 步沒有成功，這次會從初始化重來（照實說明即可）"; fi
     echo
     CMD='PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 python harness.py --max-sessions 2 --max-calls 2; echo "結束碼：$?（0＝正常、1＝harness 停止）"'
     show "$CMD"; (cd "$S3" && eval "$CMD")
     printf '\n%s還沒做完的部分：%s還有 TODO 的話，下次再跑同一條指令就會接著做（本章模型預算 4 次到這裡用完，所以先停）。\n' "$B" "$N"
     done_step
   fi ;;

7) banner "用代理寫出來的 chat_store.py 跑一次示範資料"
   tip "代理接力寫出的資料層真的能用嗎？把 sample-conversations.json（虛構但照官方 schema）灌進記憶體資料庫，依序跑 F1～F5：列表排序、改名、軟刪除、搜尋 50%／底線／中文、依日期分組。剛剛演練的 workdir 若還沒 5/5，就改用備份版。最後跑全部驗收測試。本步不呼叫模型。"
   P='import json, os, subprocess, sys
from datetime import datetime
from pathlib import Path
import harness

drill, full = Path("workdir"), Path(os.environ["S3_BAK"])
def status(d):
    if not (d / "feature_list.json").exists():
        return "沒有功能清單"
    feats = harness.load_features(d)
    return "{}/{} 完成".format(sum(f["passes"] for f in feats), len(feats))
print("演練的 workdir：{}｜備份 workdir.bak-5of5：{}".format(status(drill), status(full) if full.exists() else "不存在"))
target = drill
if not ((drill / "feature_list.json").exists() and all(f["passes"] for f in harness.load_features(drill))):
    target = full if full.exists() else drill
print("這一步用：", target.as_posix())
if not (target / "chat_store.py").exists():
    print("找不到 chat_store.py，請先 bash s3.sh restore 或 bash s3.sh seed")
    raise SystemExit(1)
sys.path.insert(0, str(target))
from chat_store import ChatStore, group_by_date
data = json.loads(Path("sample-conversations.json").read_text(encoding="utf-8"))
now = datetime.fromisoformat(data["now"])
ts = datetime.fromisoformat
store, ids = ChatStore(":memory:"), {}
for c in data["conversations"]:
    ids[c["title"]] = store.create_conversation(c["title"], now=ts(c["created_at"]))["id"]
    for m in c["messages"]:
        store.add_message(ids[c["title"]], m["role"], m["content"], now=ts(m["created_at"]))
print("示範用的「現在」：", data["now"])
print()
print("【F1】list_conversations（updated_at 新到舊）")
for c in store.list_conversations():
    print("  #{} {}  {}".format(c["id"], c["updated_at"], c["title"]))
print()
r = store.rename_conversation(ids["Long-running agent 讀書心得"], "  長時間代理讀書心得  ", now=now)
print("【F2】rename_conversation → 標題 {!r}，updated_at {}（排到第一）".format(r["title"], r["updated_at"]))
print("  現在第一筆：", store.list_conversations()[0]["title"])
print()
print("【F4】search_conversations（刪除前）")
for q in ["50%", "_", "太魯閣", "LIKE", "不存在的字"]:
    print("  {:<10} → {}".format(repr(q), [c["title"] for c in store.search_conversations(q)]))
print()
store.delete_conversation(ids["要刪除的測試對話"], now=now)
print("【F3】delete_conversation(要刪除的測試對話) 之後")
print("  列表剩 {} 筆；搜尋 50% → {}".format(len(store.list_conversations()), [c["title"] for c in store.search_conversations("50%")]))
try:
    store.get_conversation(ids["要刪除的測試對話"])
    print("  get_conversation 還拿得到（不合規格）")
except KeyError:
    print("  get_conversation → KeyError（合規格：軟刪除後視為不存在）")
print()
print("【F5】group_by_date(now={})".format(data["now"]))
for g in group_by_date(store.list_conversations(), now):
    print("  {:<16} {}".format(g["group"], ["{}（{}）".format(c["title"], c["updated_at"][:10]) for c in g["conversations"]]))
store.close()
print()
env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
t = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=target,
                   capture_output=True, text=True, encoding="utf-8", env=env)
print("=== 全部驗收測試：python -m unittest discover -s tests（結束碼 {}） ===".format(t.returncode))
print("  " + next((l for l in t.stderr.splitlines() if l.startswith("Ran ")), "") + "｜" + (t.stderr.strip().splitlines() or ["（無輸出）"])[-1])'
   show "$P"; ensure_wd; run "$P" ;;

8) banner "三個靈魂拷問：先自己回答"
   tip "先不要看答案。對著 S3 想一想三題，各用一兩句話說出來；第 2 題特別想一下：官方原版的模型有 Read／Write／Bash，S3 的模型什麼工具都沒有，那 init.sh 是誰寫、誰執行、怎麼擋？想好之後說「繼續」，教練會執行 bash s3.sh 8b。"
   P='qs = [
    "1. 這個代理是做給誰用的？（誰下指令、有沒有人在旁邊看著）",
    "2. 被賦予了哪些工具權限？（模型能做什麼、harness 代做什麼、init.sh 怎麼處理、刻意不給什麼）",
    "3. 資料和成果最後存在哪裡？（哪些交接檔是記憶、哪些進版控、哪些不進）",
]
print("三個靈魂拷問：")
for q in qs:
    print("  " + q)
print()
print("提示：第 3 步的交接檔、第 4 步三張表被擋下的路徑與指令、第 5～6 步的 --max-calls 都是線索。")
print("想好後說「繼續」→ bash s3.sh 8b")'
   show "$P"; run "$P" ;;

8b) banner "三個靈魂拷問：範例答案＋縮小了什麼、保留了什麼"
   tip "範例答案直接從 s3-long-running/README.md 第 2 節讀出來。後半對照官方原版：縮小的是題材規模和權限，保留的是兩種角色、交接檔、只改 passes、先重測再做新的。最後把 workdir 還原成演練前 5/5 完成的備份。"
   P='import re
from pathlib import Path

readme = Path("README.md").read_text(encoding="utf-8")
rows = [line for line in readme.splitlines() if re.match(r"^[|] (做給誰用|工具權限|資料與成果)", line)]
print("=== 範例答案（摘自 s3-long-running/README.md） ===")
for line in rows:
    cells = [c.strip() for c in line.strip("|").split("|")]
    q, a = cells[0], re.sub(r"<br/?>", " ", cells[1]).replace("**", "").replace(chr(96), "")
    print("■ " + q)
    print("  " + a)
    print()
if len(rows) != 3:
    print("（README 表格只讀到 {} 列，請直接打開 README 第 2 節看）".format(len(rows)))
print("=== 縮小了什麼、保留了什麼 ===")
pairs = [
    ("規模", "200 項、claude.ai 複製品網頁應用", "5 項、對話管理 SQLite 資料層"),
    ("模型呼叫", "Claude Agent SDK，要 API 金鑰", "claude -p，不設金鑰（Max 訂閱）"),
    ("模型工具", "Read／Write／Bash／Puppeteer", "沒有，只回 JSON；harness 代做"),
    ("驗收", "瀏覽器截圖", "python -m unittest"),
    ("保留", "兩種角色、交接檔、只改 passes、先重測再做新的", "同左，而且改由程式強制，不只靠提示詞"),
    ("補上", "沒有全部完成就停、重試無上限", "全部通過就停、每項最多 2 次、--max-calls 上限"),
]
print("{:<8} | {:<44} | {}".format("項目", "官方 autonomous-coding", "K904 S3"))
print("-" * 110)
for r in pairs:
    print("{:<8} | {:<44} | {}".format(*r))
print()
print("一句話：無人看著跑好幾個小時，程式就是唯一的護欄，所以規則要寫進 harness，不能只寫在提示詞。")'
   show "$P"; (cd "$S3" && PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 python - <<PY
$P
PY
)
   echo
   printf '%s=== 還原 workdir ===%s\n' "$B" "$N"
   printf '演練的 workdir：%s｜備份 workdir.bak-5of5：%s\n' "$(label_of "$WD")" "$([ -d "$BAK" ] && label_of "$BAK" || echo 不存在)"
   if [ -d "$BAK" ] || [ -d "$DRYWD" ]; then
     ans=n
     if [ -t 0 ]; then printf '%s⌨  要現在把 workdir 還原成 5/5 完成的備份嗎？（演練產物會刪掉）[y/N] %s' "$Y" "$N"; read -r ans; fi
     case "$ans" in
       y|Y) restore ;;
       *) printf '先不還原。之後要還原，執行：bash %s restore\n' "$0" ;;
     esac
   else
     printf 'workdir 就是原本的版本，不需要還原。\n'
   fi
   done_step ;;

restore) STEP=8b; ensure_wd; restore ;;

*) echo "步驟要 1～8（第 8 步的後半是 8b）；還原 workdir 用 restore；新電腦從快照重建 workdir 用 seed"; exit 2 ;;
esac
