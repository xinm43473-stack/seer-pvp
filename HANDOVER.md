# seer-peak-pvp · 交接文档

> 快照 2026-11-20｜项目 `E:\seerskill\seer-peak-pvp`｜Skill 镜像 `C:\Users\SHM20\.workbuddy\skills\seer-peak-pvp`
> **本文是唯一交接文档**（原 `STRUCTURE.md`／`OPTIMIZATION.md`／`dist/HANDOVER-archive-*.md` 已并入或删除）。
> 机制正文以 `references/docs/tactics.md` 为准，魂印原文以 `data/seerapi/soul_full.json` 为准。
> **最近一次改动（2026-11-20）**：①拉取改为「每次都取最新」——抓取脚本默认全量重抓、前端每次重建魂印索引、同一只精灵取 id 最大的魂印、拉到的新魂印经覆盖层写进节点 `soul_mark`；②新增 `scripts/sync_latest_soul.py` 把最新魂印同步进展示层（14 只节点由旧版升到加强版，3396 灾厄女神潘多拉 709→2170）。此前同日还做过（已全部回退）：前端改名、魂印「强化前／强化后」开关、拉取覆盖与超时改造、编辑补丁字段白名单。`smoke_test` **54/54**。

---

## 1 项目是什么

《赛尔号：巅峰之战》PvP 精灵资料与战术知识库，打包为 Agent Skill，同时提供一个离线单文件前端。

| 产物 | 路径 | 说明 |
|---|---|---|
| 前端 | `references/spirit_synergy_view.html` | 单文件 11MB，内联全部 DATA，`file://` 双击即用（2026-11-20 由 `spirit_synergy_view.html` 改名） |
| 分发包 | `dist/seer-peak-pvp.zip` | 91.7MB / 4388 项，`testzip` 必须为 `None` |
| Skill 入口 | `SKILL.md` | 速查表与命令；`check_roster.py` 会校验其中的硬编码计数 |

前端形态：左侧精灵列表（头像／名称／序号／评级），右侧「立绘｜定位＋魂印」→ 备注 → 技能表 → 体系画布 → 相似定位。顶部右侧：`编辑器`、`管理体系`（新建／编辑体系都在里面）、`全量拉取`、`备注`（开关，开＝蓝底同全量拉取）。

---

## 2 现状（2026-11-20）

| 项 | 数值 |
|---|---|
| 精灵 | **218 只**，10 档：九星 2／八星 3／七星半 5／七星 10／六星半 38／六星 41／五星半 55／五星 37／四星 19／特殊 8 |
| 体系／显式边／联动声明 | **21 / 34 / 24**（`stats.verified_pairs` 68，双向计） |
| 体系退役记录 | 42 条（`references/systems/index.json#retired_systems`，只留名称，不占计数） |
| 深研层 | `roster.json` 133 只（classes／roles／note／play／sources） |
| 隐藏精灵库 | 1977 只（`DATA.library.spirits`，只作「＋」添加来源，不渲染） |
| 资料层 | 230 只（`DATA.media`）；魂印标签 1595 条；种族值 4951 条；魂印名词 548 条 |
| 强化形态 | 22 只使用强化后魂印／种族值（附录 B）；**前端只显示最新一版魂印，没有版本开关** |
| 体积 | 项目约 221MB＝`assets` 84M ＋ `data` 29M ＋ `references` 14M ＋ `dist` 92M ＋ `scripts` 1M |
| 脚本 | `scripts/*.py` 43 个 ＋ `scripts/history/` 18 个一次性脚本 |

校验必须全绿：`check_roster.py` **0 ERROR**、`editor_schema.py` invariants OK、`audit_mechanics.py` 0 条、`smoke_test.py` **54/54**。

---

## 3 八条口径铁律

1. **收录**：唯一依据是蝶夏Channel（59224295）／不要脸的狗子（287935100）是否出过**配置／攻略专题**（`creator_index.json` → `themed_spirits`）。魂印条数、种族值、自动 `tier/score` 不作判断；作品提及不算；新线索先入 `roster.pending_research` ＋ `references/docs/candidates.md`。**录入 ≠ 推荐**。
2. **三项强制检查**：晋升前写「无上位／有上位但独立价值／有上位则排除」；除自然王 3355 外不录一代精灵王基础形态；2022 年及以前资料只作历史线索并标赛季。
3. **强度**：唯一来源 `references/catalog/strength.json`。证据序＝当月竞技图鉴（B站 UID 271393197）＞官方限制池＞实战复盘／用户判定＞社区口径＞机制推演。`data/bwiki/pool.json` 的 `tier/score` 只是**机制文本复杂度，不是强度**。未核写「未评级（不推断）」，禁编 T 级／胜率／使用率。
4. **同队配合**：只认 `systems.json` 的显式 `chain_edges`，禁止把 `core`/`support` 两两展开；`alternatives` 是并列位；查不到就显示空框。显式边本身即依据，`chain_status=顺序链已核` 只表示「还能给出逐回合顺序」，不是引用门槛。
5. **相似定位**：`role_groups.json` 只收「共享同一可辨识结算机制」的 2-3 只，禁按泛功能位凑组；词表 `core_roles.json` 是唯一口径源，一级 6 类（主力／突破手／拦截／辅助／干扰／特殊）。
6. **名称与序号**：玩家表格**以名称反查库内正式 ID 为准，序号只作参考**（218 行里 30 处笔误，见附录 A）。错别字一律用 `data/derived/spirit_library.json` 正式名覆盖，**禁止造 9000x 占位精灵**。
7. **魂印核验**：短魂印／状态名型机制先查 `soul_expansions.json` 与技能页；BWIKI 旧文与客户端冲突时采信 SeerAPI 客户端版并留痕旧文（`SA:<ID>`）。BWIKI 请求必须浏览器 UA ＋ 同站 Referer，否则 WAF 567。
8. **前端文案**：不得出现「剔除／作废／自动留痕／种族值过低／单条魂印／全量图鉴」。**术语**：连线相关一律叫「连线」，画布上的文本节点叫「备注文本」；代码里的 `note_links`／`.cnote` 等标识保持不变。

