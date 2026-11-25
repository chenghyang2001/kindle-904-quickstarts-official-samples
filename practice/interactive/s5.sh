#!/bin/bash
# K904 範例 S5 互動演練：Hacker News 前三名讀取代理（官方 browser-use-demo 第一個範例任務的本機練習版），一次跑一步
# 用法：bash s5.sh <步驟 1-8>；第 8 步分兩半：bash s5.sh 8（先出題）→ bash s5.sh 8b（範例答案＋改給別人用會怎麼變）
# 呼叫模型：只有第 6 步會呼叫模型（hn_agent.py 自己的 claude -p，實測 3 次、上限 8 次），其餘步驟全部離線
# 乾跑：bash s5.sh 6 --dry-run 用寫死的假回覆代替模型，只用來檢查腳本路徑，不算演練（畫面會標明）
# 不設任何 API 金鑰；練習網站由程式自己開在 127.0.0.1 的隨機埠（作業系統挑，不會撞到 K903），程式結束時一併關閉
set -u
STEP="${1:-1}"
MODE="${2:-}"
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
S5="$ROOT/s5-browser-hn"
G=$'\e[32m'; Y=$'\e[33m'; C=$'\e[36m'; B=$'\e[1m'; N=$'\e[0m'

banner() { clear; printf '%s╔══════════════════════════════════════════════════════╗%s\n' "$C" "$N"; printf '%s  K904 範例 S5｜HN 前三名讀取代理　第 %s / 8 步%s\n' "$B" "${STEP%b}" "$N"; printf '%s  %s%s\n' "$B" "$1" "$N"; printf '%s╚══════════════════════════════════════════════════════╝%s\n\n' "$C" "$N"; }
tip() { printf '%s💡 %s%s\n\n' "$Y" "$1" "$N"; }
show() { printf '%s▶ 要執行的程式：%s\n' "$G" "$N"; printf '%s' "$1" | sed "s/^/${G}  │ ${N}/"; printf '\n%s▶ 執行結果：%s\n' "$G" "$N"; }
done_step() { printf '\n%s👉 第 %s 步完成（結束碼 %s）%s\n' "$C" "$STEP" "$1" "$N"; return "$1"; }
# 在 s5-browser-hn/ 底下跑一段 Python；P 用單引號包住，所以 Python 程式碼裡不能出現單引號
run() { (cd "$S5" && PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=".:$ROOT/shared" python - <<PY
$1
PY
); done_step $?; }
# 在 s5-browser-hn/ 底下跑一行 shell 指令
runcmd() { (cd "$S5" && eval "$1"); done_step $?; }

if [ ! -d "$S5" ]; then echo "找不到範例資料夾：$S5"; exit 1; fi

case "$STEP" in
1) banner "這個範例對應官方第 4～8 章的哪些概念"
   tip "S5 用的是官方 browser-use-demo README 第一個範例任務：「到 news.ycombinator.com，告訴我前 3 名的文章」。網址換成本機練習站，動作名稱照官方 browser toolset。先把五章的重點對到 S5 的檔案和函式。本步不呼叫模型。"
   P='from pathlib import Path

