"""把隐藏精灵库（data/derived/spirit_library.json，1977 只）的头像与立绘落到本地。

背景：`assets/seerapi/` 原来只有深研层 234 只的图；库内其余精灵只能走
官方 H5 / GitHub 镜像在线取图，离线时只剩首字占位。本脚本按库内全部序号
补 `<id>.webp`，让选择器、列表、详情页全部离线可用。

尺寸按前端实际用量收紧（不追求原图）：
  pet_head  200px  q80   —— 列表 38px、画布约 44px、选择器 38px
  pet_body  340px  q78   —— 详情页立绘 max-height 400px

已存在且大于 100 字节的成品直接跳过（深研层 234 只的 560/420 版本保留），
可反复增量运行。

用法：
  python scripts/fetch_library_images.py                 # 补齐两种图
  python scripts/fetch_library_images.py --kind body     # 只补立绘
  python scripts/fetch_library_images.py --limit 50      # 先试跑
"""

from __future__ import annotations

import argparse
import io
import json
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    from PIL import Image  # noqa: PLC0415
    HAS_PIL = True
except ImportError:  # pragma: no cover
    HAS_PIL = False

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "data" / "derived" / "spirit_library.json"
ASSETS = ROOT / "assets" / "seerapi"
FAILED = ROOT / "data" / "derived" / "library_images_failures.json"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

H5_BASE = "https://seerh5.61.com/resource/assets/"
H5_PATHS = {"head": "pet/head", "body": "fightResource/pet"}
GH_PATH = "newseer/assets/art/ui/assets/pet"
GH_BASES = (
    "https://ghfast.top/https://raw.githubusercontent.com/SeerAPI/seer-unity-assets/main/",
    "https://gh-proxy.com/https://raw.githubusercontent.com/SeerAPI/seer-unity-assets/main/",
    "https://gcore.jsdelivr.net/gh/SeerAPI/seer-unity-assets@main/",
    "https://fastly.jsdelivr.net/gh/SeerAPI/seer-unity-assets@main/",
    "https://raw.githubusercontent.com/SeerAPI/seer-unity-assets/main/",
)
SIZE = {"head": (200, 80), "body": (340, 78)}
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

_lock = threading.Lock()
_stats = {"ok": 0, "skip": 0, "fail": 0}


def candidates(kind: str, rid: int) -> list[str]:
    h5 = f"{H5_BASE}{H5_PATHS[kind]}/{rid}.png"
    return [h5] + [f"{base}{GH_PATH}/{kind}/{rid}.png" for base in GH_BASES]


def download(url: str, timeout: float = 25.0) -> bytes | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        if resp.status != 200:
            return None
        return resp.read()


def to_webp(blob: bytes, kind: str) -> bytes | None:
    if not HAS_PIL:
        return None
    max_side, quality = SIZE[kind]
    try:
        with Image.open(io.BytesIO(blob)) as im:
            im = im.convert("RGBA")
            im.thumbnail((max_side, max_side), Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, "WEBP", quality=quality, method=5)
            return buf.getvalue()
    except Exception:  # noqa: BLE001 - 单张失败不阻断整批
        return None


def fetch_one(kind: str, rid: int, refresh: bool) -> tuple[str, str]:
    stem = ASSETS / f"pet_{kind}" / str(rid)
    for ext in (".webp", ".png"):
        p = stem.with_suffix(ext)
        if p.exists() and p.stat().st_size > 100 and not refresh:
            return "skip", ""
    last = ""
    for url in candidates(kind, rid):
        try:
            blob = download(url)
        except Exception as exc:  # noqa: BLE001
            last = f"{type(exc).__name__}"
            continue
        if not blob or not blob.startswith(PNG_MAGIC):
            last = f"not-png:{len(blob or b'')}"
            continue
        out = to_webp(blob, kind)
        target = stem.with_suffix(".webp") if out else stem.with_suffix(".png")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(out or blob)
        return "ok", ""
    return "fail", last or "no-source"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", choices=("head", "body", "both"), default="both")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--ids", default="")
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    doc = json.loads(LIB.read_text(encoding="utf-8"))
    ids = sorted(int(k) for k in doc.get("spirits", {}))
    if args.ids:
        wanted = {int(x) for x in args.ids.replace(" ", "").split(",") if x}
        ids = [i for i in ids if i in wanted]
    if args.limit:
        ids = ids[: args.limit]

    kinds = ("head", "body") if args.kind == "both" else (args.kind,)
    jobs = [(k, i) for k in kinds for i in ids]
    total = len(jobs)
    print(f"library images: {len(ids)} ids x {len(kinds)} kinds = {total} jobs", flush=True)

    t0 = time.time()
    failures: list[dict] = []
    done = 0
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futs = {pool.submit(fetch_one, k, i, args.refresh): (k, i) for k, i in jobs}
        for fut in as_completed(futs):
            kind, rid = futs[fut]
            state, err = fut.result()
            with _lock:
                done += 1
                _stats[state] = _stats.get(state, 0) + 1
                if state == "fail":
                    failures.append({"kind": kind, "id": rid, "error": err})
                if done % 40 == 0 or done == total:
                    rate = done / max(0.1, time.time() - t0)
                    print(f"  [{done}/{total}] ok={_stats['ok']} skip={_stats['skip']} "
                          f"fail={_stats['fail']} {rate:.1f}/s", flush=True)

    FAILED.write_text(json.dumps({"generated_at": time.strftime("%Y-%m-%d"),
                                  "failed": failures}, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    print(f"done {int(time.time() - t0)}s {_stats} failures={len(failures)} -> "
          f"{FAILED.relative_to(ROOT)}", flush=True)


if __name__ == "__main__":
    main()