---

## 4 目录与边界

```
seer-peak-pvp/
├─ SKILL.md            Skill 入口（速查表＋命令）
├─ HANDOVER.md         本文（唯一交接文档）
├─ references/         ① 业务层：程序读取、人维护
│   ├─ spirit_synergy_view.html            前端产物（内联 DATA）——不要手改逻辑
│   ├─ systems/                   体系真源：一体系一个 <体系名>.json ＋ index.json
│   ├─ catalog/                   口径层：roster／strength／systems 聚合／定位词表／advance_forms／
│   │                             审计结果／editor_schema／manual_overrides
│   └─ docs/                      文档层：tactics／aliases／catalog／sources／candidates
├─ data/               ② 抓取层：脚本用，前端不直接读
│   ├─ bwiki/                     BWIKI 抓取：elves／souls／typeChart／pool
│   ├─ seerapi/                   SeerAPI 抓取：skills(_full)／elf_skills／soul_full／
│   │                             spirit_info／spirit_media／技能缓存
│   └─ derived/                   派生：typechart／spirit_library（1977 只）／soul_terms
├─ assets/seerapi/     前端图片：pet_head／pet_body／pettype／effecticon
├─ scripts/            工具与构建（history/ 内 18 个一次性脚本只留档）
└─ dist/               分发包（不进 zip 内的开发缓存）
```

**两条边界**（2026-11-19 用户口径）：会被 `fetch_*` 覆盖的进 `data/`，供前端／校验读取的进 `references/`。新增文件先想清楚属于哪一区。

**两条铁律**：

1. **体系改 `references/systems/<体系名>.json`** → `merge_systems.py` → `rebuild_view.py`。
   `references/catalog/systems.json` 是聚合产物，手改会被下次 merge 覆盖。
2. **前端逻辑改 `scripts/synergy_view_template.html`** → `rebuild_view.py`。
   `references/spirit_synergy_view.html` 是产物，直接改逻辑会在下次重建时丢失。

**内联 DATA 只有一个读写入口**：`scripts/viewdata.py`（`read`／`parse`／`save_payload`／`build`）。以前 `rebuild_view`／`check_roster`／`editor_schema`／`recover_local_storage` 各写一遍「切字符串 → `json.loads`」和「`json.dumps` → 拼回整文件」，口径已漂移过；现在**不要再在别处切 `const DATA = `**。

---

## 5 三条日常链路

### A 只改前端样式／逻辑

```bash
# 改 scripts/synergy_view_template.html
python scripts/rebuild_view.py      # 新模板 + 当前 DATA → 新 HTML（自动同步 systems/）
```

`rebuild_view.py` 会重算 `DATA.systems`／`edges`／`stats`（systems、explicit_edges、verified_pairs、verified_synergies、media_*、archived_leads）与 `attr_types`／`soul_tags`，并执行 `sync_editor_schema`／`sync_spirit_profile`／`sync_library_skills`／`sanitize_soul_markup`。原文件备份到系统临时目录（`--backup-dir` 可改）。开关：`--only-existing-systems`、`--no-sync-systems`。

### B 改一个体系

```bash
# 改 references/systems/<体系名>.json（或前端体系管理里改后导出覆盖）
python scripts/merge_systems.py     # 单文件 → references/catalog/systems.json
python scripts/rebuild_view.py      # 聚合 → 前端内联
python scripts/check_roster.py      # 0 ERROR 才算完
```

体系文件首键 `$schema: "seer-system/1"`，字段：`key/name/aliases/core/support/counter/kind/evidence/sources/section/carrier/status/evidence_grade/chain_status/chain_review/chain_edges/alternatives/review_note/warning_edges/edge_meta/canvas/body`。`index.json` 只放元信息与 `order`。

### C 加精灵／改精灵数据

单个精灵：优先在前端编辑面板改并导出补丁；或直接改内联 `const DATA`（走 `viewdata`，注意 CRLF）。改完跑 A 的第二步。

批量刷新：顶部「全量拉取」走 SeerAPI 分页接口，**每次点击都全量重抓**（魂印索引每次重建、同一只精灵取 id 最大的魂印＝最新结算文本）；新序号只进库（1977 只隐藏源），已录入的 218 只**只覆盖魂印**（写进 `localStorage[…]_raw` 覆盖层，重建节点时叠到 `soul_mark`，其它字段不动）；拉完从列表底部「＋」逐只添加。图像随拉取一并下载并缓存进 IndexedDB。

命令行侧同一件事（先抓、再同步、再重建）：

```bash
python scripts/fetch_seerapi.py --all-deep   # 默认全量重抓（--skip-existing 才是旧行为）
python scripts/sync_latest_soul.py --dry-run # 看哪些精灵的魂印有新版
python scripts/sync_latest_soul.py           # 写进 spirit_library／spirit_info／内联 DATA
python scripts/rebuild_view.py
```

### 禁跑／不可跑

| 脚本 | 状态 |
|---|---|
| `build_synergy_view.py` | **禁跑**。按旧口径（227 只／62 体系）整页覆盖，并把已退役体系灌回前端 |
| `build_spirit_library.py`／`build_soul_terms.py`／`build_spirit_media.py`／`import_spirit_info.py` | **不可跑**。依赖的 160MB 原始层 `data/seerapi_media/raw/` 已删，要重跑必须先 `fetch_*` 重抓 |
| `scripts/history/*`（18 个） | 一次性脚本，`legacy_guard.py` 按 `schema_state.json` 默认跳过；`--force` 会回退数据层 |

**库里某只技能为空**别去动 `build_*`，跑 `python scripts/fetch_missing_skills.py`（HTTP 增量补，见 §8）。

---

## 6 前端结构