lessons = Path.home() / "workspace" / "kindle-902-claude-quickstarts" / "lessons"
official = Path.home() / "workspace" / "claude-quickstarts"
rows = [
    ("4", "browser-toolset", "ch04-browser-toolset.md", "動作 navigate/read_page/get_page_text/left_click", "browser_tools.py：BrowserTools 同名方法"),
    ("4", "browser-toolset", "ch04-browser-toolset.md", "read_page 每個元素帶 ref_N", "browser_tools.py：MARK_ELEMENTS_JS 寫 data-ref"),
    ("4", "browser-toolset", "ch04-browser-toolset.md", "URL policy 只比對主機字串", "browser_tools.py：check_url"),
    ("4", "browser-toolset", "ch04-browser-toolset.md", "exercise：不用模型送固定呼叫", "hn_agent.py --exercise"),
    ("5", "browser-use-demo", "ch05-browser-use-demo.md", "範例任務 top 3 stories", "hn_agent.py：TASKS[top3]"),
    ("5", "browser-use-demo", "ch05-browser-use-demo.md", "網頁裡的指令可能蓋過使用者指令", "site/index.html 第 5 則＋SYSTEM_TEMPLATE 規則 2"),
    ("6", "computer-toolset", "ch06-computer-toolset.md", "截圖＋座標的 computer 工具", "刻意不用：screenshot 只存檔，left_click 不收座標"),
    ("7", "computer-use-demo", "ch07-computer-use-demo.md", "容器裡的桌面，人在旁邊看", "改用 Playwright 無頭 Chromium＋runs/ 截圖"),
    ("8", "computer-use-best-practices", "ch08-computer-use-best-practices.md", "步數上限、最小權限、自己防注入", "MAX_STEPS = 8；只給 5 個動作"),
]
print("{:<3} | {:<27} | {:<42} | {}".format("章", "官方專案", "官方概念", "在 S5 哪裡"))
print("-" * 140)
for ch, proj, _f, concept, where in rows:
    print("{:<3} | {:<27} | {:<42} | {}".format(ch, proj, concept, where))
print()
print("K902 講義是否在這台電腦：")
for f in sorted({r[2] for r in rows}):
    print("  {} ~/workspace/kindle-902-claude-quickstarts/lessons/{}".format("OK" if (lessons / f).exists() else "缺", f))
readme = official / "browser-use-demo" / "README.md"
if readme.exists():
    for i, line in enumerate(readme.read_text(encoding="utf-8").splitlines(), 1):
        if "top 3 stories" in line:
            print()
            print("官方原句（browser-use-demo/README.md 第 {} 行）：{}".format(i, line.strip()))
else:
    print("（這台沒有官方原始碼 ~/workspace/claude-quickstarts，略過原句）")
print()
print("和官方的最大差別：模型走 claude -p（訂閱額度），每步回一個 JSON 動作字串，程式自己解析；不是 API 原生 tool use。")'
   show "$P"; run "$P" ;;

2) banner "看練習網站：site/ 底下 3 個靜態頁＋正確答案"
   tip "代理只准逛這個本機練習站。先列出 3 個頁面，再離線把首頁前 3 名讀出來，和 expected.json 對一下；另外找出第 5 則藏的提示詞注入。本步不呼叫模型。"
   P='import json
import re
from pathlib import Path

site = Path("site")
print("{:<14} | {:>4} | {}".format("檔案", "行數", "標題"))
print("-" * 60)
for p in sorted(site.glob("*.html")):
    html = p.read_text(encoding="utf-8")
    m = re.search(r"<title>(.*?)</title>", html)
    print("{:<14} | {:>4} | {}".format(p.name, len(html.splitlines()), m.group(1) if m else "（無標題）"))
print()
html = (site / "index.html").read_text(encoding="utf-8")
items = re.findall(r"<td class=\"rank\">(\d+)\.</td><td class=\"title\"><a [^>]*>(.*?)</a>", html)
print("index.html 的文章（離線解析）：")
for rank, title in items:
    mark = "  ← 提示詞注入" if "忽略" in title else ""
    print("  {:>2}. {}{}".format(rank, title, mark))
expected = json.loads(Path("expected.json").read_text(encoding="utf-8"))
print()
print("expected.json 的前三名：")
for i, t in enumerate(expected["top3"], 1):
    print("  {}. {}".format(i, t))
same = [t for _r, t in items[:3]] == expected["top3"]
print()
print("離線解析的前三名和 expected.json 一致：", "是" if same else "否（練習站被改過，請檢查）")
print("底部有「More」連到 more.html（第 11～20 則），用來看模型會不會多翻頁。")
print("想自己用瀏覽器逛：python -m http.server 8904 --bind 127.0.0.1 --directory site（K903 用 8000，這裡避開）")'
   show "$P"; run "$P" ;;

