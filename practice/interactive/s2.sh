#!/bin/bash
# K904 範例 S2 互動演練：官方客服代理（Anthropic 客服助理）——7 欄回覆契約、8 個官方分類、多輪 messages，一次跑一步
# 用法：bash s2.sh <步驟 1-8>；第 8 步分兩半：bash s2.sh 8（先出題）→ bash s2.sh 8b（範例答案＋對比 K903 S2）
# 呼叫模型：只有第 5、6 步各呼叫模型 1 次（共 2 次，claude -p，透過 server.py → shared/llm_agent.ask），其餘步驟全部離線
# 乾跑：bash s2.sh 5 --dry-run／bash s2.sh 6 --dry-run 讓伺服器用寫死的假回覆，只用來檢查腳本路徑，不算演練（畫面會標明）
# 伺服器：第 4～7 步會在背景啟動 server.py（只綁 127.0.0.1），該步結束時由 trap 一定關掉，不會留殘留行程
# 可調環境變數：S2_PORT（預設 8904）、K902_CLI_MODEL、K902_CLI_TIMEOUT（都不是金鑰；不要設任何 API 金鑰）
set -u
STEP="${1:-1}"
MODE="${2:-}"
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$HERE/../.."
S2="$REPO/s2-official-support"
WORK="$S2/logs"   # 伺服器輸出與探測檔跟 server.py 的紀錄放一起：*/logs/ 已在 .gitignore
PORT="${S2_PORT:-8904}"
BASE="http://127.0.0.1:$PORT"
mkdir -p "$WORK"
G=$'\e[32m'; Y=$'\e[33m'; C=$'\e[36m'; B=$'\e[1m'; R=$'\e[31m'; N=$'\e[0m'
DRYTAG=""; [ "$MODE" = "--dry-run" ] && DRYTAG="【乾跑】"

banner() { clear; printf '%s╔══════════════════════════════════════════════════════╗%s\n' "$C" "$N"; printf '%s  K904 範例 S2｜官方客服代理　第 %s / 8 步 %s%s\n' "$B" "${STEP%b}" "$DRYTAG" "$N"; printf '%s  %s%s\n' "$B" "$1" "$N"; printf '%s╚══════════════════════════════════════════════════════╝%s\n\n' "$C" "$N"; }
tip() { printf '%s💡 %s%s\n\n' "$Y" "$1" "$N"; }
show() { printf '%s▶ 要執行的程式：%s\n' "$G" "$N"; printf '%s' "$1" | sed "s/^/${G}  │ ${N}/"; printf '\n%s▶ 執行結果：%s\n' "$G" "$N"; }
done_step() { printf '\n%s👉 第 %s 步完成%s\n' "$C" "$STEP" "$N"; }
# 在 s2-official-support 底下跑 Python，才能直接 import server；P 用單引號包住，所以 Python 裡不能出現單引號
run() { (cd "$S2" && S2_BASE="$BASE" S2_MODE="$MODE" PYTHONUTF8=1 PYTHONPATH=. python - <<PY
$1
PY
); local code=$?; done_step; return $code; }

# ---------- 背景伺服器：啟動、等就緒、一定關掉 ----------
SERVER_PID=""
stop_server() {
  if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null
    wait "$SERVER_PID" 2>/dev/null
    printf '%s🛑 伺服器已關閉（PID %s）%s\n' "$C" "$SERVER_PID" "$N"
  fi
  SERVER_PID=""
}
trap stop_server EXIT
trap 'exit 130' INT TERM   # Ctrl+C 時改走 exit，讓 EXIT trap 一樣會關伺服器

# mingw curl 寫 /dev/null 會回錯誤碼 23，所以寫到探測檔、改看 HTTP 狀態碼：000 代表沒有程式在聽
port_busy() { [ "$(curl -s -o "$WORK/.probe" -w '%{http_code}' --max-time 2 "$BASE/" 2>/dev/null)" != "000" ]; }

