#!/usr/bin/env python3
"""把单文件前端打成 Android APK —— 不依赖 Gradle 的最小构建链。

步骤：javac → d8 → aapt2 compile/link → 塞 classes.dex → zipalign → apksigner。
依赖：JDK 17、Android SDK 的 build-tools;34.0.0 与 platforms;android-34。

用法::

    python desktop/android/build_apk.py
    python desktop/android/build_apk.py --sdk-root E:\\seerskill\\.buildtools\\sdk --jdk E:\\seerskill\\.buildtools\\jdk\\jdk-17...
"""
from __future__ import annotations

import argparse
import math
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJ = HERE.parent.parent
BUILD = PROJ / "build" / "android"
DIST = PROJ / "dist"

MANIFEST = HERE / "AndroidManifest.xml"
SRC = HERE / "src"
RES = HERE / "res"
ICON = RES / "mipmap-xxhdpi" / "ic_launcher.png"

MIN_SDK = "24"
TARGET_SDK = "34"
BUILD_TOOLS = "34.0.0"
PLATFORM = "android-34"

# 版本号：每次发布递增，安装器据此区分新旧；Android 只允许同签名覆盖升级
VERSION_CODE = 2
VERSION_NAME = "1.0.1"

# 签名密钥固定在项目内（build/ 每次构建都会被清空，放那里会导致签名漂移）
KEYSTORE = HERE / "seerpeak.jks"


def log(msg: str) -> None:
    print(f"[apk] {msg}", flush=True)


