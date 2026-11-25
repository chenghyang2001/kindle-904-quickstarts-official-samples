# K904 Claude Quickstarts 官方範例版實作

K903 的對照版。K903 照官方 `anthropics/claude-quickstarts` 的做法，用使用者自己生活與工作的題材做了 5 個小範例；K904 用**同一套結構、同樣的學習順序、同樣的架構**，把題材換回官方 quickstarts 裡實際示範的範例（客服代理、agents 工具迴圈、autonomous-coding 的應用規格、managed-agents 子專案、browser／computer use 的示範任務）。

書號 9 開頭代表這是自製教材，沒有對應的原書。

> 目前狀態：五章規格（`specs/`）、五個範例資料夾與互動演練（`practice/interactive/`）都已完成，每個範例都用真模型（`claude -p`）跑過一次，結果記在各範例 README 第 5 節。

## K904 與 K903 的差別

| 面向 | K903 生活題材版 | K904 官方範例版 |
| --- | --- | --- |
| 題材 | 使用者自己的案例（購物筆記、AMR 產品問答、記帳、交換器比價…） | 官方 quickstarts 的原始題材，以盤點報告與官方原始碼為準 |
| 資料 | 自己的真實或自編資料 | 官方資料；拿不到的（Bedrock、Slack、GitHub、Sentry、外部網站）用本機假資料，標「虛構但照官方格式」 |
| 結構 | S1～S5、shared/ 轉接層、三個靈魂拷問 | 完全相同，方便兩版逐檔對照 |
| 學習目的 | 把官方做法套到自己的需求 | 先看清楚官方原本在示範什麼，再回頭對照 K903 怎麼改寫 |

建議讀法：同一章先做 K904（看官方原題），再做 K903（看怎麼換成自己的題材）；各規格最後一節「與 K903 版的差異」就是對照重點。

## 學習順序（由簡到難，和 K903 相同）

| 順序 | 範例 | 對應官方章（K902） | 一句話主題 | 規格 |
| --- | --- | --- | --- | --- |
| 1 | S1 | 第 3 章 agents | 代理迴圈：模型想、呼叫工具、看結果、再想 | [specs/s1.md](specs/s1.md) |
| 2 | S2 | 第 1 章 customer-support-agent | 給客戶用的客服網頁加知識庫問答 | [specs/s2.md](specs/s2.md) |
| 3 | S3 | 第 10 章 autonomous-coding | 長時間工作：初始化代理加寫程式代理接力 | [specs/s3.md](specs/s3.md) |
| 4 | S4 | 第 9 章 managed-agents | 雲端代管：設定、session、事件紀錄分開存 | [specs/s4.md](specs/s4.md) |
| 5 | S5 | 第 4～8 章 browser／computer use | 瀏覽器與電腦操作，權限最大、放最後 | [specs/s5.md](specs/s5.md) |

### 五章規格摘要

| 範例 | 官方題材 | 資料夾 | 真模型呼叫上限（規格） |
| --- | --- | --- | --- |
| S1 | `agents` 筆記本的 Multi-Tool Agent（think、calculator、brave_web_search；OKC 人口開根號、GR86 裝幾根香蕉），搜尋改讀官方筆記本存檔結果 | [s1-multi-tool-agent/](s1-multi-tool-agent/) | 單題 6 次，整章 12 次 |
| S2 | `customer-support-agent` 的 Anthropic 客服助理（官方 7 欄 JSON 回覆、8 個分類），Bedrock 知識庫改本機 `kb/` | [s2-official-support/](s2-official-support/) | 冒煙 3 次，整章 5 次 |
| S3 | `autonomous-coding` 的 `app_spec.txt`（claude.ai 複製品）縮小版：只做第 3 步「Conversation Management」5 項功能 | [s3-long-running/](s3-long-running/) | 單次 10 次，兩次執行合計 12 次 |
| S4 | `managed-agents/daily-brief`（讀 Slack 與 GitHub PR 貼簡報，含書籤與帳本跨日記憶），資料改本機 JSON | [s4-daily-brief/](s4-daily-brief/) | 每 session 4 次，整章 12 次 |
| S5 | `browser-use-demo` 範例任務「告訴我 Hacker News 前 3 名文章」，改在本機 127.0.0.1 練習頁重現 | [s5-browser-hn/](s5-browser-hn/) | 每次 8 次 |