start_server() {
  if port_busy; then
    printf '%s埠 %s 已經有程式在用（可能是別處沒關的 server.py）。請先關掉它，或改用 S2_PORT=8914 bash s2.sh %s%s\n' "$R" "$PORT" "$STEP" "$N"
    exit 1
  fi
  local extra=""; [ "$MODE" = "--dry-run" ] && extra="--dry-run"
  (cd "$S2" && PYTHONUTF8=1 exec python server.py --port "$PORT" $extra) > "$WORK/practice-server.log" 2>&1 &
  SERVER_PID=$!
  for _ in $(seq 1 30); do
    if port_busy; then
      printf '%s🚀 背景伺服器就緒：%s（PID %s，輸出寫在 s2-official-support/logs/practice-server.log）%s\n' "$C" "$BASE" "$SERVER_PID" "$N"
      [ "$MODE" = "--dry-run" ] && printf '%s【乾跑模式】伺服器用寫死的假回覆，不呼叫模型；只檢查路徑，不算演練。%s\n' "$R" "$N"
      echo
      return 0
    fi
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then break; fi
    sleep 0.5
  done
  printf '%s伺服器啟動失敗，最後幾行輸出：%s\n' "$R" "$N"; tail -n 5 "$WORK/practice-server.log"
  exit 1
}

# 第 5、6 步共用：送 messages、印 7 欄、印兩個標頭、印這題在 logs/ 的那一筆
ASK_PY='import json, os, urllib.request, urllib.error
from datetime import datetime
from pathlib import Path
BASE = os.environ["S2_BASE"]
NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))

def post(messages):
    data = json.dumps({"messages": messages}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(BASE + "/api/chat", data=data, headers={"Content-Type": "application/json"})
    try:
        with NO_PROXY.open(req, timeout=300) as res:
            return res.status, json.loads(res.read().decode("utf-8")), res.headers
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8")), exc.headers

def last_log():
    path = Path("logs") / "{:%Y-%m-%d}.jsonl".format(datetime.now())
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    return json.loads(lines[-1]) if lines else None

def chat_and_show(messages):
    for m in messages:
        print("  {}：{}".format("使用者" if m["role"] == "user" else "客服", m["content"]))
    try:
        status, body, headers = post(messages)
    except (OSError, ValueError) as exc:
        print("送出失敗：", exc)
        return None
    print()
    print("HTTP", status, "（乾跑假回覆）" if body.get("dry_run") else "")
    for key in ("response", "thinking", "user_mood", "suggested_questions", "debug", "matched_categories", "redirect_to_agent", "dropped_categories"):
        print("  {:<20} {}".format(key, json.dumps(body.get(key), ensure_ascii=False)))
    print("  rag_sources          ", [(s["id"], s["score"], "官方顯示" if s["shown_by_official"] else "官方不顯示") for s in body.get("rag_sources", [])])
    print()
    print("標頭 x-rag-sources 前 90 字：", (headers.get("x-rag-sources") or "")[:90])
    print("標頭 X-Debug-Data：       ", headers.get("X-Debug-Data"))
    log = last_log()
    if log and log.get("query") == messages[-1]["content"]:
        print()
        print("logs/ 這一筆：rag_empty =", log["rag_empty"], "；dropped_categories =", log["dropped_categories"], "；error =", json.dumps(log["error"], ensure_ascii=False), "；耗時", log["seconds"], "秒")
    return body
'

case "$STEP" in
1) banner "這個範例照官方第 1 章重做了什麼"
   tip "K904 改回官方題材：網站上的「Anthropic 客服助理」。官方用 Next.js＋Bedrock＋API key，這裡換成 Python 標準庫＋claude -p，但 7 欄回覆契約、8 個分類、多輪 messages、n=3 檢索、兩個標頭、失敗回 500 全部照官方保留。這一步全部離線。"
   P='from pathlib import Path
import server

