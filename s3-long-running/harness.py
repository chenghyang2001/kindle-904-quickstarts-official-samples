"""S3 兩階段自動寫程式 harness（官方 claude-quickstarts/autonomous-coding 縮小版，K904 官方題材）。

題材：官方 app_spec.txt（claude.ai 複製品）implementation_steps 第 3 步「Conversation Management」，
     只做資料層 chat_store.py（Python 標準庫 sqlite3），5 項功能 F1～F5。

第 1 階段：初始化代理讀 app_spec.txt，產出 feature_list.json（官方欄位）、tests/、init.sh；
          harness 寫 claude-progress.txt、harness_state.json，git init＋第一個 commit。
第 2 階段：寫程式代理每個 session 只做一項；harness 先跑 init.sh、重測已通過的功能（官方第 3 步），
          再請模型回 JSON（檔名＋內容），寫檔、跑測試、改 passes、commit 全由 harness 負責。
可續跑：狀態全在 workdir 的檔案與 git 裡，中斷後重跑同一條指令就接著做。

用法（Git Bash，在 s3-long-running 目錄）：
    PYTHONUTF8=1 python harness.py --selftest            # 離線檢查（不呼叫模型）
    PYTHONUTF8=1 python harness.py                       # 預設 --max-sessions 3 --max-calls 10
    PYTHONUTF8=1 python harness.py --max-sessions 6 --max-calls 10
    PYTHONUTF8=1 python harness.py --dry-run --workdir logs/dry-run-workdir   # 乾跑：假回覆，不呼叫模型
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "shared"))
# 寫程式 session 的回覆含整份 chat_store.py，比預設 180 秒容易超時
os.environ.setdefault("K902_CLI_TIMEOUT", "300")
from llm_agent import ask  # 要先把 shared 加進 sys.path 才能匯入，所以放在這裡

SPEC_FILE = HERE / "app_spec.txt"
DEFAULT_WORKDIR = HERE / "workdir"
DRY_WORKDIR = HERE / "logs" / "dry-run-workdir"
SNAPSHOT_DIR = HERE / "snapshot-5of5"
FEATURE_COUNT = 5
MAX_ATTEMPTS = 2           # 第一次＋重試 1 次，用完就 GAVE-UP
MAX_INIT_TRIES = 2         # 初始化回覆不合格時，在呼叫上限內再要求一次
TEST_TIMEOUT_SECONDS = 60
MAX_CONTEXT_CHARS = 40000  # 帶給模型的現有檔案總長上限
# 只有 harness 能寫的檔：清單、進度、狀態，以及 harness 自己複製進去的規格
HARNESS_OWNED = {"feature_list.json", "claude-progress.txt", "harness_state.json", "app_spec.txt", ".gitignore"}
SAFE_TEST_MODULE = re.compile(r"^tests(\.[A-Za-z0-9_]+)+$")
SHELL_META = re.compile(r"[;&|`$<>\\]")
GIT_ID = ["-c", "user.name=k904-harness", "-c", "user.email=harness@localhost"]

INIT_SYSTEM = "你是軟體專案的初始化代理（initializer agent）。你只輸出一個 JSON 物件，不輸出任何其他文字。"
CODE_SYSTEM = (
    "你是寫程式代理（coding agent）。這是全新的 context，你對之前的 session 沒有記憶，"
    "只能靠提示詞裡的 feature_list.json、claude-progress.txt 與 git log 接上進度。你只輸出一個 JSON 物件。"
)

AskFn = Callable[..., str]


class HarnessError(Exception):
    """harness 拒絕執行的情況（路徑跳脫、指令不在白名單、模型回覆格式錯、呼叫上限）。"""


class BudgetExhausted(HarnessError):
    """模型呼叫次數用完。"""


# ---------- 安全檢查：寫檔路徑、驗收指令、init.sh ----------

def safe_target(workdir: Path, rel_path: str, role: str) -> Path:
    """把模型給的相對路徑轉成 workdir 內的絕對路徑。

    role="init"：初始化代理只能寫 tests/ 與 init.sh；role="coding"：寫程式代理不能碰 tests/、init.sh。
    兩者都不能寫 .git/、harness 專屬檔、絕對路徑或跳出 workdir 的路徑。
    """
    if not rel_path or Path(rel_path).is_absolute() or ":" in rel_path or rel_path.startswith(("/", "\\")):
        raise HarnessError(f"不接受絕對路徑或空路徑：{rel_path!r}")
    root = workdir.resolve()
    target = (root / rel_path).resolve()
    if target != root and root not in target.parents:
        raise HarnessError(f"路徑跳出 workdir：{rel_path!r}")
    parts = target.relative_to(root).parts
    if not parts or parts[0] == ".git" or (len(parts) == 1 and parts[0] in HARNESS_OWNED):
        raise HarnessError(f"這個檔案只有 harness 能寫：{rel_path!r}")
    init_owned = parts[0] == "tests" or (len(parts) == 1 and parts[0] == "init.sh")
    if role == "coding" and init_owned:
        # 驗收測試由初始化代理寫好就鎖住，寫程式代理不能改測試讓自己過關
        raise HarnessError(f"寫程式代理不能修改 tests/ 或 init.sh：{rel_path!r}")
    if role == "init" and not init_owned:
        raise HarnessError(f"初始化代理只能寫 tests/ 與 init.sh：{rel_path!r}")
    return target


def parse_test_command(command: str, strict: bool = True) -> list[str]:
    """驗收指令白名單：只接受 `python -m unittest tests.<模組>`，回傳可直接執行的參數（不經 shell）。

    strict=False 時另外接受 `python -m unittest discover -s tests`（給 init.sh 用）。
    """
    if SHELL_META.search(command):
        raise HarnessError(f"指令含 shell 特殊字元：{command!r}")
    try:
        tokens = shlex.split(command)
    except ValueError as exc:
        raise HarnessError(f"指令解析失敗：{command!r}") from exc
    if tokens[:3] != ["python", "-m", "unittest"]:
        raise HarnessError(f"不在白名單（只接受 python -m unittest …）：{command!r}")
    args = tokens[3:]
    ok_modules = len(args) >= 1 and all(SAFE_TEST_MODULE.match(a) for a in args)
    if strict:
        ok = len(args) == 1 and ok_modules
    else:
        ok = ok_modules or args == ["discover", "-s", "tests"]
    if not ok:
        raise HarnessError(f"不在白名單：{command!r}")
    # 用執行 harness 的同一個 Python，避免 Windows 上 python 指向別的版本
    return [sys.executable, "-m", "unittest", *args]


def check_init_sh(text: str) -> list[tuple[str, list[str] | str]]:
    """逐行檢查 init.sh，每一行都通過白名單才回傳要做的動作；任何一行不合格就整份不執行。

    允許：空行、註解、shebang、set -e 類、echo 文字、python --version、python -m unittest（同一份白名單）。
    對照官方：init.sh 是 COMMANDS_NEEDING_EXTRA_VALIDATION 之一（security.py 第 44 行）。
    """
    actions: list[tuple[str, list[str] | str]] = []
    for no, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#") or re.fullmatch(r"set -[euxo pipefail]+", line):
            continue
        if SHELL_META.search(line):
            raise HarnessError(f"init.sh 第 {no} 行含 shell 特殊字元：{line!r}")
        if line == "echo" or line.startswith("echo "):
            try:
                words = shlex.split(line[4:])
            except ValueError as exc:
                raise HarnessError(f"init.sh 第 {no} 行解析失敗：{line!r}") from exc
            actions.append(("echo", " ".join(words)))
        elif line in ("python --version", "python3 --version"):
            actions.append(("run", [sys.executable, "--version"]))
        elif line.startswith(("python -m unittest", "python3 -m unittest")):
            actions.append(("run", parse_test_command(re.sub(r"^python3 ", "python ", line), strict=False)))
        else:
            raise HarnessError(f"init.sh 第 {no} 行不在白名單：{line!r}")
    return actions


def run_init_sh(workdir: Path) -> str:
    """harness 代跑 init.sh（不經 shell，逐行照白名單執行）；不合格只記錄，不影響已通過的功能。"""
    path = workdir / "init.sh"
    if not path.exists():
        return "（沒有 init.sh）"
    try:
        actions = check_init_sh(path.read_text(encoding="utf-8"))
    except HarnessError as exc:
        return f"init.sh 未執行：{exc}"
    out = []
    for kind, payload in actions:
        if kind == "echo":
            out.append(str(payload))
            continue
        try:
            proc = subprocess.run(payload, cwd=workdir, capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", timeout=TEST_TIMEOUT_SECONDS, check=False)
            text = (proc.stdout + proc.stderr).strip().splitlines()
            out.append(f"$ {' '.join(payload[1:])} → 結束碼 {proc.returncode}" + (f"｜{text[-1]}" if text else ""))
        except subprocess.TimeoutExpired:
            out.append(f"$ {' '.join(payload[1:])} → 超過 {TEST_TIMEOUT_SECONDS} 秒")
    return "\n".join(out) or "（init.sh 沒有可執行的行）"


def run_test(command: str, workdir: Path) -> tuple[bool, str]:
    """跑驗收測試（60 秒 timeout、不經 shell），回傳（是否通過, 輸出尾段）。"""
    argv = parse_test_command(command)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    try:
        proc = subprocess.run(argv, cwd=workdir, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=TEST_TIMEOUT_SECONDS, check=False, env=env)
    except subprocess.TimeoutExpired:
        return False, f"測試超過 {TEST_TIMEOUT_SECONDS} 秒"
    return proc.returncode == 0, (proc.stdout + proc.stderr).strip()[-2000:]


# ---------- 檔案、狀態與 git ----------

def git(workdir: Path, *args: str) -> str:
    """在 workdir 跑 git，失敗丟 HarnessError。"""
    try:
        proc = subprocess.run(["git", *GIT_ID, *args], cwd=workdir, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", check=False)
    except OSError as exc:
        raise HarnessError(f"無法執行 git：{exc}") from exc
    if proc.returncode != 0:
        raise HarnessError(f"git {' '.join(args)} 失敗：{proc.stderr.strip()[:300]}")
    return proc.stdout.strip()


def commit_all(workdir: Path, message: str) -> str:
    git(workdir, "add", "-A")
    git(workdir, "commit", "-q", "-m", message)
    return git(workdir, "rev-parse", "--short", "HEAD")


def atomic_write(path: Path, text: str) -> None:
    """先寫暫存檔再改名：中斷時不會留下寫一半的檔（官方陷阱 6）。"""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def load_features(workdir: Path) -> list[dict]:
    """feature_list.json 照官方格式是一個 JSON 陣列。"""
    data = json.loads((workdir / "feature_list.json").read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise HarnessError("feature_list.json 不是陣列")
    return data


def save_features(workdir: Path, features: list[dict]) -> None:
    atomic_write(workdir / "feature_list.json", json.dumps(features, ensure_ascii=False, indent=2) + "\n")


def load_state(workdir: Path) -> dict:
    """harness_state.json：每項的嘗試次數與上次錯誤（不放進清單，讓清單維持官方「只改 passes」的形狀）。"""
    path = workdir / "harness_state.json"
    if not path.exists():
        return {"features": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HarnessError(f"harness_state.json 壞了：{exc}") from exc


def save_state(workdir: Path, state: dict) -> None:
    atomic_write(workdir / "harness_state.json", json.dumps(state, ensure_ascii=False, indent=2) + "\n")


def fstate(state: dict, fid: str) -> dict:
    return state.setdefault("features", {}).setdefault(fid, {"attempts": 0, "last_error": None})


def append_progress(workdir: Path, session_no: int, title: str, body: str) -> None:
    with (workdir / "claude-progress.txt").open("a", encoding="utf-8") as handle:
        handle.write(f"\n## Session {session_no}：{title}\n\n{body.strip()}\n")


def next_session_no(workdir: Path) -> int:
    """session 編號從 claude-progress.txt 數出來，續跑時接著編。"""
    path = workdir / "claude-progress.txt"
    if not path.exists():
        return 1
    return len(re.findall(r"^## Session ", path.read_text(encoding="utf-8"), re.MULTILINE)) + 1


def write_files(workdir: Path, files: object, role: str) -> list[str]:
    """先全部檢查路徑再寫，任何一個不合法就整批不寫（邊界案例 3）。"""
    if not isinstance(files, list) or not files:
        raise HarnessError("模型回覆沒有 files 清單")
    planned = []
    for item in files:
        if not isinstance(item, dict) or not isinstance(item.get("content"), str):
            raise HarnessError(f"files 項目格式錯：{str(item)[:120]}")
        planned.append((safe_target(workdir, str(item.get("path", "")), role), item["content"]))
    for target, content in planned:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return [t.relative_to(workdir.resolve()).as_posix() for t, _ in planned]


def revert_files(workdir: Path, written: list[str]) -> None:
    """失敗的嘗試不留在工作區：已追蹤的檔還原成 HEAD，新檔刪掉（官方：結束前把程式庫留在乾淨狀態）。"""
    for rel in written:
        tracked = subprocess.run(["git", "ls-files", "--error-unmatch", rel], cwd=workdir,
                                 capture_output=True, check=False).returncode == 0
        if tracked:
            git(workdir, "checkout", "HEAD", "--", rel)
        else:
            (workdir / rel).unlink(missing_ok=True)


def snapshot_files(workdir: Path) -> str:
    """把 workdir 現有原始碼串成文字，讓全新 context 的模型看得到現況（清單、進度另外帶）。"""
    skip = {"feature_list.json", "claude-progress.txt", "harness_state.json", "app_spec.txt"}
    chunks, total = [], 0
    for path in sorted(workdir.rglob("*")):
        rel = path.relative_to(workdir).as_posix()
        if (not path.is_file() or rel.startswith(".git/") or "__pycache__" in rel or rel in skip
                or path.suffix in (".db", ".tmp", ".pyc")):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        total += len(text)
        if total > MAX_CONTEXT_CHARS:
            chunks.append(f"（其餘檔案省略：超過 {MAX_CONTEXT_CHARS} 字）")
            break
        chunks.append(f"--- {rel} ---\n{text}")
    return "\n".join(chunks)


# ---------- 模型呼叫 ----------

def parse_model_json(text: str) -> dict:
    """從回覆抽出第一個 JSON 物件；用 raw_decode，程式碼裡有大括號也不會切錯。"""
    start = text.find("{")
    if start == -1:
        raise HarnessError(f"模型回覆沒有 JSON：{text[:200]}")
    try:
        obj, _ = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError as exc:
        raise HarnessError(f"模型回覆的 JSON 解析失敗：{exc}") from exc
    if not isinstance(obj, dict):
        raise HarnessError("模型回覆的 JSON 不是物件")
    return obj


class CallBudget:
    """整次執行的模型呼叫上限（官方原版沒有上限，講義陷阱 3）。"""

    def __init__(self, limit: int, ask_fn: AskFn) -> None:
        self.limit, self.used, self.ask_fn = limit, 0, ask_fn

    def call(self, prompt: str, system: str) -> dict:
        if self.used >= self.limit:
            raise BudgetExhausted(f"已達模型呼叫上限 {self.limit} 次")
        self.used += 1
        try:
            return parse_model_json(self.ask_fn(prompt, system=system))
        except (RuntimeError, ValueError) as exc:
            raise HarnessError(f"模型呼叫失敗：{exc}") from exc


# ---------- 第 1 階段：初始化代理 ----------

INIT_PROMPT = """請讀下面的規格 app_spec.txt，產出 feature_list.json 的內容、驗收測試與 init.sh。

