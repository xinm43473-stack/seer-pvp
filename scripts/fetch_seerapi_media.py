#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通过 SeerAPI 抓取「列表里的精灵」的魂印／技能／图像等原始文件。

数据源（全部来自 GitHub 上的 SeerAPI 生态，2026-11-08 实测可用）：
  1. 结构化数据   https://api.seerapi.com/v1/{pet,soulmark,skill,...}/{id}
                  官方 CLI 通道见 scripts/seerapi_cli.py（单条人工核查）；
                  本脚本走同一 API 的批量 HTTP，CLI 每次启动约 2.5s 不适合数千次调用。
  2. 静态图像     https://github.com/SeerAPI/seer-unity-assets
                  （SeerAPI 组织维护的 Unity 端静态资源节选）
                  pet/head 立绘、pet/body 头像、effecticon 魂印图标、pettype 属性图标。
                  按 pet.resource_id / soulmark.effect.effect.id / type.id 拼文件名。

目标清单：scripts/editor_schema.py#editable_ids()（活跃总表＋资料层参照，
共 230 个整数序号），与前端可编辑节点、import_spirit_info.py 的白名单同源。

产物（都是离线文件，后续脚本不再联网）：
  data/seerapi_media/raw/<resource>/<id>.json   每条 API 原始响应
  assets/seerapi/<kind>/<id>.png                图像文件
  data/seerapi_media/manifest.json             来源、时间、计数、失败留痕

用法：
  python scripts/fetch_seerapi_media.py                    # 增量（已有文件跳过）
  python scripts/fetch_seerapi_media.py --refresh         # 全部重抓
  python scripts/fetch_seerapi_media.py --skip-images     # 只抓数据
  python scripts/fetch_seerapi_media.py --images-only     # 只补图像
  python scripts/fetch_seerapi_media.py --limit 5         # 小样本试跑

不编造数据：任何 404 / 网络失败都写进 manifest.failures，下游只显示真正拿到的文件。
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CACHE = DATA / "seerapi_media" / "raw"
ASSETS = ROOT / "assets" / "seerapi"
MANIFEST = DATA / "seerapi_media" / "manifest.json"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import editor_schema  # noqa: E402

API = "https://api.seerapi.com/v1"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# 精灵立绘/头像原图较大（单张最多 1.8MB），落盘前转成带透明通道的 WebP
# 缩略图；小图标保持 PNG 原样。没有 Pillow 时自动退回 PNG，不阻断采集。
try:
    from PIL import Image  # noqa: PLC0415
    HAS_PIL = True
except ImportError:  # pragma: no cover - 取决于运行环境
    HAS_PIL = False
WEBP_KINDS = {"pet_head", "pet_body"}
WEBP_MAX = {"pet_head": 560, "pet_body": 420}

# 静态资源仓库的目录（相对仓库根），以及落到本项目的目录名。
GH_PATHS = {
    "pet_head": "newseer/assets/art/ui/assets/pet/head",
    "pet_body": "newseer/assets/art/ui/assets/pet/body",
    "effecticon": "newseer/assets/art/ui/assets/effecticon",
    "pettype": "newseer/assets/art/ui/assets/pettype",
}
GH_BASES = (
    # 同一仓库的多个 CDN / 代理镜像；当前网络下 raw.githubusercontent 与 fastly
    # 会间歇性挂起，因此按实测稳定性排序并做坏源熔断。
    "https://gcore.jsdelivr.net/gh/SeerAPI/seer-unity-assets@main/",
    "https://ghfast.top/https://raw.githubusercontent.com/SeerAPI/seer-unity-assets/main/",
    "https://gh-proxy.com/https://raw.githubusercontent.com/SeerAPI/seer-unity-assets/main/",
    "https://fastly.jsdelivr.net/gh/SeerAPI/seer-unity-assets@main/",
    "https://raw.githubusercontent.com/SeerAPI/seer-unity-assets/main/",
    "https://github.com/SeerAPI/seer-unity-assets/raw/refs/heads/main/",
)
BASE_FAIL_LIMIT = 8
# 仓库镜像全部不可用时，精灵图退回官方 H5 资源域（SeerAPI 的 resource_id 即对应
# 该域的文件名）；只对 pet_head / pet_body 生效，图标仍只认 SeerAPI 仓库。
H5_BASE = "https://seerh5.61.com/resource/assets/"
H5_PATHS = {"pet_head": "pet/head", "pet_body": "fightResource/pet"}
TRIMMED_META = {"skill_category", "soulmark_tag"}  # 响应带全量反查列表，只留 id/name
# 某个 CDN 连续失败就临时跳过，避免每张图都在坏源上耗掉超时时间。
BASE_FAILS: dict[str, int] = {}
BASE_LOCK = threading.Lock()