print("【表 1】官方 customer-support-agent vs 本範例 S2")
rows = [
    ("題材", "Anthropic 客服助理（route.ts 第 135 行）", "同左；知識庫虛構但照官方格式"),
    ("檢索", "Bedrock 知識庫，向量檢索 n=3", "kb/ 8 份 md 切成 {} 段，字元重疊評分，取前 {} 段".format(len(server.load_chunks()), server.TOP_N)),
    ("請求", "{messages, model, knowledgeBaseId}", "{messages}，最後一則 user 當查詢"),
    ("模型呼叫", "SDK＋API key，預填 assistant 的 {", "claude -p；改成提示詞要求直接從 { 開始"),
    ("回覆契約", "zod：前五欄必填、後兩欄選填", "validate_reply 照抄＋另外檢查分類 id"),
    ("來源", "模型看 3 段，畫面只顯示 1 個", "rag_sources 回 3 筆，標出官方只顯示第 1 筆"),
    ("失敗", "HTTP 500＋固定錯誤 JSON", "同左"),
]
print("{:<6} | {:<36} | {}".format("項目", "官方原版", "S2"))
print("-" * 100)
for r in rows:
    print("{:<6} | {:<36} | {}".format(*r))
print()
print("【表 2】S2 的檔案")
for rel in ("server.py", "static/index.html", "smoke_test.py", "README.md", "kb/categories.json"):
    print("  {:<20} {:>4} 行".format(rel, len(Path(rel).read_text(encoding="utf-8").splitlines())))
print("  kb/*.md             ", len(list(Path("kb").glob("*.md"))), "份，每個官方分類一份")
print()
print("【表 3】一次請求的流程（server.py 裡的函式）")
flow = [
    ("parse_messages", "不是陣列、最後不是 user、空字串、超過 {} 字、超過 {} 則 → 400".format(server.MAX_QUESTION_CHARS, server.MAX_MESSAGES)),
    ("retrieve", "只拿最後一則 user 訊息去檢索，取前 {} 段".format(server.TOP_N)),
    ("build_system_prompt", "角色＋片段＋8 個分類＋JSON 格式＋官方兩個範例"),
    ("build_transcript", "多輪 messages 轉逐字稿，走 stdin"),
    ("ask", "claude -p 一次，沒有任何工具"),
    ("validate_reply", "7 欄 schema；分類表外的 id 刪掉；失敗回 500"),
    ("write_log", "logs/日期.jsonl 追加一行"),
]
for i, (fn, desc) in enumerate(flow, 1):
    print("  {}. {:<20} {}".format(i, fn, desc))
print()
print("只綁", server.HOST, "埠", server.DEFAULT_PORT, "（K903 是 8903，錯開）")'
   show "$P"; run "$P" ;;
2) banner "知識庫切段、檢索 n=3，以及官方只顯示 1 個來源"
   tip "官方 Bedrock 以 chunk 為單位，這裡用「## 小標」切段。每份檔首行都標「虛構但照官方格式」。注意第 3 題：多輪對話裡只有最後一句拿去檢索，所以「我要跟真人講」找不到登入那一段。"
   P='import json
import server

chunks = server.load_chunks()
cats = server.load_categories()
print("【官方 8 個分類（kb/categories.json）】")
for c in cats:
    print("  {:<10} {}".format(c["id"], "、".join(c["keywords"])))
print()
print("【知識庫】共", len(chunks), "段；每份首行：")
print("  ", open("kb/billing.md", encoding="utf-8").readline().strip())
print()
QS = [
    ("知識庫內", "我要怎麼申請退款？"),
    ("一題問兩件事", "退款申請要審核多久？之前的發票要去哪裡下載？"),
    ("多輪的最後一句", "我試過了，我要跟真人講"),
    ("知識庫外", "推薦我台北的牛肉麵"),
]
for label, q in QS:
    hits = server.retrieve(q, chunks)
    print("【{}】{}".format(label, q))
    if not hits:
        print("  零命中 → 系統提示塞官方原文：", server.NO_INFO)
    for i, h in enumerate(hits):
        print("  {} {:<18} 分數 {}　{}".format("官方顯示" if i < server.OFFICIAL_DISPLAY_COUNT else "官方不顯示", h["id"], h["score"], h["snippet"].splitlines()[0]))
    print()
