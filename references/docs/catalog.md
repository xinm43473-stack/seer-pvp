# 数据层总览

本技能有三层精灵数据，**不要把深研层的 133 只当成全部精灵**。文件归属见 `HANDOVER.md` §4：`data/` 是抓取层（脚本写），`references/` 是业务层（人维护、程序读）。

## 1 三层结构

| 层 | 文件 | 数量 | 用途 |
|---|---|---|---|
| 全量图鉴层 | `data/bwiki/pool.json#elves` | **1203 只**（ID 2987–4950，全部有魂印） | 查魂印全文、六维、机制标签、克制面、机制文本复杂度；任意精灵都能查 |
| 历史筛选留痕 | `data/bwiki/pool.json#dropped` | **757 只**（每条带原因） | **只作历史留痕，不作判断依据** |
| 深研战术层 | `references/catalog/roster.json#spirits` | **133 只** | 人工逐只写定位、魂印拆解、联动、出场顺序、BP 成本与失效点；阵容与强度结论优先用这一层 |
| 候选池 | `roster.json#pending_research` ＋ `candidates.md` | **94 条** | 用户点名／UP 主专题等待深研；**不得直接推荐** |
| 隐藏精灵库 | `data/derived/spirit_library.json` | **1977 只** | 前端「＋」添加来源，默认不显示 |
| 资料层 | `data/seerapi/spirit_media.json` | **230 只**（魂印各版本 289、技能 4488、图像 642） | 只读机制与图像资料，不参与收录／强度／联动判断 |

## 2 判断与口径层

| 层 | 文件 | 规模 | 要点 |
|---|---|---|---|
| 人工强度层 | `references/catalog/strength.json` | 1 只已评 ＋ 56 个偏差位 | **唯一可引用的强度层**；未核写「未评级（不推断）」 |
| 体系 | `references/systems/*.json`（真源）＋ `catalog/systems.json`（聚合） | **21 项 / 34 条显式边** | 只认正文写出资源交接／先后／互相放大的显式边；成员名单与 `alternatives` 不是联动 |
| 链路审计 | `catalog/chain_audit.json` | 34 条边 → **68 个双向对**；24 条互证联动声明 | 按 `chain_edges` 生成，逐条带 `source_field` 与分级 |
| 旧声明归档 | `catalog/historical_leads.json` | 418 条 | 查询、前端、推荐一律不读 |
| 撤销边 | `catalog/retired_edges.json` | 3 条 | 只表示「不构成同队联动」，不删精灵 |
| 相似定位 | `catalog/role_groups.json` ＋ `core_roles.json` | **4 组**；词表一级 6 类 | 只收共享同一可辨识结算机制的 2-3 只；**不是配合、不是上位替代** |
| 全量复查 | `catalog/full_audit.json` | 227 只 / 21 体系 / 24 链路 | 逐只证据标记、冲突与复核优先级；**复核队列不是强度榜** |
| 深研深度 | `catalog/depth_audit.json` | 17/133 完整链 | 一句话占位 `play` 不算深研 |
| 状态补核 | `catalog/soul_expansions.json` | 7 条 | BWIKI 只写状态名时，按「效果IDs」追技能页核出的原文 |
| 强化形态 | `catalog/advance_forms.json` | 22 只 | 强化后换过魂印的精灵；前版文本由 `rebuild_view.sync_soul_versions()` 从资料层取，缺的 4 只写在本文件里 |
| 主题覆盖 | `catalog/creator_index.json` | 119 只专题／46 在深研层 | 收录唯一依据；提及层已删除 |
| 来源白名单 | `catalog/source_markers.json` | 78 个标记 | 新增来源标记只改这里 ＋ `sources.md` |
| 编辑字段注册表 | `catalog/editor_schema.json` ＋ `scripts/editor_schema.py` | schema 3.2 / 13 字段 | 字段、词表、上限的唯一来源；前端动态渲染，校验脚本共用 |
| 脚本守卫 | `catalog/schema_state.json` ＋ `scripts/legacy_guard.py` | 11 个 | 重跑会回退数据层的一次性脚本，默认跳过 |

