"""S5 瀏覽器工具組：Playwright 無頭 Chromium，動作名稱照官方 browser toolset。

官方 browser-toolset（K902 第 4 章）的動作：navigate、read_page（每個元素帶 ref_N）、left_click、
get_page_text、wait；本範例只實作這題用得到的五個：navigate／read_page／get_page_text／left_click／screenshot。
- 元素編號寫在頁面的 data-ref 屬性上，換頁就失效（對應官方 README「點擊觸發換頁後，下一次讀取可能讀到舊頁」）。
- 白名單照官方 example policy 的做法：只比對主機字串，所以 localhost 與 127.0.0.1 是兩個不同主機。
- left_click 只收 ref_N，不收座標；screenshot 只存檔給人看，不回傳給模型。

同檔附練習網站伺服器 PracticeSite（http.server，只綁 127.0.0.1）。
用法：PYTHONUTF8=1 python browser_tools.py --selftest   （不開瀏覽器、不呼叫模型，只測白名單與 ref 解析）
"""
from __future__ import annotations

import functools
import re
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urljoin, urlparse

MAX_TEXT_CHARS = 1500  # 沿用 K903：可見文字截斷上限，避免整頁塞給模型
INSTALL_HINT = "python -m pip install playwright && python -m playwright install chromium"
# 為什麼加 h1～h3：官方 read_page 回「headings、links、buttons、form controls」，標題也給 ref
MARK_ELEMENTS_JS = """
() => {
  document.querySelectorAll('[data-ref]').forEach((el) => el.removeAttribute('data-ref'));
  const sel = 'h1, h2, h3, a, button, input, select, textarea';
  const out = [];
  document.querySelectorAll(sel).forEach((el) => {
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) return;
    const ref = 'ref_' + (out.length + 1);
    el.setAttribute('data-ref', ref);
    const label = (el.innerText || el.value || el.placeholder || el.name || '').trim();
    out.push({ref, tag: el.tagName.toLowerCase(), label: label.slice(0, 90), href: el.getAttribute('href') || ''});
  });
  return out;
}
"""
REF_PATTERN = re.compile(r"^ref_(\d+)$")


class ToolError(Exception):
    """工具執行失敗：訊息原樣回給模型（對應官方 tool_result 的 is_error），讓它自己修正。"""


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        # 為什麼關掉：每個請求都印一行會淹沒「第 N 步」的輸出
        return


class PracticeSite:
    """在背景執行緒啟動練習網站。

    port=0 讓作業系統挑空的埠：K903 S5 也是 port=0，兩邊同時跑也不會拿到同一個埠；
    指定的埠被占用時，自動改用作業系統挑的下一個空埠。
    """

    def __init__(self, root: Path, port: int = 0):
        if not root.is_dir():
            raise FileNotFoundError(f"找不到練習網站資料夾：{root}")
        handler = functools.partial(_QuietHandler, directory=str(root))
        try:
            self.server = ThreadingHTTPServer(("127.0.0.1", port), handler)
        except OSError:
            print(f"埠 {port} 被占用，改用作業系統挑的空埠", file=sys.stderr)
            self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def host(self) -> str:
        host, port = self.server.server_address[:2]
        return f"{host}:{port}"

    @property
    def base_url(self) -> str:
        return f"http://{self.host}/"

    def __enter__(self) -> PracticeSite:
        self.thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self.server.shutdown()
        self.server.server_close()