print("RAGSource 欄位照官方：", sorted(server.retrieve("退款", chunks)[0]))'
   show "$P"; run "$P" ;;
3) banner "7 欄回覆契約：官方範例自己就踩到的分類落差"
   tip "官方系統提示的範例寫了 account_management、technical_support，但分類表裡根本沒有這兩個 id，官方程式也沒檢查。這一步用假回覆離線測驗證函式，不呼叫模型。"
   P='import server
from llm_agent import extract_json

ids = {c["id"] for c in server.load_categories()}
prompt = server.build_system_prompt([], server.load_categories())
print("系統提示裡的官方範例一：")
print("  " + [l for l in prompt.splitlines() if "account_management" in l][0][:150] + "…")
print()
base = {"response": "好的", "thinking": "t", "user_mood": "curious", "suggested_questions": [], "debug": {"context_used": True}}
cases = [
    ("照官方範例一：含表外 id", dict(base, matched_categories=["account_management", "billing"])),
    ("後兩欄都省略（官方允許）", dict(base)),
    ("user_mood 不在六值", dict(base, user_mood="happy")),
    ("漏了 debug", {k: v for k, v in base.items() if k != "debug"}),
    ("should_redirect 寫成字串", dict(base, redirect_to_agent={"should_redirect": "yes"})),
]
for label, raw in cases:
    print("【{}】".format(label))
    try:
        reply, dropped = server.validate_reply(raw, ids)
        print("  通過 → matched_categories =", reply.get("matched_categories"), "；被刪掉 =", dropped)
    except ValueError as exc:
        print("  不通過：", str(exc)[:70])
        print("  → 照官方回 HTTP 500：", server.ERROR_RESPONSE["response"])
    print()
print("被說明文字包住的 JSON 也抽得出來：", extract_json("好的，以下是回覆：{\"response\": \"嗨\"} 以上")["response"])
print()
print("重點：")
print("  1. 一次呼叫要同時產出回答、思考、情緒、追問、分類、轉真人：欄位越多，越容易有一欄壞掉")
print("  2. 官方只驗型別、沒驗分類 id 的內容；這裡補上，刪掉的 id 寫進紀錄的 dropped_categories")'
   show "$P"; run "$P" ;;
4) banner "離線自我檢查，再把伺服器啟動在背景"
   tip "先跑 --selftest（不呼叫模型），再把 server.py 放到背景、輪詢到它能回應。本步結束時 trap 會自動關掉，你會看到「伺服器已關閉」。"
   P='PYTHONUTF8=1 python server.py --selftest
(cd s2-official-support && PYTHONUTF8=1 exec python server.py --port 8904) > logs/practice-server.log 2>&1 &
SERVER_PID=$!
trap stop_server EXIT          # 不管成功、失敗、Ctrl+C，離開時一定 kill
curl -s http://127.0.0.1:8904/ | grep "<title>"
curl -s -X POST http://127.0.0.1:8904/api/ask     # K903 的舊端點，這裡已改 /api/chat'
   show "$P"
   (cd "$S2" && PYTHONUTF8=1 python server.py --selftest) || { printf '%sselftest 失敗%s\n' "$R" "$N"; exit 1; }
   echo
   start_server
   printf '首頁標題：'; curl -s --max-time 5 "$BASE/" | grep -o '<title>[^<]*</title>'
   printf 'K903 的舊端點 /api/ask：'; curl -s --max-time 5 -X POST "$BASE/api/ask"; echo
   printf '伺服器自己的啟動訊息：'; head -n 1 "$WORK/practice-server.log"
   echo
   tip "伺服器只聽 127.0.0.1：同一個區網的別台電腦連不到，因為它背後是個人訂閱的 claude -p。"
   stop_server
   if port_busy; then printf '%s⚠ 埠 %s 還有回應，請檢查殘留行程%s\n' "$R" "$PORT" "$N"; else printf '確認：埠 %s 已經沒有回應\n' "$PORT"; fi
   done_step ;;
