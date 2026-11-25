"""K904 範例 S1：官方 Multi-Tool Agent（對應官方 claude-quickstarts 第 3 章 agents／agent_demo.ipynb）。

照官方 agents/agent.py 的形狀寫一個 Agent 類別（name、system、tools、run），工具迴圈是：
呼叫模型 → 取出 tool_use block → 執行工具 → 把 tool_result 當成 user 訊息加回 → 再呼叫模型，
直到模型這一輪沒有要工具。官方是 while True；本範例加了 --max-rounds 上限（K902 第 3 章陷阱 1）。

三個工具都照官方筆記本：think、calculator、brave_web_search。
- think：照 tools/think.py，只回 "Thinking complete!"。
- calculator：照 tools/calculator_mcp.py 的簽名、運算子與錯誤字串，但直接是 Python 函式，不走 MCP 協定
  （shared 轉接層沒有 MCP 功能）。
- brave_web_search：離線假搜尋，讀 data/search_fixture.json（逐字取自官方筆記本存檔的搜尋結果）。
  「用查詢字串比對存檔結果」是本教材的替代做法，官方未載明。

模型一律走 shared/claude_cli_client.py（claude -p，訂閱額度），不設任何 API 金鑰、不 mock 模型。
--dry-run 是唯一例外：用寫死的假回覆檢查程式路徑，畫面與紀錄都標 [dry-run]，不算演練。

用法（Git Bash，在 s1-multi-tool-agent/）：
    PYTHONUTF8=1 python multi_tool_agent.py "What's the square root of the OKC population in 2022"
    PYTHONUTF8=1 python multi_tool_agent.py --max-rounds 3 "<問題>"
    PYTHONUTF8=1 python multi_tool_agent.py --fix-prompt "<問題>"     # 系統提示改用正確工具名 calculator
    PYTHONUTF8=1 python multi_tool_agent.py --dry-run "<問題>"        # 不呼叫模型
    PYTHONUTF8=1 python multi_tool_agent.py --selftest                # 離線自我檢查
結束碼：0 有效答案｜1 模型呼叫失敗（逾時、超過 K902_CLI_MAX_CALLS）｜2 用法錯誤｜3 模型未給出有效答案
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
import types
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "shared"))
import claude_cli_client  # shared 轉接層要先把路徑加進來才匯入得到

FIXTURE_PATH = HERE / "data" / "search_fixture.json"
RUNS_DIR = HERE / "runs"
DEFAULT_MAX_ROUNDS = 6       # 官方 OKC 題存檔是 5 次模型呼叫，留 1 次餘裕
MODEL = "claude-sonnet-5-5"  # 官方筆記本的設定；轉接層預設不把它傳給 CLI（要換用 K902_CLI_MODEL）
MAX_TOKENS = 4096
DRY_TAG = "[dry-run]"

# 逐字照抄官方 agent_demo.ipynb 第 110～116 行（含 calculate 這個和實際工具名不一致的寫法）
OFFICIAL_SYSTEM_PROMPT = """
You are a helpful assistant with access to:
1. Web search (brave_web_search, brave_local_search)
2. Mathematical calculator (calculate)
3. A tool to think and reason (think)

Always use the most appropriate tool for each task.
"""
# --fix-prompt：只把工具名稱改成真的註冊名稱，並拿掉本範例沒提供的 brave_local_search
FIXED_SYSTEM_PROMPT = """
You are a helpful assistant with access to:
1. Web search (brave_web_search)
2. Mathematical calculator (calculator)
3. A tool to think and reason (think)

