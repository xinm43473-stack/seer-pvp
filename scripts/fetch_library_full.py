"""Cache the *whole* SeerAPI catalogue locally for the hidden spirit library.

2026-11-09: the library must give an added spirit full SeerAPI-format data
(soul mark + complete skill table) without any network call from the browser.
Only /v1/{pet,soulmark,skill,...} list endpoints are used, with
``?expand=true&limit=200`` paging; ~175 requests cover the entire catalogue
instead of tens of thousands of single-item GETs.

All rows are written to the same ``data/seerapi_media/raw/<resource>/<id>.json``
cache used by fetch_seerapi_media.py, so build_spirit_media.py and
build_spirit_library.py share one source of truth.  Existing verified files are
never overwritten.

    python scripts/fetch_library_full.py            # incremental (skip cached)
    python scripts/fetch_library_full.py --refresh # rewrite everything
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "seerapi_media" / "raw"
API = "https://api.seerapi.com/v1"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
PAGE = 200
RESOURCES = (
    "pet", "soulmark", "skill",
    "element_type_combination", "skill_category", "soulmark_tag",
)


def fetch(url: str, timeout: float = 60.0, retries: int = 4) -> dict:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - network failures are retried
            last = exc
            time.sleep(0.8 * (attempt + 1))
    raise RuntimeError(f"{url}: {last}")


def cache_dir(resource: str) -> Path:
    path = RAW / resource
    path.mkdir(parents=True, exist_ok=True)
    return path


def save(resource: str, row: dict, refresh: bool) -> bool:
    rid = row.get("id")
    if not isinstance(rid, int):
        return False
    path = cache_dir(resource) / f"{rid}.json"
    if path.exists() and not refresh:
        return False
    path.write_text(json.dumps(row, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true", help="覆盖已有缓存")
    args = ap.parse_args()

    total_new = 0
    for resource in RESOURCES:
        offset, pages, seen, added = 0, 0, 0, 0
        print(f"[{resource}] paging ...", flush=True)
        while pages < 300:
            url = f"{API}/{resource}?expand=true&limit={PAGE}&offset={offset}"
            doc = fetch(url)
            results = doc.get("results") or []
            for row in results:
                seen += 1
                if save(resource, row, args.refresh):
                    added += 1
            pages += 1
            nxt = doc.get("next")
            if not nxt or not results:
                break
            try:
                if isinstance(nxt, dict):
                    next_offset = int(nxt["offset"])
                else:
                    from urllib.parse import parse_qs, urlparse  # noqa: PLC0415
                    next_offset = int(parse_qs(urlparse(str(nxt)).query)["offset"][0])
            except (KeyError, TypeError, ValueError, IndexError):
                next_offset = offset + PAGE
            if next_offset <= offset:
                break
            offset = next_offset
            if pages % 25 == 0:
                print(f"  [{resource}] page {pages} | seen {seen} | new {added}", flush=True)
        total_new += added
        print(f"[{resource}] pages={pages} count={doc.get('count')} seen={seen} new={added}", flush=True)

    print(f"library full cache: {total_new} new files -> {RAW.relative_to(ROOT)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
