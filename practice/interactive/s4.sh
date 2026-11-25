#!/bin/bash
# K904 範例 S4 互動演練：代管式每日簡報代理（官方 managed-agents/daily-brief 原題材，本機模擬），一次跑一步
# 用法：bash s4.sh <步驟 1-9>；第 9 步分兩半：bash s4.sh 9（先出題）→ bash s4.sh 9b（範例答案＋本機和雲端的差別）
# 呼叫模型：只有第 4、5、6 步會呼叫模型，每步通常 2 次、最多 4 次（claude -p，透過 shared/llm_agent.py），整份最多 12 次
# 乾跑：bash s4.sh 4|5|6 --dry-run 用寫死的假回覆代替模型，state／outbox／runs 寫在暫存資料夾、跑完刪除，不算演練
# 第 4 步（非乾跑）會先清空 s4-daily-brief/state 與 outbox，從第 1 天重新開始；其他步驟不改範例資料夾裡的任何檔案
set -u
STEP="${1:-1}"
MODE="${2:-}"
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$HERE/../.."
G=$'\e[32m'; Y=$'\e[33m'; C=$'\e[36m'; B=$'\e[1m'; N=$'\e[0m'

banner() { clear; printf '%s╔══════════════════════════════════════════════════════╗%s\n' "$C" "$N"; printf '%s  K904 範例 S4｜代管式每日簡報代理　第 %s / 9 步%s\n' "$B" "${STEP%b}" "$N"; printf '%s  %s%s\n' "$B" "$1" "$N"; printf '%s╚══════════════════════════════════════════════════════╝%s\n\n' "$C" "$N"; }
tip() { printf '%s💡 %s%s\n\n' "$Y" "$1" "$N"; }
show() { printf '%s▶ 要執行的程式：%s\n' "$G" "$N"; printf '%s' "$1" | sed "s/^/${G}  │ ${N}/"; printf '\n%s▶ 執行結果：%s\n' "$G" "$N"; }
# 在 repo 根目錄執行；P 用單引號包住，所以 Python 程式碼裡不能出現單引號、錢字號與反斜線
run() { (cd "$REPO" && PYTHONUTF8=1 PYTHONUNBUFFERED=1 S4_MODE="$MODE" python - <<PY
import sys
sys.path.insert(0, "s4-daily-brief")
sys.path.insert(0, "shared")
$1
PY
); rc=$?; printf '\n%s👉 第 %s 步完成（結束碼 %s）%s\n' "$C" "$STEP" "$rc" "$N"; return $rc; }

# 第 4～6 步共用：呼叫 run_session.py，再讀最新 session 的 summary.json 算模型呼叫次數
SESSION_HELPER='import json, os, subprocess, sys, time
from pathlib import Path
DRY = os.environ.get("S4_MODE") == "--dry-run"
BASE = Path("s4-daily-brief")
def session(args):
    if DRY:
        args = args + ["--dry-run"]
        print("【乾跑，不算演練】模型是寫死的假回覆，資料寫在暫存資料夾、跑完刪除；正式演練不要加 --dry-run。")
    before = set((BASE / "runs").glob("sesn_*"))
    started = time.time()
    proc = subprocess.run([sys.executable, "run_session.py"] + args, cwd=BASE, text=True,
                          encoding="utf-8", errors="replace", timeout=900)
    print()
    print("run_session.py 結束碼：", proc.returncode, "｜耗時 {:.1f} 秒".format(time.time() - started))
    new = sorted(set((BASE / "runs").glob("sesn_*")) - before)
    if DRY or not new:
        return None
    summary = json.loads((new[-1] / "summary.json").read_text(encoding="utf-8"))
    print("模型呼叫：{} 次（上限 4）｜狀態：{}".format(summary["model_calls"], summary["status"]))
    return summary
'

case "$STEP" in
1) banner "官方 daily-brief 由哪些資源組成"
   tip "官方 daily-brief 沒有任何常駐主機程式：六個資源檔用 ant apply 套上去，之後每個工作日由排程開一個全新 session。連續性完全靠 state 這個 memory store。S4 不用 API，改由 run_session.py 扮演伺服器、Slack 和 GitHub，每個資源各用一個本機檔案代替。"
   P='from pathlib import Path

