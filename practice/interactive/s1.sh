#!/bin/bash
# K904 範例 S1 互動演練：官方多工具代理（Multi-Tool Agent，對應官方第 3 章 agents），一次跑一步
# 用法：bash s1.sh <步驟 1-8>；第 8 步分兩半：bash s1.sh 8（先出題）→ bash s1.sh 8b（範例答案＋改給客戶用會怎麼變）
# 呼叫模型：只有第 4 步會呼叫模型，最多 6 次（claude -p，透過 shared/claude_cli_client.py；不重試），其餘步驟全部離線
# 乾跑：bash s1.sh 4 --dry-run 用寫死的假回覆代替模型，只用來檢查腳本路徑，不算演練（畫面會標明）
set -u
STEP="${1:-1}"
MODE="${2:-}"
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$HERE/../.."
G=$'\e[32m'; Y=$'\e[33m'; C=$'\e[36m'; B=$'\e[1m'; N=$'\e[0m'

banner() { clear; printf '%s╔══════════════════════════════════════════════════════╗%s\n' "$C" "$N"; printf '%s  K904 範例 S1｜官方多工具代理　第 %s / 8 步%s\n' "$B" "${STEP%b}" "$N"; printf '%s  %s%s\n' "$B" "$1" "$N"; printf '%s╚══════════════════════════════════════════════════════╝%s\n\n' "$C" "$N"; }
tip() { printf '%s💡 %s%s\n\n' "$Y" "$1" "$N"; }
show() { printf '%s▶ 要執行的程式：%s\n' "$G" "$N"; printf '%s' "$1" | sed "s/^/${G}  │ ${N}/"; printf '\n%s▶ 執行結果：%s\n' "$G" "$N"; }
# 在 repo 根目錄執行；P 用單引號包住，所以 Python 程式碼裡不能出現單引號（要用 \x27 或 chr(39)）
run() { (cd "$REPO" && PYTHONUTF8=1 S1_MODE="$MODE" python - <<PY
import sys
sys.path.insert(0, "s1-multi-tool-agent")
sys.path.insert(0, "shared")
$1
PY
); rc=$?; printf '\n%s👉 第 %s 步完成（結束碼 %s）%s\n' "$C" "$STEP" "$rc" "$N"; return $rc; }

case "$STEP" in
1) banner "這個範例模仿官方第 3 章的什麼"
   tip "官方 agents 的核心是 while True：呼叫模型 → 有 tool_use 就執行工具 → tool_result 加回 messages → 再呼叫。官方筆記本拿它做「Multi-Tool Agent」：搜尋、計算機、思考三個工具，回答 OKC 人口開根號。S1 照抄題材與工具，模型改走 claude -p。"
   P='from pathlib import Path
import multi_tool_agent as mta

home = Path.home()
src = Path("s1-multi-tool-agent/multi_tool_agent.py").read_text(encoding="utf-8").splitlines()
print("S1 主程式：s1-multi-tool-agent/multi_tool_agent.py，共", len(src), "行")
lesson = home / "workspace/kindle-902-claude-quickstarts/lessons/ch03-agents.md"
print("官方講義：~/workspace/kindle-902-claude-quickstarts/lessons/ch03-agents.md（存在：{}）".format(lesson.is_file()))
print()
rows = [
    ("代理形狀", "Agent(name, system, tools, mcp_servers)", "Agent(name, system, tools)，同樣 run(question)"),
    ("呼叫模型", "anthropic SDK＋API 金鑰", "shared/claude_cli_client.py（claude -p），不設金鑰"),
    ("工具協定", "API 原生 tool_use／tool_result", "同樣的 block 形狀，轉接層用提示詞模擬"),
    ("結束條件", "這一輪沒有 tool_use（while True）", "同上，再加 --max-rounds {}".format(mta.DEFAULT_MAX_ROUNDS)),
    ("搜尋", "Brave Search MCP（上網、要金鑰）", "離線假搜尋，讀官方存檔結果"),
    ("計算機", "calculator_mcp.py（MCP 伺服器）", "同簽名同錯誤字串的 Python 函式"),
    ("思考", "ThinkTool：只回 Thinking complete!", "一樣"),
]
print("{:<8} | {:<38} | {}".format("項目", "官方 agents＋agent_demo.ipynb", "S1 官方多工具代理"))
print("-" * 104)
for r in rows:
    print("{:<8} | {:<38} | {}".format(*r))