Always use the most appropriate tool for each task.
"""
LAST_ROUND_NOTE = (
    "（這是最後一輪：不能再使用任何工具。請只根據上面已經拿到的工具結果，直接用文字回答原本的問題；"
    "資料不足就照實說查不到，不要自己編數字。）"
)
NO_RESULT_TEXT = "No results found.（本範例只有官方筆記本存檔的搜尋資料：OKC 人口、GR86 行李廂、香蕉尺寸）"


# ───────────────────────── 工具本體（全部沒有副作用） ─────────────────────────

def think(thought: str) -> str:
    """照官方 tools/think.py：不做任何事，只回固定字串。"""
    return "Thinking complete!"


def calculator(number1: float, number2: float, operator: str) -> str:
    """照官方 tools/calculator_mcp.py 第 12～51 行：只接受 + - * / ^ sqrt 符號，錯誤回 Error 字串。"""
    try:
        # 官方靠 MCP（pydantic）把參數轉成 float；這裡沒有 MCP，自己轉，轉不了就丟例外給 execute_tools
        number1, number2 = float(number1), float(number2)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"number1／number2 必須是數字：{exc}") from exc
    try:
        if operator == "+":
            result = number1 + number2
        elif operator == "-":
            result = number1 - number2
        elif operator == "*":
            result = number1 * number2
        elif operator == "/":
            if number2 == 0:
                return "Error: Division by zero"
            result = number1 / number2
        elif operator == "^":
            result = number1 ** number2
        elif operator == "sqrt":
            if number1 < 0:
                return "Error: Cannot take square root of negative number"
            result = math.sqrt(number1)
        else:
            return f"Error: Unsupported operator '{operator}'"
        if isinstance(result, float) and result.is_integer():
            result = int(result)
        return f"Result: {result}"
    except (OverflowError, ArithmeticError) as exc:
        return f"Error: {exc}"


STOPWORDS = {"the", "of", "in", "a", "an", "and", "for", "what", "is", "how", "many", "to", "on", "by"}
# 每組存檔查詢的「主題詞」：查詢至少要命中一個主題詞才算同一題，避免「台北 2022 人口」被當成 OKC
SUBJECT_ALIASES = {"okc": "oklahoma", "bananas": "banana", "gr": "gr86", "86": "gr86"}
SUBJECT_WORDS = {"oklahoma", "toyota", "gr86", "banana"}


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {SUBJECT_ALIASES.get(w, w) for w in words if w not in STOPWORDS}


def load_fixture(path: Path = FIXTURE_PATH) -> list[dict[str, Any]]:
    """讀官方存檔的搜尋結果；檔案壞掉直接丟錯，讓使用者知道資料有問題。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"找不到搜尋資料：{path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"搜尋資料不是合法 JSON：{path}（{exc}）") from exc
    results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(results, list) or not results:
        raise ValueError(f"搜尋資料沒有 results 清單：{path}")
    return results


def brave_web_search(query: str, count: int = 10, *, fixture: list[dict[str, Any]] | None = None) -> str:
    """離線假搜尋：挑「主題詞相同、字詞重疊最多」的那組存檔查詢，照官方三行格式回傳。"""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query 不可為空")
    rows = fixture if fixture is not None else load_fixture()
    asked = _tokens(query)
    best_query, best_score = None, 0
    for stored in dict.fromkeys(r["query"] for r in rows):
        stored_tokens = _tokens(stored)
        if not (asked & stored_tokens & SUBJECT_WORDS):
            continue
        score = len(asked & stored_tokens)
        if score > best_score:
            best_query, best_score = stored, score
    if best_query is None:
        return NO_RESULT_TEXT
    try:
        limit = max(1, min(int(count), 20))
    except (TypeError, ValueError):
        limit = 10
    hits = [r for r in rows if r["query"] == best_query][:limit]
    return "\n\n".join(f"Title: {r['title']}\nDescription: {r['description']}\nURL: {r['url']}" for r in hits)


# 工具定義（給模型看的）＋執行函式。brave_web_search 的官方說明在 npm 套件裡，不在官方 repo，這裡的說明是本範例自寫的
TOOLS: dict[str, tuple[dict[str, Any], Callable[..., str]]] = {
    "think": ({
        "name": "think",
        "description": ("Use the tool to think about something. It will not obtain new information or change the "
                        "database, but just append the thought to the log. Use it when complex reasoning or some "
                        "cache memory is needed."),
        "input_schema": {"type": "object", "properties": {
            "thought": {"type": "string", "description": "A thought to think about."}}, "required": ["thought"]},
    }, think),
    "calculator": ({
        "name": "calculator",
        "description": ("Performs basic calculations with two numbers. operator: Operation symbol to perform "
                        "(+, -, *, /, ^, sqrt). Note: Only these exact symbols are supported, not words. "
                        "For sqrt, number2 is ignored."),
        "input_schema": {"type": "object", "properties": {
            "number1": {"type": "number", "description": "First number in the calculation"},
            "number2": {"type": "number", "description": "Second number in the calculation"},
            "operator": {"type": "string", "description": "Operation symbol to perform (+, -, *, /, ^, sqrt)"}},
            "required": ["number1", "number2", "operator"]},
    }, calculator),
    "brave_web_search": ({
        "name": "brave_web_search",
        "description": "Search the web. Returns up to 10 results, each as Title / Description / URL lines.",
        "input_schema": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Search query"},
            "count": {"type": "integer", "description": "Number of results (1-20, default 10)"}},
            "required": ["query"]},
    }, brave_web_search),
}


# ───────────────────────── 迴圈 ─────────────────────────