細節以 `specs/` 為準。

## 三個靈魂拷問

每個範例學完都要回答這三題（說明與常見錯誤見 K903 README，空白模板見 [TEMPLATE-three-questions.md](TEMPLATE-three-questions.md)）：

1. 這個代理是做給誰用的？
2. 它被賦予了哪些工具的權限？
3. 它的資料和成果最後存在哪裡？

## 5 個範例的三個靈魂拷問總覽

> 本表摘自各範例 README 第 2 節，細節以範例內為準。五個範例的 `claude -p` 都用 `--tools ""` 啟動，模型本身沒有任何工具，下表的「工具」都是程式代為執行。

| 範例 | 做給誰用 | 工具權限 | 資料與成果存哪 |
| --- | --- | --- | --- |
| S1 官方多工具代理 | 使用者自己，在終端機一個人看著跑，目的是看懂工具迴圈 | `think`（只回 `Thinking complete!`）、`calculator`（純計算）、`brave_web_search`（只讀 `data/search_fixture.json` 的官方筆記本存檔結果，不上網）；三個都沒有副作用；不給讀寫檔、上網、執行程式碼 | 答案只印在終端機；迴圈紀錄寫 `runs/<時間>.json`（不進版控、無個資）；搜尋資料 `data/search_fixture.json` 進 git |
| S2 官方客服代理 | 官方設定是網站上的外部使用者；本範例只在 `127.0.0.1:8904` 給自己示範，正式給外部使用者要改公司 API key，並加速率限制與身分驗證 | 模型沒有工具；程式代做讀 `kb/`、檢索、驗證 JSON、寫紀錄；退款、帳號停權申訴、刪帳號、隱私與法律問題一律轉真人（`redirect_to_agent`）；不在分類表裡的分類 id 由程式刪掉 | 知識庫 `kb/*.md` 與 `kb/categories.json` 進 git；每次問答寫 `logs/YYYY-MM-DD.jsonl`（可能含個資，不進版控） |
| S3 autonomous-coding 縮小版 | 想學長時間任務怎麼分 session 接力的自己，在終端機看著跑；產出的 `chat_store.py` 是練習品 | 模型沒有工具、只回 JSON；寫檔、跑測試、跑 `init.sh`、commit 由 harness 代做；只准寫進 `workdir/`，擋 `..`、絕對路徑、`.git/`；清單與進度檔只有 harness 能寫，寫程式代理不能改 `tests/`、`init.sh`；`init.sh` 逐行白名單；一次執行最多呼叫模型 10 次 | 全部在 `workdir/`（獨立 git repo，不進版控）：`feature_list.json`、`claude-progress.txt`、`tests/`、`chat_store.py`、`harness_state.json` 與 git 歷史；5/5 完成版另存成進版控的 `snapshot-5of5/` |
| S4 代管式每日簡報代理 | 一位讀者（本範例是自己），無人值守，每個工作日排程跑一次，代理不准停下來發問 | 5 個工具全由主機代為執行：`read_preferences`（唯讀）、`read_state`、`read_source`（只讀 preferences 列的來源，取自 fixtures）、`post_brief`（只能貼到 preferences 指定的那一個頻道）、`write_state`（限定檔名，演習時拒絕）；呼叫前比對 `agent.json` 白名單；不給 `web_search`、`web_fetch`、`bash`、改 preferences | `fixtures/`、`preferences/` 進 git；跨次狀態 `state/`、每次 session 的 `runs/<session_id>/`、貼文 `outbox/` 都不進版控 |
| S5 HN 前三名讀取代理 | 使用者自己，在終端機看著它跑；學習用，不是排程爬蟲 | `navigate`（白名單只有 `127.0.0.1:<埠>`）、`read_page`、`get_page_text`、`left_click`（只收 `ref_N`，不收座標）、`screenshot`（只存檔給人看）；不給 `type`、`form_input`、`scroll`、JavaScript 執行、連外網、登入、付款 | 練習站 `site/*.html` 與 `expected.json` 進 git；每次執行的 `step-N.png` 與 `result.json` 存 `runs/<時間>/`，不進版控 |

