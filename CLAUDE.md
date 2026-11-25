# CLAUDE.md

K904「Claude Quickstarts 官方範例版實作」教材 repo（見 README.md）。K903 的對照版：結構、學習順序、五個範例 S1～S5 的架構都和 K903 一樣，差別只在**題材**——K903 用使用者自己的生活與工作案例，K904 改用官方 `anthropics/claude-quickstarts` 裡實際示範的題材（以盤點報告與官方原始碼為準）。沒有原書。

- 這是學習用教材（快速 demo 模式），不是正式專案。
- 每個範例動工前先讀 `specs/sN.md`；範例資料夾都要有 README.md，且必須回答三個靈魂拷問（做給誰用、工具權限、資料與成果存哪）；根目錄 `TEMPLATE-three-questions.md` 是空白模板。README 總覽表與各範例 README 不一致時，以各範例 README 為準。
- **模型一律走 `shared/`**：`shared/llm_agent.py` 或 `shared/claude_cli_client.py`（`claude -p`，訂閱額度）。
  - 不設定 `ANTHROPIC_API_KEY`，也不設任何其他 API 金鑰（設了 `claude -p` 會改扣 API 額度）。
  - 不 mock 模型：需要模型回答的地方一律由真模型回答。
  - 唯一例外是 `--dry-run`：用寫死的假回覆檢查程式路徑，畫面必須標明「乾跑」，不算演練、不算完成。
  - 拿不到的外部環境（Bedrock 知識庫、Slack、GitHub、Sentry、外部網站、桌面）用本機假資料或本機練習網站代替，資料標「虛構但照官方格式」；這是替代環境，不是 mock 模型。
- 官方原始碼 `~/workspace/claude-quickstarts` 只讀：不修改、不整包複製進本 repo、不安裝它的依賴。查看用 `shared/qs_source.py`。
- 報告或官方原始碼沒寫的官方細節不可自己編，寫「報告未載明」。
- 路徑一律寫 `~` 或 `Path.home()`，不寫死使用者資料夾；不寫個人資料。Windows 上執行 Python 一律加 `PYTHONUTF8=1`，用 Git Bash。
- `runs/`、`logs/`、`workdir/`、`workdir.bak-*/` 是執行產物，不進版控（已在 `.gitignore`）。

## 來源

| 來源 | 位置 |
| --- | --- |
| 盤點報告（原始報告） | `~/workspace/console/drills/anthropic-harness/quickstarts-repo-report.md` |
| K902 各章講義 | `~/workspace/kindle-902-claude-quickstarts/lessons/chNN-*.md` |
| K903 生活題材版 | `~/workspace/kindle-903-quickstarts-samples/` |
| 官方原始碼（只讀，commit `4a4224b`） | `~/workspace/claude-quickstarts/` |

## 架構

```text
README.md                    總覽、與 K903 的差別、學習順序、三個靈魂拷問
TEMPLATE-three-questions.md  空白模板與 claude -p／API 判斷表
shared/                      共用轉接層：llm_agent.py、claude_cli_client.py、qs_source.py（沿用 K903）
specs/s1.md … s5.md          五個範例的規格（報告出處、官方題材、三問、檔案與指令、完成定義、邊界案例、與 K903 差異）
s1-… ～ s5-…                  五個範例（尚未實作，依 specs 平行實作）
```

## 本專案例外

本專案是學習用教材（快速 demo 模式），豁免全域「程式碼三 agent 鐵律」：直接寫檔，不派 code-writer／code-qa／code-reviewer；不需詢問複雜度，也不需詢問是否使用快速模式。只跑一次冒煙測試（真模型跑一次＋`--dry-run`）。
`shared/` 三支共用工具改動後，要重跑 `PYTHONUTF8=1 python shared/<檔名>.py --selftest`。