| 区块 | 关键函数／id | 说明 |
|---|---|---|
| 列表 | `#list`、`renderList()`、`filtered()` | 四列栅格：头像／名称／#id／评级；底部 `＋` 打开精灵库 |
| 详情 | `#hero`、`renderHero()` | 立绘叠名称评级 → 三行种族值（总和高亮）→ 魂印（只渲染最新一版；默认封顶 360px，「展开全文」）＋名词圆环 → 技能表 |
| 体系画布 | `#systemsView`、`renderSystems()`、`graphView()` | `canvas.nodes` 保形缩放；`canvas.notes` 放并列位／待核说明；`canvas.skills` 随同一套缩放平移 |
| 体系管理画布 | `#sysCanvas`、`drawGraph()`、`drawEdges()` | 三类节点：精灵卡 `graph.nodes`、技能卡 `graph.skills`（`s:精灵:sid`）、备注文本 `graph.notes`（`n<base36>`）；三类都能当连线端点，一律按字符串比较 |
| 相似定位 | `#roles`、`renderRoles()` | 卡片可编辑备注；「编辑」走 `libContext="role"` |
| 筛选 | `#btnFilter` → `#filterPanel`、`FILTER` | 属性（含口径开关 `attrStrict`）／定位（词表 6 类＋数据里的自定义特色，任一命中）／魂印标签／评级 |
| 标签浮层 | `#tagPeek`、`openTagPeek()` | 同标签只读列表 ＋「左侧只显示列表内同标签」开关 `tagOnly` |
| 精灵库 | `#libModal`、`LIB_FILTER`、`libMatched()` | 搜索＋筛选＋只看未添加＋序号排序；首屏 80 ＋加载更多 |
| 编辑 | `#editModal`、`openEditor()` | 字段由 `DATA.editor.schema` 驱动 |
| 拉取 | `#btnPullAll` | SeerAPI 分页 CORS 直连；只入库不进列表 |
| 主题 | `#btnTheme`、`applyTheme()` | `<html data-theme>`，键 `seer_peak_view_theme` |
| 画布缩放 | `.gzoom`、`applyGraphZoom()`、`#sysStage`、`sysZoom` | 详情图用 CSS `zoom` 缩 `.ginner`；编辑器用 `transform:scale()` 缩 `#sysStage` |

节点字段：`k/id/name/attr/main/layers/tier/strength/audit/note/aliases/systems/rating/key_skills/soul_mark/portrait/skills/custom_fields/rel_count/library_added/system_keys`。`strength` 必须是对象；`rating` 是展示档位，与 `strength.grade` 无关。

**几何与层级只有一处定义**：`:root` 的 `--node-w/h`（图鉴）与 `--card-w/h`（编辑器）都是 **110×112**，`--sk-w/h` 是 **212×64**；三张卡片 `height` 绑变量 ＋ `overflow:hidden`。`GEO` 读同一份值，`editCx/editCy` 与 `nodeCx/nodeCy` 取一半（**两边中心必须同点**）。层级 `--z-edge/--z-note/--z-skill/--z-label/--z-node/--z-hover/--z-active` ＝ 1/2/3/4/5/6/8。

---

## 7 改前端前必须知道的硬约束

