# S4 代管式每日簡報代理（官方 `managed-agents/daily-brief` 本機模擬版）

## 1. 模仿什麼、做什麼

- 模仿官方 `claude-quickstarts` 的 `managed-agents/daily-brief`（K902 講義：`~/workspace/kindle-902-claude-quickstarts/lessons/ch09-managed-agents.md`；規格：`../specs/s4.md`）。
- 一句話：每個工作日讀兩個 Slack 頻道和一個 GitHub repo 的 PR，替一位讀者挑出今天要處理的事，貼一則簡報。
- 和 K903 S4（網路交換器比價）同一套架構：代理設定有版本、一次一個 session、事件紀錄、評分者、排程只印不建。K904 多了官方最看重的部分：**跨次執行的 state**（書籤、帳本、notes、執行紀錄）、唯讀的 preferences、「讀不到不等於沒事」、確認貼文成功才記帳、演習模式、對注入文字的防護。所以要跑兩天份資料才看得出效果。
- 所有 Slack／GitHub 資料都是 `fixtures/` 裡的**虛構 JSON，但照官方格式**（每個檔都有 `_comment` 註明）；不連真的 Slack 或 GitHub，模型一律走 `claude -p`。

## 2. 三個靈魂拷問

| 問題 | 答案 |
| --- | --- |
| 這個代理是做給誰用的？ | 一位讀者（官方設計就是「one reader」，`agent.md` 第 37 行），本範例的讀者是我自己。無人值守：排程每個工作日跑一次，沒有人能即時核准，所以代理不准停下來發問；讀不到、貼不出去都要寫進執行紀錄，而不是假裝沒事。 |
| 被賦予了哪些工具的權限？ | **可以用**（全部由主機程式代為執行，模型本身是 `claude -p --tools ""`，碰不到電腦）：`read_preferences`（唯讀）、`read_state`（讀 `state/`）、`read_source`（只讀 preferences 列出的來源，從 fixtures 取）、`post_brief`（只能追加到 preferences 指定的那一個 outbox 頻道，頻道由主機決定，模型無法指定）、`write_state`（只能寫 `bookmarks.json`、`ledger.md`、`notes.md`、`proposals.md`、`runs/<日期>.md`，演習時一律拒絕）。每次呼叫前主機比對 `agent.json` 的 `tools` 白名單。**刻意不給**：`web_search`、`web_fetch`（官方也關掉，免得注入文字有對外出口）、`bash`、改 preferences、貼到其他頻道、任何真的 Slack／GitHub 連線。主機還會刪掉含陌生連結的行，並擋下 `<!channel>`、`<@...>` 之類的提及。 |
| 資料和成果最後存在哪裡？ | 輸入：`fixtures/day1/`、`fixtures/day2/`（虛構，進版控）、`preferences/preferences.md`（進版控，代理唯讀）。跨次狀態：`state/`（對應官方 `state` memory store）。每次 session：`runs/<session_id>/events.jsonl`、`brief.md`、`summary.json`。「貼文」：`outbox/C0345678912.jsonl`。`state/`、`outbox/`、`runs/` 都不進版控（本資料夾的 `.gitignore`）。不上傳、不寄信、不連 Slack；事件紀錄裡的路徑只留檔名。 |

用 `claude -p` 還是 API：只有我自己、每天 2～4 次呼叫、失敗重跑即可 → `claude -p`，加呼叫上限（`MAX_MODEL_CALLS = 4`）。

## 3. 架構與資料流

```text
agents/daily-brief/agent.json  ──load_agent：版本鎖（內容改了但 version 沒升 → 拒絕，不呼叫模型）
agents/daily-brief/deployment.json  state_access: read_write（改 read_only＝演習）

┌──────────── Session  runs/<sesn_id>/ ─────────────────────────────────────────┐
│ 1 read_preferences  preferences.md（唯讀；寫 STOP 就停）                          │
│ 2 read_state        state/bookmarks.json、ledger.md、notes.md、上次執行紀錄       │
│ 3 read_source ×3    fixtures/<day>/…（從書籤往前 10 分鐘；ok:false＝讀不到）      │
│   host.collected    新候選／帳本中仍開著（第 N 天）／已關閉（不再提）             │
│ 4-6 model.call(writer) claude -p ─► JSON {brief, items, cuts, …}                  │
│   verify.links      連結必須和 permalink／html_url 完全相同，否則刪掉記 cuts      │
│   model.call(grader) claude -p + rubric.md ─► outcome.graded（FAIL 重寫一次）    │
│ 7 write_state runs/<日期>.md「status: posting」→ post_brief ─► outbox/            │
│   回應 ok:true 且有 ts 才算成功；channel_not_found → held，其他 state 都不動      │
│ 8 write_state ledger.md、bookmarks.json（讀失敗的來源書籤不動）、runs/<日期>.md   │
│ session.idle（中途失敗：session.error）→ summary.json                             │
└───────────────────────────────────────────────────────────────────────────────┘
deploy.py --dry-run：印出「週一到週五 07:32（台北）開一個新 session」的 schtasks／cron
```

