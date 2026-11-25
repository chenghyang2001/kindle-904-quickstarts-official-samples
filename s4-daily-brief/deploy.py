"""S4 排程部署（只印不做）：讀 deployment.json，印出 Windows schtasks、Linux cron 與官方 deployment 對照。

為什麼只支援 --dry-run：這是教材，看懂「排程＝每個工作日開一個新 session」即可；
真的建立排程會讓電腦每天自動呼叫模型，要不要開由使用者自己決定。
官方版是 Anthropic Managed Agents 的 scheduled deployment（ant apply，要 API 額度），本範例不呼叫。

用法（Git Bash，在 s4-daily-brief 目錄）：
    PYTHONUTF8=1 python deploy.py --dry-run
    PYTHONUTF8=1 python deploy.py --selftest
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEPLOYMENT_PATH = HERE / "agents" / "daily-brief" / "deployment.json"
CRON_DAYS = {"1-5": "MON,TUE,WED,THU,FRI", "*": "MON,TUE,WED,THU,FRI,SAT,SUN"}


def parse_cron(expression: str) -> dict:
    """只支援「固定時刻＋每天或週一到週五」的 cron，例如 32 7 * * 1-5。"""
    fields = expression.split()
    if len(fields) != 5:
        raise ValueError(f"cron 要 5 個欄位：{expression!r}")
    minute, hour, dom, month, dow = fields
    if not (minute.isdigit() and hour.isdigit()) or dom != "*" or month != "*" or dow not in CRON_DAYS:
        raise ValueError(f"本範例只支援固定時刻、每天或週一到週五：{expression!r}")
    return {"hhmm": f"{int(hour):02d}:{int(minute):02d}", "days": CRON_DAYS[dow]}


def load_deployment(path: Path = DEPLOYMENT_PATH) -> dict:
    try:
        deployment = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise SystemExit(f"錯誤：讀不到 {path}：{exc}") from exc
    try:
        deployment["_cron"] = parse_cron(deployment["schedule"]["expression"])
    except (KeyError, ValueError) as exc:
        raise SystemExit(f"錯誤：deployment.json 的 schedule 不合法：{exc}") from exc
    return deployment


def windows_command(dep: dict) -> str:
    # 路徑用 %USERPROFILE%，換電腦不用改；Git Bash 下要加 MSYS_NO_PATHCONV=1，否則 /Create 會被轉成路徑
    workdir = r"%USERPROFILE%\workspace\kindle-904-quickstarts-official-samples\s4-daily-brief"
    action = f'cmd /c "cd /d {workdir} && set PYTHONUTF8=1 && python run_session.py --day day1 >> runs\\schedule.log 2>&1"'
    return (f'MSYS_NO_PATHCONV=1 schtasks /Create /TN "{dep["task_name"]}" /SC WEEKLY /D {dep["_cron"]["days"]} '
            f'/ST {dep["_cron"]["hhmm"]} /TR \'{action}\' /F')


def cron_line(dep: dict) -> str:
    workdir = "$HOME/workspace/kindle-904-quickstarts-official-samples/s4-daily-brief"
    return (f'CRON_TZ={dep["schedule"]["timezone"]}\n{dep["schedule"]["expression"]} cd {workdir} && '
            'PYTHONUTF8=1 python3 run_session.py --day day1 >> runs/schedule.log 2>&1')


def print_plan(dep: dict) -> None:
    cron = dep["_cron"]
    print(f"[dry-run] 代理 {dep['agent']}：{dep['schedule']['timezone']} 每週 {cron['days']} {cron['hhmm']} 開一個新 session\n")
    print("Windows（Git Bash）建立排程：")
    print("  " + windows_command(dep))
    print(f'  查看：MSYS_NO_PATHCONV=1 schtasks /Query /TN "{dep["task_name"]}"')
    print(f'  刪除：MSYS_NO_PATHCONV=1 schtasks /Delete /TN "{dep["task_name"]}" /F\n')
    print("Linux／VPS（crontab -e 加入）：")
    print("  " + cron_line(dep).replace("\n", "\n  "))
    print("  （注意：本機 fixtures 只有 day1、day2 兩天，排程裡的 --day day1 只是示意；真要排程得先把來源換成真資料）\n")
    print(f"官方 deployment（{dep['official_deployment']}，ant apply 套用，要 API 額度，本範例不呼叫）：")
    print(f"  schedule: {{type: cron, expression: \"{dep['schedule']['expression']}\", "
          f"timezone: {dep['schedule'].get('official_timezone')}}}（本範例改 {dep['schedule']['timezone']}）")
    print(f"  resources: preferences → {dep['preferences_access']}、state → {dep['state_access']}"
          "（state 改 read_only 就是演習：不貼文、只把簡報放在最後訊息）")
    print(f"  首則訊息：{dep['first_message']}")
    print(f"  預算：{dep['budget_note']}")
    print("\n[dry-run] 沒有建立任何排程。")


def selftest() -> None:
    assert parse_cron("32 7 * * 1-5") == {"hhmm": "07:32", "days": "MON,TUE,WED,THU,FRI"}
    for bad in ("32 7 * *", "*/5 7 * * 1-5", "32 7 1 * *"):
        try:
            parse_cron(bad)
        except ValueError:
            continue
        raise AssertionError(f"應該拒絕：{bad}")
    dep = load_deployment()
    assert "/SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 07:32" in windows_command(dep)
    print("selftest OK")


def main() -> int:
    parser = argparse.ArgumentParser(description="印出排程指令（不建立排程）")
    parser.add_argument("--dry-run", action="store_true", help="只印出指令（本範例唯一支援的模式）")
    parser.add_argument("--selftest", action="store_true", help="離線自我檢查")
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return 0
    if not args.dry_run:
        print("本範例只支援 --dry-run：不會真的建立排程。請加上 --dry-run。", file=sys.stderr)
        return 2
    print_plan(load_deployment())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