def _get_bytes(url: str, timeout: float = 45.0, retries: int = 4) -> bytes:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code == 404:      # 资源确实不存在，不重试
                break
            time.sleep(2.0 * (attempt + 1))   # 429 / 5xx 退避
        except Exception as exc:  # noqa: BLE001 - 网络失败统一留痕
            last = exc
            time.sleep(0.8 * (attempt + 1))
    raise RuntimeError(str(last))


def _curl_bytes(url: str, timeout: int = 20) -> bytes:
    """用 curl 下载二进制：--max-time 覆盖 DNS/TLS/读全过程，避免 socket 超时失效。"""
    if not shutil.which("curl"):
        return _get_bytes(url, timeout=timeout, retries=1)
    proc = subprocess.run(
        ["curl", "-sL", "--max-time", str(timeout), "--connect-timeout", "6",
         "-A", UA, "-o", "-", url],
        capture_output=True, timeout=timeout + 5)
    body = proc.stdout
    if proc.returncode != 0 or not body:
        err = proc.stderr.decode("utf-8", "ignore").strip()[:160]
        raise RuntimeError(f"curl exit {proc.returncode} {err}")
    return body


def _json(url: str) -> dict:
    return json.loads(_get_bytes(url).decode("utf-8"))


def _write(path: Path, payload: bytes | str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_bytes(payload)


def raw_path(resource: str, rid: int) -> Path:
    return CACHE / resource / f"{rid}.json"


def fetch_resource(resource: str, rid: int, refresh: bool) -> tuple[int, dict | None, str]:
    """返回 (id, 数据|None, 错误)。命中本地缓存直接读，保证重建链离线可用。"""
    path = raw_path(resource, rid)
    if path.exists() and not refresh:
        try:
            return rid, json.loads(path.read_text(encoding="utf-8")), ""
        except (OSError, json.JSONDecodeError):
            pass  # 坏缓存重抓
    url = f"{API}/{resource}/{rid}"
    try:
        data = _json(url)
        if resource in TRIMMED_META:
            data = {"id": data.get("id"), "name": data.get("name")}
        _write(path, json.dumps(data, ensure_ascii=False, indent=1) + "\n")
        return rid, data, ""
    except Exception as exc:  # noqa: BLE001
        return rid, None, f"{resource}/{rid}: {exc}"


def fetch_batch(resource: str, ids: list[int], refresh: bool, workers: int,
                label: str) -> tuple[dict[int, dict], list[str]]:
    todo = sorted(set(ids))
    if not todo:
        return {}, []
    out: dict[int, dict] = {}
    failures: list[str] = []
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(fetch_resource, resource, rid, refresh) for rid in todo]
        for fut in as_completed(futures):
            rid, data, err = fut.result()
            done += 1
            if data is not None:
                out[rid] = data
            else:
                failures.append(err)
            if done % 250 == 0 or done == len(todo):
                print(f"  [{label}] {done}/{len(todo)} ok={len(out)} fail={len(failures)}",
                      flush=True)
    return out, failures