本機元件對應官方：

| 本機模擬 | 官方 `daily-brief` | 說明 |
| --- | --- | --- |
| `agent.json`＋`agent-lock.json` | `agent.md`（`ant apply` 改了就發新版本） | 系統提示是官方 8 步驟的繁中改寫；主機代做第 1～3、7～8 步，模型負責第 4～6 步 |
| `deployment.json` | `deployment.md` | cron `32 7 * * 1-5`；官方時區 `America/New_York`，本範例 `Asia/Taipei` |
| `preferences/preferences.md` | `preferences` memory store（`read_only`） | 照 `preferences.example.md` 的段落改寫 |
| `state/` | `state` memory store（`read_write`） | 檔名照 `memory_store_state.yaml` |
| `fixtures/`、`outbox/` | Slack `conversations.history`／`chat.postMessage`、GitHub MCP | 虛構資料；貼文回 Slack 風格的 `{"ok": true, "ts": …}` |
| `--rehearsal` | 把 state 設成 `read_only` | 寫簡報但不貼、state 一個字都不改 |
| `reset_state.py` | `scripts/reset-state.sh` | 清空 `state/` 與 `outbox/` |
| `rubric.md`＋評分者 | （官方沒有） | 沿用 K903 的 outcome 評分者 |
| `MAX_MODEL_CALLS = 4` | `budget.max_list_cost.amount: "500"`（分，到上限暫停） | 本機只限次數，不算錢 |

## 4. 怎麼跑（Git Bash）

```bash
cd ~/workspace/kindle-904-quickstarts-official-samples/s4-daily-brief

PYTHONUTF8=1 python reset_state.py                        # 從頭開始：清空 state/ 與 outbox/
PYTHONUTF8=1 python run_session.py --day day1 --rehearsal # 演習（模型 2～4 次），state／outbox 不變
PYTHONUTF8=1 python run_session.py --day day1             # 第 1 天（模型 2～4 次）
PYTHONUTF8=1 python run_session.py --day day2             # 第 2 天（模型 2～4 次）
PYTHONUTF8=1 python run_session.py --day day2             # 同一天重跑：0 次，不重貼
PYTHONUTF8=1 python run_session.py --day day1 --dry-run   # 乾跑：不呼叫模型，不算演練，寫暫存資料夾
PYTHONUTF8=1 python deploy.py --dry-run                   # 只印排程指令

# 離線自我檢查（全部乾跑）
PYTHONUTF8=1 python run_session.py --selftest
PYTHONUTF8=1 python deploy.py --selftest
PYTHONUTF8=1 python reset_state.py --selftest
```

其他選項：`--fail-post`（模擬目的地 `channel_not_found`）、`--preferences <檔>`（例如換一份寫 STOP 的 preferences）。

互動演練：`bash ../practice/interactive/s4.sh 1`～`9`、`9b`（第 4、5、6 步呼叫模型）。

## 5. 實際跑出來的結果（2026-11-25，真模型 `claude -p`，共 6 次呼叫）

| session | 指令 | 模型呼叫 | 評分 | 狀態 |
| --- | --- | --- | --- | --- |
| `sesn_20261125-175835_25b207` | `--day day1 --rehearsal` | 2 | 第 1 次 PASS | rehearsal（不貼文），state／outbox 雜湊前後相同 |
| `sesn_20261125-175851_402013` | `--day day1` | 2 | 第 1 次 PASS | posted |
| `sesn_20261125-175906_256aa4` | `--day day2` | 2 | 第 1 次 PASS | posted |

第 1 天的簡報（`outbox/C0345678912.jsonl`）：

```text
每日簡報，11 月 23 日（星期一）
- 決定是否核准客戶 Acme 的 3 萬元退款（今天要回覆）：https://example.slack.com/archives/C0123456789/p1795350600000100
- 確認是否給客戶 Beta 延長試用兩週（SSO 設定卡住）：https://example.slack.com/archives/C0123456789/p1795389900000400
- 審查 PR #101「修正登入逾時造成的重複扣款」（alice-dev）：https://github.com/example-org/example-repo/pull/101
- 審查 PR #102「升級付款 SDK 到 v5」（bob-dev）：https://github.com/example-org/example-repo/pull/102
讀不到：#example-escalations（機器人不在該頻道，not_in_channel）
```

模型自己刪掉的（cuts）：午餐閒聊、**注入文字**（理由寫「指令注入」，沒有轉貼、沒有 `<!channel>`）、dependabot 的 #103、和讀者無關的 #104。