print()
try:
    import qs_source
    for rel, pat in (("agents/agent.py", "while True:"), ("agents/agent_demo.ipynb", "agent.run\\(")):
        for no, line in qs_source.grep(rel, pat)[:1]:
            print("官方原始碼 {} 第 {} 行：{}".format(rel, no, line.strip()[:80]))
except Exception as exc:
    print("（這台電腦沒有官方 repo，略過原始碼對照：{}）".format(type(exc).__name__))'
   show "$P"; run "$P" ;;
2) banner "看工具定義：三個工具＋官方系統提示裡的 calculate 陷阱"
   tip "工具＝給模型看的定義（name、description、input_schema）＋一個 Python 函式。注意官方系統提示寫的是 calculate，真正註冊的名稱是 calculator。最後離線試計算機：錯誤不丟例外，而是回 Error 字串交還模型。"
   P='import json
import multi_tool_agent as mta

print("=== 系統提示（逐字照抄官方筆記本） ===")
print(mta.OFFICIAL_SYSTEM_PROMPT.strip())
print()
print("=== 實際註冊的工具（模型看到的定義） ===")
for name, (spec, fn) in mta.TOOLS.items():
    req = spec["input_schema"].get("required", [])
    print("  {:<17} 必填參數 {:<34} → 執行 {}()".format(name, str(req), fn.__name__))
print()
print("提示詞裡的名稱：brave_web_search, brave_local_search, calculate, think")
print("真正註冊的名稱：", ", ".join(mta.TOOLS))
print("→ calculate 與 brave_local_search 都不存在（K902 第 3 章陷阱 6）")
print()
print("=== 離線試 calculator（照官方 calculator_mcp.py） ===")
cases = [(696272, 0, "sqrt"), (6, 3, "/"), (2, 10, "^"), (1, 0, "/"), (-4, 0, "sqrt"), (4, 0, "square root")]
for a, b, op in cases:
    print("  calculator({}, {}, {!r:<14}) → {}".format(a, b, op, mta.calculator(a, b, op)))
print()
print("think(\"任何想法\") →", mta.think("任何想法"))'
   show "$P"; run "$P" ;;
3) banner "看迴圈主程式：Agent.run"
   tip "跟官方 _agent_loop 一樣：取出 tool_use、execute_tools、把 tool_result 當 user 訊息加回。差別是 for 迴圈有上限，最後一輪 tools=[]。每次 claude -p 都是新行程，轉接層把整串 messages 攤平成逐字稿重送。"
   P='import inspect
import claude_cli_client as cc
import multi_tool_agent as mta

lines, start = inspect.getsourcelines(mta.Agent.run)
print("=== Agent.run（第 {}～{} 行） ===".format(start, start + len(lines) - 1))
for i, line in enumerate(lines, start):
    print("{:>4} | {}".format(i, line.rstrip()))
print()
print("=== 示範：第 2 輪送給 claude -p 的逐字稿（離線組字串，不呼叫模型） ===")
call = mta._ns(type="tool_use", id="t1", name="brave_web_search", input={"query": "OKC population 2022"})
messages = [
    {"role": "user", "content": "What\x27s the square root of the OKC population in 2022"},
    {"role": "assistant", "content": [mta._ns(type="text", text="I will search first."), call]},
    {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "Title: ...\nDescription: ...\nURL: ..."}]},
]
print(cc.flatten_messages(messages))'
   show "$P"; run "$P" ;;
4) banner "實跑官方原題：真模型自己決定查、想、算"
   tip "這一步會呼叫模型最多 6 次（每次約 5 秒，不重試；K902_CLI_MAX_CALLS 也設成 6）。題目照官方原文：OKC 2022 年人口開根號。看模型先搜尋幾次、有沒有用 think、最後 calculator 算出的數字跟答案對不對得上。"
   P='import os, time
import multi_tool_agent as mta

