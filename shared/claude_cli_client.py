"""K904 轉接層（沿用 K902／K903 原版，環境變數名稱維持 K902_* 以便三個 repo 共用設定）：用 Claude Code 無頭模式（claude -p）模仿 anthropic SDK 的最小介面。

為什麼要有這支：官方 quickstarts 都寫成 `from anthropic import Anthropic` 再呼叫
`client.messages.create(...)`，原始做法要設 ANTHROPIC_API_KEY。本教材規定不設任何金鑰，
所以把那個呼叫換成 `claude -p` 子程序（走 Max 訂閱），讓演練仍然由真模型回答。

兩種用法：
1. 直接用：
       import claude_cli_client
       client = claude_cli_client.Anthropic()
       msg = client.messages.create(model="claude-sonnet-5-5", max_tokens=1024,
                                    system="...", messages=[...], tools=[...])
2. 讓只讀的官方模組改走轉接層：
       import claude_cli_client; claude_cli_client.install()
       from anthropic import Anthropic      # 拿到的是本轉接層

和真 API 的差異（講解時要照實說）：
  - 自訂工具（有 input_schema 的 client tool）是「用提示詞模擬」：工具定義寫進系統提示，
    請模型用 <tool_use>{...}</tool_use> 標記回覆，再解析成 tool_use block。模型是真的，
    但這不是 API 原生的 tool use，偶爾會不照格式（那時整段當成文字回傳）。
  - 伺服器端工具（web_search、code_execution、computer／browser toolset 等沒有 input_schema 的）忽略。
  - max_tokens、temperature、tool_choice、thinking、betas、extra_headers、cache_control 忽略。
  - model 參數預設不傳給 CLI（官方範例的模型名稱 CLI 不一定認得）；要指定就設 K902_CLI_MODEL。
  - 多輪 messages 攤平成一份逐字稿送進 stdin，每次呼叫都是一個全新的 claude -p 行程。
  - 沒有串流；count_tokens 只是用字數估算。

可調環境變數（都不是金鑰）：
  K902_CLI_MODEL      指定模型別名（例 haiku）
  K902_CLI_TIMEOUT    單次呼叫逾時秒數，預設 180
  K902_CLI_MAX_CALLS  單一行程最多呼叫幾次，預設 10（避免迴圈把演練拖很久）
"""
from __future__ import annotations

import json
import os
import re
import sys
import types
import uuid
from typing import Any

from llm_agent import run_claude

DEFAULT_MAX_CALLS = 10
TOOL_USE_PATTERN = re.compile(r"<tool_use>\s*(\{.*?\})\s*</tool_use>", re.DOTALL)
TOOL_PROTOCOL = """

# 工具
你可以呼叫下列工具。要呼叫工具時，為每一個呼叫輸出一段（JSON 必須合法、放在同一段標記內）：
<tool_use>{"name": "工具名稱", "input": {"參數名": "參數值"}}</tool_use>
規則：
- 標記前可以寫一句簡短說明；輸出標記後立刻停止，等待工具結果。
- 絕對不要自己編造工具結果，也不要輸出 <tool_result>。
- 不需要工具、或已經拿到足夠的工具結果時，直接用文字回答，不要輸出任何標記。
可用工具（JSON）：
"""

_call_count = 0


class APIError(Exception):
    """轉接層呼叫失敗（CLI 回錯、逾時、輸出無法解析、超過呼叫上限）。"""


class APIStatusError(APIError):
    pass


class APITimeoutError(APIError):
    pass


def _ns(**fields: Any) -> types.SimpleNamespace:
    return types.SimpleNamespace(**fields)


def _field(block: Any, name: str, default: Any = None) -> Any:
    """content block 可能是 dict（使用者組的）或物件（上一輪回傳的），統一取值。"""
    if isinstance(block, dict):
        return block.get(name, default)
    return getattr(block, name, default)