注意：官方原版要求至少 200 項，本縮小版**剛好 5 項**，就是規格 core_features 裡的 F1～F5，順序不變。

輸出 JSON 格式：
{{"features": [{{"id": "F1", "category": "functional", "description": "一句話說明這項功能與測試驗證什麼",
                 "steps": ["Step 1: ...", "Step 2: ...", "Step 3: ..."],
                 "test_command": "python -m unittest tests.test_f1"}}],
  "files": [{{"path": "tests/__init__.py", "content": ""}}, {{"path": "tests/test_f1.py", "content": "..."}},
            {{"path": "init.sh", "content": "..."}}],
  "progress_note": "給下一棒的交接筆記（做了什麼、建議先做哪一項）"}}

規則：
- features 剛好 5 項，id 依序 F1～F5；test_command 一律是 `python -m unittest tests.test_fN`，對應 tests/test_fN.py。
- 只寫 tests/ 底下的檔案與 init.sh，不要寫 chat_store.py（那是寫程式代理的工作）。
- 測試只用標準庫 unittest，`from chat_store import ChatStore, group_by_date`；資料庫用 ":memory:" 或 tempfile，
  時間一律明確傳 now=datetime(...)，不可依賴系統時鐘。測試要嚴格照規格 interface 的方法名、回傳 dict 鍵、例外型別與排序。
