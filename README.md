# K904 Claude Quickstarts 官方範例版實作

K903 的對照版。K903 照官方 `anthropics/claude-quickstarts` 的做法，用使用者自己生活與工作的題材做了 5 個小範例；K904 用**同一套結構、同樣的學習順序、同樣的架構**，把題材換回官方 quickstarts 裡實際示範的範例（客服代理、agents 工具迴圈、autonomous-coding 的應用規格、managed-agents 子專案、browser／computer use 的示範任務）。

書號 9 開頭代表這是自製教材，沒有對應的原書。

> 目前狀態：骨架與五章規格（`specs/s1.md`～`specs/s5.md`）已完成，範例程式尚未實作。

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

| 範例 | 官方題材 | 預定資料夾 | 真模型呼叫上限 |
| --- | --- | --- | --- |
| S1 | `agents` 筆記本的 Multi-Tool Agent（think、calculator、brave_web_search；OKC 人口開根號、GR86 裝幾根香蕉），搜尋改讀官方筆記本存檔結果 | `s1-multi-tool-agent/` | 單題 6 次，整章 12 次 |
| S2 | `customer-support-agent` 的 Anthropic 客服助理（官方 7 欄 JSON 回覆、8 個分類），Bedrock 知識庫改本機 `kb/` | `s2-official-support/` | 冒煙 3 次，整章 5 次 |
| S3 | `autonomous-coding` 的 `app_spec.txt`（claude.ai 複製品）縮小版：只做第 3 步「Conversation Management」5 項功能 | `s3-long-running/` | 單次 10 次，兩次執行合計 12 次 |
| S4 | `managed-agents/daily-brief`（讀 Slack 與 GitHub PR 貼簡報，含書籤與帳本跨日記憶），資料改本機 JSON | `s4-daily-brief/` | 每 session 4 次，整章 12 次 |
| S5 | `browser-use-demo` 範例任務「告訴我 Hacker News 前 3 名文章」，改在本機 127.0.0.1 練習頁重現 | `s5-browser-hn/` | 每次 8 次 |

細節以 `specs/` 為準。

## 三個靈魂拷問

每個範例學完都要回答這三題（說明與常見錯誤見 K903 README，空白模板見 [TEMPLATE-three-questions.md](TEMPLATE-three-questions.md)）：

1. 這個代理是做給誰用的？
2. 它被賦予了哪些工具的權限？
3. 它的資料和成果最後存在哪裡？

## 5 個範例的三個靈魂拷問總覽

> 範例實作完成後，從各範例 README 第 2 節摘錄填入；不一致時以各範例 README 為準。

| 範例 | 做給誰用 | 工具權限 | 資料與成果存哪 |
| --- | --- | --- | --- |
| S1 |  |  |  |
| S2 |  |  |  |
| S3 |  |  |  |
| S4 |  |  |  |
| S5 |  |  |  |

## 互動演練

> 占位：範例完成後，比照 K903 在 `practice/interactive/` 建 `s1.sh`～`s5.sh`（每章 8 步，第 8 步分 `8`／`8b`）與教練稿 `coach-s1.txt`～`coach-s5.txt`，並列出各章呼叫真模型的步驟與次數。

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
shared/                        共用轉接層（claude -p，沿用 K903）
specs/s1.md … s5.md            五個範例的規格
```