def scan_assets() -> dict[str, str]:
    """扫描 assets/seerapi 下实际存在的图像（中断的采集也会留下文件）。"""
    out: dict[str, str] = {}
    if not ASSETS.exists():
        return out
    for path in ASSETS.glob("*/*"):
        if path.suffix.lower() in (".webp", ".png"):
            out[path.relative_to(ROOT).as_posix()] = ""
    return out


def image_url(kind: str, rid: int, base: str) -> str:
    return f"{base}{GH_PATHS[kind]}/{rid}.png"


def _to_webp(blob: bytes, kind: str) -> bytes | None:
    """PNG 原图 → WebP 缩略图（保留透明通道）；失败时返回 None 让调用方留原 PNG。"""
    if not HAS_PIL or kind not in WEBP_KINDS:
        return None
    import io  # noqa: PLC0415
    try:
        with Image.open(io.BytesIO(blob)) as im:
            im = im.convert("RGBA")
            im.thumbnail((WEBP_MAX[kind], WEBP_MAX[kind]), Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, "WEBP", quality=82, method=5)
            return buf.getvalue()
    except Exception:  # noqa: BLE001 - 单张失败不阻断整批
        return None


def fetch_image(kind: str, rid: int, refresh: bool) -> tuple[str, str, str]:
    """返回 (相对项目根路径, 实际来源 URL, 错误)。

    命中已有成品文件直接跳过；只有旧版 PNG 时就地压缩，不再联网重下。
    """
    stem = ROOT / f"assets/seerapi/{kind}/{rid}"
    webp_ok = HAS_PIL and kind in WEBP_KINDS
    webp_path, png_path = stem.with_suffix(".webp"), stem.with_suffix(".png")
    if not refresh:
        if webp_ok:
            if webp_path.exists() and webp_path.stat().st_size > 100:
                return f"assets/seerapi/{kind}/{rid}.webp", "", ""
            if png_path.exists() and png_path.stat().st_size > 100:
                out = _to_webp(png_path.read_bytes(), kind)
                if out:
                    _write(webp_path, out)
                    png_path.unlink()
                    return f"assets/seerapi/{kind}/{rid}.webp", "local-png", ""
                return f"assets/seerapi/{kind}/{rid}.png", "", ""
        elif png_path.exists() and png_path.stat().st_size > 100:
            return f"assets/seerapi/{kind}/{rid}.png", "", ""

    def save(blob: bytes) -> str:
        out = _to_webp(blob, kind)
        if out:
            rel = f"assets/seerapi/{kind}/{rid}.webp"
            _write(ROOT / rel, out)
        else:
            rel = f"assets/seerapi/{kind}/{rid}.png"
            _write(ROOT / rel, blob)
        return rel

    last = ""
    candidates: list[tuple[str, str]] = []
    # 立绘/头像：官方 H5 资源域优先（实测 0.5s，容量与缩略图后质量足够），
    # SeerAPI 静态资源仓库作为高分辨率兜底。图标仍只走仓库。
    if kind in H5_PATHS:
        candidates.append((f"{H5_BASE}{H5_PATHS[kind]}/{rid}.png", "h5"))
    with BASE_LOCK:
        usable = [b for b in GH_BASES if BASE_FAILS.get(b, 0) < BASE_FAIL_LIMIT]
        if not usable:                      # 全部熔断：给一次冷却后重试
            BASE_FAILS.clear()
            usable = list(GH_BASES)
    candidates += [(image_url(kind, rid, base), base) for base in usable]

    for url, tag in candidates:
        try:
            blob = _curl_bytes(url, timeout=15)
            if not blob.startswith(b"\x89PNG\r\n\x1a\n"):
                last = f"{kind}/{rid}: not a PNG ({len(blob)} bytes)"
                continue
            if tag != "h5":
                with BASE_LOCK:
                    BASE_FAILS[tag] = 0
            return save(blob), url, ""
        except Exception as exc:  # noqa: BLE001
            last = f"{kind}/{rid}: {exc}"
            if tag != "h5" and "404" not in str(exc):
                with BASE_LOCK:
                    BASE_FAILS[tag] = BASE_FAILS.get(tag, 0) + 1
    return "", "", last