def _block_text(block: Any) -> str:
    """把一個 content block 轉成逐字稿裡的文字。"""
    if isinstance(block, str):
        return block
    block_type = _field(block, "type")
    if block_type == "text":
        return str(_field(block, "text", ""))
    if block_type == "tool_use":
        call = {"name": _field(block, "name", ""), "input": _field(block, "input", {})}
        return f"<tool_use>{json.dumps(call, ensure_ascii=False)}</tool_use>"
    if block_type == "tool_result":
        inner = _field(block, "content", "")
        if isinstance(inner, list):
            inner = "\n".join(_block_text(item) for item in inner)
        error_attr = ' is_error="true"' if _field(block, "is_error") else ""
        return f"<tool_result{error_attr}>\n{inner}\n</tool_result>"
    if block_type in ("thinking", "redacted_thinking"):
        return ""
    if block_type == "image":
        return "[圖片：轉接層不傳送圖片]"
    return json.dumps(block, ensure_ascii=False, default=str)


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    return "\n".join(text for text in (_block_text(block) for block in content or []) if text)


def flatten_messages(messages: list[dict[str, Any]]) -> str:
    """單一 user 訊息直接送；多輪則攤平成逐字稿，請模型接著回覆。"""
    if not messages:
        raise ValueError("messages 不可為空")
    if len(messages) == 1:
        return _content_text(messages[0].get("content", ""))
    lines = ["以下是到目前為止的對話紀錄（含工具呼叫與工具結果）。請以 assistant 身分接著回覆。", ""]
    for message in messages:
        role = message.get("role", "user")
        lines.append(f"<{role}>\n{_content_text(message.get('content', ''))}\n</{role}>")
    return "\n".join(lines)


def split_tools(tools: list[Any] | None) -> tuple[list[dict[str, Any]], list[str]]:
    """分出可以模擬的自訂工具，與要忽略的伺服器端工具名稱。"""
    client_tools: list[dict[str, Any]] = []
    ignored: list[str] = []
    for tool in tools or []:
        if isinstance(tool, dict) and "input_schema" in tool and "name" in tool:
            client_tools.append(
                {"name": tool["name"], "description": tool.get("description", ""), "input_schema": tool["input_schema"]}
            )
        else:
            ignored.append(str(_field(tool, "name") or _field(tool, "type") or tool))
    return client_tools, ignored


def system_text(system: Any, client_tools: list[dict[str, Any]]) -> str | None:
    """系統提示（字串或 block 清單）加上工具協定；兩者都沒有就回 None，用 llm_agent 的預設。"""
    base = _content_text(system) if system else ""
    if not client_tools:
        return base or None
    return (base or "You are a helpful assistant.") + TOOL_PROTOCOL + json.dumps(client_tools, ensure_ascii=False, indent=1)


def parse_reply(text: str, allowed_names: set[str]) -> list[types.SimpleNamespace]:
    """把模型回覆拆成 text／tool_use block；標記裡不是合法呼叫就整段保留成文字。"""
    blocks: list[types.SimpleNamespace] = []
    calls: list[types.SimpleNamespace] = []
    for match in TOOL_USE_PATTERN.finditer(text):
        try:
            call = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if not isinstance(call, dict) or call.get("name") not in allowed_names:
            continue
        tool_input = call.get("input")
        calls.append(
            _ns(type="tool_use", id="toolu_" + uuid.uuid4().hex[:16], name=call["name"],
                input=tool_input if isinstance(tool_input, dict) else {})
        )
    if not calls:
        return [_ns(type="text", text=text)]
    lead_text = TOOL_USE_PATTERN.sub("", text).strip()
    if lead_text:
        blocks.append(_ns(type="text", text=lead_text))
    return blocks + calls


def _max_calls() -> int:
    raw = os.environ.get("K902_CLI_MAX_CALLS")
    if raw is None or raw == "":
        return DEFAULT_MAX_CALLS
    try:
        return max(1, int(raw))
    except ValueError:
        print(f"[claude_cli_client] K902_CLI_MAX_CALLS={raw!r} 不是整數，改用 {DEFAULT_MAX_CALLS}", file=sys.stderr)
        return DEFAULT_MAX_CALLS


