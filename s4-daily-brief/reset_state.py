"""清空 S4 的跨次狀態：刪掉 state/ 與 outbox/（對應官方 scripts/reset-state.sh）。runs/ 的 session 紀錄保留。

為什麼需要：書籤、帳本會讓第二次跑 day1 時「什麼都不報」；想從頭重做兩天份演練，就先清空。

用法（Git Bash，在 s4-daily-brief 目錄）：
    PYTHONUTF8=1 python reset_state.py             # 真的刪除
    PYTHONUTF8=1 python reset_state.py --dry-run   # 只列出會刪什麼
    PYTHONUTF8=1 python reset_state.py --selftest  # 在暫存資料夾測試
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
TARGETS = ("state", "outbox")


def reset(base: Path, dry_run: bool = False) -> list[str]:
    """只刪 base 底下的 state/、outbox/；路徑解析後不在 base 裡就拒絕（防止誤刪別處）。"""
    removed = []
    for name in TARGETS:
        target = (base / name).resolve()
        if target.parent != base.resolve():
            raise ValueError(f"拒絕刪除範例資料夾以外的路徑：{target}")
        if target.exists():
            count = sum(1 for p in target.rglob("*") if p.is_file())
            removed.append(f"{name}/（{count} 個檔）")
            if not dry_run:
                shutil.rmtree(target)
    return removed


def selftest() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="k904-s4-reset-"))
    try:
        (tmp / "state" / "runs").mkdir(parents=True)
        (tmp / "state" / "ledger.md").write_text("x", encoding="utf-8")
        (tmp / "runs").mkdir()
        assert reset(tmp, dry_run=True) == ["state/（1 個檔）"] and (tmp / "state").exists()
        assert reset(tmp) == ["state/（1 個檔）"] and not (tmp / "state").exists() and (tmp / "runs").exists()
        assert reset(tmp) == []
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("selftest OK")


def main() -> int:
    parser = argparse.ArgumentParser(description="清空 state/ 與 outbox/")
    parser.add_argument("--dry-run", action="store_true", help="只列出會刪什麼")
    parser.add_argument("--selftest", action="store_true", help="在暫存資料夾自我檢查")
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return 0
    try:
        removed = reset(HERE, args.dry_run)
    except (OSError, ValueError) as exc:
        print(f"錯誤：{exc}", file=sys.stderr)
        return 1
    verb = "會刪除" if args.dry_run else "已刪除"
    print(f"{verb}：{'、'.join(removed)}" if removed else "state/ 與 outbox/ 本來就是空的。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