- **连线笔型只有一份**：`LINK_PEN`（`pet` 2、`skill` 1.5／`5 3`、`note` 1.4／`2 4`、`lead` 1／`3 3`、`temp` 2／`5 4`）。CSS 只负责颜色／透明度／交互，不写 `stroke-width`／`stroke-dasharray`；每条线带 `data-pen`，由 `rescaleLinks()` 写内联样式。
- **缩放必须反补偿**：`transform:scale()` 与 CSS `zoom` 会把描边和虚线一起缩小，`rescaleLinks(root, zoom)` 按 `1/zoom` 反算内联值，`applySysZoom()`／`applyGraphZoom()` 各调一次。**别用 `calc(2px / var(--lz))`**——Chrome 不会重算已有 SVG 元素的描边。
- **viewBox 必须与 SVG 的 width/height 属性逐像素相等**：`drawEdges()` 里三处同值写 `needW/needH`，`#sysLinks` **不能写 CSS `width:100%`**（不等时浏览器会把整层等比缩小并居中，线整体偏移）。
- **几何与判定各只一处**：`edgeSegment(a,b)`＝卡片中心引射线 ∩ 卡片矩形，再各留 `GEO.edgeGap`（5px，短线段按长度×0.15 收敛）；`edgeModels(edges, endsOf, skillPetOf)` 统一产出 `{kind, own, seg}`，编辑器与图鉴都走它，三类边都内缩。图鉴是拼字符串渲染，备注文本宽度用 `measureNotes()` 先在隐藏容器量。**别再回到固定内缩**（`min(56, 长度×0.32)` 会把短连线削断）。
- **短文本不给 `min-width`**：`.cnote`／`.clabel`／`.glabel` 都是 `min-width:0;width:max-content`（否则「二选一」后面拖一长条空白）。备注气泡 `--glass` 背景、`max-width:220px`、锚点 `seg.mx/my - 12`。
- **技能表不用固定列宽**：开关「只显示重点技能」在表头 `.skillhead`，表格 `width:100%` 自适应；再给 `min-width` 会超出容器被裁。
- **魂印长文本封顶**：`.soul` `max-height:min(46vh,360px)` ＋ 内部滚动，`syncSoulToggle()` 判溢出后才显示「展开全文」。
- **连线备注存哪**：精灵↔精灵进 `edge_meta`（键 `a-b`）；技能卡线／备注文本线进 `canvas.link_notes`（键 `a|b`）。`note_links[].note` 只作旧文件兼容读取。
- **线色**：右键线→「设置线条颜色」，10 色＋自定义；存 `canvas.edge_colors`，键为排序后 `a|b`（三类边共用），未设色不写字段。实现是内联 `--ec/--ec-h`，CSS `stroke:var(--ec,var(--edge))`；图鉴 `.gsvg` 同机制回放。
- **三类边必须分流**：精灵↔精灵→`chain_edges`/`edge_meta`；技能卡→`canvas.skill_links`；备注文本→`canvas.note_links`。混写会让 `check_roster` 把 `n…`／`s:…` 当精灵 id 报错。
- **备注文本参与变换**：`graphLayout()` 的包围盒 `bx/by` 要同时取节点、技能卡、备注文本；只按节点算会让左上备注文本变负坐标被裁。删备注文本要同步删线。
- **属性筛选**：`attrFilterHit(attrText, want, strict)`，最多选 2 个。宽松（默认）＝`[...want].every(a => parts.includes(a))`；严格＝`parts.length === want.size && parts.every(...)`。口径存 `localStorage[EDIT_KEY + "_attr_strict"]`。切开关只原地改 `aria-checked`／`.on`，**不重绘面板**（重绘会让点击目标脱离文档，被外点关闭逻辑误判）。
- **魂印标签筛选**：多选＝同时包含（`every`）；跨维「且」，条件以 `.fchip` 显示。`tagOnly` 只收窄左侧列表，不加节点。
- **「只看未添加」与「只看左侧列表」是同一开关**：列表模式挡已加入的；`libContext="role"` 时只留左侧那批，本组成员恒保留并顶置。
- **属性技能用专属图标**：`skill_category=4` 的 `type` 一律是占位「普通」，必须走 `skillAttrChipHtml()` → `pettype/prop.png`。**双属性只画一枚组合图标**（`DATA.attr_types` 139 条），`attrParts()` 先 `replace(/^[\s·・/、,，+]+/)` 再匹配。
- **技能卡只放摘要**，效果文本浮出 `.sktip`（可钉住）；精灵与自己技能卡的线是 `.clink.own`（`#f59e0b` 2.2px）。
- **技能选择器**：轻点＝默认位置添加并关闭；拖动 >8px 或按住 220ms＝浮层跟随，松手落画布。跟手用 `left/top`（`translate3d` 会被缓存），`pointermove` 里**先判 `pickGhost` 再判 `pickPress`**。
- **重点技能只认 `key_skills`**：`keyStateOf(n)` ＋ `isKeySkill()`，判定式就是按名称命中，**没有第二条通路**；第五／神谕／特训只影响 `orderedSkills()` 的展示档位，不再自动算重点（曾导致 218 只里 54 只编辑与显示不一致）。
- **技能表顺序**：`orderedSkills()` 三处共用（图鉴技能表、技能卡选择器、编辑面板「重点技能」候选）。档位＝重点（按 `key_skills` 顺序）→ 第五 → 神谕 → 特训 → 其余，同档内按源顺序**倒序**（学习等级升序 → 高等级在前）。不要整表 `reverse()`。
- **定位只有一组**：界面「定位」＝6 大类词表 ＋「特色」自定义文本。数据层仍写 `classes`／`roles`，`splitRoleTags()` 自动分流，图鉴与筛选用 `roleTagsOf(n)` 合并读。**`classes` 必须留在 schema fields 里（`hidden:true`）**，删了会把用户选的分类丢掉；`roles` 的校验器是 `_validate_roles()`。
- **备注只有一处**：`roster[*].note`＝实战备注＋核心机制合并文本（2026-11-18 一次性迁移，脚本已退役）；`mechanics`／`editor_note` 只作历史兜底。
- **软删除是「标记」不是「删节点」**：`deletions[id]` 写 localStorage，节点始终留在 `DATA.nodes`（画布、体系、连线都还要用它）。所以
  - **「在不在左侧列表」只认 `inListOf(k)`**（存在且未删除）。库面板的「已添加／添加」、`libOnly`「只看未添加」、重复添加拦截、标签浮层跳转、hash 选择全走它；直接写 `!!nodeOf(k)` 就是 2026-11-19 那个 bug——删掉的精灵在库里永远显示「已添加」、点了也没反应。
  - 加回列表统一走 `ensureInList(id)`：`present`／`restored`（清删除标记）／`added`（写 `library.adds`）／`none`（无魂印），别再各写一份。
  - 编辑面板的按钮在已删时是「恢复精灵」；不需要再手动去清 `DATA.library.adds`。
- **魂印只显示最新一版**：图鉴正文走 `soulBlockHtml(n)` → `soulOf(n)`（`soul_mark` → 资料层 primary → 库魂印），名词档位用 `resolveTermMode(这段文本)` 解析。2026-11-20 起**不提供「强化前／强化后」切换**：曾经的 `soul_prev`／`soul_prev_id`／`advance` 已被 `rebuild_view.strip_soul_versions()` 每次重建清掉，别再往节点上写这三个字段（老补丁／旧 DATA 里出现也要清，否则会被误读成「还有一版没显示」）。
- **「最新版」怎么算（2026-11-20）**：同一只精灵在 SeerAPI 会挂多条魂印，**老版在前、新版在后（id 递增）**，所以最新＝id 最大的那条。三处必须同一口径：`petRow()` 的 `newestSoul()`（前端拉取）、`build_spirit_library.soul_rows()`／`build_spirit_media` 的 `primary`（「有 `has_format` 优先，否则 id 最大」——**不能退化成 `out[0]`**，那是老版）。
- **拉取必须每次重建魂印索引**：`loadPullSouls(btn, true)` 清 `SOUL_MAP` 重拉；以前 `if(SOUL_MAP.size) return` 会让同一次会话的第二次拉取沿用旧文本。
- **218 只的魂印覆盖层**：内联 `DATA.media` 是构建期快照，游戏后补的魂印不在里面。拉取把结果存 `localStorage[EDIT_KEY + "_raw"]`（`rawSoul`，`{sid, soul}`），`applyLibraryAdds()` 重建节点时写进 `soul_mark`；`effective()` 的编辑补丁仍压在上面。**别直接改 `BASE_NODES`**——每次 `applyLibraryAdds()` 都会从它克隆。
- **离线同步脚本**：`sync_latest_soul.py` 只升级「还在显示旧版」的精灵（`soul_mark` 为空，或与 `DATA.media` 主版文本一致）；已经不一样的（如 22 只强化形态按强化后版本核过的）一律不动，所以可反复跑、幂等。拉取拿到的永远是最新结算文本，与这条口径一致。
- **本地缓存**：`STORAGE = "seer_peak_view_edits_v3_r2"`（`_r2` 隔离旧值）；拉取缓存 `…_pulled`，覆盖层 `…_raw`。