DRY = os.environ.get("S1_MODE") == "--dry-run"
os.environ["K902_CLI_MAX_CALLS"] = "6"
if DRY:
    print("【乾跑模式】模型是寫死的假回覆，只用來檢查路徑；正式演練不要加 --dry-run。")
QUESTION = "What\x27s the square root of the OKC population in 2022"
agent = mta.Agent("Multi-Tool Agent", mta.OFFICIAL_SYSTEM_PROMPT,
                  client=mta.DryRunClient() if DRY else None, max_rounds=6)
started = time.time()
record = agent.run(QUESTION)
seconds = time.time() - started
log = mta.save_run(QUESTION, record, seconds, DRY, "official")
print()
print("=== 答案 ===")
print(record["answer"] if record["valid_answer"] else "模型未給出有效答案")
print()
used = [c["name"] for r in record["rounds"] for c in r["tool_calls"]]
print("工具順序：", " → ".join(used) or "（沒有用工具）")
print("模型呼叫：{} 次（上限 6）｜有效答案：{}｜答案與 calculator 一致：{}｜耗時 {:.1f} 秒{}".format(
    record["model_calls"], record["valid_answer"], record.get("calc_consistent"), seconds, "｜[dry-run]" if DRY else ""))
print("紀錄：s1-multi-tool-agent/runs/" + log.name)
if record["error"]:
    print("呼叫模型失敗：", record["error"])
    raise SystemExit(1)
raise SystemExit(0 if record["valid_answer"] else 3)'
   show "$P"; run "$P" ;;
5) banner "看 runs/ 的 JSON 紀錄：記了什麼、刻意沒記什麼"
   tip "紀錄存每輪的工具名稱、參數、結果字數與首行，不存搜尋結果全文（全文本來就在 data/）。優先看第 4 步真模型的紀錄；只跑過乾跑時就看乾跑那份（檔名有 -dry-run）。"
   P='import json
from pathlib import Path

runs = sorted(Path("s1-multi-tool-agent/runs").glob("*.json"))
if not runs:
    print("runs/ 裡沒有紀錄，請先跑第 4 步。")
    raise SystemExit(0)
live = [p for p in runs if not p.stem.endswith("-dry-run")]
latest = (live or runs)[-1]
print("runs/ 共 {} 份紀錄（真模型 {} 份）；看最新一份：{}".format(len(runs), len(live), latest.name))
try:
    rec = json.loads(latest.read_text(encoding="utf-8"))
except ValueError as exc:
    print("紀錄讀不懂：", latest.name, exc)
    raise SystemExit(1)
print()
print("最上層欄位：", list(rec.keys()))
print("模式：", rec.get("mode"), "｜系統提示：", rec.get("system_prompt"), "｜模型呼叫：", rec.get("model_calls"),
      "次｜耗時：", rec.get("seconds"), "秒")
print("有效答案：", rec.get("valid_answer"), "｜答案與 calculator 一致：", rec.get("calc_consistent"))
print()
print("{:>3} | {:<17} | {:>6} | {:<5} | {}".format("輪", "工具", "結果字數", "錯誤", "參數"))
print("-" * 100)
for r in rec.get("rounds", []):
    if not r.get("tool_calls"):
        print("{:>3} | {:<17} | {:>6} | {:<5} | {}".format(r.get("round"), "（回答）", "-", "-", r.get("text_first_line", "")[:50]))
    for c in r.get("tool_calls", []):
        print("{:>3} | {:<17} | {:>6} | {:<5} | {}".format(r.get("round"), c.get("name"), c.get("result_chars"),
              str(c.get("is_error")), json.dumps(c.get("input"), ensure_ascii=False)[:50]))
print()
print("有沒有存搜尋全文：", any("result" in c for r in rec.get("rounds", []) for c in r.get("tool_calls", [])), "（預期 False）")'
   show "$P"; run "$P" ;;
6) banner "試邊界案例：錯的工具名、查不到、碰到輪數上限（離線）"
   tip "模型叫了不存在的工具（例如照提示詞寫的 calculate），程式照官方回 Tool not found，迴圈不中斷。fixture 沒有的題目回 No results found。輪數上限用乾跑假客戶端示範：最後一輪 tools 是空的。最後真的執行一次空問題，程式在呼叫模型前就以結束碼 2 離開。"
   P='import subprocess, sys