## 互動演練

`practice/interactive/` 是五個範例的逐步演練腳本，一次跑一步；`coach-sN.txt` 是每一步的教練講稿。

用法（Git Bash）：

```bash
cd practice/interactive
bash s1.sh 1      # 格式：bash sN.sh <步驟>，N 是範例編號
```

- S1、S2、S3、S5 每章 8 步，S4 有 9 步。最後一步分兩半：`bash sN.sh 8`（S4 是 `9`）先出三個靈魂拷問，自己想好後再跑 `bash sN.sh 8b`（S4 是 `9b`）看範例答案。
- 建議順序：S1 → S2 → S3 → S4 → S5（和上面的學習順序一樣）。

各章會呼叫真模型的步驟（數字取自各 `sN.sh` 開頭註解，其餘步驟全部離線）：

| 章 | 呼叫模型的步驟 | 次數 |
| --- | --- | --- |
| S1 | 第 4 步 | 最多 6 次（不重試） |
| S2 | 第 5、6 步 | 各 1 次，共 2 次 |
| S3 | 第 5、6 步 | 各最多 2 次，整章最多 4 次 |
| S4 | 第 4、5、6 步 | 每步通常 2 次、最多 4 次，整章最多 12 次 |
| S5 | 第 6 步 | 實測 3 次，上限 8 次 |

S2 第 4～7 步會在背景啟動 `server.py`（只綁 127.0.0.1，預設埠 8904，可用 `S2_PORT` 改），該步結束時一定關掉。S4 第 4 步（非乾跑）會先清空 `s4-daily-brief/state` 與 `outbox`，從第 1 天重新開始。

### `--dry-run`：不呼叫模型，只檢查腳本路徑

用寫死的假回覆代替模型，畫面會標明是乾跑，不算演練：

```bash
bash s1.sh 4 --dry-run
bash s2.sh 5 --dry-run    # 第 6 步同樣可加
bash s3.sh 5 --dry-run    # 產出寫到 s3-long-running/logs/dry-run-workdir，不動真正的 workdir
bash s3.sh 6 --dry-run
bash s4.sh 4 --dry-run    # 第 5、6 步同樣可加；state／outbox／runs 寫在暫存資料夾，跑完刪掉
bash s5.sh 6 --dry-run
```

### S3 的 `seed` 與 `restore`

S3 第 5 步會先把 5/5 完成的 `s3-long-running/workdir` 改名成 `workdir.bak-5of5`，再從空的 workdir 重跑。演練完要還原：

```bash
bash s3.sh restore    # workdir.bak-5of5 → workdir（8b 結尾也會問要不要還原）
```

**新電腦先跑 seed（或讓它自動重建）**：`workdir/` 與 `workdir.bak-*/` 都在 `.gitignore`，clone 下來時不存在。5/5 完成版的工作樹放在進版控的 `s3-long-running/snapshot-5of5/`：

```bash
bash s3.sh seed       # 從 snapshot-5of5 重建 workdir：複製檔案、git init、一個 commit；不呼叫模型
```

第 3、4、7 步與 `restore` 發現 workdir 和 `workdir.bak-5of5` 都不存在時會自動重建，不跑 seed 也可以。重建版只有 1 個 commit，第 3 步會改顯示 `snapshot-5of5/git-log.txt` 裡原本的 6 個 commit。

## K903 對照

同一章兩版的結構、工具迴圈與三個靈魂拷問都相同，只有題材不同。K903 在 `~/workspace/kindle-903-quickstarts-samples/`。