- F4 至少測：搜尋 "50%" 只命中字面含 50% 的對話、"_" 不當萬用字元、中文標題與訊息內容都搜得到、已刪除的不出現。
- F5 至少測：跨午夜（昨天 23:59 算 Yesterday）、剛好 7 天算 Previous 7 days、8 天算 Older、空的群組不出現。
- init.sh 每一行只能是：註解、`set -e`、`echo 文字`、`python --version`、`python -m unittest discover -s tests`；
  不能有其他指令，也不能用 ; | & $ > < 反引號 反斜線。

=== 規格 app_spec.txt ===
{spec}
"""


def validate_features(raw: object, files: object) -> list[dict]:
    """檢查初始化代理的清單：剛好 5 項、官方四欄位＋id、test_command 在白名單、測試檔有附上（邊界案例 1）。"""
    if not isinstance(raw, list) or len(raw) != FEATURE_COUNT:
        got = len(raw) if isinstance(raw, list) else type(raw).__name__
        raise HarnessError(f"features 必須剛好 {FEATURE_COUNT} 項，收到 {got}")
    paths = {str(f.get("path", "")) for f in files} if isinstance(files, list) else set()
    features = []
    for no, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            raise HarnessError(f"第 {no} 項不是物件")
        fid = str(item.get("id", ""))
        if fid != f"F{no}":
            raise HarnessError(f"第 {no} 項的 id 應是 F{no}，收到 {fid!r}")
        steps = item.get("steps")
        if not item.get("description") or not isinstance(steps, list) or not steps:
            raise HarnessError(f"{fid} 缺 description 或 steps")
        cmd = str(item.get("test_command", ""))
        parse_test_command(cmd)
        module_file = cmd.split()[-1].replace(".", "/") + ".py"
        if module_file not in paths:
            raise HarnessError(f"{fid} 的測試檔 {module_file} 沒有附在 files 裡")
        features.append({"id": fid, "category": str(item.get("category") or "functional"),
                         "description": str(item["description"]), "steps": [str(s) for s in steps],
                         "test_command": cmd, "passes": False})
    return features


def run_initializer(workdir: Path, budget: CallBudget) -> None:
    """初始化：最多要求 2 次；合格才寫檔，而且 feature_list.json 最後才寫（它存在＝初始化完成）。"""
    print("Session 1：初始化代理（讀 app_spec.txt → feature_list.json、tests/、init.sh）")
    prompt = INIT_PROMPT.format(spec=SPEC_FILE.read_text(encoding="utf-8"))
    reply, features = {}, []
    for attempt in range(1, MAX_INIT_TRIES + 1):
        reply = budget.call(prompt, INIT_SYSTEM)
        try:
            features = validate_features(reply.get("features"), reply.get("files"))
            break
        except HarnessError as exc:
            print(f"  初始化回覆第 {attempt} 次不合格，拒收：{exc}")
            if attempt == MAX_INIT_TRIES:
                raise HarnessError(f"初始化代理連續 {MAX_INIT_TRIES} 次不合格，停止") from exc
            prompt += f"\n\n上一次的回覆被拒收，原因：{exc}。請嚴格照規則重新輸出。\n"
    workdir.mkdir(parents=True, exist_ok=True)
    if not (workdir / ".git").exists():
        git(workdir, "init", "-q")
    # 跑測試會產生 __pycache__ 與暫存資料庫，不排除的話會被 commit 進去
    (workdir / ".gitignore").write_text("__pycache__/\n*.pyc\n*.db\n*.tmp\n", encoding="utf-8")
    shutil.copyfile(SPEC_FILE, workdir / "app_spec.txt")
    written = write_files(workdir, reply.get("files"), role="init")
    if not (workdir / "tests" / "__init__.py").exists():
        (workdir / "tests" / "__init__.py").write_text("", encoding="utf-8")
    # 初始化若曾中斷過，舊的進度檔不算數，從頭寫
    (workdir / "claude-progress.txt").write_text("# claude-progress.txt（每個 session 由 harness 追加）\n", encoding="utf-8")
    append_progress(workdir, 1, "初始化", f"寫入：{', '.join(written)}\n\n{reply.get('progress_note', '')}")
    save_state(workdir, {"features": {f["id"]: {"attempts": 0, "last_error": None} for f in features}})
    save_features(workdir, features)
    commit = commit_all(workdir, "Initial setup: feature_list.json, init.sh, and project structure（初始化）")
    print(f"  → 功能 {len(features)} 項：{', '.join(f['id'] for f in features)} → commit {commit}")


# ---------- 第 2 階段：寫程式代理 ----------

CODE_PROMPT = """這個 session 只做一項功能：{fid}（{desc}）。
驗收方式：harness 會在 workdir 執行 `{cmd}`，結束碼 0 才算通過；之後也會重跑所有已通過的功能，弄壞任何一項都算失敗。