def _ns(**fields: Any) -> types.SimpleNamespace:
    return types.SimpleNamespace(**fields)


def execute_tools(tool_calls: list[Any], tools: dict[str, tuple[dict, Callable[..., str]]]) -> list[dict[str, Any]]:
    """照官方 utils/tool_util.py：找不到工具、執行丟例外，都變成 is_error 的 tool_result，迴圈不中斷。
    官方用 asyncio.gather 平行執行；這裡的工具都是瞬間完成的純函式，所以依序執行。"""
    results = []
    for call in tool_calls:
        response: dict[str, Any] = {"type": "tool_result", "tool_use_id": call.id}
        try:
            response["content"] = str(tools[call.name][1](**call.input))
        except KeyError:
            response["content"] = f"Tool '{call.name}' not found"
            response["is_error"] = True
        except Exception as exc:  # noqa: BLE001 —— 官方就是接住所有例外交還模型
            response["content"] = f"Error executing tool: {exc}"
            response["is_error"] = True
        results.append(response)
    return results


def recover_unknown_calls(text: str, known: set[str]) -> list[types.SimpleNamespace]:
    """轉接層只認得已註冊的工具名，其他名稱（例如照提示詞寫的 calculate）會被當成純文字。
    這裡把它們撿回來變成 tool_use，才能照官方回 "Tool 'calculate' not found" 讓模型自己改正。"""
    calls = []
    for match in claude_cli_client.TOOL_USE_PATTERN.finditer(text or ""):
        try:
            call = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(call, dict) and isinstance(call.get("name"), str) and call["name"] not in known:
            tool_input = call.get("input") if isinstance(call.get("input"), dict) else {}
            calls.append(_ns(type="tool_use", id="toolu_" + uuid.uuid4().hex[:16], name=call["name"], input=tool_input))
    return calls


def is_valid_answer(text: str) -> bool:
    """擋掉空答案、太短的答案、以及最後一輪還在寫工具呼叫標記的回覆。"""
    stripped = (text or "").strip()
    return len(stripped) >= 8 and "<tool_use>" not in stripped and "<tool_result" not in stripped


def calc_consistent(answer: str, calc_results: list[str]) -> bool | None:
    """答案裡的數字是否和最後一次成功的 calculator 結果一致（取整數部分比對）；沒用過 calculator 回 None。"""
    values = [m.group(1) for r in calc_results if (m := re.match(r"Result: (-?[\d.eE+]+)", r))]
    if not values:
        return None
    integer_part = str(int(float(values[-1])))
    return integer_part in (answer or "").replace(",", "")


def _first_line(text: str, width: int = 90) -> str:
    return (text or "").strip().splitlines()[0][:width] if (text or "").strip() else ""


