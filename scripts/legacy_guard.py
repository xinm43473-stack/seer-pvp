"""一次性历史脚本守卫（2026-11-08 全量审计）

2026-11-05~11-07 期间写过一批「一次性修复脚本」，它们把当时的常量全量写回
数据层。此后数据层又经历了特色定位词表重定、关系层审核修补、社区线索扩充、
757 条历史留痕口径确立等改动；这些老脚本若被重跑，会把新数据覆盖回旧值：

  apply_tree_sea_system.py / restore_sanxie.py / build_dataset.py 重跑后
  check_roster.py 直接报错（旧定位词、丢失的 section、收录留痕被重建）；
  apply_relation_completion.py / apply_community_leads.py 会把已订正的机制
  说明与 13 条线索回退；build_overrides.py 会把 roles 改回旧词表。

因此由 references/catalog/schema_state.json 登记「已被取代的脚本」，默认重跑直接
跳过（退出码 0，不写任何文件）；确需重建时显式加 --force。

用法（在被守卫脚本的 main() 首行）：
    from legacy_guard import guard_legacy
    guard_legacy(__file__)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "references" / "catalog" / "schema_state.json"


def guard_legacy(script_path: str, *, force_flag: str = "--force") -> bool:
    """返回 True 表示允许继续执行；否则打印说明并 SystemExit(0)。"""
    name = Path(script_path).name
    if force_flag in sys.argv:
        print(f"[legacy] --force：{name} 强制执行（可能把数据层回退到旧版，请自行复核）")
        return True
    if not STATE_PATH.exists():
        return True  # 没有最终态标记时保持旧行为（便于从零重建）
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return True
    if name not in state.get("superseded_scripts", []):
        return True
    print(f"[legacy] {name} 已由后续改动取代，默认跳过以免回退数据层。")
    print(f"         原因：{state.get('note', '见 references/catalog/schema_state.json')}")
    print(f"         确需重跑：python scripts/{name} --force")
    raise SystemExit(0)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("legacy_guard 是库模块，请在被守卫脚本的 main() 里调用 guard_legacy(__file__)。")