def check_url(url: str, allowed_hosts: set[str]) -> None:
    """白名單政策：放行就什麼都不做，不放行就丟 ToolError。

    只比對 scheme 與主機字串（含埠），和官方 example policy 一樣不做 DNS 解析，
    所以 http://localhost:<埠>/ 指向同一台機器也會被擋。
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or parsed.netloc not in allowed_hosts:
        raise ToolError(f"網址不在白名單，拒絕前往：{url}（只允許 {sorted(allowed_hosts)}）")


def parse_ref(ref: object) -> str:
    """只收 ref_N 字串；座標、數字、空值一律拒絕（本範例刻意不給座標點擊）。"""
    text = str(ref or "").strip()
    if not REF_PATTERN.match(text):
        raise ToolError(f"left_click 只接受 ref_N（例如 ref_3），收到：{ref!r}；本範例不支援座標點擊")
    return text


class BrowserTools:
    """五個瀏覽器工具。allowed_hosts 是白名單，只放行這些 host:port。"""

    def __init__(self, allowed_hosts: set[str], shot_dir: Path):
        try:
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(f"沒有安裝 Playwright，請先執行：{INSTALL_HINT}") from exc
        self._pw_error = PlaywrightError
        self.allowed_hosts = allowed_hosts
        self.shot_dir = shot_dir
        self._pw = sync_playwright().start()
        try:
            self._browser = self._pw.chromium.launch(headless=True)
        except PlaywrightError as exc:
            self._pw.stop()
            raise RuntimeError(f"無法啟動 Chromium，請先執行：{INSTALL_HINT}（{str(exc).splitlines()[0]}）") from exc
        self.page = self._browser.new_page(viewport={"width": 1000, "height": 760})

    def close(self) -> None:
        try:
            self._browser.close()
        finally:
            self._pw.stop()

    def navigate(self, url: str) -> str:
        check_url(url, self.allowed_hosts)
        try:
            self.page.goto(url, wait_until="load", timeout=10_000)
        except self._pw_error as exc:
            raise ToolError(f"開啟失敗：{str(exc).splitlines()[0]}") from exc
        return f"已開啟 {self.page.url}（標題：{self.page.title()}）"

    def read_page(self) -> str:
        """標題、連結、按鈕、表單元件，每個帶 ref_N；不含整頁文字（那是 get_page_text 的事）。"""
        elements = self.page.evaluate(MARK_ELEMENTS_JS)
        lines = [f"網址：{self.page.url}", f"標題：{self.page.title()}", "元素："]
        lines += [f"[{e['ref']}] <{e['tag']}> {e['label']}" + (f"  (href={e['href']})" if e["href"] else "")
                  for e in elements]
        return "\n".join(lines)

    def get_page_text(self) -> str:
        text = self.page.inner_text("body").strip()
        cut = "" if len(text) <= MAX_TEXT_CHARS else f"\n（已截斷，原長 {len(text)} 字）"
        return f"網址：{self.page.url}\n可見文字：\n{text[:MAX_TEXT_CHARS]}{cut}"

    def left_click(self, ref: object) -> str:
        ref_id = parse_ref(ref)
        loc = self.page.locator(f"[data-ref='{ref_id}']")
        if loc.count() == 0:
            raise ToolError(f"元素編號已失效，請重新 read_page（找不到 {ref_id}，可能已換頁）")
        target = loc.first
        href = target.get_attribute("href")
        if href:
            # 點連結前也過白名單：避免模型繞過 navigate 直接點到外站
            check_url(urljoin(self.page.url, href), self.allowed_hosts)
        try:
            target.click(timeout=5_000)
            self.page.wait_for_load_state("load")
        except self._pw_error as exc:
            raise ToolError(f"點擊失敗：{str(exc).splitlines()[0]}") from exc
        return f"已點擊 {ref_id}，目前網址 {self.page.url}"

    def screenshot(self, name: str) -> Path:
        path = self.shot_dir / f"{name}.png"
        self.page.screenshot(path=str(path))
        return path


def selftest() -> None:
    """離線自我檢查：白名單與 ref 解析，不開瀏覽器、不呼叫模型。"""
    allowed = {"127.0.0.1:18904"}
    check_url("http://127.0.0.1:18904/index.html", allowed)
    for bad in ("https://news.ycombinator.com/", "http://localhost:18904/", "http://LOCALHOST:18904/",
                "file:///C:/Windows/win.ini", "javascript:alert(1)", "http://127.0.0.1:8000/"):
        try:
            check_url(bad, allowed)
        except ToolError:
            continue
        raise AssertionError(f"應該擋下：{bad}")
    assert parse_ref("ref_3") == "ref_3"
    for bad_ref in ("3", "ref_", "ref_x", None, [100, 200], "ref_1; drop"):
        try:
            parse_ref(bad_ref)
        except ToolError:
            continue
        raise AssertionError(f"應該拒絕 ref：{bad_ref!r}")
    with PracticeSite(Path(__file__).resolve().parent / "site") as site:
        assert site.host.startswith("127.0.0.1:")
    print("selftest OK：白名單擋 6 種網址、ref 解析拒絕 6 種錯誤輸入、練習站可啟動並關閉")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        try:
            selftest()
        except AssertionError as exc:
            print(f"selftest 失敗：{exc}", file=sys.stderr)
            sys.exit(1)
        sys.exit(0)
    print(__doc__)