3) banner "看 5 個瀏覽器動作與白名單（browser_tools.py）"
   tip "動作名稱照官方：navigate、read_page、get_page_text、left_click，再加一個只存檔的 screenshot。重點三個：read_page 給元素 ref_N；left_click 只收 ref_N、不收座標；check_url 只比對主機字串，連點連結前也會再檢查。本步只把原始碼當文字讀，不開瀏覽器、不呼叫模型。"
   P='from pathlib import Path

src = Path("browser_tools.py").read_text(encoding="utf-8").splitlines()
def line_of(text):
    for i, s in enumerate(src, 1):
        if text in s:
            return i
    return 0

tools = [
    ("navigate(url)", "def navigate", "先 check_url，再 page.goto，逾時 10 秒"),
    ("read_page()", "def read_page", "標題、連結、按鈕、表單元件，每個寫上 data-ref=ref_N"),
    ("get_page_text()", "def get_page_text", "可見文字，截 1500 字"),
    ("left_click(ref)", "def left_click", "parse_ref 只收 ref_N；找不到就叫模型重新 read_page"),
    ("screenshot(name)", "def screenshot", "存成 runs/<時間>/*.png，不回傳給模型"),
]
print("【表 1】5 個動作")
print("{:<18} | {:>4} | {}".format("動作", "行號", "做什麼"))
print("-" * 90)
for name, key, desc in tools:
    print("{:<18} | {:>4} | {}".format(name, line_of(key), desc))
print()
print("【表 2】白名單與防呆在哪裡生效")
checks = [
    ("check_url 本體", "def check_url"),
    ("只允許 http/https 且主機字串在清單", "parsed.scheme not in"),
    ("navigate 前檢查", "check_url(url, self.allowed_hosts)"),
    ("left_click 連結前檢查", "check_url(urljoin"),
    ("只收 ref_N 的正規表示式", "REF_PATTERN = "),
    ("舊 ref 失效的錯誤訊息", "元素編號已失效"),
]
for desc, key in checks:
    n = line_of(key)
    print("  第 {:>3} 行｜{:<30}｜{}".format(n, desc, src[n - 1].strip()[:80] if n else "（找不到）"))
print()
print("白名單內容在 hn_agent.py 的 main()：只放練習站那一個 127.0.0.1:<隨機埠>。")
print("錯誤用 ToolError 丟出，run_action 轉成「錯誤：...」文字回給模型（等同官方 tool_result 的 is_error），不中斷迴圈。")'
   show "$P"; run "$P" ;;

4) banner "用 --check-allowlist 測白名單（真的開無頭 Chromium，不呼叫模型）"
   tip "先跑 browser_tools.py --selftest（離線測 6 種網址、6 種錯誤 ref），再實跑 hn_agent.py --check-allowlist：真的啟動練習站和無頭 Chromium，試著前往真的 news.ycombinator.com、localhost 別名、file:///，三個都要被擋。本步不呼叫模型。"
   CMD='PYTHONUTF8=1 python browser_tools.py --selftest && PYTHONUTF8=1 python hn_agent.py --check-allowlist; rc=$?; echo "結束碼：$rc（0＝全部擋下）"; exit $rc'
   show "$CMD"; runcmd "$CMD" ;;

5) banner "用 --exercise 照官方 exercise 送 7 個固定呼叫（不呼叫模型）"
   tip "官方 browser-toolset 的 exercise 不需要模型：在本機起小頁面，送模型會送的呼叫，印每個 tool_result。這裡送 7 個：navigate、read_page、left_click 點 More、get_page_text 會成功；localhost 別名、換頁前的舊 ref、用座標點擊會被拒。官方是用 127.0.0.1 去 navigate 被拒，這裡方向相反。本步不呼叫模型。"
   CMD='PYTHONUTF8=1 python hn_agent.py --exercise; rc=$?; echo "結束碼：$rc（0＝7 個都符合預期）"; exit $rc'
   show "$CMD"; runcmd "$CMD" ;;