base = Path("s4-daily-brief")
rows = [
    ("agent", "模型、工具、系統提示（8 個步驟）", "agents/daily-brief/agent.json＋agent-lock.json", "agent.md"),
    ("deployment", "排程、記憶體掛載權限、預算、首則訊息", "agents/daily-brief/deployment.json", "deployment.md"),
    ("preferences", "讀者規則，代理唯讀", "preferences/preferences.md", "memory store（read_only）"),
    ("state", "書籤、帳本、notes、proposals、執行紀錄", "state/（執行後才出現）", "memory store（read_write）"),
    ("來源", "Slack 頻道與 GitHub PR", "fixtures/day1、day2（虛構）", "Slack API＋GitHub MCP"),
    ("目的地", "貼簡報的頻道", "outbox/C0345678912.jsonl", "chat.postMessage"),
    ("憑證", "Slack bot token、GitHub token", "不需要", "vault.yaml"),
    ("評分", "照 rubric 打分，不過就重寫", "rubric.md＋評分者 claude -p", "（官方沒有，沿用 K903）"),
]
print("{:<12} | {:<30} | {:<44} | {}".format("資源", "做什麼", "S4 本機檔案", "官方"))
print("-" * 130)
for r in rows:
    print("{:<12} | {:<30} | {:<44} | {}".format(*r))
print()
for rel in ["run_session.py", "deploy.py", "reset_state.py", "rubric.md", "preferences/preferences.md",
            "agents/daily-brief/agent.json", "agents/daily-brief/deployment.json"]:
    p = base / rel
    print("  {:<36} {}".format(rel, "{} 行".format(len(p.read_text(encoding="utf-8").splitlines())) if p.is_file() else "（找不到）"))
print("  state/ 目前", "存在" if (base / "state").exists() else "還不存在（第 1 天執行前就是這樣）")
print()
try:
    import qs_source
    for pat in ("rules and is read-only", "this is a dry run"):
        hits = qs_source.grep("managed-agents/daily-brief/agents/daily-brief/agent.md", pat)
        if hits:
            print("官方 agent.md 第 {} 行：{}".format(hits[0][0], hits[0][1].strip()[:150]))
except Exception as exc:
    print("（這台電腦沒有官方 repo，略過原始碼對照：{}）".format(type(exc).__name__))'
   show "$P"; run "$P" ;;
2) banner "看 agent.json、版本鎖和 deployment.json"
   tip "agent.json 的 tools 是主機會代執行的五個工具；denied_tools 是刻意不給的，官方也關掉 web_search、web_fetch，免得讀到的注入文字有對外出口。後半在暫存資料夾示範：改了 model 卻沒升 version，程式在建立 session 前就拒絕，不會呼叫模型。"
   P='import json, shutil, tempfile
from pathlib import Path
import run_session as rs

d = Path("s4-daily-brief/agents/daily-brief")
agent = json.loads((d / "agent.json").read_text(encoding="utf-8"))
dep = json.loads((d / "deployment.json").read_text(encoding="utf-8"))
print("=== agent.json ===")
for k, v in agent.items():
    text = json.dumps(v, ensure_ascii=False)
    print("  {:<15} {}".format(k, text if len(text) <= 80 else text[:80] + "…（共 {} 字）".format(len(text))))
print()
print("可以用 tools：", agent["tools"])
print("刻意不給 denied_tools：", agent["denied_tools"])
print()
print("=== deployment.json ===")
for k in ("schedule", "preferences_access", "state_access", "first_message"):
    print("  {:<19} {}".format(k, json.dumps(dep[k], ensure_ascii=False)))