---

## 8 数据与资源

- **体系单一真源** `references/systems/`；`catalog/systems.json` 是聚合产物。前端导入／导出与单文件格式互通。
- **隐藏库** `data/derived/spirit_library.json` 1977 只（`id/name/attr/soul/soulmarks/avatar/portrait/skills`），内联为 `DATA.library.spirits`，只用于「＋」添加与筛选。
- **头像** `assets/seerapi/pet_head/{id}.webp`（1969 只，200×200 WebP q82）。**不要走 `seerh5.61.com/pet/head`**（id 不对齐，5 只共用占位图）；立绘 `/fightResource/pet` 对得上。
- **属性图标** `pettype/{单属性 id}.png`：草 1／水 2／火 3／飞行 4／电 5／机械 6／地面 7／普通 8／冰 9／超能 10／战斗 11／光 12／暗影 13／神秘 14／龙 15／圣灵 16／次元 17／远古 18／邪灵 19／自然 20／王 221／混沌 222／神灵 223／轮回 224／虫 225／虚空 226；26 个基础 ＋ 组合共 140 个文件。
- **技能字段**：`e` 只放实际效果（`effects`），`d` 放战报描述（`info`），不能混。
- **库里技能为空**：只补一次 `python scripts/fetch_missing_skills.py`（只补空的、不覆盖已有，产出与 `skill_rows()` 同格式，并同步 `skills.json`／`elf_skills.json`），补完必须 `rebuild_view.py`（`sync_library_skills()` 才会写进内联库）。
- **魂印文本不许带 `[sprite …]`**：`sanitize_soul_markup()` 每次重建自动清洗 `nodes[].soul`／`soul_mark`／`library[].soul`，新增魂印字段时要纳入这一步。
- **魂印名词** 548 条分 `ex`（专属）／`eff`（效果）／`timing`（时点）；找不到官方释义不编。
- **强化形态** `references/catalog/advance_forms.json`（22 只 id→名称），只作**口径记录**：说明哪 22 只用了强化后的魂印／种族值（附录 B）。前端已不做版本切换，`rebuild_view` 不再读这个文件，也不再往节点写 `soul_prev`／`advance`。
- **资料层是构建期快照**：`spirit_media.json`（11-10）／`spirit_library.json`（11-18）都不是实时数据，游戏后补的魂印只能靠 `fetch_seerapi.py` → `sync_latest_soul.py` 补进来（本次 3396 就是 11-06 快照缺 soulmark 2170）。`spirit_info.json` 的 `soul_mark` 口径＝**当前生效版全文**，同步脚本会一并更新。
- **`data/seerapi/seerapi.json` 的 `soulmarks`** 已按 id 升序排列并标 `latest`（最后一条＝最新），`compare_souls.py` 之类按候选集比对，不受顺序影响。

---

## 9 已知坑

1. **本机改动只在浏览器里，且按 origin 隔离**：编辑／体系／库添加都写 localStorage。`file://` 与 `http://127.0.0.1:端口` 是两个域，端口还每次变 → 换打开方式就等于换了一份存储，页面「什么都没有」。
   - 找回：`python scripts/recover_local_storage.py` 扫 Edge/Chrome leveldb，导出 `references/catalog/recovered_local_state.json`；加 `--apply` 写入内联 `DATA.editor.persisted`／`DATA.library.adds`，之后任何 origin 都生效。
   - 想保留本机编辑就固定一种打开方式（推荐双击 HTML）。
2. **无魂印过滤有三层**：`filtered()`、`applyLibraryAdds()`、`ensureInList()`（原 `addFromLibrary()` 内联判断）。
   - **别再用 `nodeOf()` 判「在不在列表」**：删除是软删除，`nodeOf()` 对已删精灵仍为真；列表语义一律 `inListOf()`，见 §7。
3. **属性图标不要加 `loading="lazy"`**：首屏／无头不加载。
4. **写回 `const DATA` 一律用 `viewdata`**：它用 `raw_decode` 定边界、紧凑 JSON、`</` 转义、CRLF、结尾分号。手写会出裸 `\r` 粘连或 JSON Extra data。
5. **`DATA.systems` 必须与 `systems/` 同量**：少了会出现「管理体系比文件夹少」。只跑 `merge_systems.py` ＋ `rebuild_view.py`。
6. **schema 三处同源**：`editor_schema.json` 是唯一注册表；`rebuild_view` 自动同步 `system_edit`；`check_roster`／前端都读它。画布容量／长度上限只在 `system_edit.canvas`（Python `canvas_limits()`，前端 `SYS_CFG.canvas`），琥珀强调色只在 `:root` 的 `--edge-own*`。
7. **写 `roster.json` 一律 `json.dumps(indent=2)`**，否则全文件 diff 抖动。
8. **`check_roster` 强校验 `SKILL.md` 的硬编码计数**：改体系数／精灵数／分组数要同步改文案。
9. **`.btn` 是 `inline-flex`**，`[hidden]` 要显式写 `.btn[hidden]{display:none}`。
10. **魂印名词圆环不能同时绑 `focusin` 与 `click`**，会立刻互相关闭。
11. **配色走变量**：浅色在 `:root`、深色在 `html[data-theme="dark"]`；不要写死 `#fff`／浅灰。唯一保留的硬编码是强调色（`#f59e0b`、名词三色 `#d94a86`／`#2fa96b`／`#3d84d6`）。
12. **头像只有资产仓库一个可信源**：`gcore.jsdelivr.net/gh/SeerAPI/seer-unity-assets@main/...`；gcore 偶发 403，换镜像或重试。
13. **两种缩放机制别混**：详情 `.ginner` 用 CSS `zoom`，体系管理 `#sysStage` 用 `transform:scale()`；拖拽坐标在 `pos()` 里统一除以 `sysZoom`。
14. **改卡片尺寸只改变量**：别在 `graphView`／`drawEdges`／`addSkillToCanvas` 里写数字。
15. **`robocopy /MIR` 必须用 PowerShell 跑**：Git Bash 会把 `/MIR` 当路径转义，命令失败（exit 16）。
16. **删体系会带走关系层依据**：`chain_audit` 的 `verified_pairs` 来自 `chain_edges`，删体系后要移出到 `historical_leads.json` 并重跑 `build_chain_audit.py` ＋ `build_full_audit.py`。
17. **线色不要写进 `edge_meta`**：`edge_meta` 由 `build_chain_audit.py`／`syncEdgesFor()` 重建；颜色只在 `canvas.edge_colors`，两套键格式不同（`a-b` vs `a|b`）。
18. **`editor_schema` 只保留 `#rrggbb` 六位小写**，其余色值会被丢弃。

