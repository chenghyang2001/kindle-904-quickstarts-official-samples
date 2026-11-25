"""K904 真實模型轉接腳本（沿用 K902／K903 原版，環境變數名稱維持 K902_*）：用 Claude Code 無頭模式（claude -p）回答提示詞。

為什麼用 claude -p：走 Max 訂閱，不需要也不可以設定任何 API 金鑰。
用法（在 shared 目錄）：
    命令列：  echo "你的提示詞" | PYTHONUTF8=1 python llm_agent.py           → 印出模型文字回覆
              echo "..." | PYTHONUTF8=1 python llm_agent.py --json         → 從回覆抽出第一個 JSON 物件並印出
              PYTHONUTF8=1 python llm_agent.py --selftest                  → 離線自我檢查（不呼叫模型）
    匯入：    from llm_agent import ask, ask_json   （腳本需在 shared 目錄執行，或把 shared 加進 PYTHONPATH）
規則：每個練習呼叫 claude -p 不超過 2 次，整章不超過 4 次。

可調環境變數（都不是金鑰）：
  K902_CLI_MODEL     指定模型別名（例 haiku、sonnet）；沒設就用 Claude Code 的預設模型
  K902_CLI_TIMEOUT   單次呼叫逾時秒數，預設 180
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_TIMEOUT_SECONDS = 180
DEFAULT_SYSTEM = "You are a helpful assistant. Answer the user's message directly."
# 金鑰（成本規定）與上層 Claude Code session 的狀態變數都不能傳給子程序
STRIP_ENV_EXACT = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDECODE")
STRIP_ENV_PREFIXES = ("CLAUDE_CODE_",)


def clean_env() -> dict[str, str]:
    """子程序環境：移除 API 金鑰與巢狀 session 變數，其餘（PATH、家目錄等登入要用的）保留。"""
    return {
        key: value
        for key, value in os.environ.items()
        if key not in STRIP_ENV_EXACT and not key.startswith(STRIP_ENV_PREFIXES)
    }


def timeout_seconds() -> int:
    """讀 K902_CLI_TIMEOUT；不是正整數就退回預設值並提示。"""
    raw = os.environ.get("K902_CLI_TIMEOUT")
    if raw is None or raw == "":
        return DEFAULT_TIMEOUT_SECONDS
    try:
        value = int(raw)
    except ValueError:
        value = 0
    if value <= 0:
        print(f"[llm_agent] K902_CLI_TIMEOUT={raw!r} 不是正整數，改用 {DEFAULT_TIMEOUT_SECONDS}", file=sys.stderr)
        return DEFAULT_TIMEOUT_SECONDS
    return value


def build_command(exe: str, system_file: str, model: str | None) -> list[str]:
    """組出 claude -p 指令。提示詞走 stdin、系統提示走檔案：Windows 的 claude.CMD 會截斷多行參數。"""
    cmd = [
        exe, "-p", "--output-format", "json",
        "--system-prompt-file", system_file,
        "--tools", "",                 # 不給任何內建工具：模型只能回文字，不會動到電腦
        "--restricted",                # 不讀使用者／專案設定與 hooks，演練結果不受個人設定影響
        "--strict-mcp-config",         # 不載入 MCP 伺服器
        "--disable-slash-commands",    # 不載入 skills
        "--no-session-persistence",    # 不在磁碟留 session 紀錄
    ]
    if model:
        cmd += ["--model", model]
    return cmd


def run_claude(prompt: str, system: str | None = None, model: str | None = None) -> dict:
    """呼叫一次 claude -p，回傳它的 JSON 輸出（含 result、usage、stop_reason）；失敗丟 RuntimeError。"""
    if not prompt or not prompt.strip():
        raise ValueError("prompt 是空的")
    exe = shutil.which("claude")
    if exe is None:
        raise RuntimeError("找不到 claude 指令（Claude Code CLI），請確認已安裝並在 PATH 中")
    chosen_model = model or os.environ.get("K902_CLI_MODEL") or None
    limit = timeout_seconds()
    # 在空的暫存夾啟動：不讀到任何專案的 CLAUDE.md，也不會把 .claude/ 寫進練習目錄
    work_dir = Path(tempfile.gettempdir()) / "k902-cli-cwd"
    work_dir.mkdir(exist_ok=True)
    fd, system_file = tempfile.mkstemp(prefix="k902-sys-", suffix=".txt")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(system or DEFAULT_SYSTEM)
        try:
            proc = subprocess.run(
                build_command(exe, system_file, chosen_model),
                input=prompt, capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=limit, env=clean_env(), cwd=str(work_dir), check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"claude -p 超過 {limit} 秒未回應") from exc
        except OSError as exc:
            raise RuntimeError(f"無法啟動 claude -p：{exc}") from exc
    finally:
        try:
            os.remove(system_file)
        except OSError:
            pass
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        detail = (proc.stderr or proc.stdout or "").strip()[:500]
        raise RuntimeError(f"claude -p 輸出不是 JSON（exit {proc.returncode}）：{detail}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"claude -p 輸出不是 JSON 物件：{proc.stdout[:300]}")
    if payload.get("is_error") or proc.returncode != 0:
        raise RuntimeError(f"claude -p 失敗（exit {proc.returncode}）：{str(payload.get('result'))[:500]}")
    return payload


def ask(prompt: str, system: str | None = None) -> str:
    """把 prompt 交給 claude -p，回傳模型的文字結果；失敗時丟出 RuntimeError。"""
    return str(run_claude(prompt, system=system).get("result", ""))


def extract_json(text: str) -> dict:
    """從模型回覆抽出第一個 JSON 物件（容許 ```json 程式碼區塊包裝）。"""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else None
    if candidate is None:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise ValueError(f"回覆中找不到 JSON 物件：{text[:200]}")
        candidate = text[start : end + 1]
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValueError(f"回覆裡的 JSON 無法解析：{candidate[:200]}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"回覆裡的 JSON 不是物件：{candidate[:200]}")
    return parsed


def ask_json(prompt: str, system: str | None = None) -> dict:
    """要求模型只回 JSON，並解析成 dict。"""
    return extract_json(ask(prompt + "\n\n只輸出一個 JSON 物件，不要任何其他文字。", system=system))


def selftest() -> None:
    """離線檢查：JSON 抽取、環境清理、指令組裝（不呼叫模型）。"""
    assert extract_json('前言 ```json\n{"tool": "patch_repo"}\n``` 後記') == {"tool": "patch_repo"}
    assert extract_json('{"a": 1}') == {"a": 1}
    for bad in ("沒有 JSON", "{壞掉}"):
        try:
            extract_json(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"應該丟 ValueError：{bad}")
    os.environ["CLAUDE_CODE_SELFTEST_DUMMY"] = "1"
    env = clean_env()
    os.environ.pop("CLAUDE_CODE_SELFTEST_DUMMY", None)
    assert not any(k in STRIP_ENV_EXACT or k.startswith(STRIP_ENV_PREFIXES) for k in env)
    cmd = build_command("claude", "sys.txt", "haiku")
    assert cmd[cmd.index("--tools") + 1] == "" and cmd[-2:] == ["--model", "haiku"]
    try:
        run_claude("   ")
    except ValueError:
        pass
    else:
        raise AssertionError("空提示詞應該丟 ValueError")
    print("selftest OK")


def main() -> int:
    if "--selftest" in sys.argv[1:]:
        selftest()
        return 0
    prompt = sys.stdin.read()
    try:
        if "--json" in sys.argv[1:]:
            print(json.dumps(ask_json(prompt), ensure_ascii=False, indent=2))
        else:
            print(ask(prompt))
    except (RuntimeError, ValueError) as exc:
        print(f"錯誤：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