print()
_, digest = rs.load_agent(d)
lock = json.loads((d / "agent-lock.json").read_text(encoding="utf-8"))
print("版本鎖：", lock, "｜現在指紋：", digest, "→ 一致" if lock.get(str(agent["version"])) == digest else "→ 不一致！")
print()
tmp = Path(tempfile.mkdtemp(prefix="k904-s4-lock-"))
try:
    shutil.copytree(d, tmp / "a")
    changed = dict(agent, model="haiku")
    (tmp / "a" / "agent.json").write_text(json.dumps(changed, ensure_ascii=False), encoding="utf-8")
    try:
        rs.load_agent(tmp / "a")
        print("（沒被擋，不正常）")
    except SystemExit as exc:
        print("暫存副本改 model 不升 version →", exc)
    (tmp / "a" / "agent.json").write_text(json.dumps(dict(changed, version=agent["version"] + 1), ensure_ascii=False), encoding="utf-8")
    _, d2 = rs.load_agent(tmp / "a")
    print("升成第 {} 版 → 放行，指紋 {}；鎖裡兩版並存：{}".format(agent["version"] + 1, d2,
          (tmp / "a" / "agent-lock.json").read_text(encoding="utf-8").replace(chr(10), " ")))
finally:
    shutil.rmtree(tmp, ignore_errors=True)
print("真正的 agent.json、agent-lock.json 都沒有被改動。")'
   show "$P"; run "$P" ;;
3) banner "兩天份虛構資料：讀不到的頻道、注入文字、主機先整理好的候選"
   tip "資料都是虛構但照官方格式：Slack 外層有 ok 欄位，PR 有 html_url。第 1 天 #example-escalations 回 ok:false（not_in_channel），support 頻道裡藏了一則叫 assistant 轉貼到 #general 的注入文字。最後在暫存資料夾跑主機的第 1～3 步（不呼叫模型），看模型實際會拿到什麼。"
   P='import json, shutil
from pathlib import Path
import run_session as rs

base = Path("s4-daily-brief/fixtures")
for day in ("day1", "day2"):
    meta = json.loads((base / day / "meta.json").read_text(encoding="utf-8"))
    print("=== {}：{} ===".format(day, meta["now"]))
    print("  " + meta["說明"])
    for f in sorted((base / day).rglob("*.json")):
        if f.name == "meta.json":
            continue
        body = json.loads(f.read_text(encoding="utf-8"))
        if "pull_requests" in body:
            print("  github {}：".format(body["repo"]), ", ".join("#{}({})".format(p["number"], p["state"]) for p in body["pull_requests"]))
        elif body.get("ok") is not True:
            print("  slack {}：ok={} error={}  ← 讀不到".format(f.stem, body.get("ok"), body.get("error")))
        else:
            print("  slack {}：{} 則訊息".format(body["channel"]["name"], len(body["messages"])))
            for m in body["messages"]:
                flag = "  ← 注入文字" if "assistant" in m["text"] else ""
                print("     - {}{}".format(m["text"][:46], flag))
    print()
print("=== 主機第 1～3 步（暫存資料夾、不呼叫模型）：第 1 天模型會拿到什麼 ===")
tmp = rs.use_sandbox(copy_existing=False)
try:
    agent, digest = rs.load_agent(rs.AGENT_DIR)
    s = rs.Session(agent, digest, "day1", rehearsal=True)
    ctx = rs.prepare(s, rs.PREFS_PATH)
    print()
    print("今天的標題：", ctx["title"], "｜長度上限：", ctx["prefs"]["length_cap"], "行｜目的地：", ctx["prefs"]["destination"])
    print("讀不到：", ctx["unreadable"])
    print("新候選 {} 項（主機不替模型挑，dependabot、閒聊、注入文字都在裡面）：".format(len(ctx["items"]["new"])))
    for it in ctx["items"]["new"]:
        print("  -", it["id"])
finally:
    shutil.rmtree(tmp, ignore_errors=True)'
   show "$P"; run "$P" ;;
4) banner "演習：state 唯讀，寫簡報但不貼、不記帳"
   tip "官方把 state 設成 read_only 就是演習：照樣寫簡報，但什麼都不貼、state 一個字都不改。這一步先清空 state 與 outbox 從頭開始，再呼叫模型通常 2 次（寫手＋評分者），最多 4 次，約 30～90 秒。最後比對演習前後的雜湊。"
   P="$SESSION_HELPER"'