def run(cmd: list[str], cwd: Path | None = None) -> None:
    shown = " ".join(cmd)
    log("$ " + shown)
    proc = subprocess.run(cmd, cwd=str(cwd) if cwd else None, text=True,
                          capture_output=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise SystemExit(f"命令失败（{proc.returncode}）：{shown}\n{proc.stdout[-4000:]}\n{proc.stderr[-4000:]}")


def as_cmd(exe: Path, *args: str) -> list[str]:
    """Windows 上 .bat 需要通过 cmd /c 执行。"""
    if exe.suffix.lower() in (".bat", ".cmd"):
        return ["cmd", "/c", str(exe), *args]
    return [str(exe), *args]


def _roots() -> list[Path]:
    """打包工具链的探测位置：用户长期存放目录优先，其次项目外的历史位置。"""
    roots = []
    env = os.environ.get("SEERPKG_TOOLS")
    if env:
        roots.append(Path(env))
    roots += [Path("D:/ruanjianmen/dabao"), Path("E:/seerskill/.buildtools")]
    return roots


def find_jdk(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    env = os.environ.get("JAVA_HOME")
    if env and (Path(env) / "bin" / "javac.exe").is_file():
        return Path(env)
    for root in _roots():
        for base in (root / "jdk", root):
            if (base / "bin" / "javac.exe").is_file():
                return base
            for cand in sorted(base.glob("*/bin/javac.exe")):
                return cand.parent.parent
    raise SystemExit("找不到 JDK，请用 --jdk 指定（需要 javac / keytool）")


def find_sdk(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    for key in ("ANDROID_SDK_ROOT", "ANDROID_HOME"):
        env = os.environ.get(key)
        if env and (Path(env) / "platforms" / PLATFORM).is_dir():
            return Path(env)
    for root in _roots():
        for base in (root / "sdk", root):
            if (base / "platforms" / PLATFORM).is_dir():
                return base
    raise SystemExit("找不到 Android SDK，请用 --sdk-root 指定")


def ensure_icon() -> None:
    if ICON.is_file():
        return
    from PIL import Image, ImageDraw, ImageFont

    ICON.parent.mkdir(parents=True, exist_ok=True)
    size = 512
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=112, fill=(11, 18, 32, 255))
    cx = cy = size / 2
    r = 196
    pts = [(cx + r * math.cos(math.pi / 2 + i * math.pi / 3),
            cy - r * math.sin(math.pi / 2 + i * math.pi / 3)) for i in range(6)]
    draw.polygon(pts, outline=(240, 190, 80, 255), width=16)
    font_path = "C:/Windows/Fonts/msyhbd.ttc"
    try:
        font = ImageFont.truetype(font_path, 210)
        draw.text((cx, cy - 6), "赛", font=font, fill=(255, 255, 255, 255), anchor="mm")
    except OSError:
        pass
    img.save(ICON)


def link_tree(src: Path, dst: Path) -> None:
    """硬链接整棵树（同盘秒级），失败退回复制。"""
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.rglob("*"):
        rel = item.relative_to(src)
        target = dst / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            continue
        try:
            os.link(item, target)
        except OSError:
            shutil.copy2(item, target)


def stage_assets() -> Path:
    www = BUILD / "assets" / "www"
    if www.exists():
        shutil.rmtree(www)
    (www / "references").mkdir(parents=True)
    entry = PROJ / "references" / "spirit_synergy_view.html"
    if not entry.is_file():
        raise SystemExit(f"缺少前端产物：{entry}")
    log("镜像前端与资源（硬链接）")
    try:
        os.link(entry, www / "references" / "spirit_synergy_view.html")
    except OSError:
        shutil.copy2(entry, www / "references" / "spirit_synergy_view.html")
    link_tree(PROJ / "assets", www / "assets")
    return BUILD / "assets"


def stage_manifest(version_code: int, version_name: str) -> Path:
    """manifest 里写死了版本号，aapt2 的 --version-code 会被它压过，先落到构建目录再 link。"""
    text = MANIFEST.read_text(encoding="utf-8")
    text, n1 = re.subn(r'android:versionCode="\d+"', f'android:versionCode="{version_code}"', text)
    text, n2 = re.subn(r'android:versionName="[^"]*"', f'android:versionName="{version_name}"', text)
    if n1 != 1 or n2 != 1:
        raise SystemExit("AndroidManifest.xml 缺少唯一的 versionCode / versionName 声明")
    out = BUILD / "AndroidManifest.xml"
    out.write_text(text, encoding="utf-8")
    return out


def build(jdk: Path, sdk: Path, version_code: int, version_name: str) -> Path:
    # build-tools 的 d8/apksigner 启动脚本依赖 JAVA_HOME / PATH 找到 java
    os.environ["JAVA_HOME"] = str(jdk)
    os.environ["PATH"] = str(jdk / "bin") + os.pathsep + os.environ.get("PATH", "")
    javac = jdk / "bin" / "javac.exe"
    keytool = jdk / "bin" / "keytool.exe"
    bt = sdk / "build-tools" / BUILD_TOOLS
    d8 = bt / "d8.bat"
    aapt2 = bt / "aapt2.exe"
    zipalign = bt / "zipalign.exe"
    apksigner = bt / "apksigner.bat"
    android_jar = sdk / "platforms" / PLATFORM / "android.jar"
    for f in (javac, keytool, d8, aapt2, zipalign, apksigner, android_jar):
        if not f.is_file():
            raise SystemExit(f"缺少构建组件：{f}")

    if BUILD.exists():
        shutil.rmtree(BUILD)
    BUILD.mkdir(parents=True)
    DIST.mkdir(parents=True, exist_ok=True)
    ensure_icon()

    manifest = stage_manifest(version_code, version_name)
    assets_dir = stage_assets()
    log(f"assets 体积 {sum(f.stat().st_size for f in (assets_dir / 'www').rglob('*') if f.is_file()) / 1048576:.1f} MB")

    # 1) javac
    classes = BUILD / "classes"
    classes.mkdir()
    java_files = sorted(str(p) for p in SRC.rglob("*.java"))
    run([str(javac), "-source", "8", "-target", "8", "-encoding", "UTF-8",
         "-bootclasspath", str(android_jar), "-d", str(classes), *java_files])

    # 2) d8 → classes.dex
    dex = BUILD / "dex"
    dex.mkdir()
    class_files = sorted(str(p) for p in classes.rglob("*.class"))
    if not class_files:
        raise SystemExit("javac 未产出 class 文件")
    run(as_cmd(d8, "--release", "--min-api", MIN_SDK, "--lib", str(android_jar),
               "--output", str(dex), *class_files))
    if not (dex / "classes.dex").is_file():
        raise SystemExit("d8 未产出 classes.dex")

    # 3) aapt2 compile / link
    res_zip = BUILD / "res.zip"
    run([str(aapt2), "compile", "--dir", str(RES), "-o", str(res_zip)])
    unsigned = BUILD / "unsigned.apk"
    gen = BUILD / "gen"
    gen.mkdir()
    run([str(aapt2), "link", "-o", str(unsigned), "-I", str(android_jar),
         "--manifest", str(manifest), "-A", str(assets_dir),
         "--java", str(gen), "--min-sdk-version", MIN_SDK, "--target-sdk-version", TARGET_SDK,
         "--version-code", str(version_code), "--version-name", version_name, str(res_zip)])

    # 4) 把 classes.dex 写进 APK（aapt2 不处理 dex）
    with zipfile.ZipFile(unsigned, "a", zipfile.ZIP_DEFLATED) as zf:
        zf.write(dex / "classes.dex", "classes.dex")

    # 5) zipalign
    aligned = BUILD / "aligned.apk"
    run([str(zipalign), "-p", "-f", "4", str(unsigned), str(aligned)])

    # 6) 签名
    keystore = KEYSTORE
    if not keystore.is_file():
        run([str(keytool), "-genkeypair", "-keystore", str(keystore), "-alias", "seerpeak",
             "-keyalg", "RSA", "-keysize", "2048", "-validity", "10000",
             "-storepass", "android", "-keypass", "android",
             "-dname", "CN=Seer Peak, OU=DSH, O=Local, L=Local, ST=Local, C=CN"])
    out = DIST / "SeerPeak.apk"
    run(as_cmd(apksigner, "sign", "--ks", str(keystore), "--ks-key-alias", "seerpeak",
               "--ks-pass", "pass:android", "--key-pass", "pass:android",
               "--out", str(out), str(aligned)))
    run(as_cmd(apksigner, "verify", "--print-certs", str(out)))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sdk-root", default=None)
    ap.add_argument("--jdk", default=None)
    ap.add_argument("--version-code", type=int, default=VERSION_CODE)
    ap.add_argument("--version-name", default=VERSION_NAME)
    args = ap.parse_args()
    start = time.time()
    jdk = find_jdk(args.jdk)
    sdk = find_sdk(args.sdk_root)
    log(f"JDK  {jdk}")
    log(f"SDK  {sdk}")
    out = build(jdk, sdk, args.version_code, args.version_name)
    log(f"完成 {out}  {out.stat().st_size / 1048576:.1f} MB  {time.time() - start:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())