import multi_tool_agent as mta

print("=== 1. 錯的工具名與錯的參數 → is_error 的 tool_result ===")
calls = [
    mta._ns(id="a", name="calculate", input={"number1": 2, "number2": 3, "operator": "+"}),
    mta._ns(id="b", name="brave_local_search", input={"query": "pizza near OKC"}),
    mta._ns(id="c", name="calculator", input={"number1": "很多", "number2": 0, "operator": "sqrt"}),
    mta._ns(id="d", name="calculator", input={"number1": 9}),
]
for call, res in zip(calls, mta.execute_tools(calls, mta.TOOLS)):
    print("  {:<19} is_error={!s:<5} → {}".format(call.name, res.get("is_error", False), res["content"][:70]))
print()
print("轉接層只認得已註冊的工具名；模型若寫出 calculate，recover_unknown_calls 會把它撿回來：")
found = mta.recover_unknown_calls("<tool_use>{\"name\": \"calculate\", \"input\": {}}</tool_use>", set(mta.TOOLS))
print("  撿回：", [c.name for c in found])
print()
print("=== 2. 搜尋 fixture 沒有的題目 ===")
for q in ("Taipei population 2022", "OKC population 2022", "how big is a banana"):
    first = mta.brave_web_search(q).splitlines()[0]
    print("  {:<26} → {}".format(q, first[:70]))
print()
print("=== 3. --max-rounds 2：第 2 輪是最後一輪，不給工具 ===")
fake = mta.DryRunClient()
seen = []
orig = fake.create
def spy(**kw):
    seen.append(len(kw.get("tools") or []))
    return orig(**kw)
fake.create = spy
rec = mta.Agent("邊界測試", mta.OFFICIAL_SYSTEM_PROMPT, client=fake, max_rounds=2, verbose=False).run("q")
print("  每輪送出的工具數：", seen, "｜呼叫次數：", rec["model_calls"], "｜最後一輪：", rec["rounds"][-1]["last_round"])
print("  最後一輪附加的要求：", mta.LAST_ROUND_NOTE[:60] + "…")
print()
print("=== 4. 空問題：實際執行 multi_tool_agent.py \"   \" ===")
proc = subprocess.run([sys.executable, "s1-multi-tool-agent/multi_tool_agent.py", "   "],
                      capture_output=True, text=True, encoding="utf-8", errors="replace")
print("  exit code：", proc.returncode, "（預期 2，沒有呼叫模型）")
print("  stderr 最後一行：", proc.stderr.strip().splitlines()[-1])'
   show "$P"; run "$P" ;;
7) banner "搜尋資料從哪來：對照官方筆記本行號（離線）"
   tip "data/search_fixture.json 不是虛構的，每筆都逐字取自官方筆記本已存檔的工具結果，source_line 是筆記本行號。這一步抽三筆回去官方檔案對行號，再看比對規則：問法不同也可能拿到同一組結果。"
   P='import json
from collections import Counter
from pathlib import Path
import multi_tool_agent as mta

rows = mta.load_fixture()
print("fixture 共 {} 筆，依存檔查詢分組：".format(len(rows)))
for q, n in Counter(r["query"] for r in rows).items():
    print("  {:<46} {} 筆".format(q, n))
print()
try:
    import qs_source
    nb = qs_source.read_text("agents/agent_demo.ipynb").splitlines()
    print("抽三筆對照官方 agents/agent_demo.ipynb：")
    for r in (rows[0], rows[15], rows[-1]):
        line = nb[r["source_line"] - 1]
        print("  第 {:>3} 行 含標題「{}」：{}".format(r["source_line"], r["title"][:40], r["title"] in line))
except Exception as exc:
    print("（這台電腦沒有官方 repo，略過行號對照：{}）".format(type(exc).__name__))
