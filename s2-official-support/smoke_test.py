"""S2 冒煙測試：背景啟動 server.py，打 4 個案例（3 次呼叫模型），測完一定關掉伺服器。

用法（Git Bash，在本資料夾）：
    PYTHONUTF8=1 python smoke_test.py               → 真模型，呼叫 3 次
    PYTHONUTF8=1 python smoke_test.py --dry-run     → 乾跑：伺服器用假回覆，只檢查路徑，不算完成
    PYTHONUTF8=1 python smoke_test.py --port 8914   → 換埠
輸出同時寫到 logs/smoke-<時間>.txt（logs/ 不進版控）。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
MOODS = ("positive", "neutral", "negative", "curious", "frustrated", "confused")
NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # 本機請求不要走系統代理


def user(text: str) -> dict:
    return {"role": "user", "content": text}


def check_kb_inside(status: int, body: dict) -> str | None:
    if status != 200 or not body.get("response"):
        return "應該 200 且有回答"
    if "billing" not in body.get("matched_categories", []):
        return "matched_categories 應含 billing"
    reason = body.get("redirect_to_agent", {}).get("reason")
    if reason is not None and not reason.strip():
        return "reason 存在時要有內容"
    return None


def check_redirect(status: int, body: dict) -> str | None:
    if status != 200 or body.get("redirect_to_agent", {}).get("should_redirect") is not True:
        return "應該 200 且 should_redirect=true"
    if body.get("user_mood") not in MOODS:
        return "user_mood 不在六值"
    return None


def check_400(status: int, body: dict) -> str | None:
    return None if status == 400 else "應該 400"


# （名稱, messages, 會不會呼叫模型, 檢查函式）
CASES = [
    ("知識庫內：退款", [user("我要怎麼申請退款？")], True, check_kb_inside),
    ("知識庫外：牛肉麵", [user("推薦我台北的牛肉麵")], True, check_redirect),
    ("多輪：明說要找真人", [user("我的帳號登不進去"), {"role": "assistant", "content": "請先確認登入信箱是否正確。"},
                          user("我試過了，我要跟真人講")], True, check_redirect),
    ("空字串", [user("   ")], False, check_400),
]


class Tee:
    """同時印到終端機與紀錄檔。"""

    def __init__(self, path: Path) -> None:
        LOG_DIR.mkdir(exist_ok=True)
        self.handle = path.open("w", encoding="utf-8")

    def __call__(self, text: str = "") -> None:
        print(text, flush=True)
        self.handle.write(text + "\n")


def post(url: str, messages: list[dict]) -> tuple[int, dict, dict]:
    """送 POST；4xx/5xx 也讀回 JSON 與標頭。"""
    data = json.dumps({"messages": messages}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with NO_PROXY.open(req, timeout=300) as res:
            return res.status, json.loads(res.read().decode("utf-8")), dict(res.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8")), dict(exc.headers)


def wait_ready(base_url: str, server: subprocess.Popen, seconds: int = 15) -> None:
    """輪詢首頁直到伺服器能回應；伺服器先死掉或逾時都丟 RuntimeError。"""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if server.poll() is not None:
            raise RuntimeError(f"伺服器啟動失敗（exit {server.returncode}），埠可能被佔用")
        try:
            with NO_PROXY.open(base_url + "/", timeout=2):
                return
        except (urllib.error.URLError, ConnectionError):
            time.sleep(0.5)
    raise RuntimeError("伺服器啟動逾時")


def run_cases(base_url: str, out: Tee) -> tuple[int, int]:
    """跑全部案例，回傳（失敗數, 送進模型的次數）。"""
    failures = calls = 0
    for label, messages, hits_model, check in CASES:
        started = time.monotonic()
        status, body, headers = post(base_url + "/api/chat", messages)
        calls += 1 if status != 400 else 0
        problem = check(status, body)
        failures += 1 if problem else 0
        out(f"[{'FAIL' if problem else 'PASS'}] {label}（{time.monotonic() - started:.1f} 秒）HTTP {status}"
            + (f"｜{problem}" if problem else ""))
        out("       " + json.dumps({k: v for k, v in body.items() if k != "rag_sources"}, ensure_ascii=False))
        if "rag_sources" in body:
            out("       rag_sources：" + json.dumps([(s["id"], s["score"]) for s in body["rag_sources"]]))
            out("       x-rag-sources 標頭（非 ASCII 已去除）前 100 字：" + headers.get("x-rag-sources", "")[:100])
        if hits_model != (status != 400):
            out("       ⚠ 呼叫模型與否和預期不同")
    return failures, calls


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8904)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    base_url = f"http://127.0.0.1:{args.port}"
    out = Tee(LOG_DIR / f"smoke-{datetime.now():%Y%m%d-%H%M%S}{'-dry' if args.dry_run else ''}.txt")
    if args.dry_run:
        out("【乾跑模式】伺服器用寫死的假回覆，不呼叫模型；只檢查路徑，不算完成。")
    cmd = [sys.executable, str(BASE_DIR / "server.py"), "--port", str(args.port)] + (["--dry-run"] if args.dry_run else [])
    server = subprocess.Popen(cmd, env={**os.environ, "PYTHONUTF8": "1"},
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8")
    calls = 0
    try:
        wait_ready(base_url, server)
        failures, calls = run_cases(base_url, out)
    except (RuntimeError, OSError, json.JSONDecodeError) as exc:
        out(f"錯誤：{exc}")
        failures = 1
    finally:
        server.terminate()   # 一定關掉，避免 8904 被殘留行程佔住
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
    kind = "乾跑假回覆" if args.dry_run else "真模型 claude -p"
    out(f"結果：{'全部通過' if failures == 0 else f'{failures} 項失敗'}（{kind} 呼叫 {0 if args.dry_run else calls} 次"
        + (f"，假回覆 {calls} 次" if args.dry_run else "") + "）")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