if not DRY:
    r = subprocess.run([sys.executable, "reset_state.py"], cwd=BASE, capture_output=True, text=True, encoding="utf-8")
    print("先清空：", r.stdout.strip())
    print()
s = session(["--day", "day1", "--rehearsal"])
if s:
    print("演習前雜湊：", s["hash_before"])
    print("演習後雜湊：", s["hash_after"], "→", "完全沒變" if s["hash_before"] == s["hash_after"] else "被改動了！")
    print("state/ 存在嗎：", (BASE / "state").exists(), "｜outbox/ 存在嗎：", (BASE / "outbox").exists())'
   show "$P"; run "$P" ;;
5) banner "第 1 天正式跑：貼文成功才記帳"
   tip "第 1 天 state 不存在＝第一次執行，讀最近 24 小時。呼叫模型通常 2 次，最多 4 次。貼文前先寫 status: posting，讀回 ok:true 和 ts 才記帳。注意 #example-escalations 讀不到，它的書籤不會前進。"
   P="$SESSION_HELPER"'
s = session(["--day", "day1"])
if s:
    out = BASE / "outbox" / "C0345678912.jsonl"
    print()
    print("=== outbox（模擬的 #example-brief）===")
    for line in out.read_text(encoding="utf-8").splitlines() if out.exists() else []:
        rec = json.loads(line)
        print("  ts={} title={}".format(rec["ts"], rec["title"]))
    print()
    print("=== state/ledger.md ===")
    print((BASE / "state/ledger.md").read_text(encoding="utf-8") if (BASE / "state/ledger.md").exists() else "（沒有，代表沒記帳）")
    print("=== state/bookmarks.json ===")
    for k, v in json.loads((BASE / "state/bookmarks.json").read_text(encoding="utf-8")).items():
        print("  {:<32} {}".format(k, v["iso"]))'
   show "$P"; run "$P" ;;
6) banner "第 2 天：書籤與帳本有沒有作用"
   tip "第 2 天要看三件事：第 1 天報過、還開著的 #101 只寫一行「仍在等，第 2 天」；已合併的 #102 不出現；第 1 天讀不到的 escalations 從原書籤重讀，所以看得到第 1 天凌晨那則事故訊息。呼叫模型通常 2 次，最多 4 次。"
   P="$SESSION_HELPER"'
s = session(["--day", "day2"])
if s:
    brief = s["brief"]
    checks = [
        ("#101 標「第 2 天」", "pull/101" in brief and "第 2 天" in brief),
        ("#102（已合併）不出現", "pull/102" not in brief),
        ("escalations 第 1 天的事故訊息有被重讀", "p1795372000000100" in brief),
        ("第 1 天報過的 Beta SSO 不重報", "p1795389900000400" not in brief),
        ("最後沒有「讀不到」（兩天都讀到了）", "讀不到" not in brief),
    ]
    print()
    for name, ok in checks:
        print("  {} {}".format("PASS" if ok else "FAIL", name))
    print()
    print("=== state/ledger.md（第 2 天追加的行）===")
    for line in (BASE / "state/ledger.md").read_text(encoding="utf-8").splitlines():
        if line.startswith("- 2026-11-24"):
            print("  " + line)'
   show "$P"; run "$P" ;;
7) banner "失敗時怎麼辦：同日重跑、STOP、貼文失敗（離線）"
   tip "官方最在意失敗時的行為。這一步在暫存副本做、不呼叫模型（萬一呼叫就直接報錯）：同一天重跑不會重貼；preferences 寫 STOP 就停；目的地頻道不存在時記 held、保留簡報，帳本和書籤一個字都不動。貼文失敗那段用第 6 步真模型寫的簡報。"
   P='import hashlib, json, shutil
from pathlib import Path
import run_session as rs