print()
print("比對規則（本教材的替代做法，官方未載明）：要命中主題詞", sorted(mta.SUBJECT_WORDS), "才挑重疊最多的那組")
for q in ("Oklahoma City population 2022 census estimate", "Oklahoma City population July 1 2022 Census Bureau estimate",
          "Oklahoma City population 2022 exact figure"):
    first = mta.brave_web_search(q).splitlines()[0]
    print("  {:<60} → {}".format(q[:60], first[:40]))
print("→ 前兩個問法不同卻拿到同一組：真模型實測時第二次搜尋就是這樣。")
print()
print("演練結束後可以自己試（各會再呼叫模型 2～6 次）：")
print("  cd ~/workspace/kindle-904-quickstarts-official-samples/s1-multi-tool-agent")
print("  PYTHONUTF8=1 python multi_tool_agent.py \"How many bananas will fit in an Toyota GR86?\"")
print("  PYTHONUTF8=1 python multi_tool_agent.py --fix-prompt \"What\x27s the square root of the OKC population in 2022\"")'
   show "$P"; run "$P" ;;
8) banner "三個靈魂拷問：先自己回答"
   tip "先不要看答案。對著 S1 想一想三題，各用一兩句話說出來；想好之後說「繼續」，教練會執行 bash s1.sh 8b 顯示範例答案。"
   P='qs = [
    "1. 這個代理是給誰用的？（誰在什麼地方、用什麼方式跟它說話）",
    "2. 被賦予了哪些工具權限？（三個工具各能做什麼、刻意不給什麼、最壞情況）",
    "3. 資料和成果最後存在哪裡？（搜尋資料、答案、紀錄各在哪，哪些進 git）",
]
print("三個靈魂拷問：")
for q in qs:
    print("  " + q)
print()
print("提示：第 2 步的工具清單、第 6 步的 is_error、第 5 步的紀錄欄位、第 7 步的 fixture 都是線索。")
print("想好後說「繼續」→ bash s1.sh 8b")'
   show "$P"; run "$P" ;;
8b) banner "三個靈魂拷問：範例答案＋改給客戶用會怎麼變"
   tip "範例答案直接從 s1-multi-tool-agent/README.md 的表格讀出來。重點在右半：同一個迴圈接上真的搜尋、開給客戶用，三題答案都要重寫。"
   P='import re
from pathlib import Path

readme = Path("s1-multi-tool-agent/README.md").read_text(encoding="utf-8")
rows = [line for line in readme.splitlines() if re.match(r"^[|] (這個代理|被賦予|資料和成果)", line)]
print("=== 範例答案（摘自 s1-multi-tool-agent/README.md） ===")
for line in rows:
    cells = [c.strip() for c in line.strip("|").split("|")]
    q, a = cells[0], re.sub(r"<br/?>", " ", cells[1]).replace("**", "").replace(chr(96), "")
    print("■ " + q)
    print("  " + a)
    print()
if len(rows) != 3:
    print("（README 表格只讀到 {} 列，請直接打開 README 第 2 節看）".format(len(rows)))
print("=== 如果改成給客戶用（例：網站上的「問答＋試算」助理） ===")
change = [
    ("給誰用", "自己，在終端機一個人用",
     "外部客戶從網頁進來；要限流、擋提示詞注入，回答前要過濾"),
    ("工具權限", "三個工具都沒副作用，搜尋是離線存檔",
     "搜尋改接真的搜尋 API（會上網、要金鑰、限網域）；calculator 要限數字範圍；仍然不給檔案與執行程式；迴圈上限必留"),
    ("存在哪裡", "答案印終端機；runs/ 只存長度與首行",
     "答案回客戶畫面；紀錄去識別化、定保存期限；模型改用 API（金鑰放伺服器環境變數），不能用個人訂閱的 claude -p"),
]
print("{:<8} | {:<30} | {}".format("題目", "現在（給自己）", "改給客戶用"))
print("-" * 120)
for r in change:
    print("{:<8} | {:<30} | {}".format(*r))
print()
print("一句話：S1 安全是因為三個工具都沒有副作用、搜尋不上網；一接上真的網路，模型引用的數字就要逐一查核（本次實測就出現工具結果以外的數字）。")'
   show "$P"; run "$P" ;;
*) echo "步驟要 1～8（第 8 步的後半是 8b）" ;;
esac