| 章 | K903 生活題材版 | K904 官方範例版 |
| --- | --- | --- |
| S1 | 本機資料夾小管家（`s1-agent-loop/`）：唯讀查使用者自己的 shopping-notes 資料夾，工具 `list_dir`、`read_file`、`search_text` | 官方 `agents` 筆記本的 Multi-Tool Agent（`s1-multi-tool-agent/`）：`think`、`calculator`、離線 `brave_web_search`，回答 OKC 人口開根號等官方原題 |
| S2 | AMR 產品問答網頁（`s2-customer-web/`）：給想買 AMR 的工廠、倉儲人員，知識庫 5 份 markdown | 官方 `customer-support-agent` 的 Anthropic 客服助理（`s2-official-support/`）：官方 7 欄 JSON 回覆、8 個分類，Bedrock 知識庫改本機 `kb/` |
| S3 | 兩階段自動寫程式（`s3-long-running/`）：代理接力寫出自用記帳小工具 `ledger.py`，4 項功能 | 官方 `autonomous-coding` 縮小版（`s3-long-running/`）：claude.ai 複製品的「對話管理」資料層 `chat_store.py`，5 項功能 |
| S4 | 代管式每日比價代理（`s4-managed-cloud/`）：讀 `data/switches.json` 交換器價格，寫比價報告 | 官方 `managed-agents/daily-brief`（`s4-daily-brief/`）：讀 Slack 與 GitHub PR（本機虛構 JSON）貼每日簡報，含書籤與帳本跨日記憶 |
| S5 | 瀏覽器讀價代理（`s5-browser-computer/`）：在本機練習網站讀價格，工具含 `click`、`type` | 官方 `browser-use-demo` 範例任務「Hacker News 前 3 名」（`s5-browser-hn/`）：本機 HN 練習頁，只能讀與點 `ref_N`，不能打字 |

## 使用前準備

1. `claude` CLI 已安裝並登入（跑 `claude -p "hi"` 能回應）。
2. 不設定 `ANTHROPIC_API_KEY`（也不設任何其他 API 金鑰）；一旦設了，`claude -p` 會改扣 API 額度。
3. 所有模型呼叫一律走 `shared/` 轉接層（`claude -p`，用訂閱額度），不 mock 模型；只有 `--dry-run` 用寫死的假回覆檢查程式路徑：
   - `shared/llm_agent.py`：單次問答與 JSON 抽取（`ask`、`ask_json`）
   - `shared/claude_cli_client.py`：模仿 anthropic SDK 的最小介面，含工具迴圈
   - `shared/qs_source.py`：唯讀查看官方 quickstarts 原始碼（`~/workspace/claude-quickstarts`）
4. Windows 上執行 Python 要加 `PYTHONUTF8=1`。轉接層自我檢查：

   ```bash
   PYTHONUTF8=1 python shared/llm_agent.py --selftest
   ```

## 來源

- 盤點報告：`~/workspace/console/drills/anthropic-harness/quickstarts-repo-report.md`
- K902 講義：`~/workspace/kindle-902-claude-quickstarts/lessons/`
- K903 生活題材版：`~/workspace/kindle-903-quickstarts-samples/`
- 官方原始碼（只讀，commit `4a4224b`）：`~/workspace/claude-quickstarts/`

## 目錄

```text
README.md                      本檔
CLAUDE.md                      給 Claude Code 的專案說明
TEMPLATE-three-questions.md    三個靈魂拷問空白模板
shared/                        共用轉接層（claude -p，沿用 K903）：llm_agent.py、claude_cli_client.py、qs_source.py
specs/s1.md … s5.md            五個範例的規格
s1-multi-tool-agent/           S1：multi_tool_agent.py、data/search_fixture.json
s2-official-support/           S2：server.py、smoke_test.py、kb/（8 份 md＋categories.json）、static/index.html、docs/screenshot.png
s3-long-running/               S3：harness.py、app_spec.txt、sample-conversations.json、snapshot-5of5/（5/5 完成版工作樹）
s4-daily-brief/                S4：run_session.py、deploy.py、reset_state.py、rubric.md、agents/daily-brief/、fixtures/day1～day2/、preferences/
s5-browser-hn/                 S5：hn_agent.py、browser_tools.py、expected.json、site/（3 個練習頁）
practice/interactive/          互動演練腳本 s1.sh～s5.sh 與教練稿 coach-s1.txt～coach-s5.txt
```

執行期產物（`runs/`、`logs/`、`workdir/`、`workdir.bak-*/`、`state/`、`outbox/`、`__pycache__/`、`.ruff_cache/`）都在 `.gitignore`，不進版控。