---

## 10 待办

1. 21 项体系只有机制边，**没有逐回合顺序与赛季／月榜证据**，全部「社区／攻略」级；不自行提级。
2. 218 只里仍有 104 只没有定位（`sync_spirit_profile()` 只注入 roster 里与节点对得上的 114 只）；可用编辑面板补，或按 `core_roles.json` 批量赋值。
3. 22 只强化形态只换了魂印／种族值／标签，强化后的技能尚未并入技能表。
4. `tactics.md` 里 41 个已退役体系章节仍在（约 4 万字符），`query.py --system` 查不到；要清需用户确认。
5. `SKILL.md` 部分段落仍是「41 项／227 只」的历史快照口径（开头已加注），未逐条改写。
6. 拉取只同步魂印**正文**，不同步魂印效果标签（`DATA.soul_tags` 是构建期产物）：3396 换到 2170 后，标签仍按旧版那组显示（强攻／恢复／弱化），要重算得重跑 `fetch_seerapi_media.py` ＋ `build_spirit_media.py`。

---

## 11 验收与交付

```bash
python scripts/check_roster.py                     # 0 ERROR
python scripts/editor_schema.py                    # invariants OK
python scripts/audit_mechanics.py                  # issues: 0
python scripts/smoke_test.py                       # 54/54（自动找 Chrome/Edge，--browser 可指定）
python scripts/fetch_missing_skills.py --dry-run    # 库内技能为空的精灵（正常 0 只）
```

`smoke_test.py` 覆盖：数据规模（218 只／21 体系，下限断言）、图鉴详情、属性技能图标、编辑器四张卡、卡片尺寸与层级、连线落心、备注文本可连线并落库、属性口径（宽松／严格／开关）、取色面板与线色生效／落库／回放、体系导出、两处线型一致、端点贴边、短备注贴合、技能表窄宽不塌、库内技能已补、图鉴显示定位与备注、顶部按钮与备注开关、技能表与候选倒序、双第五只标一条重点、重点只认编辑设置、删除后回库面板可重加（`inListOf`）、魂印只显示最新版（不含旧版文本）、魂印无版本切换控件、**加强魂印已同步到图鉴（3396 显示 2170 而不是 709）**、名词释义正常。**改体系数或卡片尺寸要同步改断言。**

**版本管理（2026-11-20 起）**：仓库已 `git init`（首次提交 `回退到 11-19 口径`）。`dist/`、`assets/`、`references/spirit_synergy_view.html` 在 `.gitignore` 里（产物与重资源可重建），改动只提交 `scripts/`、`references/`、`data/`、`*.md`。**每次改前端先看一眼 `git status`，改完提交一次**——回滚用 `git diff` / `git checkout`，不要再靠「有没有备份」猜。

**重建前的备份**：`rebuild_view.py` 每次把当前产物复制到 `dist/backups/backup-YYYYMMDD-HHMMSS.html`（保留最近 20 份）。以前写系统临时目录 + 固定文件名，既会被下一次覆盖、又会被系统清理（11-19 的产物当晚就没了，想回滚都找不到）。

交付三步，缺一不可：

```powershell
# 1) 同步镜像（必须 PowerShell）
robocopy "E:\seerskill\seer-peak-pvp" "C:\Users\SHM20\.workbuddy\skills\seer-peak-pvp" /MIR /XD ".workbuddy" "__pycache__" /XF *.pyc
# 2) 打包
python scripts\pack_skill.py     # 输出 items / testzip / 关键文件 md5
# 3) 项目 / 镜像 / zip 内三处 md5 比对，必须一致
```

`pack_skill.py` 排除 `.workbuddy`、`dist`、`__pycache__`、`.git`、`node_modules`、`.cache`、`_*.html`、`.pyc/.tmp/.bak`。

### 11.5 桌面版与 Android 版（2026-11-20）

把单文件前端装进原生壳，给「不想开浏览器／想在手机上打巅峰」的场景。**两者都不复制数据源**：壳只负责起一个 `127.0.0.1` 随机端口的本地静态服务再指向 `references/spirit_synergy_view.html`。不能直接 `file://` 加载——WebView 在 `file://` 下禁用 IndexedDB，前端图片缓存会失效（见 §9.1 的 origin 说明）。

| 端 | 源码 | 构建命令 | 产物 |
|---|---|---|---|
| Windows | `desktop/exe/launcher.py`、`desktop/exe/build_exe.ps1` | `pwsh -NoProfile -File desktop/exe/build_exe.ps1` | `dist/desktop/SeerPeak/SeerPeak.exe`（onedir，116.7MB） |
| Android | `desktop/android/AndroidManifest.xml`、`desktop/android/src/`、`desktop/android/res/`、`desktop/android/build_apk.py` | `python desktop/android/build_apk.py` | `dist/SeerPeak.apk`（83.2MB，已签名） |