ID 覆盖：2987–4950 共 1964 个序号，已记录 1960 个；跳号 3085／3431／4399／4543 为官方未使用或数据缺号，非遗漏。

## 3 查询方式

```bash
python scripts/query.py 至序圣华 --full     # 魂印全文 / 六维 / 标签 / 克制面 / 技能
python scripts/query.py --id 4321 --full
python scripts/query.py --tag 复活 驱逐      # 按机制标签
python scripts/query.py --attr 混沌
python scripts/query.py --tier T0 T1        # 机制文本复杂度分档（非强度）
python scripts/query.py --strength          # 人工强度评级与官方限制池
python scripts/query.py --audit 机盖        # 单只评级依据、证据、冲突、优先级
python scripts/query.py --system 猫阵       # 成员、显式边、并列位、证据等级与章节
python scripts/query.py --role 机盖         # 相似定位（同类机制位，不是配合）
python scripts/query.py --media 机盖        # 魂印各版本、完整技能表、图像路径
```

前端入口：`references/spirit_synergy_view.html`（双击打开）。左侧选精灵，右侧按「同队可配合（显式边）／相似定位／反向对位・BP 对策・组件互斥」分组；没有已核实关系的精灵直接写「暂无已核实关联」。改数据层的链路见 `HANDOVER.md` §5。

## 4 强度与机制复杂度必须分开

`pool.tier / score` 是「种族值归一 ＋ 魂印分句数 ＋ 标签权重 ＋ 越新加权」的百分位排名，衡量**机制文本复杂度**（T0 仅 3 只、T1 140、T2 224、T3 360、T4 476）。它不是强度、不是月榜、不是官方梯度，也不能当强度排序的辅助依据。

典型反例 3056 圣甲·盖亚：种族 680、魂印两段、标签词库没识别「战斗阶段内死亡附加等同伤害的真实伤害」，自动判 T4；但它是官方准限制池成员、联防阵常见组件，用户判定**至少 T1**。系统性偏差集中在反伤／拦截／清 PP／复活／消逝等「机制短但结算强」的功能位。

规则：强度结论只写在 `strength.json`，必须带具体月份竞技图鉴／官方限制池／实战复盘／用户明确判定；强度是带日期的快照。未核一律「未评级（不推断）」，门户 SEO 的胜率／使用率不引用，机制推演只能作线索并标「当月梯度待月榜复核」。

## 5 数据来源与 SeerAPI 通道

前端「全量拉取」的主源是 `api.seerapi.com/v1`（SeerAPI，作者坚果），精灵名单拉不到时退到
`Nattsu39/seer_data` 的 `monsters.json`（H5 客户端配置备份，只含名称／属性／六维，无魂印）；
魂印原文与历史文案以 BWIKI 为准。用户 2026-11-20 给的参考来源：「坚果 / 聿聿 / 醉星河 / 赛尔号WIKI站长」，
分别对应 SeerAPI、H5 JSON 全量备份、技术支持与 WIKI 正文。



主体数据来自 BWIKI，4399 只是备用链接、未实际抓取。`api.seerapi.com/v1` 提供结构化客户端数据，关键字段：`soulmark.desc`（分析简版）、`soulmark.desc_formatting_adjustment`（**只有当前生效版才有**）、`skill.skill_effect[].info`（逐条效果）、`pet.skill`（技能归属正查）。

- **新旧魂印判定**：`has_format` 优先于文本长度（4364 旧版 `desc` 反而更长，但只有新带格式化文本）。规则实现在 `scripts/compare_souls.py`。
- **冲突处理**：BWIKI 与客户端冲突时采信客户端并留痕旧文，来源标 `SA:<ID>`（已确认 3056 `SA:410`、4364 `SA:1588`）。
- **单条核查**：`python scripts/seerapi_cli.py --pet/--soulmark/--skill/--pool/--verify`，输出 `catalog/seerapi_cli_audit.json`。
- **批量抓取**：`scripts/fetch_seerapi.py`；图像走 jsDelivr 镜像并转 WebP 缩略图（`scripts/fetch_seerapi_media.py` 一次拉原始层，`build_spirit_media.py` 离线整理，需先重抓原始层才可用）。
