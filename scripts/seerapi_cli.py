#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用官方 seerapi CLI 复核本项目数据（单条核查通道）

背景：用户 2026-11-06 指出 GitHub 的 SeerAPI/seerapi 自带 **seerapi-cli skill**。
官方 skill 已安装到 ``~/.workbuddy/skills/seerapi-cli``（命令：
``seerapi skill install --target ~/.workbuddy/skills``），标准工作流是
``resources`` → ``describe`` → ``get/list/get-by-name``，输出为 stdout JSON。

本项目里两条通道的分工：
  * **单条人工核查 / 争议复核** → 本脚本，走官方 CLI（数据源权威、字段最全）
  * **批量落盘（133 只魂印、全部技能）** → fetch_seerapi.py / fetch_seerapi_media.py
    （一次进程内 HTTP 批量，CLI 每次启动约 2.5s，不适合 2000+ 次调用）

用法:
  python scripts/seerapi_cli.py --pet 4364
  python scripts/seerapi_cli.py --soulmark 410
  python scripts/seerapi_cli.py --skill 17908
  python scripts/seerapi_cli.py --pool
  python scripts/seerapi_cli.py --verify     # 生成本地 vs CLI 复核报告

注意：``seerapi`` 由系统 Python 3.14 提供；项目脚本跑在 WorkBuddy 自带
Python 3.13 上，不要 ``from seerapi import ...``，一律走 CLI 子进程。
"""
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "references"
DATA = ROOT / "data"
TAG_RE = re.compile(r"<[^>]+>")

# 官方池 ID → 本项目 official_pool.json 的键
POOL_MAP = {0: "ban", 2: "limit", 3: "semi_limit"}


def cli(*args):
    """执行 seerapi CLI，返回解析后的 JSON；失败时抛出带 stderr 的错误。"""
    # 官方客户端会在 cwd 写 .cache/hishel HTTP 缓存；改到系统临时目录，
    # 避免污染项目目录（否则每次核查都会多出一个 .cache，打包时还得排除）。
    proc = subprocess.run(["seerapi", *args], capture_output=True,
                          text=True, encoding="utf-8",
                          cwd=tempfile.gettempdir())
    if proc.returncode != 0:
        raise RuntimeError("seerapi %s 失败 (exit %d): %s" % (
            " ".join(args), proc.returncode, (proc.stderr or "").strip()[:400]))
    return json.loads(proc.stdout)


def clean(text):
    if not text:
        return ""
    text = TAG_RE.sub("", text.replace("\r\n", "\n"))
    return "\n".join(x.strip() for x in text.split("\n") if x.strip())


def show_pet(pid):
    p = cli("get", "pet", str(pid),
            "--fields", "id,name,soulmark,skill,peak_pool,peak_expert_pool,peak_cost_pool")
    print("精灵 %s %s" % (p["id"], p.get("name")))
    print("  池: peak_pool=%s expert=%s cost=%s" % (
        (p.get("peak_pool") or {}).get("id"),
        (p.get("peak_expert_pool") or {}).get("id"),
        (p.get("peak_cost_pool") or {}).get("id")))
    print("  技能 %d 条" % len(p.get("skill") or []))
    for ref in p.get("soulmark") or []:
        s = cli("get", "soulmark", str(ref["id"]))
        print("  魂印 %-5s has_format=%-5s pve=%s" % (
            s["id"], bool(s.get("desc_formatting_adjustment")), s.get("pve_effective")))
        print("    ", (clean(s.get("desc_formatting_adjustment"))
                       or clean(s.get("desc")))[:160].replace("\n", " / "))
    return p


def show_soulmark(sid):
    s = cli("get", "soulmark", str(sid))
    print("魂印 %s | has_format=%s | pve_effective=%s | intensified=%s" % (
        s["id"], bool(s.get("desc_formatting_adjustment")),
        s.get("pve_effective"), s.get("intensified")))
    print("精灵:", [x["id"] for x in (s.get("pet") or [])])
    print("--- desc (分析简版) ---")
    print(clean(s.get("desc")))
    print("--- desc_formatting_adjustment (游戏内结算文本，当前版才有) ---")
    print(clean(s.get("desc_formatting_adjustment")) or "(无)")
    return s


def show_skill(sid):
    s = cli("get", "skill", str(sid))
    print("技能 %s %s | 威力 %s | 先制 %s | PP %s" % (
        s["id"], s.get("name"), s.get("power"),
        s.get("priority"), s.get("max_pp")))
    for e in s.get("skill_effect") or []:
        print("  • [%s] %s  args=%s" % (
            (e.get("effect") or {}).get("id"), e.get("info"), e.get("args")))
    return s


def show_pool():
    out = {}
    for pid, key in POOL_MAP.items():
        d = cli("get", "peak_pool", str(pid))
        ids = [x["id"] for x in (d.get("pet") or [])]
        out[key] = ids
        print("%-10s count=%-2s %s ~ %s | %d 只" % (
            key, d.get("count"), d.get("start_time"), d.get("end_time"), len(ids)))
        print("   ", ids)
    return out


def verify():
    """本地关键数据与官方 CLI 逐项比对，输出 references/catalog/seerapi_cli_audit.json。"""
    report = {
        "generated_at": time.strftime("%Y-%m-%d"),
        "channel": "seerapi CLI (bundled seerapi-cli skill, SeerAPI/seerapi)",
        "cli_version": subprocess.run(["seerapi", "-V"], capture_output=True,
                                      text=True, encoding="utf-8",
                                      cwd=tempfile.gettempdir()).stdout.strip(),
        "checks": [],
        "verdict": "pass",
    }

    def check(name, ok, detail):
        report["checks"].append({"name": name, "ok": bool(ok), "detail": detail})
        if not ok:
            report["verdict"] = "needs_attention"
        print("%s %-42s %s" % ("OK " if ok else "!! ", name, detail))

    # 1) 官方池期次与成员
    local_pool = json.loads((REF / "catalog" / "official_pool.json").read_text(encoding="utf-8"))
    for pid, key in POOL_MAP.items():
        d = cli("get", "peak_pool", str(pid))
        ids = sorted(x["id"] for x in (d.get("pet") or []))
        mine = sorted(local_pool["pools"][key]["ids"])
        check("官方池 %s 成员一致" % key, ids == mine,
              "CLI %d 只 / 本地 %d 只%s" % (
                  len(ids), len(mine),
                  "" if ids == mine else " 差集 %s" % (set(ids) ^ set(mine))))
    check("官方池期次一致",
          str(d.get("start_time")) == str(local_pool["period"]["start"]),
          "CLI %s / 本地 %s" % (d.get("start_time"), local_pool["period"]["start"]))

    # 2) 关键魂印的当前版判定（has_format 优先于文本长度）
    for sid, expected in [(410, 3056), (1588, 4364), (2080, 4364)]:
        s = cli("get", "soulmark", str(sid))
        has_fmt = bool(s.get("desc_formatting_adjustment"))
        check("soulmark %s 归属 %s" % (sid, expected),
              expected in [x["id"] for x in (s.get("pet") or [])],
              "has_format=%s（True=当前生效版）" % has_fmt)
    s1588 = cli("get", "soulmark", "1588")
    s2080 = cli("get", "soulmark", "2080")
    check("4364 当前版 = 1588（而非更长的 2080）",
          bool(s1588.get("desc_formatting_adjustment"))
          and not s2080.get("desc_formatting_adjustment"),
          "1588 has_format=%s / 2080 has_format=%s" % (
              bool(s1588.get("desc_formatting_adjustment")),
              bool(s2080.get("desc_formatting_adjustment"))))

    # 3) 3056 机盖魂印措辞：限定「100 级 + 致死伤害 + 所受技能伤害」
    s410 = cli("get", "soulmark", "410")
    desc410 = clean(s410.get("desc"))
    local_soul = json.loads((DATA / "seerapi/soul_full.json").read_text(encoding="utf-8"))["souls"]["3056"]
    check("3056 本地魂印含「真实伤害」", "真实伤害" in local_soul.get("text", ""),
          "CLI desc 头部: %s" % desc410[:70])
    check("3056 本地魂印注明「100 级」触发条件",
          "100" in local_soul.get("text", "") or "100级" in local_soul.get("text", ""),
          "CLI desc 明确「若自身的等级为100级」")

    # 4) 诛魔杀阵：三段效果 + 圣光灵神持有
    sk = cli("get", "skill", "17908")
    effects = [x.get("info") for x in (sk.get("skill_effect") or [])]
    check("技能 17908 效果条数 = 3", len(effects) == 3, " / ".join(effects))
    pet3311 = cli("get", "pet", "3311", "--fields", "id,name,skill")
    owned = [x["skill"]["id"] for x in (pet3311.get("skill") or [])]
    check("圣光灵神 3311 持有 17908", 17908 in owned,
          "3311 技能表 %d 条；learned_by_pet 反查为空是 API 索引缺口" % len(owned))
    lib = json.loads((DATA / "seerapi/skills_full.json").read_text(encoding="utf-8"))
    check("本地技能库已收录 17908", "17908" in lib["skills"],
          "当前技能库 %d 只精灵 / %d 条技能" % (len(lib["elves"]), len(lib["skills"])))

    out = REF / "catalog" / "seerapi_cli_audit.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print("-> %s | verdict=%s" % (out, report["verdict"]))
    return report


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return
    if "--verify" in args:
        verify()
    elif "--pool" in args:
        show_pool()
    elif "--pet" in args:
        show_pet(args[args.index("--pet") + 1])
    elif "--soulmark" in args:
        show_soulmark(args[args.index("--soulmark") + 1])
    elif "--skill" in args:
        show_skill(args[args.index("--skill") + 1])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