- **构建依赖不随仓库**：2026-11-20 起放在 `D:\ruanjianmen\dabao\`（705MB）——`jdk\jdk-17.0.2`、`sdk\cmdline-tools\latest` ＋ `sdk\build-tools\34.0.0` ＋ `sdk\platforms\android-34`、exe 用的 `venv-exe`（pywebview 6.2.1 ＋ PyInstaller 6.22.3）。两个构建脚本自动探测该目录（也认 `E:\seerskill\.buildtools`），或 `--jdk`／`--sdk-root` 指定。
- **换机／重装一条命令**：`pwsh -NoProfile -File desktop/tools/install_toolchain.ps1`（默认 `-Root D:\ruanjianmen\dabao`，会跳过已装组件）。走镜像：华为云 JDK 17.0.2、腾讯云 cmdline-tools、清华 pypi。官方源（api.adoptium.net／dl.google.com）在本机要 45s 才响应头，别直连。
- **工具链只是「能再造一个」的能力**：`dist/desktop/SeerPeak/` 是自包含的，删掉工具链也不影响已构建的 exe 运行。
- **exe**：pywebview ＋ PyInstaller `--onedir`。发布必须带上整个 `SeerPeak` 文件夹（只拷 exe 跑不起来）；依赖系统 WebView2 Runtime（Win10/11 一般已装）。`build/` 与 `dist/` 不入库。
- **apk**：无 Gradle 的手工链 —— `javac -source 8 -target 8 -bootclasspath android.jar` → `d8 --min-api 24` → `aapt2 compile/link -A assets` → 塞 `classes.dex` → `zipalign` → `apksigner`。`minSdk 24 / targetSdk 34`，横屏，`usesCleartextTraffic` 只为回环 HTTP。
- **APK 体积来自离线全图**：`assets/www/assets/seerapi` 4248 个文件 80.5MB（头像／立绘／属性图）直接打进 assets，不再联网取图；`assets/www/references/spirit_synergy_view.html` 11.4MB。
- **签名是本地调试 key**：`build/android/seerpeak.jks`（alias `seerpeak`，store/key 密码均 `android`），只适合自己安装；要分发或上架必须换正式 keystore，并先卸载同包名应用。
- **重建顺序**：改前端或 `rebuild_view.py` 之后，exe／apk 都要重新构建才会带上新产物；`desktop/` 源码入库，`build/`、`dist/` 忽略。

---

## 12 变更史（只留会被误判的节点）

| 日期 | 内容 |
|---|---|
| 2026-11-13 | 按用户清单录入 21 项体系，前端从 0 → 21 项 |
| 2026-11-15 | **精简**：用户判定 41 项历史体系与 160MB `seerapi_media/raw/` 无用 → 体系 62→21、删 raw；关系层改为「显式边即依据」；项目 403MB→243MB |
| 2026-11-17 | 连线重构：`LINK_PEN` 单一笔型 ＋ `rescaleLinks` 反补偿 ＋ `edgeSegment()` 射线求交（弃固定内缩）＋ `edgeModels()` 三类边同源；修 viewBox 与 CSS 宽度不一致导致的整层缩放；新增 `canvas.note_links` 与 `canvas.edge_colors` |
| 2026-11-18 | 定位／备注合并并上图鉴（`sync_spirit_profile()` 此前从未注入）；重点技能改为只认 `key_skills`；技能表与候选倒序；顶部「精选拉取」改「备注」开关 |
| 2026-11-19 | 从 Edge leveldb 恢复「丢失」的 23 只补丁与 18 只库添加（`recover_local_storage.py`）；目录按来源拆成 `data/` 与 `references/`；**内联 DATA 读写收敛到 `scripts/viewdata.py`，交接文档合并为本文件** |
| 2026-11-19 | 修「删除后从精灵库添加仍显示已添加」：新增 `inListOf()`（存在且未软删除）作为列表成员的唯一判定，库面板／`libOnly`／重复拦截／标签跳转／hash 全走它；`addFromLibrary` 抽出 `ensureInList()` 统一 present／restored／added／none 四条路；`smoke_test` 50/50 |
| 2026-11-20 | 当日先后做过：前端改名 `赛尔号巅峰.html`、魂印「强化前／强化后」开关、全量拉取覆盖与超时重构、编辑补丁字段白名单。**当天全部回退**（用户要求回到 11-19 的程序）：文件名恢复 `references/spirit_synergy_view.html`；魂印只显示最新一版；拉取回到「只入库、图像一并下载」；编辑补丁不做字段过滤；`smoke_test` 53/53 |
| 2026-11-20 | **拉取改为「每次都取最新」**：`fetch_seerapi.py` 默认全量重抓（`--skip-existing` 才跳过）、魂印按 id 排序标 `latest`；前端 `loadPullSouls(btn,true)` 每次重建索引、`newestSoul()` 取 id 最大的一条、拉到的魂印经 `rawSoul` 覆盖层写进节点 `soul_mark`、拉完无条件重绘；库构建 `primary` 不再退化成 `out[0]`；新增 `sync_latest_soul.py`（只升级还在显示旧版的精灵，幂等）。修 3396 灾厄女神潘多拉加强魂印不显示：709→2170，连带 14 只同类精灵升到加强版；`smoke_test` 54/54 |
| 2026-11-20 | **代码整理（行为不变）**：拉取参数收敛到前端 `PULL_CFG`（分页／并发／收录下限／重试／图片尺寸／`skillWorkers`），以后调速率或接新区间只改这一处；`apiJSON` 对 4xx 不再盲目重试、`seerPages` 的 `next` 支持相对 URL；修 `imgCachePut` 的 async executor 反模式；`imgCacheLoad` 从「每 key 开一次事务」改为单事务游标遍历；列表头像每只只算一次；`soulHtml` 改用入参 `mode` 避免串档；`fetch_seerapi.py` 每次保存刷新 `generated_at`；`smoke_test` 体系数改为下限断言；HANDOVER 命令示例 53→54 |
| 2026-11-20 | **清理**：删掉 `dist/SeerPeak.apk`（83MB）、`E:\seerskill\.buildtools`（1.0GB 打包工具链）、`.workbuddy/memory`（16 天开发日志，与 HANDOVER 重叠）、`_work_v5`（v5 评分原始数据）；项目 353.6→269.8MB，exe 产物与源码不动 |
| 2026-11-20 | **工具链迁到 D 盘**：删掉 `E:\seerskill\.buildtools`（1.0GB）后重装到 `D:\ruanjianmen\dabao`（705MB）；新增 `desktop/tools/install_toolchain.ps1` 一键重装，`build_apk.py`／`build_exe.ps1` 改为优先探测该目录；APK 用新工具链重建验证（7s／83.2MB／签名 OK）后按用户要求删除产物 |
| 2026-11-20 | **手机竖屏布局**（`@media (max-width:640px)`，桌面与平板样式不变）：首页改成一行四个的方形头像卡片墙——头像铺满卡片、名字与序号压在头像下缘、评级徽标在右上角，点卡片进图鉴；图鉴顶部新增返回栏（‹／名称／编辑／体系）。`body[data-mview]` 切「列表页／图鉴页」，`select()` 配 `pushState`/`popstate` 走两页导航（详情内换选中只 `replaceState`），返回时复原列表滚动位置；顶部工具栏单行横滑吸顶，搜索／筛选行吸在工具栏下方（CSS 变量 `--mhead`）。断点常量 `PHONE_MQ`，桌面分支仍走 `replaceState`；`smoke_test` 54/54 |
| 2026-11-20 | **打包**：新增 `desktop/exe`（pywebview＋PyInstaller onedir）与 `desktop/android`（javac/d8/aapt2 手工链，无 Gradle），产出 `dist/desktop/SeerPeak/SeerPeak.exe`（116.7MB）与 `dist/SeerPeak.apk`（83.2MB，minSdk 24／targetSdk 34）；两者都走 `127.0.0.1` 随机端口服务，避开 `file://` 下 IndexedDB 失效 |