class Agent:
    """照官方 agents/agent.py 的形狀：Agent(name, system, tools)，run(question)。"""

    def __init__(self, name: str, system: str, tools: dict[str, tuple[dict, Callable[..., str]]] | None = None,
                 client: Any = None, max_rounds: int = DEFAULT_MAX_ROUNDS, verbose: bool = True):
        if max_rounds < 1:
            raise ValueError("max_rounds 至少要 1")
        self.name, self.system, self.verbose = name, system, verbose
        self.tools = dict(tools if tools is not None else TOOLS)
        self.client = client or claude_cli_client.Anthropic()
        self.max_rounds = max_rounds

    def _say(self, text: str) -> None:
        if self.verbose:
            print(f"\n[{self.name}] {text}", flush=True)

    def _send(self, messages: list[dict[str, Any]], is_last: bool) -> Any:
        """最後一輪不給工具，並在最後一則 user 訊息後面附上「直接作答」的要求（只加在送出的副本上）。"""
        outgoing = list(messages)
        if is_last:
            last = dict(outgoing[-1])
            content = last["content"]
            note = {"type": "text", "text": LAST_ROUND_NOTE}
            last["content"] = (f"{content}\n\n{LAST_ROUND_NOTE}" if isinstance(content, str) else list(content) + [note])
            outgoing[-1] = last
        return self.client.messages.create(
            model=MODEL, max_tokens=MAX_TOKENS, system=self.system, messages=outgoing,
            tools=[] if is_last else [spec for spec, _ in self.tools.values()],
        )

    def run(self, question: str) -> dict[str, Any]:
        """跑工具迴圈，回傳紀錄 dict（answer、valid_answer、rounds、model_calls、error）。"""
        self._say(f"Received: {question}")
        messages: list[dict[str, Any]] = [{"role": "user", "content": question}]
        record: dict[str, Any] = {"answer": "", "valid_answer": False, "rounds": [], "model_calls": 0, "error": None}
        calc_results: list[str] = []
        for round_no in range(1, self.max_rounds + 1):
            is_last = round_no == self.max_rounds
            try:
                response = self._send(messages, is_last)
            except claude_cli_client.APIError as exc:
                record["error"] = str(exc)
                self._say(f"模型呼叫失敗（已完成 {round_no - 1} 輪）：{exc}")
                return record
            record["model_calls"] = round_no
            text = "\n".join(b.text for b in response.content if b.type == "text").strip()
            tool_calls = [b for b in response.content if b.type == "tool_use"]
            if not is_last:
                tool_calls += recover_unknown_calls(text, set(self.tools))
            step: dict[str, Any] = {"round": round_no, "last_round": is_last, "text_first_line": _first_line(text),
                                    "tool_calls": []}
            record["rounds"].append(step)
            if text:
                self._say(f"Output: {text if not tool_calls else _first_line(text, 200)}")
            messages.append({"role": "assistant", "content": response.content})
            if not tool_calls:
                record["answer"] = text
                record["valid_answer"] = is_valid_answer(text)
                record["calc_consistent"] = calc_consistent(text, calc_results)
                return record
            results = execute_tools(tool_calls, self.tools)
            for call, result in zip(tool_calls, results):
                self._say(f"Tool call: {call.name}({', '.join(f'{k}={v}' for k, v in call.input.items())})")
                lines = result["content"].splitlines()
                shown = "\n".join(lines[:3]) + (f"\n  …（共 {len(result['content'])} 字）" if len(lines) > 3 else "")
                self._say(f"Tool result{' [is_error]' if result.get('is_error') else ''}: {shown}")
                if call.name == "calculator" and not result.get("is_error"):
                    calc_results.append(result["content"])
                step["tool_calls"].append({
                    "name": call.name, "input": call.input, "is_error": bool(result.get("is_error")),
                    "result_chars": len(result["content"]), "result_first_line": _first_line(result["content"]),
                })
            messages.append({"role": "user", "content": results})
        return record  # 理論上到不了：最後一輪 tools=[]，不會再有 tool_use


# ───────────────────────── 乾跑、紀錄、命令列 ─────────────────────────

class DryRunClient:
    """--dry-run 專用：寫死「搜尋 → think → calculator → 回答」四步假回覆，不啟動 claude 子程序。"""

    SCRIPT: ClassVar[list[tuple[str | None, Any]]] = [
        ("brave_web_search", {"query": "Oklahoma City population 2022 census data"}),
        ("think", {"thought": f"{DRY_TAG} 假想法：用 696272 當 2022 年人口"}),
        ("calculator", {"number1": 696272, "number2": 0, "operator": "sqrt"}),
        (None, f"{DRY_TAG} 假答案（不是模型回的）：square root of 696,272 ≈ 834.43"),
    ]

    def __init__(self) -> None:
        self.calls = 0
        self.messages = self

    def create(self, **kwargs: Any) -> types.SimpleNamespace:
        name, payload = self.SCRIPT[min(self.calls, len(self.SCRIPT) - 1)]
        self.calls += 1
        if name is None or not kwargs.get("tools"):
            return _ns(content=[_ns(type="text", text=self.SCRIPT[-1][1])], stop_reason="end_turn")
        block = _ns(type="tool_use", id=f"toolu_dry{self.calls}", name=name, input=payload)
        return _ns(content=[_ns(type="text", text=f"{DRY_TAG} 第 {self.calls} 步"), block], stop_reason="tool_use")