def fetch_skills_bulk(wanted: set[int], refresh: bool) -> tuple[dict[int, dict], list[str]]:
    """技能用列表分页批量取（每页 200 条、expand=true 返回完整对象）。

    逐条 GET 3000+ 次会触发官方 API 限流；全库 27414 条技能用 138 页即可覆盖，
    且分页响应本身就是完整对象，不需要再逐条补字段。只落盘目标清单需要的 id。
    """
    out: dict[int, dict] = {}
    if not refresh:
        for rid in wanted:
            path = raw_path("skill", rid)
            if path.exists():
                try:
                    out[rid] = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    pass
    missing = wanted - set(out)
    if not missing:
        return out, []
    failures: list[str] = []
    offset, pages = 0, 0
    while missing and pages < 200:
        url = f"{API}/skill?expand=true&limit=200&offset={offset}"
        try:
            doc = _json(url)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"skill list offset={offset}: {exc}")
            break
        results = doc.get("results") or []
        for item in results:
            rid = item.get("id")
            if rid in missing:
                _write(raw_path("skill", rid),
                       json.dumps(item, ensure_ascii=False, indent=1) + "\n")
                out[rid] = item
                missing.discard(rid)
        pages += 1
        nxt = doc.get("next")
        if not nxt or not results:
            break
        try:
            if isinstance(nxt, dict):
                offset = int(nxt["offset"])
            else:
                from urllib.parse import parse_qs, urlparse  # noqa: PLC0415
                offset = int(parse_qs(urlparse(str(nxt)).query)["offset"][0])
        except (KeyError, TypeError, ValueError, IndexError):
            offset += len(results)
        if pages % 20 == 0:
            print(f"  [skill/bulk] page {pages} cached={len(out)} missing={len(missing)}",
                  flush=True)
    if missing:
        # 分页没覆盖到的（例如接口分页口径变化）退回低并发单条，避免静默漏数据。
        extra, errs = fetch_batch("skill", sorted(missing), refresh, 3, "skill/retry")
        out.update(extra)
        failures.extend(errs)
    print(f"  [skill/bulk] pages={pages} cached={len(out)} missing={len(missing)}", flush=True)
    return out, failures