---

## 附录 A｜218 只录入时的 30 处序号校正

按名称反查全库得到的正式 ID（表上序号 → 实际 ID）：

| 行号 | 表上 | 实际 | 名称 |
|---|---|---|---|
| 1 | 4188 | 4186 | 镇世·乔特鲁德 |
| 6 | 3518 | 3516 | 混沌地王莱茵哈特 |
| 10 | 4782 | 4762 | 湮灭之主·咤克斯 |
| 11 | 3058 | 3056 | 圣甲·盖亚 |
| 17 | 4788 | 4766 | 灭战神决·盖亚 |
| 28 | 3588 | 3586 | 战之狂热·英卡洛斯 |
| 42 | 4488 | 4468 | 始皇帝·嬴政 |
| 46 | 4822 | 4622 | 希拓 |
| 47 | 4843 | 4643 | 蓓丽安特 |
| 48 | 4844 | 4644 | 克雷弗德 |
| 49 | 4861 | 4661 | 无为觉者 |
| 50 | 4678 | 4676 | 神觉·米斯蒂克 |
| 53 | 4787 | 4797 | 极渊DS-001 |
| 54 | 4881 | 4861 | 涂蝶 |
| 57 | 4948 | 4946 | 万霆神律·雷伊 |
| 63 | 3487 | 3467 | 不灭·艾恩斯 |
| 81 | 4388 | 4386 | 缔笙 |
| 86 | 4800 | 4600 | 斯布林蒂 |
| 87 | 4833 | 4633 | 腐坏幽魔·克劳里菲 |
| 88 | 4708 | 4706 | 奥菲利娅 |
| 101 | 3158 | 3156 | 路希菲尔德 |
| 114 | 3984 | 3964 | 辛 |
| 159 | 3587 | 3567 | 魔钰 |
| 172 | 4446 | 4507 | 拉托奥 |
| 178 | 4832 | 4632 | 卡威治 |
| 179 | 4848 | 4648 | 星光·鲁斯王 |
| 182 | 4863 | 4663 | 凌虎·关银屏 |
| 183 | 4871 | 4671 | 噬夜疾袭·库拉塔克 |
| 184 | 4893 | 4693 | 星光·蘑菇怪 |
| 196 | 3786 | 3766 | 黑翼天马·克萨雷恩 |

另有 32 处只是名称错别字（序号正确），已统一改用库内正式名，例如瀚字星皇→瀚宇星皇 3291、伟迹·米修莉→讳迹·米修莉 4808、帝灵天锋→帝录天锋 4903、帝皇之戒→帝皇之戎 4950。

## 附录 B｜22 只使用强化后数据的精灵

4186 镇世·乔特鲁德、3516 混沌地王莱茵哈特、4004 圣光格劳瑞、3432 柯尔霍德、3524 乔列尼德、3711 圣光莫妮卡、3886 冰魄·柯尔德、4125 洪荒·列奥尼达、3407 格劳恩斯、3670 圣耀之光·黄金天马、3724 混沌·哈肯萨、3740 怒涛·沧岚、3941 混沌暗王霍德尔、3954 枫眠、3156 路希菲尔德、3507 冥王·苍月影、3613 芳馨·茉蕊儿、3623 鬼面幽蝶、3716 该洛西斯、3506 惊涛海皇·波塞冬、3705 守护者·艾里克、3766 黑翼天马·克萨雷恩。

数据已固化进 `DATA.race` 与节点 `soul_mark`；原始来源 `pet_advance/{id}.json` 曾位于已删除的 `data/seerapi_media/raw/`。例：4186 总和 750→790，魂印 1409→2028。