def save_run(question: str, record: dict[str, Any], seconds: float, dry_run: bool, prompt_variant: str) -> Path:
    """紀錄存問題、每輪工具名稱與參數、結果長度與首行，不存搜尋結果全文（全文已在 data/ 裡）。"""
    RUNS_DIR.mkdir(exist_ok=True)
    out = RUNS_DIR / f"{datetime.now().astimezone():%Y%m%d-%H%M%S}{'-dry-run' if dry_run else ''}.json"
    full = {"mode": DRY_TAG if dry_run else "live", "question": question, "system_prompt": prompt_variant,
            "seconds": round(seconds, 1), **record}
    out.write_text(json.dumps(full, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def selftest() -> None:
    """離線檢查工具與迴圈（不呼叫模型）。"""
    assert calculator(696272, 0, "sqrt") == "Result: 834.4291461831855"
    assert calculator(6, 3, "/") == "Result: 2" and calculator(2, 10, "^") == "Result: 1024"
    assert calculator(1, 0, "/") == "Error: Division by zero"
    assert calculator(-4, 0, "sqrt") == "Error: Cannot take square root of negative number"
    assert calculator(4, 0, "square root") == "Error: Unsupported operator 'square root'"
    fixture = load_fixture()
    okc = brave_web_search("OKC population 2022", fixture=fixture)
    assert okc.startswith("Title: ") and "Oklahoma" in okc and okc.count("URL: ") == 10
    assert "GR86" in brave_web_search("Toyota GR86 trunk volume", fixture=fixture)
    assert brave_web_search("Taipei population 2022", fixture=fixture) == NO_RESULT_TEXT
    calls = [_ns(id="a", name="calculate", input={}), _ns(id="b", name="calculator", input={"number1": "x"})]
    bad = execute_tools(calls, TOOLS)
    assert bad[0]["content"] == "Tool 'calculate' not found" and bad[0]["is_error"]
    assert bad[1]["is_error"] and bad[1]["content"].startswith("Error executing tool:")
    found = recover_unknown_calls('<tool_use>{"name": "calculate", "input": {"a": 1}}</tool_use>', set(TOOLS))
    assert [c.name for c in found] == ["calculate"]
    assert not is_valid_answer("  ") and not is_valid_answer('<tool_use>{"name":"think"}</tool_use>')
    assert calc_consistent("about 834.43", ["Result: 834.4291461831855"]) is True
    assert calc_consistent("about 900", ["Result: 834.43"]) is False and calc_consistent("x", []) is None
    record = Agent("selftest", OFFICIAL_SYSTEM_PROMPT, client=DryRunClient(), verbose=False).run("q")
    assert record["valid_answer"] and record["model_calls"] == 4 and record["calc_consistent"] is True
    capped = Agent("selftest", OFFICIAL_SYSTEM_PROMPT, client=DryRunClient(), max_rounds=2, verbose=False).run("q")
    assert capped["model_calls"] == 2 and capped["rounds"][-1]["last_round"]
    print("selftest OK")


def main() -> int:
    parser = argparse.ArgumentParser(description="官方 Multi-Tool Agent（think、calculator、離線 brave_web_search），模型走 claude -p")
    parser.add_argument("question", nargs="*", help="要問的問題（英文照官方原題即可）")
    parser.add_argument("--max-rounds", type=int, default=DEFAULT_MAX_ROUNDS, help=f"最多幾次模型呼叫（預設 {DEFAULT_MAX_ROUNDS}）")
    parser.add_argument("--dry-run", action="store_true", help="用寫死的假回覆走一遍，不呼叫模型")
    parser.add_argument("--fix-prompt", action="store_true", help="系統提示改用正確工具名 calculator")
    parser.add_argument("--selftest", action="store_true", help="離線自我檢查")
    opts = parser.parse_args()
    if opts.selftest:
        selftest()
        return 0
    question = " ".join(opts.question).strip()
    if not question or opts.max_rounds < 1:
        parser.print_usage(sys.stderr)
        print("錯誤：問題不可為空，--max-rounds 至少要 1", file=sys.stderr)
        return 2
    if opts.dry_run:
        print(f"{DRY_TAG} 乾跑模式：模型是寫死的假回覆，只檢查程式路徑，不算演練。")
    agent = Agent("Multi-Tool Agent", FIXED_SYSTEM_PROMPT if opts.fix_prompt else OFFICIAL_SYSTEM_PROMPT,
                  client=DryRunClient() if opts.dry_run else None, max_rounds=opts.max_rounds)
    started = time.time()
    record = agent.run(question)
    seconds = time.time() - started
    log = save_run(question, record, seconds, opts.dry_run, "fixed" if opts.fix_prompt else "official")
    print("\n=== 答案 ===")
    print(record["answer"] if record["valid_answer"] else "模型未給出有效答案")
    print(f"\n模型呼叫 {record['model_calls']} 次（上限 {opts.max_rounds}）｜有效答案：{record['valid_answer']}"
          f"｜答案與 calculator 一致：{record.get('calc_consistent')}｜耗時 {seconds:.1f} 秒"
          f"{'｜' + DRY_TAG if opts.dry_run else ''}")
    print(f"紀錄：s1-multi-tool-agent/runs/{log.name}")
    if record["error"]:
        print(f"錯誤：{record['error']}", file=sys.stderr)
        return 1
    return 0 if record["valid_answer"] else 3


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, ValueError) as exc:
        print(f"錯誤：{exc}", file=sys.stderr)
        raise SystemExit(1)
