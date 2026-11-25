"""K904 導讀小工具（沿用 K902／K903 原版）：只讀方式查看官方 claude-quickstarts 原始碼（帶行號），不執行、不修改。

用法（在 shared 目錄）：
    PYTHONUTF8=1 python qs_source.py autonomous-coding/agent.py            → 印出整個檔
    PYTHONUTF8=1 python qs_source.py autonomous-coding/agent.py 140 180    → 只印第 140～180 行
    PYTHONUTF8=1 python qs_source.py --grep autonomous-coding/agent.py "is_first_run"
    PYTHONUTF8=1 python qs_source.py --selftest                            → 離線自我檢查
匯入：
    from qs_source import root, read_text, grep

官方 repo 位置預設是 ~/workspace/claude-quickstarts，可用環境變數 K902_QUICKSTARTS_DIR 改。
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path


def root() -> Path:
    """回傳官方 repo 根目錄；不存在就丟 FileNotFoundError 並說明怎麼取得。"""
    override = os.environ.get("K902_QUICKSTARTS_DIR")
    base = Path(override).expanduser() if override else Path.home() / "workspace" / "claude-quickstarts"
    if not base.is_dir():
        raise FileNotFoundError(
            f"找不到官方 repo：{base}\n"
            "請先執行：git clone https://github.com/anthropics/claude-quickstarts ~/workspace/claude-quickstarts"
        )
    return base


def resolve(rel_path: str) -> Path:
    """把相對路徑接到官方 repo 底下；擋掉跳出 repo 的路徑。"""
    base = root().resolve()
    target = (base / rel_path).resolve()
    if base != target and base not in target.parents:
        raise ValueError(f"路徑超出官方 repo 範圍：{rel_path}")
    if not target.is_file():
        raise FileNotFoundError(f"官方 repo 裡沒有這個檔：{rel_path}")
    return target


def read_text(rel_path: str) -> str:
    """讀官方 repo 裡的一個文字檔（UTF-8，讀不懂的位元組用替代字元）。"""
    return resolve(rel_path).read_text(encoding="utf-8", errors="replace")


def grep(rel_path: str, pattern: str) -> list[tuple[int, str]]:
    """回傳符合正規表示式的 (行號, 該行文字) 清單，行號從 1 開始。"""
    regex = re.compile(pattern)
    return [(number, line) for number, line in enumerate(read_text(rel_path).splitlines(), 1) if regex.search(line)]


def show(rel_path: str, start: int = 1, end: int | None = None) -> None:
    """印出檔案的一段，帶行號。"""
    lines = read_text(rel_path).splitlines()
    if start < 1 or (end is not None and end < start):
        raise ValueError(f"行號範圍不合理：{start}～{end}")
    last = min(end or len(lines), len(lines))
    print(f"── {rel_path}（第 {start}～{last} 行，共 {len(lines)} 行）")
    for number in range(start, last + 1):
        print(f"{number:5d}  {lines[number - 1]}")


def selftest() -> None:
    """只檢查路徑防護與參數檢查；官方 repo 不在時也能跑。"""
    try:
        base = root()
    except FileNotFoundError as exc:
        print(f"selftest：略過讀檔檢查（{str(exc).splitlines()[0]}）")
        return
    assert (base / "README.md").is_file(), "官方 repo 應該有 README.md"
    assert read_text("README.md").strip(), "README.md 不應該是空的"
    for bad in ("../outside.txt", "no-such-file.xyz"):
        try:
            resolve(bad)
        except (ValueError, FileNotFoundError):
            pass
        else:
            raise AssertionError(f"應該被擋下：{bad}")
    assert grep("README.md", r"^# "), "README.md 應該有一級標題"
    print("selftest OK")


def main(argv: list[str]) -> int:
    try:
        if argv[:1] == ["--selftest"]:
            selftest()
        elif argv[:1] == ["--grep"] and len(argv) == 3:
            for number, line in grep(argv[1], argv[2]):
                print(f"{number:5d}  {line}")
        elif len(argv) == 1:
            show(argv[0])
        elif len(argv) == 3:
            show(argv[0], int(argv[1]), int(argv[2]))
        else:
            print(__doc__)
            return 2
    except (FileNotFoundError, ValueError, re.error) as exc:
        print(f"錯誤：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