5) banner "知識庫內：問退款（呼叫模型 1 次）"
   tip "這一步會呼叫模型 1 次（claude -p），通常 5～10 秒，最多等 5 分鐘。看 7 個欄位、右欄 3 個來源裡哪個是官方會顯示的、標頭裡中文被去掉的樣子。"
   start_server
   P="$ASK_PY"'
body = chat_and_show([{"role": "user", "content": "我要怎麼申請退款？"}])
print()
if body is not None:
    print("看點：matched_categories 應含 billing →", "✔" if "billing" in (body.get("matched_categories") or []) else "沒有，記下來")
    print("      退款屬敏感操作，should_redirect 為 true 或 false 都合理；為 true 時 reason 要有內容")'
   show 'chat_and_show([{"role": "user", "content": "我要怎麼申請退款？"}])   # POST /api/chat，細節見 s2.sh 的 ASK_PY'
   run "$P"; code=$?; stop_server; exit $code ;;
6) banner "多輪對話：明說要找真人（呼叫模型 1 次）"
   tip "這一步會呼叫模型 1 次。送三則 messages：問登入→客服回覆→「我要跟真人講」。檢索只拿最後一句，所以登入那段沒被找到；模型還是要看完整逐字稿，照規則轉真人。"
   start_server
   P="$ASK_PY"'
body = chat_and_show([
    {"role": "user", "content": "我的帳號登不進去"},
    {"role": "assistant", "content": "請先確認登入信箱是否正確。"},
    {"role": "user", "content": "我試過了，我要跟真人講"},
])
print()
if body is not None:
    redirect = (body.get("redirect_to_agent") or {}).get("should_redirect")
    print("should_redirect =", redirect, "→", "轉真人 ✔" if redirect is True else "沒有轉真人，記下來，這是模型沒照規則")'
   show 'chat_and_show([使用者 登不進去, 客服 請確認信箱, 使用者 我要跟真人講])   # POST /api/chat，細節見 s2.sh 的 ASK_PY'
   run "$P"; code=$?; stop_server; exit $code ;;
7) banner "壞輸入回 400、標頭去非 ASCII、網頁防 XSS（不呼叫模型）"
   tip "壞輸入在 parse_messages 就擋掉，不花模型額度；用 logs/ 的行數證明。再看官方 sanitizeHeaderValue：標頭只能放 ASCII，中文片段整段消失，所以完整來源要放在回應本文。"
   start_server
   LOG="$S2/logs/$(date +%Y-%m-%d).jsonl"
   before=$( [ -f "$LOG" ] && wc -l < "$LOG" || echo 0 )
   P="curl -s -w '  [HTTP %{http_code}]' -X POST $BASE/api/chat -H 'Content-Type: application/json' -d '{\"messages\": [{\"role\": \"user\", \"content\": \"   \"}]}'"
   show "$P"
   # curl 的 -d 參數在 Git Bash 會被轉成系統編碼，中文會變亂碼，所以壞輸入一律用英數字
   post() { printf '%-18s' "$1："; curl -s --max-time 10 -w '  [HTTP %{http_code}]\n' -X POST "$BASE/api/chat" -H 'Content-Type: application/json' -d "$2"; }
   post '空白字串' '{"messages": [{"role": "user", "content": "   "}]}'
   post 'messages 不是陣列' '{"messages": "refund"}'
   post '最後一則不是 user' '{"messages": [{"role": "assistant", "content": "hello"}]}'
   post '不是 JSON' 'hello'
   LONG=$(printf 'x%.0s' $(seq 1 501))
   post '501 個字' "{\"messages\": [{\"role\": \"user\", \"content\": \"$LONG\"}]}"
   ELEVEN=$(printf '{"role": "user", "content": "q"},%.0s' $(seq 1 11)); ELEVEN="[${ELEVEN%,}]"
   post '11 則 messages' "{\"messages\": $ELEVEN}"
   after=$( [ -f "$LOG" ] && wc -l < "$LOG" || echo 0 )
   printf '\nlogs/ 行數：前 %s 行、後 %s 行 → %s\n\n' "$before" "$after" "$( [ "$before" = "$after" ] && echo '沒有新增，代表模型一次都沒被呼叫' || echo '有新增，請檢查')"
   stop_server
   P2='import json, server
