# -*- coding: utf-8 -*-
"""单文件前端「内联 DATA 行」的唯一读写实现。

为什么要有这个模块：`references/spirit_synergy_view.html` 是 11MB 单文件，
数据藏在 `const DATA = {...};` 这一行里。以前 rebuild_view / check_roster /
editor_schema / recover_local_storage 各自写了一遍「切字符串 → json.loads」和
「json.dumps → 拼回整文件」，口径已经漂移过：

- 读：多数地方按首个 ``\\n`` 切行，DATA 一旦被格式化成多行就整体失效；
      rebuild_view 用 ``raw_decode``，两边结果其实不一样。
- 写：紧凑分隔符、``</`` 转义、CRLF、结尾分号、是否保留其余文本，
      每处都要重新抄一遍。

现在只有这里一处实现，其它脚本一律 ``import viewdata``。

四条不能改的约定：
1. 标记 ``const DATA = `` 在产物里唯一出现；模板里对应的占位是 ``/*__SYNERGY_DATA__*/``。
2. 写回用紧凑 JSON（``separators=(",", ":")``）＋ ``</`` → ``<\\/`` 转义，
   否则长文本里的 ``</script>`` 会提前闭合脚本块。
3. 整文件统一 CRLF（模板与产物同源，避免整文件 diff 抖动）。
4. JSON 边界用 ``JSONDecoder.raw_decode()`` 定，不靠数括号、不靠切行。

改这个文件后必须跑：``python scripts/rebuild_view.py`` → ``python scripts/check_roster.py``
→ ``python scripts/smoke_test.py``。
"""
from __future__ import annotations

import io
import json
from pathlib import Path

MARKER = "const DATA = "
PLACEHOLDER = "/*__SYNERGY_DATA__*/"

_DECODER = json.JSONDecoder()


class ViewDataError(Exception):
    """产物里的内联 DATA 缺失或不是合法 JSON。"""


def encode(payload: dict) -> str:
    """payload → 紧凑 JSON 文本（已做 </ 转义，可直接嵌进 <script>）。"""
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return text.replace("</", "<\\/")


def line(payload: dict) -> str:
    """payload → 完整的数据行（含标记与结尾分号，不含换行）。"""
    return MARKER + encode(payload) + ";"


def _span(text: str) -> tuple[int, int]:
    """返回 JSON 对象的 [start, end) 下标；END 停在结尾分号之前。"""
    at = text.find(MARKER)
    if at < 0:
        raise ViewDataError(f"产物里找不到 {MARKER!r}，文件不是本项目的单文件前端")
    start = at + len(MARKER)
    while start < len(text) and text[start] in " \t\r\n":
        start += 1
    try:
        _, end = _DECODER.raw_decode(text, start)
    except json.JSONDecodeError as exc:
        raise ViewDataError(f"内联 DATA 不是合法 JSON：{exc}") from exc
    return start, end


def parse(text: str) -> dict:
    """整页 HTML 文本 → payload。"""
    start, end = _span(text)
    return json.loads(text[start:end])


def read(path: str | Path) -> dict:
    """读产物文件 → payload（newline="" 保留原始行尾，交给 parse 处理）。"""
    return parse(io.open(path, encoding="utf-8", newline="").read())


def replace_in_text(text: str, payload: dict) -> str:
    """只换掉数据行，其余字节原样保留（编辑器 / 恢复脚本用）。"""
    start, end = _span(text)
    return text[:start] + encode(payload) + text[end:]


def write(path: str | Path, text: str) -> None:
    """写产物文件，不做换行转换（文本里已统一 CRLF）。"""
    io.open(path, "w", encoding="utf-8", newline="").write(text)


def save_payload(path: str | Path, payload: dict) -> None:
    """读入 → 换数据行 → 写回。"""
    write(path, replace_in_text(io.open(path, encoding="utf-8", newline="").read(), payload))


def crlf(text: str) -> str:
    """统一成 CRLF。"""
    return text.replace("\r\n", "\n").replace("\n", "\r\n")


def build(template_text: str, payload: dict) -> str:
    """模板 + payload → 完整产物文本（CRLF）。占位符必须恰好一个。"""
    count = template_text.count(PLACEHOLDER)
    if count != 1:
        raise ViewDataError(f"模板占位符 {PLACEHOLDER} 出现 {count} 次，必须是 1 次")
    return crlf(template_text.replace(PLACEHOLDER, line(payload)))


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    target = sys.argv[1] if len(sys.argv) > 1 else str(
        Path(__file__).resolve().parents[1] / "references" / "spirit_synergy_view.html")
    doc = read(target)
    known = ("nodes", "systems", "edges", "build", "stats")
    print(f"{target}")
    print("  keys:", ", ".join(k for k in doc if k not in known)[:200] or "-")
    for key in ("build", "nodes", "systems", "edges"):
        value = doc.get(key)
        print(f"  {key}: {len(value) if isinstance(value, list) else value}")