base = Path("s4-daily-brief")
runs = sorted(base.glob("runs/sesn_*/summary.json"))
day2 = [json.loads(p.read_text(encoding="utf-8")) for p in runs]
day2 = [s for s in day2 if s["day"] == "day2" and str(s["status"]).startswith("posted") and not s["dry_run"]]
if not day2 or not (base / "state").exists():
    print("還沒有第 2 天的正式紀錄，請先跑第 5、6 步。")
    raise SystemExit(0)
def guard(*a, **k):
    raise RuntimeError("這一步不該呼叫模型")
rs.run_claude = guard
tmp = rs.use_sandbox(copy_existing=True)
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()[:12] if p.exists() else "-"
try:
    print("=== (a) 同一天（第 2 天）再跑一次 ===")
    s = rs.run("day2")
    print("  → 模型呼叫", s.model_calls, "次；", json.loads((s.dir / "summary.json").read_text(encoding="utf-8"))["status"])
    print()
    print("=== (b) preferences 最後一行改成 STOP ===")
    stop = tmp / "stop.md"
    stop.write_text(rs.PREFS_PATH.read_text(encoding="utf-8").replace("- RUN", "- STOP"), encoding="utf-8")
    s = rs.run("day2", prefs_path=stop)
    print("  → 模型呼叫", s.model_calls, "次；", json.loads((s.dir / "summary.json").read_text(encoding="utf-8"))["status"])
    print()
    print("=== (c) 目的地 channel_not_found：用第 6 步真模型寫的簡報再貼一次 ===")
    shutil.rmtree(rs.OUTBOX_DIR)
    before = {n: sha(rs.STATE_DIR / n) for n in ("ledger.md", "bookmarks.json")}
    agent, digest = rs.load_agent(rs.AGENT_DIR)
    s = rs.Session(agent, digest, "day2", rehearsal=False)
    ctx = rs.prepare(s, rs.PREFS_PATH)
    final = {"brief": day2[-1]["brief"], "items": [{"id": i} for i in day2[-1]["items"]], "cuts": [],
             "grades": [{"overall": "PASS"}]}
    status = rs.publish(s, ctx, final, fail_post=True)
    after = {n: sha(rs.STATE_DIR / n) for n in ("ledger.md", "bookmarks.json")}
    print("  → 狀態：", status, "｜outbox 存在嗎：", rs.OUTBOX_DIR.exists())
    for n in before:
        print("  {} {} → {}  {}".format(n, before[n], after[n], "沒動" if before[n] == after[n] else "被改了！"))
    record = (rs.STATE_DIR / "runs" / "2026-11-24.md").read_text(encoding="utf-8")
    tail = record[record.rfind("## sesn_"):]
    print("  執行紀錄最後一節：")
    for line in tail.splitlines()[:8]:
        print("    " + line)
finally:
    shutil.rmtree(tmp, ignore_errors=True)
print()
print("以上都在暫存副本，真的 state／outbox 沒有變動。")'
   show "$P"; run "$P" ;;
8) banner "deploy.py --dry-run：排程怎麼寫、雲端版要花多少"
   tip "排程的本質是「每個工作日固定時間開一個新 session」。官方 cron 是 32 7 * * 1-5（紐約時間），本範例改台北時間。deploy.py 只印不建：不加 --dry-run 就拒絕。官方 README 實測每次約 1.00～1.50 美元，預算 500 是以「分」為單位的字串，到上限是暫停不是失敗。"
   P='import subprocess, sys
from pathlib import Path

def call(args):
    return subprocess.run([sys.executable, "deploy.py"] + args, cwd="s4-daily-brief", capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=30)

p = call(["--dry-run"])
print("=== python deploy.py --dry-run（結束碼 {}）===".format(p.returncode))
print(p.stdout.replace(str(Path.home()), "~"))
p = call([])
print("=== 不加 --dry-run（結束碼 {}，預期 2）===".format(p.returncode))
print("  " + p.stderr.strip())
if sys.platform == "win32":
    q = subprocess.run(["schtasks", "/Query", "/TN", "K904-S4-daily-brief"], capture_output=True, text=True,
                       encoding="cp950", errors="replace")
    print()
    print("確認沒有真的建排程：schtasks /Query 結束碼", q.returncode, "（非 0＝查無此排程）")