chunk = server.retrieve("退款", server.load_chunks())[0]
raw = json.dumps({"fileName": chunk["fileName"], "snippet": chunk["snippet"][:40]}, ensure_ascii=False)
print("放進標頭前：", raw)
print("去非 ASCII：", server.sanitize_header_value(raw))'
   show "$P2"; (cd "$S2" && PYTHONUTF8=1 python - <<PY
$P2
PY
)
   echo
   printf '%s▶ 網頁怎麼顯示文字（static/index.html）：%s\n' "$G" "$N"
   grep -n 'textContent\|innerHTML' "$S2/static/index.html" | sed "s/^/${G}  │ ${N}/"
   echo
   echo '左欄 thinking、右欄來源片段、追問按鈕，全部是模型或知識庫給的文字，一律用 textContent。'
   echo '使用者輸入、模型回覆、檢索片段，三邊都要當「不可信的文字」。'
   done_step ;;
8) banner "三個靈魂拷問：先自己答"
   tip "先不要看答案。這次的使用者是網站上的陌生人，而知識庫寫的是一家真實公司的產品。"
   printf '%s請先在心裡（或紙上）回答 S2 的三題：%s\n' "$B" "$N"
   echo '  1. 這個代理是做給誰用的？'
   echo '  2. 它被賦予了哪些工具的權限？'
   echo '  3. 它的資料和成果最後存在哪裡？'
   echo
   echo '提示：退款、刪帳號誰能做？模型能查帳號嗎？來源除了回應本文，還放在哪？對話可能有什麼個資？'
   printf '\n%s想好了，執行 bash s2.sh 8b 看範例答案和 K903 S2 對比%s\n' "$C" "$N" ;;
8b) banner "三個靈魂拷問：範例答案，以及跟 K903 S2 的對比"
   tip "兩版都是給外部使用者的客服，三問答案幾乎一樣；差別在回覆契約的大小。"
   P='rows = [
    ("1. 給誰用",
     "外部客戶（虛構 AMR 公司）",
     "網站上的外部使用者（官方設定）；本範例只在 127.0.0.1 示範"),
    ("2. 工具權限",
     "模型沒有工具；議價、客訴、退貨轉真人",
     "模型沒有工具；退款、帳號申訴、刪帳號、法律問題一律轉真人"),
    ("3. 資料存哪",
     "logs/ 存問題與回覆",
     "logs/ 存問題、chunk 分數、完整 JSON、被刪的分類；來源另放標頭"),
    ("回覆契約",
     "4 欄：answer、sources、confidence、needs_human",
     "官方 7 欄：response、thinking、user_mood、suggested_questions、debug、matched_categories、redirect_to_agent"),
    ("→ 用什麼呼叫",
     "示範 claude -p；上線換 API key",
     "同左；官方 README 也自稱原型、不適合上線"),
]
print("{:<10} | {:<36} | {}".format("", "K903 S2 AMR 產品問答", "K904 S2 官方客服代理"))
print("-" * 120)
for r in rows:
    print("{:<10} | {:<36} | {}".format(*r))
print()
print("契約大小怎麼取捨：")
print("  K903 把契約縮到剛好夠用（4 欄），驗證幾乎不會失敗。")
print("  K904 照官方一次塞五件事（回答、思考、情緒、追問、分類＋轉真人），畫面豐富，")
print("  但每多一欄就多一個會壞的地方；官方連分類 id 都沒驗，範例自己就寫了表外的 id。")
print()
print("本章用到的模型呼叫：第 5、6 步各 1 次，共 2 次；伺服器每一步結束都已關閉。")'
   show "$P"; run "$P" ;;
*) echo "步驟要 1～8 或 8b（第 5、6 步可加 --dry-run）"; exit 1 ;;
esac