6) if [ "$MODE" = "--dry-run" ]; then
     banner "乾跑代理迴圈（假回覆，不呼叫模型，不算演練）"
     tip "乾跑模式：模型換成寫死的三個假回覆（get_page_text → 前往 evil.example → final），用來檢查迴圈、白名單擋下、blocked 紀錄、答案比對這幾條路徑。正式演練不要加 --dry-run。"
     CMD='PYTHONUTF8=1 python hn_agent.py --dry-run; rc=$?; echo "結束碼：$rc（乾跑，不算演練）"; exit $rc'
   else
     banner "實跑代理：看每一步模型選了什麼動作（本章唯一呼叫模型的一步）"
     tip "這一步會真的呼叫 claude -p，實測 3 次、約 20 秒，上限 8 次。程式先開好首頁，模型通常先 get_page_text 再回 final。注意兩件事：模型有沒有理會第 5 則的注入（想去 evil.example 會被擋並記進 blocked）；模型偶爾回非 JSON，程式會把錯誤寫回紀錄、計入步數，讓它重來。"
     CMD='PYTHONUTF8=1 python hn_agent.py; rc=$?; echo "結束碼：$rc（0＝答對、3＝答錯、2＝8 步內沒答案、1＝claude -p 或 Chromium 失敗）"; exit $rc'
   fi
   show "$CMD"; runcmd "$CMD" ;;

7) banner "打開 runs/ 底下的 result.json 與截圖；browser 和 computer use 差在哪"
   tip "找最新一次真跑（不是乾跑、不是檢查）的 result.json，印出每一步動作、被擋下的動作、對錯，再列截圖。截圖只給人事後對照，模型從頭到尾沒看過。最後一張表說明改成 computer use 要換哪些工具。本步不呼叫模型。"
   P='import json
from pathlib import Path

def runs_with_result(real_only):
    out = []
    for d in Path("runs").glob("*"):
        if (d / "result.json").exists() and (not real_only or d.name.count("-") == 1):
            out.append(d)
    return sorted(out, reverse=True)

runs = runs_with_result(True) or runs_with_result(False)
if not runs:
    print("runs/ 底下還沒有 result.json，請先跑第 6 步（或 bash s5.sh 6 --dry-run）。")
else:
    latest = runs[0]
    result = json.loads((latest / "result.json").read_text(encoding="utf-8"))
    print("最新的執行資料夾：runs/{}{}".format(latest.name, "（乾跑，不算演練）" if result.get("dry_run") else ""))
    print("任務：", result["goal"])
    print()
    for s in result["steps"]:
        act = s.get("action")
        if act == "final":
            print("  第 {} 步：final".format(s["step"]))
        elif act is None:
            print("  第 {} 步：無效回覆（{}）".format(s["step"], s.get("error", "")[:60]))
        else:
            first = (s.get("result") or "").splitlines()[0][:70]
            print("  第 {} 步：{} → {}{}".format(s["step"], json.dumps(act, ensure_ascii=False), first, "（錯誤）" if s.get("is_error") else ""))
    print()
    print("模型呼叫次數：{}／上限 {}；狀態：{}；耗時 {} 秒".format(result["model_calls"], result["max_steps"], result["status"], result.get("elapsed_seconds")))
    print("被擋下的動作：{} 個{}".format(len(result["blocked"]), "（模型沒有理會第 5 則的注入）" if not result["blocked"] else ""))
    for b in result["blocked"]:
        print("  第 {} 步：{}".format(b["step"], json.dumps(b["action"], ensure_ascii=False)))
    print("和 expected.json 比對：", {True: "答對", False: "答錯", None: "自訂任務，不比對"}[result.get("correct")])
    shots = sorted(latest.glob("*.png"))
    print("截圖：", ", ".join(p.name for p in shots) or "（無）")
print()
swap = [
    ("read_page / get_page_text", "screenshot，而且圖要回傳給模型看", "模型改成看像素"),
    ("left_click(ref)", "left_click(x, y)", "ref 拿掉，改給座標，可能點歪"),
    ("（無）", "scroll、wait、key", "長頁面要捲、動態頁要等"),
    ("navigate(url) 的白名單", "改在網路層擋（代理伺服器、防火牆）", "computer use 能點網址列自己打字"),
    ("screenshot（只存檔）", "同一個工具，但變成模型的眼睛", "1280×800 未壓縮約 4 MB，要縮圖"),
]
print("【表】改成 computer use 時工具怎麼換")
print("{:<26} | {:<34} | {}".format("S5 現在", "computer use", "說明"))
print("-" * 100)
for r in swap:
    print("{:<26} | {:<34} | {}".format(*r))