class _Messages:
    def create(self, *, model: str | None = None, messages: list[dict[str, Any]], system: Any = None,
               tools: list[Any] | None = None, max_tokens: int | None = None, **ignored: Any):
        """模仿 messages.create；ignored 收下 temperature、betas、extra_headers 等不支援的參數。"""
        global _call_count
        limit = _max_calls()
        if _call_count >= limit:
            raise APIError(f"已達本行程呼叫上限 K902_CLI_MAX_CALLS={limit}，停止以免演練拖太久")
        client_tools, ignored_tools = split_tools(tools)
        if ignored_tools:
            print(f"[claude_cli_client] 忽略伺服器端工具：{', '.join(ignored_tools)}", file=sys.stderr)
        prompt = flatten_messages(messages)
        _call_count += 1
        try:
            payload = run_claude(prompt, system=system_text(system, client_tools))
        except RuntimeError as exc:
            raise (APITimeoutError if "未回應" in str(exc) else APIStatusError)(str(exc)) from exc
        content = parse_reply(str(payload.get("result") or ""), {tool["name"] for tool in client_tools})
        has_tool_use = any(block.type == "tool_use" for block in content)
        usage_raw = payload.get("usage") or {}
        usage = _ns(
            input_tokens=usage_raw.get("input_tokens", 0),
            output_tokens=usage_raw.get("output_tokens", 0),
            cache_creation_input_tokens=usage_raw.get("cache_creation_input_tokens", 0),
            cache_read_input_tokens=usage_raw.get("cache_read_input_tokens", 0),
        )
        return _ns(
            id="msg_" + uuid.uuid4().hex[:16], type="message", role="assistant",
            model=os.environ.get("K902_CLI_MODEL") or model, content=content,
            stop_reason="tool_use" if has_tool_use else "end_turn", stop_sequence=None, usage=usage,
        )

    def count_tokens(self, *, messages: list[dict[str, Any]], system: Any = None, **ignored: Any):
        """粗估 token 數（每 4 個字元算 1 個）；CLI 沒有對應功能。"""
        total_chars = len(_content_text(system) if system else "") + len(flatten_messages(messages))
        return _ns(input_tokens=max(1, total_chars // 4))


class Anthropic:
    """模仿 anthropic.Anthropic；忽略 api_key 等參數（本來就不該有金鑰）。"""

    def __init__(self, *args: Any, **kwargs: Any):
        self.messages = _Messages()
        self.beta = _ns(messages=self.messages)


def calls_made() -> int:
    """回傳本行程已呼叫 claude -p 的次數（練習用來回報呼叫數）。"""
    return _call_count


def install() -> types.ModuleType:
    """把本模組註冊成 `anthropic`，之後 `from anthropic import Anthropic` 拿到轉接層。"""
    if os.environ.get("ANTHROPIC_API_KEY"):
        print("[claude_cli_client] 偵測到 ANTHROPIC_API_KEY：子程序會移除它，不會使用金鑰", file=sys.stderr)
    module = sys.modules[__name__]
    sys.modules["anthropic"] = module
    return module


def install_mcp_stub() -> bool:
    """沒裝 mcp 套件時，註冊空殼模組讓 `from mcp import ...` 不會失敗；回傳是否真的裝了空殼。

    用在第 3 章：官方 agents/utils/connections.py 一匯入就要 mcp，但只要 mcp_servers 是空清單，
    裡面的東西完全不會被呼叫。空殼不提供任何 MCP 功能，真的要連 MCP 伺服器仍需安裝官方套件。
    """
    import importlib.util

    if "mcp" in sys.modules or importlib.util.find_spec("mcp") is not None:
        return False

    def _unavailable(*args: Any, **kwargs: Any):
        raise RuntimeError("這是 K902 的 mcp 空殼，沒有 MCP 功能；請把 mcp_servers 設成空清單")

    stub = types.ModuleType("mcp")
    stub.ClientSession = _unavailable
    stub.StdioServerParameters = _unavailable
    client = types.ModuleType("mcp.client")
    sse = types.ModuleType("mcp.client.sse")
    sse.sse_client = _unavailable
    stdio = types.ModuleType("mcp.client.stdio")
    stdio.stdio_client = _unavailable
    stub.client, client.sse, client.stdio = client, sse, stdio
    sys.modules.update({"mcp": stub, "mcp.client": client, "mcp.client.sse": sse, "mcp.client.stdio": stdio})
    return True


def selftest() -> None:
    """離線檢查純函式（不呼叫模型）。"""
    assert flatten_messages([{"role": "user", "content": "hi"}]) == "hi"
    transcript = flatten_messages([
        {"role": "user", "content": "1+1?"},
        {"role": "assistant", "content": [_ns(type="tool_use", id="t1", name="add", input={"a": 1, "b": 1})]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "2"}]},
    ])
    assert '<tool_use>{"name": "add"' in transcript and "<tool_result>\n2\n</tool_result>" in transcript
    client_tools, ignored = split_tools([
        {"name": "add", "description": "加法", "input_schema": {"type": "object"}},
        {"type": "web_search_20250305", "name": "web_search"},
    ])
    assert [t["name"] for t in client_tools] == ["add"] and ignored == ["web_search"]
    assert system_text(None, []) is None and "可用工具" in system_text("你是助手", client_tools)
    blocks = parse_reply('我來算。<tool_use>{"name": "add", "input": {"a": 2, "b": 3}}</tool_use>', {"add"})
    assert [b.type for b in blocks] == ["text", "tool_use"] and blocks[1].input == {"a": 2, "b": 3}
    assert parse_reply("直接回答 5", {"add"})[0].text == "直接回答 5"
    # 邊界：工具名不在清單、JSON 壞掉，都要退回純文字，不可丟例外
    assert parse_reply('<tool_use>{"name": "rm", "input": {}}</tool_use>', {"add"})[0].type == "text"
    assert parse_reply("<tool_use>{壞掉}</tool_use>", {"add"})[0].type == "text"
    try:
        flatten_messages([])
    except ValueError:
        pass
    else:
        raise AssertionError("空 messages 應該丟 ValueError")
    print("selftest OK")