def fetch_images(jobs: list[tuple[str, int]], refresh: bool,
                 workers: int = 8) -> tuple[dict[str, str], list[str]]:
    todo = sorted(set(jobs))
    assets: dict[str, str] = {}
    failures: list[str] = []
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_image, kind, rid, refresh): (kind, rid)
                   for kind, rid in todo}
        for fut in as_completed(futures):
            rel, url, err = fut.result()
            done += 1
            if rel:
                assets[rel] = url
            else:
                failures.append(err)
            if done % 100 == 0 or done == len(todo):
                print(f"  [images] {done}/{len(todo)} ok={len(assets)} fail={len(failures)}",
                      flush=True)
    return assets, failures


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true", help="忽略本地缓存，全部重抓")
    ap.add_argument("--skip-images", action="store_true", help="只抓结构化数据")
    ap.add_argument("--images-only", action="store_true", help="只读缓存补抓图像")
    ap.add_argument("--scan-only", action="store_true",
                    help="不联网，只按磁盘实际文件刷新 manifest 的图像清单")
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 只（试跑用）")
    ap.add_argument("--workers", type=int, default=8, help="API 并发数")
    ap.add_argument("--image-workers", type=int, default=8, help="图像下载并发数")
    ap.add_argument("--with-icons", action="store_true",
                    help="同时抓魂印图标/属性图标（默认只抓立绘+头像，图标量少但个别会卡源）")
    args = ap.parse_args()

    targets = sorted(editor_schema.editable_ids())
    if args.limit:
        targets = targets[:args.limit]
    print(f"seerapi media: {len(targets)} spirits | refresh={args.refresh}", flush=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    ASSETS.mkdir(parents=True, exist_ok=True)

    old: dict = {}
    if MANIFEST.exists():
        try:
            old = json.loads(MANIFEST.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            old = {}

    if args.scan_only:
        assets = scan_assets()
        counts = dict(old.get("counts", {}))
        counts["images"] = len(assets)
        old.update({
            "status": "ready" if counts.get("pets") else old.get("status", "ready"),
            "generated_at": date.today().isoformat(),
            "assets": assets,
            "counts": counts,
            "failures": [],
        })
        _write(MANIFEST, json.dumps(old, ensure_ascii=False, indent=2) + "\n")
        print(f"scan-only: {len(assets)} images -> {MANIFEST.relative_to(ROOT)}", flush=True)
        return 0

    if args.images_only:
        # 从已落盘的 raw 缓存重建待抓清单，不联网取 API。
        pets = {}
        for path in (CACHE / "pet").glob("*.json"):
            try:
                pets[int(path.stem)] = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, ValueError):
                continue
        souls = {}
        for path in (CACHE / "soulmark").glob("*.json"):
            try:
                souls[int(path.stem)] = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, ValueError):
                continue
        skills = {}
        for path in (CACHE / "skill").glob("*.json"):
            try:
                skills[int(path.stem)] = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, ValueError):
                continue
        types = {}
        for path in (CACHE / "element_type_combination").glob("*.json"):
            try:
                types[int(path.stem)] = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, ValueError):
                continue
        # API 失败的留痕保留；图像失败以本次补抓结果为准，避免旧 502 永久残留。
        failures = [f for f in old.get("failures", [])
                    if not any(f.startswith(k + "/") for k in GH_PATHS)]
    else:
        print("[1/4] pet", flush=True)
        pets, f_pet = fetch_batch("pet", targets, args.refresh, args.workers, "pet")
        soul_ids = [r["id"] for p in pets.values() for r in (p.get("soulmark") or [])
                    if isinstance(r, dict) and isinstance(r.get("id"), int)]
        skill_ids = [r.get("skill", {}).get("id") for p in pets.values()
                     for r in (p.get("skill") or [])
                     if isinstance(r, dict) and isinstance(r.get("skill"), dict)]
        skill_ids = [i for i in skill_ids if isinstance(i, int)]
        type_ids = [x["id"] for p in pets.values()
                    for x in [p.get("type") or {}] if isinstance(x.get("id"), int)]
        cat_ids = []
        print(f"  unique soulmarks={len(set(soul_ids))} skills={len(set(skill_ids))} "
              f"types={len(set(type_ids))}", flush=True)

        print("[2/4] soulmark / skill", flush=True)
        souls, f_soul = fetch_batch("soulmark", soul_ids, args.refresh,
                                    min(args.workers, 6), "soulmark")
        skills, f_skill = fetch_skills_bulk(set(skill_ids), args.refresh)

        # 类型名、技能分类名、魂印标签名只是展示用元数据，数量很少。
        type_ids += [s.get("type", {}).get("id") for s in skills.values()
                     if isinstance(s.get("type"), dict)]
        type_ids = [i for i in type_ids if isinstance(i, int)]
        cat_ids = [s.get("category", {}).get("id") for s in skills.values()
                   if isinstance(s.get("category"), dict)]
        tag_ids = [t["id"] for s in souls.values() for t in (s.get("tag") or [])
                   if isinstance(t, dict) and isinstance(t.get("id"), int)]
        print("[3/4] metadata", flush=True)
        types, f_type = fetch_batch("element_type_combination", type_ids,
                                    args.refresh, min(args.workers, 6), "type")
        cats, f_cat = fetch_batch("skill_category", cat_ids,
                                  args.refresh, min(args.workers, 6), "category")
        tags, f_tag = fetch_batch("soulmark_tag", tag_ids,
                                  args.refresh, min(args.workers, 6), "tag")
        for path in (CACHE / "skill_category").glob("*.json"):
            try:
                cats[int(path.stem)] = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, ValueError):
                continue
        failures = f_pet + f_soul + f_skill + f_type + f_cat + f_tag
        print(f"  metadata: types={len(types)} categories={len(cats)} tags={len(tags)}",
              flush=True)

    image_jobs_count = 0
    if args.skip_images:
        assets = {rel: url for rel, url in old.get("assets", {}).items()
                  if (ROOT / rel).exists()}
        img_failures = []
    else:
        print("[4/4] images", flush=True)
        jobs: list[tuple[str, int]] = []
        for p in pets.values():
            rid = p.get("resource_id") or p.get("id")
            if isinstance(rid, int):
                jobs += [("pet_head", rid), ("pet_body", rid)]
            if args.with_icons:
                t = p.get("type") or {}
                if isinstance(t.get("id"), int):
                    jobs.append(("pettype", t["id"]))
        if args.with_icons:
            for s in souls.values():
                eff = ((s.get("effect") or {}).get("effect") or {}).get("id")
                if isinstance(eff, int):
                    jobs.append(("effecticon", eff))
            # 技能属性图标同样按 type.id 落盘（技能表展示用）
            for sk in skills.values():
                t = sk.get("type") or {}
                if isinstance(t.get("id"), int):
                    jobs.append(("pettype", t["id"]))
        image_jobs_count = len(set(jobs))
        assets, img_failures = fetch_images(jobs, args.refresh,
                                            workers=args.image_workers)
        if not args.with_icons:
            # 之前已经抓到的图标继续保留在 manifest 里，不因本次只补立绘而丢记录。
            for rel, url in old.get("assets", {}).items():
                if (ROOT / rel).exists() and rel not in assets:
                    assets[rel] = url
        print(f"  images ok={len(assets)} fail={len(img_failures)}", flush=True)

    # 以磁盘为准补齐清单：中断的采集可能已写文件但未写 manifest。
    for rel in scan_assets():
        assets.setdefault(rel, "")
    manifest = {
        "schema_version": 1.0,
        "status": "ready" if pets else "empty",
        "generated_at": date.today().isoformat(),
        "target_source": "scripts/editor_schema.py#editable_ids()",
        "target_count": len(targets),
        "api": API,
        "api_cli": "seerapi (GitHub SeerAPI/seerapi, seerapi-cli skill)",
        "asset_repo": "https://github.com/SeerAPI/seer-unity-assets",
        "asset_dirs": GH_PATHS,
        "asset_bases": list(GH_BASES),
        "raw_cache": "data/seerapi_media/raw/<resource>/<id>.json",
        "asset_root": "assets/seerapi",
        "image_format": ("pet_head/pet_body 转 WebP 缩略图（Pillow，最长边 %s / 质量 82），"
                         "图标保留 PNG" % WEBP_MAX) if HAS_PIL else "PNG 原图（未安装 Pillow）",
        "counts": {
            "pets": len(pets), "soulmarks": len(souls), "skills": len(skills),
            "types": len(types),
            "images": len(assets),
            "image_jobs": image_jobs_count,
        },
        "assets": assets,
        "failures": failures + img_failures,
        "policy": "只登记真正取回的文件；404/网络失败写入 failures，不推断、不编造。",
    }
    text = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    if not MANIFEST.exists() or MANIFEST.read_text(encoding="utf-8") != text:
        _write(MANIFEST, text)
    print(f"manifest: pets={len(pets)} soulmarks={len(souls)} skills={len(skills)} "
          f"images={len(assets)} failures={len(manifest['failures'])} -> {MANIFEST.relative_to(ROOT)}",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