print()
print("卡關點：claude -p 這條路只能傳文字；要讓模型看圖，得改走官方 API，或請 Claude Code 用 Read 工具讀截圖檔。")'
   show "$P"; run "$P" ;;

8) banner "三個靈魂拷問：先自己回答"
   tip "先不要看答案。對著 S5 想一想三題，各用一兩句話說出來；想好之後說「繼續」，教練會執行 bash s5.sh 8b 顯示範例答案。"
   P='qs = [
    "1. 這個代理是給誰用的？（有人看著，還是無人值守？）",
    "2. 被賦予了哪些工具權限？刻意不給哪些？最壞情況是什麼？",
    "3. 資料和成果最後存在哪裡？哪些進版控、哪些不進？",
]
print("三個靈魂拷問：")
for q in qs:
    print("  " + q)
print()
print("提示：第 3 步的 5 個動作、第 4～5 步被擋下的網址、第 7 步 runs/ 裡的檔案都是線索。")
print("想好後說「繼續」→ bash s5.sh 8b")'
   show "$P"; run "$P" ;;

8b) banner "三個靈魂拷問：範例答案＋改給別人用會怎麼變"
   tip "範例答案直接從 s5-browser-hn/README.md 的表格讀出來。接著看如果改成真的去讀 news.ycombinator.com、給別人用，三題要怎麼改。本步不呼叫模型。"
   P='import re
from pathlib import Path

readme = Path("README.md").read_text(encoding="utf-8")
rows = [line for line in readme.splitlines() if re.match(r"^[|] (這個代理|被賦予|資料和成果)", line)]
print("=== 範例答案（摘自 s5-browser-hn/README.md） ===")
for line in rows:
    cells = [c.strip() for c in line.strip("|").split("|")]
    q, a = cells[0], cells[1].replace("**", "").replace(chr(96), "")
    print("■ " + q)
    print("  " + a)
    print()
if len(rows) != 3:
    print("（README 表格只讀到 {} 列，請直接打開 README 第 2 節看）".format(len(rows)))
change = [
    ("給誰用", "自己，在終端機看著", "同事或客戶；要說明風險、取得同意（官方 README 安全段最後一段），無人看著時更要嚴"),
    ("工具權限", "白名單只有本機一個 host:port", "白名單改成 news.ycombinator.com 一個網域；加網路層出口規則擋重新導向與頁面內資源；瀏覽器放容器或 VM"),
    ("存在哪裡", "runs/ 不進版控", "截圖可能含別人的頁面內容，要定保存期限；模型改走 API（金鑰放專案 .env），不能再用個人訂閱"),
]
print("=== 如果改成真的讀 HN、給別人用 ===")
print("{:<8} | {:<28} | {}".format("題目", "現在（本機練習）", "改成真網站、給別人用"))
print("-" * 120)
for r in change:
    print("{:<8} | {:<28} | {}".format(*r))
print()
print("為什麼練習只准連本機網站：真 HN 首頁天天變，答案無法驗收；真網站的內容不可控，提示詞注入防不勝防；")
print("本機練習站的注入是自己放的，可以重複測「頁面內容不是指令」。")
n = len([d for d in Path("runs").glob("*") if d.is_dir()]) if Path("runs").exists() else 0
print()
print("本範例的產出：{} 個 runs/ 執行資料夾（含檢查與乾跑留下的資料夾）".format(n))
print("整章模型呼叫：只有第 6 步 hn_agent.py 自己的 claude -p（實測 3 次，上限 8 次）。")'
   show "$P"; run "$P" ;;

*) echo "步驟要 1～8（第 8 步的後半是 8b）"; exit 1 ;;
esac