print()
print("費用對照：本機版走 claude -p（Max 訂閱），每天通常 2 次、最多 4 次呼叫；")
print("          官方雲端版每次約 1.00～1.50 美元，一年約 260 個工作日 ≈ 260～390 美元。")'
   show "$P"; run "$P" ;;
9) banner "三個靈魂拷問：先自己回答"
   tip "先不要看答案。對著 S4 想一想三題，各用一兩句話說出來。第 2 題特別想一下：模型自己碰得到 Slack 嗎？第 3 題想一下：帳本和書籤如果放在雲端，誰保管？想好之後說「繼續」，教練會執行 bash s4.sh 9b。"
   P='qs = [
    "1. 這個代理是給誰用的？（幾個讀者、有沒有人即時看著、所以它遇到問題該怎麼辦）",
    "2. 被賦予了哪些工具權限？（可以用什麼、刻意不給什麼、誰在檢查白名單、讀到注入文字會怎樣）",
    "3. 資料和成果最後存在哪裡？（輸入、跨日狀態、每次 session、貼文各在哪；換成真雲端又在哪）",
]
print("三個靈魂拷問：")
for q in qs:
    print("  " + q)
print()
print("提示：第 2 步的 tools／denied_tools、第 5 步的 state/、第 7 步的 held 都是線索。")
print("想好後說「繼續」→ bash s4.sh 9b")'
   show "$P"; run "$P" ;;
9b) banner "三個靈魂拷問：範例答案＋本機和真雲端的差別"
   tip "範例答案直接從 s4-daily-brief/README.md 的表格讀出來。重點在第 3 題：本機版的跨日記憶就是 state 資料夾，刪掉就失憶；真雲端版放在 Anthropic 保管的 memory store，preferences 唯讀、state 讀寫由 deployment 決定。"
   P='import re
from pathlib import Path

readme = Path("s4-daily-brief/README.md").read_text(encoding="utf-8")
rows = [line for line in readme.splitlines() if re.match("^[|] (這個代理|被賦予|資料和成果)", line)]
print("=== 範例答案（摘自 s4-daily-brief/README.md）===")
for line in rows:
    cells = [c.strip() for c in line.strip("|").split("|")]
    print("■ " + cells[0])
    print("  " + cells[1].replace("**", "").replace(chr(96), ""))
    print()
if len(rows) != 3:
    print("（README 表格只讀到 {} 列，請直接打開 README 第 2 節）".format(len(rows)))
change = [
    ("讀者規則", "preferences/preferences.md（git 裡）", "preferences memory store，deployment 掛成 read_only"),
    ("跨日狀態", "state/（本機，不進版控）", "state memory store（Anthropic 保管，read_write）"),
    ("session", "runs/<sesn_id>/", "Anthropic 伺服器，用 session ID 查"),
    ("來源", "fixtures/（虛構 JSON）", "真的 Slack 頻道與 GitHub repo"),
    ("貼文", "outbox/C0345678912.jsonl", "真的 Slack 頻道，所有成員都看得到"),
    ("憑證", "不需要", "vault：Slack bot token、唯讀 GitHub token"),
]
print("=== 第 3 題：本機模擬 vs 真正雲端 ===")
print("{:<8} | {:<36} | {}".format("項目", "本機模擬（S4）", "真正雲端（Managed Agents）"))
print("-" * 110)
for r in change:
    print("{:<8} | {:<36} | {}".format(*r))
print()
print("一句話：本機版「記憶在自己的資料夾、刪掉就重來」；雲端版「記憶由 Anthropic 保管，換來無人值守的每日排程，代價是 API 額度、憑證要放進 vault、簡報真的會被同事看到」。")'
   show "$P"; run "$P" ;;
*) echo "步驟要 1～9（第 9 步的後半是 9b）"; exit 2 ;;
esac