輸出 JSON 格式：
{{"files": [{{"path": "chat_store.py", "content": "完整檔案內容"}}], "note": "給下一棒的交接筆記（一兩句）"}}

規則：
- 每個檔案都給完整內容（會整個覆蓋），路徑相對於 workdir。
- 不能修改 tests/、init.sh，也不能寫 feature_list.json、claude-progress.txt、harness_state.json、app_spec.txt。
- 只用 Python 標準庫；SQL 一律參數化。
{extra}
=== 規格 app_spec.txt ===
{spec}

=== feature_list.json ===
{features}

=== claude-progress.txt ===
{progress}

=== git log --oneline -20 ===
{log}

=== harness 代跑 init.sh 的結果 ===
{init_out}

=== workdir 現有檔案 ===
{files}
"""


def regression_check(workdir: Path, features: list[dict], state: dict) -> list[str]:
    """官方第 3 步：重測已通過的功能，壞了就把 passes 改回 false（邊界案例 4）。"""
    broken = []
    for feature in features:
        if not feature["passes"]:
            continue
        ok, output = run_test(feature["test_command"], workdir)
        if not ok:
            feature["passes"] = False
            fstate(state, feature["id"])["last_error"] = "回歸測試失敗：\n" + output[-1500:]
            broken.append(feature["id"])
    return broken


def pick_feature(features: list[dict], state: dict, broken: list[str]) -> dict | None:
    """先修回歸壞掉的，再挑第一項沒通過、嘗試未滿 2 次的功能。"""
    candidates = [f for f in features if f["id"] in broken] + features
    for feature in candidates:
        if not feature["passes"] and fstate(state, feature["id"])["attempts"] < MAX_ATTEMPTS:
            return feature
    return None


def build_code_prompt(workdir: Path, feature: dict, state: dict, init_out: str, broken: list[str]) -> str:
    extra = ""
    if broken:
        extra += f"- 回歸測試發現已通過的功能壞了：{', '.join(broken)}，這一輪先修好它。\n"
    last_error = fstate(state, feature["id"])["last_error"]
    if last_error:
        extra += f"- 上一次嘗試失敗，輸出如下，請針對它修正：\n```\n{last_error}\n```\n"
    return CODE_PROMPT.format(
        fid=feature["id"], desc=feature["description"], cmd=feature["test_command"], extra=extra,
        spec=SPEC_FILE.read_text(encoding="utf-8"),
        features=(workdir / "feature_list.json").read_text(encoding="utf-8"),
        progress=(workdir / "claude-progress.txt").read_text(encoding="utf-8"),
        log=git(workdir, "log", "--oneline", "-20"), init_out=init_out, files=snapshot_files(workdir))


def attempt_feature(workdir: Path, budget: CallBudget, feature: dict, features: list[dict],
                    prompt: str) -> tuple[bool, str, list[str], dict]:
    """請模型寫一次，跑目標測試＋其他已通過功能的測試；回傳（通過, 輸出, 寫入的檔, 回覆）。"""
    written: list[str] = []
    try:
        reply = budget.call(prompt, CODE_SYSTEM)
        written = write_files(workdir, reply.get("files"), role="coding")
        passed, output = run_test(feature["test_command"], workdir)
        if passed:
            for other in features:
                if other["passes"] and other is not feature:
                    ok, out = run_test(other["test_command"], workdir)
                    if not ok:
                        return False, f"{feature['id']} 通過但弄壞了 {other['id']}：\n{out}", written, reply
        return passed, output, written, reply
    except BudgetExhausted:
        raise
    except HarnessError as exc:
        return False, f"harness 拒絕：{exc}", written, {}


def run_coding(workdir: Path, budget: CallBudget, session_no: int) -> bool:
    """一個寫程式 session；回傳 False 表示沒有可做的功能了。"""
    features, state = load_features(workdir), load_state(workdir)
    init_out = run_init_sh(workdir)
    broken = regression_check(workdir, features, state)
    if broken:
        save_features(workdir, features)
        save_state(workdir, state)
        print(f"Session {session_no}：回歸測試發現 {', '.join(broken)} 壞了，passes 改回 false")
    feature = pick_feature(features, state, broken)
    if feature is None:
        if broken:
            append_progress(workdir, session_no, "回歸失敗", f"{', '.join(broken)} 壞了且已用完嘗試次數")
        return False
    st = fstate(state, feature["id"])
    tag = "（重試）" if st["attempts"] else ""
    print(f"Session {session_no}：處理功能 {feature['id']}{tag} {feature['description'][:70]}")
    prompt = build_code_prompt(workdir, feature, state, init_out, broken)
    passed, output, written, reply = attempt_feature(workdir, budget, feature, features, prompt)
    st["attempts"] += 1
    feature["passes"] = passed
    st["last_error"] = None if passed else output[-1500:]
    if not passed and written:
        revert_files(workdir, written)
    healed = []
    if passed:
        # 同一輪回歸壞掉的其他功能，修好目標後常常一起恢復；重測一次，不必再各花一次模型呼叫
        for other in features:
            if other["id"] in broken and other is not feature and run_test(other["test_command"], workdir)[0]:
                other["passes"] = True
                fstate(state, other["id"])["last_error"] = None
                healed.append(other["id"])
        if healed:
            print(f"  回歸壞掉的 {', '.join(healed)} 重測已恢復通過")
    result = "通過" if passed else ("失敗" if st["attempts"] < MAX_ATTEMPTS else "失敗，GAVE-UP")
    save_state(workdir, state)
    save_features(workdir, features)
    regress = f"\n\n回歸測試壞掉：{', '.join(broken)}" if broken else ""
    regress += f"；重測已恢復：{', '.join(healed)}" if healed else ""
    append_progress(workdir, session_no, f"{feature['id']} {result}",
                    f"寫入：{', '.join(written) or '（無）'}{regress}\n\n{reply.get('note', '')}")
    if passed:
        commit = commit_all(workdir, f"完成 {feature['id']}：{feature['description'][:80]}")
    else:
        commit = "（未 commit：失敗的檔案已還原，錯誤記在 harness_state.json，帶進下一次重試）"
        print("  測試輸出尾段：\n    " + output[-600:].replace("\n", "\n    "))
    print(f"  → 測試結果：{result} → commit {commit}")
    return True


# ---------- 外層迴圈 ----------

def mark_of(feature: dict, state: dict) -> str:
    if feature["passes"]:
        return "PASS"
    return "GAVE-UP" if fstate(state, feature["id"])["attempts"] >= MAX_ATTEMPTS else "TODO"


def print_summary(workdir: Path, budget: CallBudget) -> None:
    print(f"\n本次模型呼叫：{budget.used} 次（上限 {budget.limit}）")
    if not (workdir / "feature_list.json").exists():
        return
    features, state = load_features(workdir), load_state(workdir)
    print("== git log --oneline ==")
    print(git(workdir, "log", "--oneline"))
    done = sum(f["passes"] for f in features)
    print(f"== feature_list.json 狀態：{done}/{len(features)} ==")
    for f in features:
        print(f"  {f['id']:<3} {mark_of(f, state):<8} 嘗試 {fstate(state, f['id'])['attempts']} 次  {f['description'][:60]}")


def run(workdir: Path, max_sessions: int, max_calls: int, ask_fn: AskFn = ask) -> int:
    budget = CallBudget(max_calls, ask_fn)
    try:
        for _ in range(max_sessions):
            if not (workdir / "feature_list.json").exists():
                run_initializer(workdir, budget)
                continue
            if not run_coding(workdir, budget, next_session_no(workdir)):
                features = load_features(workdir)
                print(f"沒有可做的功能了：已完成 {sum(f['passes'] for f in features)}/{len(features)} 項")
                break
            if all(f["passes"] for f in load_features(workdir)):
                print(f"全部通過：{FEATURE_COUNT}/{FEATURE_COUNT}，停止（官方原版沒有這個判斷）")
                break
    except HarnessError as exc:
        print(f"停止：{exc}", file=sys.stderr)
        print_summary(workdir, budget)
        return 1
    print_summary(workdir, budget)
    return 0


# ---------- 乾跑：用快照當寫死的假回覆 ----------

def make_fake_ask(src: Path) -> AskFn:
    """乾跑用：初始化回快照的清單＋tests＋init.sh，寫程式回快照的 chat_store.py。不呼叫模型。"""
    if not (src / "chat_store.py").exists() or not (src / "feature_list.json").exists():
        raise HarnessError(f"乾跑需要 5/5 快照當假回覆來源，找不到 {src}/chat_store.py")

    def fake_ask(prompt: str, system: str | None = None) -> str:
        if system == INIT_SYSTEM:
            feats = json.loads((src / "feature_list.json").read_text(encoding="utf-8"))
            files = [{"path": "tests/" + p.name, "content": p.read_text(encoding="utf-8")}
                     for p in sorted((src / "tests").glob("*.py"))]
            files.append({"path": "init.sh", "content": (src / "init.sh").read_text(encoding="utf-8")})
            keys = ("id", "category", "description", "steps", "test_command")
            return json.dumps({"features": [{k: f[k] for k in keys} for f in feats], "files": files,
                               "progress_note": "（乾跑假筆記）"}, ensure_ascii=False)
        return json.dumps({"files": [{"path": "chat_store.py",
                                      "content": (src / "chat_store.py").read_text(encoding="utf-8")}],
                           "note": "（乾跑假筆記）"}, ensure_ascii=False)
    return fake_ask


# ---------- 離線自我檢查 ----------

def expect_error(fn: Callable[[], object], label: str) -> None:
    try:
        fn()
    except HarnessError:
        return
    raise AssertionError(f"應該擋下：{label}")


def selftest() -> None:
    """離線檢查安全規則與狀態處理（不呼叫模型）。"""
    wd = DEFAULT_WORKDIR
    assert safe_target(wd, "chat_store.py", "coding").name == "chat_store.py"
    assert safe_target(wd, "tests/test_f1.py", "init").name == "test_f1.py"
    for bad in ("../x.py", "/etc/passwd", "C:/x.py", ".git/config", "feature_list.json", "claude-progress.txt",
                "harness_state.json", "app_spec.txt", "tests/test_f1.py", "init.sh", "a/../../x.py"):
        expect_error(lambda b=bad: safe_target(wd, b, "coding"), bad)
    expect_error(lambda: safe_target(wd, "chat_store.py", "init"), "初始化代理寫 chat_store.py")
    assert parse_test_command("python -m unittest tests.test_f1")[1:] == ["-m", "unittest", "tests.test_f1"]
    for bad in ("rm -rf .", "python -c 'import os'", "python ../evil.py", "python -m pip install x",
                "python -m unittest tests.test_f1;rm", "bash -c ls", "python -m unittest discover -s tests",
                "python -m unittest ../x", "python -m unittest tests.test_f1 tests.test_f2"):
        expect_error(lambda b=bad: parse_test_command(b), bad)
    good_sh = "#!/bin/bash\nset -e\n# 說明\necho \"Chat store ready\"\npython --version\npython -m unittest discover -s tests\n"
    assert [k for k, _ in check_init_sh(good_sh)] == ["echo", "run", "run"]
    for bad in ("rm -rf /", "curl http://x", "echo hi > a.txt", "pip install x", "python -m unittest discover; ls",
                "cd ..", "echo $HOME"):
        expect_error(lambda b=bad: check_init_sh(b), bad)
    feat = {"category": "functional", "description": "d", "steps": ["s"]}
    five = [dict(feat, id=f"F{i}", test_command=f"python -m unittest tests.test_f{i}") for i in range(1, 6)]
    files = [{"path": f"tests/test_f{i}.py", "content": ""} for i in range(1, 6)]
    assert len(validate_features(five, files)) == 5 and validate_features(five, files)[0]["passes"] is False
    expect_error(lambda: validate_features(five[:4], files), "只有 4 項")
    expect_error(lambda: validate_features(five + five[:1], files), "6 項")
    expect_error(lambda: validate_features(five, files[:4]), "缺測試檔")
    assert parse_model_json('說明\n```json\n{"files": [{"path": "a.py", "content": "d = {1: 2}"}]}\n```')["files"]
    with tempfile.TemporaryDirectory() as tmp:
        tdir = Path(tmp)
        save_features(tdir, validate_features(five, files))
        assert load_features(tdir)[4]["id"] == "F5" and not (tdir / "feature_list.json.tmp").exists()
        state = load_state(tdir)
        fstate(state, "F1")["attempts"] = 2
        assert pick_feature(load_features(tdir), state, [])["id"] == "F2"
        assert pick_feature(load_features(tdir), state, ["F3"])["id"] == "F3"
        (tdir / "claude-progress.txt").write_text("# x\n\n## Session 1：初始化\n\n## Session 2：F1\n", encoding="utf-8")
        assert next_session_no(tdir) == 3
        budget = CallBudget(1, lambda p, system=None: '{"ok": 1}')
        assert budget.call("p", "s") == {"ok": 1}
        try:
            budget.call("p", "s")
        except BudgetExhausted:
            pass
        else:
            raise AssertionError("超過呼叫上限應該停")
    print("selftest 通過")


def main() -> int:
    parser = argparse.ArgumentParser(description="S3 兩階段自動寫程式 harness（claude -p，官方 autonomous-coding 縮小版）")
    parser.add_argument("--max-sessions", type=int, default=3, help="這次最多跑幾個 session（預設 3）")
    parser.add_argument("--max-calls", type=int, default=10, help="這次最多呼叫模型幾次（預設 10）")
    parser.add_argument("--workdir", type=Path, default=None, help="產出的專案資料夾（預設 workdir/）")
    parser.add_argument("--dry-run", action="store_true", help="乾跑：用 snapshot-5of5 當假回覆，不呼叫模型")
    parser.add_argument("--selftest", action="store_true", help="離線檢查，不呼叫模型")
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return 0
    if args.max_sessions < 1 or args.max_calls < 1:
        print("錯誤：--max-sessions 與 --max-calls 都要 >= 1", file=sys.stderr)
        return 2
    if not SPEC_FILE.exists():
        print(f"錯誤：找不到規格 {SPEC_FILE}", file=sys.stderr)
        return 2
    if args.dry_run:
        workdir = (args.workdir or DRY_WORKDIR).resolve()
        if workdir == DEFAULT_WORKDIR.resolve():
            print("錯誤：乾跑不能寫進真正的 workdir/，請改用 --workdir logs/dry-run-workdir", file=sys.stderr)
            return 2
        try:
            fake = make_fake_ask(SNAPSHOT_DIR)
        except HarnessError as exc:
            print(f"錯誤：{exc}", file=sys.stderr)
            return 2
        print(f"【乾跑模式】模型是寫死的假回覆（取自 snapshot-5of5），產出寫到 {workdir.name}；不算演練、不算完成。\n")
        return run(workdir, args.max_sessions, args.max_calls, fake)
    workdir = (args.workdir or DEFAULT_WORKDIR).resolve()
    return run(workdir, args.max_sessions, args.max_calls)


if __name__ == "__main__":
    sys.exit(main())
