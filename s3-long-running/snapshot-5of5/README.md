# snapshot-5of5：S3 workdir 的 5/5 完成版快照

## 這是什麼

`s3-long-running/workdir/` 是 harness 產出的資料夾，本身是獨立的 git repo，外層 `.gitignore` 排除了它（`*/workdir/`），所以換電腦 clone 之後不會有 workdir。

這個資料夾是 2026-11-25 真模型（`claude -p`）兩次執行跑出來的 5/5 完成版（workdir 的 HEAD 是 `dbbd407`），去掉 `.git/` 與 `__pycache__/` 之後的工作樹。用途有兩個：

1. 新電腦**不呼叫模型**也能演練 S3 的第 3、4、7 步與 `restore`。
2. `harness.py --dry-run` 拿它當寫死的假回覆來源（初始化回這裡的清單、tests、init.sh，寫程式回這裡的 `chat_store.py`）。

| 檔案 | 用途 |
| --- | --- |
| `app_spec.txt`、`feature_list.json`、`claude-progress.txt`、`init.sh`、`chat_store.py`、`tests/`、`harness_state.json`、`.gitignore` | workdir 工作樹的原樣複本 |
| `git-log.txt` | 原本 workdir 的 `git log --oneline`（6 個 commit：初始化＋F1～F5 各一）。重建出來的 workdir 只有 1 個 commit，第 3 步會改顯示這份 |
| `README.md` | 本說明（重建時不會複製進 workdir） |

## 怎麼還原

在 `practice/interactive/` 底下：

```bash
bash s3.sh seed
```

它會把本資料夾的檔案（`README.md`、`git-log.txt` 除外）複製成 `s3-long-running/workdir/`，`git init`，再用一個 commit 提交，訊息是「從 snapshot-5of5 重建…」。

- workdir 已經存在時什麼都不做，只印提示。
- 不跑 seed 也可以：第 3、4、7 步與 `restore` 發現 workdir 和 `workdir.bak-5of5` 都不存在時會自動重建。

## 跟原本 workdir 的差別

- git 歷史只有 1 個 commit，原本的 6 個 commit 只留在 `git-log.txt`，不能 `git checkout` 回到中間的存檔點。
- 其他檔案內容相同。Windows 上 git 的換行轉換（`core.autocrlf`）可能讓換行字元不同，不影響執行與測試。