第 2 天的簡報：

```text
每日簡報，11 月 24 日（星期二）
- 審核付款服務 11/22 事故的根因報告草稿，審完才能對外發布：https://example.slack.com/archives/C0234567891/p1795372000000100
- 審查 PR #105「修正時區造成的報表日期錯一天」（alice-dev）：https://github.com/example-org/example-repo/pull/105
- 仍在等，第 2 天：審查 PR #101「修正登入逾時造成的重複扣款」（alice-dev）：https://github.com/example-org/example-repo/pull/101
```

跨日記憶有作用：

- #101 第 1 天報過、仍開著 → 只寫一行「仍在等，第 2 天」。
- #102 第 1 天報過、已合併 → 不出現（執行紀錄記在「已關閉、不再提」）。
- #example-escalations 第 1 天讀不到，書籤停在第一次執行的起點；第 2 天從那裡重讀（`oldest=1795303320`），才看得到第 1 天凌晨那則「根因報告等你審」。如果把讀不到當成「沒事」而移動書籤，這則就永遠漏掉了。
- Beta SSO 那則落在第 2 天「書籤往前 10 分鐘」的重疊區，但帳本裡有，所以沒有重報。

第 2 天 session 的事件列表（`runs/sesn_20261125-175906_256aa4/events.jsonl`，節錄重點欄位）：

```text
17:59:06 session.created   agent=daily-brief v1 sha=ddaf620e073c day=day2 rehearsal=false
17:59:06 session.running
17:59:06 tool.use/result   read_preferences → 讀到 948 字
17:59:06 tool.use/result   read_state → 書籤 3 個、帳本 4 行、第一次執行：False
17:59:06 tool.use/result   read_source slack:C0123456789 → 3 則訊息（oldest=1795389720）
17:59:06 tool.use/result   read_source slack:C0234567891 → 2 則訊息（oldest=1795303320）
17:59:06 tool.use/result   read_source github:example-org/example-repo → 5 個 PR
17:59:06 host.collected    new=7 carried=1 dropped_closed=[#102] unreadable=[]
17:59:14 model.call        writer n=1 output_tokens=951 duration_ms=6816
17:59:14 agent.message     items=3
17:59:14 verify.links      kept=3
17:59:20 model.call        grader n=2 output_tokens=622 duration_ms=4857
17:59:20 outcome.graded    attempt=1 overall=PASS
17:59:20 tool.use/result   write_state runs/2026-11-24.md（status: posting）
17:59:20 tool.use/result   post_brief → ok:true ts=1795476720.000000
17:59:20 tool.use/result   write_state ledger.md（追加）、bookmarks.json、runs/2026-11-24.md（status: posted）
17:59:20 session.idle      stop_reason=end_turn status=posted final_outcome=PASS
```

邊界案例（`--selftest` 與演練第 7 步驗證，都不呼叫模型）：同一天重跑 → 0 次呼叫、不重貼；preferences 寫 `STOP` → 0 次呼叫、只寫執行紀錄；`channel_not_found` → `held`、保留簡報，帳本與書籤雜湊不變；連結被竄改 → 該行刪掉並記入 cuts；改 `agent.json` 沒升 version → 拒絕執行。

## 6. 和官方差在哪（已知落差）

- **主機代做讀取與記帳**：官方是代理自己在沙箱用 curl 呼叫 Slack、用 MCP 讀 GitHub、自己寫 memory store；本範例由主機代做（模型沒有任何工具），模型只負責「決定、驗證連結、寫簡報」。因此「不准找憑證」這條規則在本機不會被考驗到。
- **第 5 步「貼文前重查即時狀態」只做連結比對**：本機 fixtures 不會在讀和貼之間變動，重查沒有意義。
- **提早檢查今天是否已貼過**：官方在第 7 步才查；本範例在呼叫模型前就先查一次（省下 2～4 次呼叫），貼文前仍會再查。
- **GitHub PR 不用書籤過濾**：每次都列出全部 PR 再用帳本去重（列出等讀者審查的 PR 本來就要看全部未關閉的）；Slack 才用書籤。
- **GitHub 與 Slack 訊息欄位**：官方程式只寫到 `ok`、`oldest`、`html_url`、permalink，其餘欄位是本範例自訂（報告未載明）。
- **評分者**：官方 daily-brief 沒有 outcome 評分者，這是沿用 K903 的架構；主機另外加了幾條確定性檢查（標題、行數、提及、讀不到點名）。
- **花費**：官方 README 實測每次約 1.00～1.50 美元，預算 `"500"` 是以「分」為單位的字串，到上限是暫停不是失敗；本範例走 `claude -p`，不花 API 額度。