def live_test() -> None:
    """真的呼叫模型 2 次，跑完一個最小的工具迴圈：模型要求算乘法 → 程式算 → 模型講答案。"""
    tools = [{
        "name": "multiply", "description": "把兩個整數相乘，回傳乘積。",
        "input_schema": {"type": "object", "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
                         "required": ["a", "b"]},
    }]
    client = Anthropic()
    messages: list[dict[str, Any]] = [{"role": "user", "content": "請用 multiply 工具算 123 乘以 456，再用一句話告訴我答案。"}]
    first = client.messages.create(model="claude-sonnet-5-5", max_tokens=300, messages=messages, tools=tools)
    calls = [block for block in first.content if block.type == "tool_use"]
    print("第 1 次：stop_reason =", first.stop_reason, "｜工具呼叫 =", [(c.name, c.input) for c in calls])
    if not calls:
        raise SystemExit("模型沒有呼叫工具（提示詞模擬的工具呼叫偶爾會這樣），請重跑一次")
    results = [{"type": "tool_result", "tool_use_id": c.id, "content": str(int(c.input["a"]) * int(c.input["b"]))}
               for c in calls]
    messages += [{"role": "assistant", "content": first.content}, {"role": "user", "content": results}]
    second = client.messages.create(model="claude-sonnet-5-5", max_tokens=300, messages=messages, tools=tools)
    print("第 2 次：stop_reason =", second.stop_reason, "｜回覆 =", _content_text(second.content))
    print("呼叫次數 =", calls_made())


if __name__ == "__main__":
    try:
        selftest()
        if "--live" in sys.argv[1:]:
            live_test()
    except (APIError, ValueError, KeyError) as exc:
        print(f"錯誤：{exc}", file=sys.stderr)
        raise SystemExit(1)
