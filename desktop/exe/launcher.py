"""赛尔号：巅峰之战 —— Windows 桌面壳（本地静态服务 + WebView 窗口）。

打包后的目录结构（onedir）::

    SeerPeak.exe
    _internal/app/references/spirit_synergy_view.html
    _internal/app/assets/seerapi/...

开发模式直接指向项目根（含 references/ 与 assets/）。
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

APP_NAME = "赛尔号：巅峰之战"
ENTRY = "references/spirit_synergy_view.html"


class QuietHandler(SimpleHTTPRequestHandler):
    """只服务 app 目录，静默日志，给静态资源长缓存。"""

    def log_message(self, fmt, *args):  # noqa: D401 - 静默
        pass

    def end_headers(self):
        if self.path.endswith((".webp", ".png", ".jpg", ".svg", ".woff2")):
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        super().end_headers()


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        for cand in (base / "app", Path(sys.executable).parent / "app"):
            if (cand / ENTRY).is_file():
                return cand
        raise SystemExit("找不到 app/references/spirit_synergy_view.html")
    return Path(__file__).resolve().parent.parent.parent


def serve(root: Path, port: int):
    handler = partial(QuietHandler, directory=str(root))
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=0, help="0 = 系统分配")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    root = app_root()
    entry = root / ENTRY
    if not entry.is_file():
        raise SystemExit(f"缺少入口文件：{entry}")

    httpd = serve(root, args.port)
    port = httpd.server_address[1]
    url = f"http://127.0.0.1:{port}/{ENTRY}"

    import webview  # 延迟导入，便于 --check

    window = webview.create_window(
        APP_NAME,
        url=url,
        width=1440,
        height=900,
        min_size=(1024, 640),
        background_color="#0B1220",
        text_select=True,
    )
    try:
        webview.start(debug=args.debug, private_mode=False)
    finally:
        httpd.shutdown()
        window.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
