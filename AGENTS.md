# 伴学智能体 — 开发记录

> 基于 [DeepTutor](https://github.com/HKUDS/DeepTutor) (Apache 2.0) 二次开发

---

## 架构参考

### 两层插件模型

- **Tools（Level 1）** — 单函数工具, LLM 通过 function calling 调用
- **Capabilities（Level 2）** — 多阶段管道, 接管整个 turn
- **LoopCapability** — 在 chat agent 循环中插入 owned_tools + 系统提示, 不跑独立管道

所有入口（CLI / WebSocket / Python SDK）→ `ChatOrchestrator` → 选中的 Capability → `StreamBus` 扇出。

### 扩展模式

**加工具：** `deeptutor/core/tool_protocol.py` → 实现 `BaseTool` → 加进 `deeptutor/tools/builtin/__init__.py` 的 `BUILTIN_TOOL_TYPES` 元组。

**加管道 Capability：** 继承 `BaseCapability` → 注册到 `deeptutor/runtime/bootstrap/builtin_capabilities.py`。

**加 LoopCapability：** 实现 `LoopCapability` 协议 → 注册到 `deeptutor/capabilities/registry.py` 的 `LOOP_CAPABILITIES` 元组。

### 关键文件

| 路径 | 说明 |
|------|------|
| `deeptutor/runtime/orchestrator.py` | `ChatOrchestrator.handle()` — 统一入口 |
| `deeptutor/core/context.py` | `UnifiedContext` dataclass |
| `deeptutor/core/stream_bus.py` | `StreamBus` — 异步事件扇出 |
| `deeptutor/core/tool_protocol.py` | `BaseTool`, `ToolDefinition`, `ToolResult` |
| `deeptutor/core/capability_protocol.py` | `BaseCapability`, `CapabilityManifest` |
| `deeptutor/capabilities/protocol.py` | `LoopCapability` 协议 |
| `deeptutor/capabilities/registry.py` | LoopCapability 注册处 |
| `deeptutor/runtime/bootstrap/builtin_capabilities.py` | 管道 Capability 注册处 |
| `deeptutor/tools/builtin/__init__.py` | 工具注册处 |
| `deeptutor/services/path_service.py` | 跨平台路径解析 |
| `deeptutor/services/session/sqlite_store.py` | SQLite 会话存储（无 ORM） |
| `deeptutor/services/memory/` | 三层记忆（L1 轨迹, L2 摘要, L3 汇聚） |
| `deeptutor/agents/chat/agentic_pipeline.py` | 核心 chat agent 循环 |
| `deeptutor/agents/chat/agent_loop.py` | LLM 调用 ↔ 工具分发循环 |
| `deeptutor/agents/_shared/tool_composition.py` | `ToolMountFlags` + 工具组合策略 |
| `deeptutor/api/routers/unified_ws.py` | WebSocket 端点 |
| `deeptutor_cli/main.py` | Typer CLI 入口 |
| `web/` | Next.js 16 前端（React 19, Tailwind CSS） |
| `data/user/settings/*.json` | 运行时配置（无 `.env`） |

### 开发命令

```bash
pip install -e .
deeptutor init           # 首次配置
deeptutor chat           # 交互式 REPL
deeptutor run chat "..." # 单次执行
deeptutor start          # 启动后端 + 前端
deeptutor serve          # 仅 API

cd web && npm run dev    # 前端开发（另一终端）
pytest -q tests deeptutor/learning/tests  # 运行测试
ruff check . && ruff format --check .     # 检查格式
```

### 约定

- **无 `.env` 文件。** 配置在 `data/user/settings/*.json`，环境变量可覆盖。
- **所有源文件强制 LF**（`.gitattributes`），不可改动。
- **路径用 `pathlib.Path`**，不要字符串拼接。用 `PathService` 拿数据路径。
- **无 SQL ORM**，用原生 `sqlite3` + `check_same_thread=False`。
- **Skills 不是代码。** 它们是 Markdown 说明书，LLM 通过 `read_skill` 读取。不能定义工具/能力/存储。
- **i18n** 提示词放在 `prompts/{en,zh}/` 目录下。
- **跨平台**：分支用 `sys.platform == "win32"` / `os.name == "nt"` 保护，子进程用 argv 列表（不用 `shell=True`）。

---

## 修改总览

### 修改的源文件

| 文件 | 修改内容 | 修改日期 |
|------|---------|---------|
| `deeptutor/tools/builtin/__init__.py` | 导入并注册 `CUSTOM_TOOL_TYPES` | 2026-07-21 |
| `deeptutor/capabilities/registry.py` | 注册 `VolunteerLoopCapability` + `CareerLoopCapability` | 2026-07-21 |
| `web/components/sidebar/SidebarShell.tsx` | 侧边栏新增"志愿填报"/"学习分析"导航 | 2026-07-21 |
| `deeptutor/services/custom/db.py` | 新增 `user_settings` 表 | 2026-07-22 |
| `deeptutor/capabilities/volunteer/loop.py` | `owned_tools` 新增 `volunteer_weights` | 2026-07-22 |
| `deeptutor/tools/custom/volunteer_tools.py` | 新增 `VolunteerWeightsTool` + 评分工具集成用户权重 | 2026-07-22 |
| `deeptutor/tools/custom/__init__.py` | 注册 `VolunteerWeightsTool` | 2026-07-22 |
| `deeptutor/api/main.py` | 注册 `volunteer` API 路由 | 2026-07-22 |
| `web/app/(workspace)/volunteer/page.tsx` | 添加权重配置滑块面板 | 2026-07-22 |
| `deeptutor/api/routers/cron_router.py` | 新增 cron 任务管理 REST API | 2026-07-23 |
| `web/app/(workspace)/study-lab/page.tsx` | 新增定时查缺补漏提醒配置 UI | 2026-07-23 |
| `deeptutor/services/custom/volunteer_scorer.py` | `_calc_academic_fit` 重写，对接学习数据 | 2026-07-23 |
| `deeptutor/api/routers/volunteer.py` | 新增推荐 /study/summary /study/gap API | 2026-07-23 |
| `web/app/(workspace)/volunteer/page.tsx` | 推荐结果可视化 + 评分进度条 | 2026-07-23 |
| `web/app/(workspace)/study-lab/page.tsx` | 学习趋势 + 薄弱点标签云 | 2026-07-23 |
| `web/app/layout.tsx` | title → "伴学tutor" | 2026-07-23 |
| `web/app/(auth)/login/page.tsx` | 标题品牌替换 | 2026-07-23 |
| `web/app/(auth)/register/page.tsx` | 标题品牌替换 | 2026-07-23 |
| `web/components/sidebar/SidebarShell.tsx` | alt 属性替换 | 2026-07-23 |
| `web/app/(workspace)/home/[[...sessionId]]/page.tsx` | alt 属性替换 | 2026-07-23 |
| `web/components/chat/home/SessionLoadingView.tsx` | alt 属性替换 | 2026-07-23 |
| `web/app/(admin)/admin/users/page.tsx` | 标题品牌替换 | 2026-07-23 |
| `web/locales/{en,zh}/app.json` | i18n 品牌替换（约 30 处） | 2026-07-23 |
| `deeptutor/runtime/banner.py` | ASCII art 标题 + 文案替换 | 2026-07-23 |
| `deeptutor/api/main.py` | API 标题 + 欢迎消息 | 2026-07-23 |
| `deeptutor_cli/main.py` | CLI help 文本 | 2026-07-23 |
| `deeptutor/tools/web_fetch.py` | User-Agent | 2026-07-23 |
| `web/app/(workspace)/study-lab/page.tsx` | 修复 `subjects.map` 类型错误（`r.ok` 检查 + `Array.isArray` guard） | 2026-07-23 |
| `web/app/(workspace)/volunteer/page.tsx` | 修复按钮 `res.ok` 检查 + 错误提示显示 + 自动调优按钮 | 2026-07-23 |
| `deeptutor/api/routers/volunteer.py` | 新增 `POST /weights/auto-tune/{user_id}` 端点 + `auto_tuned` 响应字段 | 2026-07-23 |
| `deeptutor/services/custom/db.py` | schema 升级：`admission_ranks` 加 `group_code`，重建 PRIMARY KEY + `volunteer_plans` 表 | 2026-07-24 |
| `deeptutor/services/custom/admission_dao.py` | 所有查询函数增加 `group_code` 参数，新增 `get_college_group_ranks` | 2026-07-24 |
| `deeptutor/services/custom/volunteer_scorer.py` | `_calc_admission_prob` 改为按年取最佳位次（多 group 场景） | 2026-07-24 |
| `deeptutor/services/custom/volunteer_table_dao.py` | 志愿表 CRUD 数据层（新建） | 2026-07-24 |
| `deeptutor/api/routers/volunteer_table.py` | 志愿表 REST API + 省份规则 + 一键调序 + 诊断（新建） | 2026-07-24 |
| `deeptutor/api/routers/volunteer.py` | `RecommendRequest` 增加 `admission_province` / `college_province` 区分；新增 `POST /study/rank-convert`；新增 `GET /volunteer/admission-history/{college_id}` | 2026-07-24 |
| `deeptutor/api/main.py` | 注册 `volunteer_table` 路由 | 2026-07-24 |
| `web/app/(workspace)/study-lab/page.tsx` | 修正 API URL（去掉多余的 `/volunteer/` 段） | 2026-07-24 |
| `web/app/(workspace)/volunteer/page.tsx` | 省份标签 "省份" → "考生省份"；API 参数 `province` → `admission_province`；卡片显示录取概率百分比 + 位次趋势折叠面板 | 2026-07-24 |
| `web/app/(workspace)/volunteer/table/page.tsx` | 志愿表管理页面（一键生成/调序/诊断/删除）（新建） | 2026-07-24 |
| `web/components/sidebar/SidebarShell.tsx` | 侧边栏新增"智能推荐" / "志愿表" 导航条目 | 2026-07-24 |
| `scripts/import_guangdong_data_v3.py` | 保留原始专业组代码的导入器（2710 物理 + 1627 历史）（新建） | 2026-07-24 |
| `deeptutor/services/custom/volunteer_scorer.py` | SQL 重写评分引擎：纯 SQL + 比值概率（~24k rows vs 82k+），`score_group` 去 DB 调用，`group_recs` < 2s | 2026-07-27 |
| `deeptutor/services/custom/volunteer_scorer.py` | `_compute_rank_ratio_prob` 公式反转 + major_prob 同理 + academic_fit 冷启动 | 2026-07-27 |
| `scripts/seed_rag_from_db.py` | RAG 种子脚本（新建）——从 DB 生成 FAQ/院校/专业/录取数据灌入向量库，2667 条 | 2026-07-27 |
| `deeptutor/services/custom/rag/retriever.py` | 增加关键词搜索回退（中文 bigram 分词），FAQ + 院校档案检索可用 | 2026-07-27 |
| `deeptutor/services/custom/rag/store.py` | 新增 `search_by_keywords` 函数，SQL LIKE 回退 | 2026-07-27 |
| `deeptutor/services/custom/volunteer_chat_service.py` | CRAG 风格工具调用：意图分类 + tool 执行 + RAG 综合回答 | 2026-07-27 |
| `web/app/(workspace)/volunteer/page.tsx` | 位次输入框旁增加"问 AI"按钮，直接打开聊天抽屉 | 2026-07-27 |
| `deeptutor/services/custom/db.py` | `colleges` 表加 `city_tier`/`region` 字段迁移 | 2026-07-28 |
| `deeptutor/services/custom/college_dao.py` | `search_colleges` 加 `city_tier`/`region`/`cities` 参数 | 2026-07-28 |
| `deeptutor/services/custom/volunteer_scorer.py` | `_resolve_strategy_weights` 支持 `list[str]` 多选融合 | 2026-07-28 |
| `scripts/seed_region_data.py` | city_tier + region 数据回填脚本（4588 所） | 2026-07-28 |
| `web/app/(workspace)/volunteer/page.tsx` | 地域选择/策略多选/城市多选/分数分布图/保存/历史方案管理 | 2026-07-28 |
| `deeptutor/services/custom/art_sports.py` | 艺体类填报框架：8 类类别 + 综合分公式 + 本科批 20 组规则（新建） | 2026-08-19 |
| `deeptutor/services/custom/volunteer_scorer.py` | `generate_group_recommendations` 艺体类分支（cap 20 / no_data 提示 / art_category 列过滤） | 2026-08-19 |
| `deeptutor/services/custom/db.py` | `admission_ranks` 加 `art_category` 列 + PK 重建迁移纳入 art_category | 2026-08-19 |
| `deeptutor/api/routers/volunteer.py` | Browse/Recommend 加 art 字段 + `data_status` + art-sports 元数据端点 | 2026-08-19 |
| `deeptutor/api/routers/volunteer_table.py` | 艺体类建表：batch 强制艺体类本科批 / cap 20 / 每组 6 专业 / 综合分校验 | 2026-08-19 |
| `web/app/(workspace)/volunteer/page.tsx` | 选考科目加"艺体类"radio + 专业类别/综合分表单 + 艺体类批次联动 | 2026-08-19 |
| `tests/services/custom/test_art_sports.py` | 艺体类框架测试（综合分公式/类别/no_data/20 组 cap）（新建） | 2026-08-19 |
| `deeptutor/services/custom/art_sports.py` | 加 `ART_DIRECTIONS` 方向映射（音乐5/表导3/播音2）+ `art_directions`/`default_art_direction` | 2026-08-19 |
| `deeptutor/api/routers/volunteer.py` | Browse/Recommend/composite-score 加 `art_direction`；综合分→位次按方向一分一段表换算 | 2026-08-19 |
| `deeptutor/api/routers/volunteer_table.py` | CreatePlanRequest 加 `art_direction`；建表无位次时用综合分自动换算 | 2026-08-19 |
| `web/app/(workspace)/volunteer/page.tsx` | 艺体类方向下拉（音乐/表导/播音）+ 综合分联动显示 ≈位次；browse/create 透传 art_direction | 2026-08-19 |
| `tests/services/custom/test_art_sports.py` | 新增 `TestArtDirections`（方向映射/默认方向/未知回退） | 2026-08-19 |
| `deeptutor/services/custom/student_profile.py` | 体检受限清单按《指导意见》官方表3-1修正：删 501/502（身高体重非考试院数据）、新增 104（显示器色觉）/204（矫正>800度）/205（一眼失明）/306（斜视口吃）、203 改官方屈光400度文本、401 补心肌病高血压、101-103/301/302 受影响专业逐条修正 | 2026-08-20 |
| `deeptutor/services/custom/medical_dao.py` | 志愿册专业备注 → 受限码分类规则（hard/soft）+ `extract_medical_clause`/`major_medical_status`；备注按括号单元切分提取医学片段 | 2026-08-21 |
| `scripts/backfill_medical_notes.py` | 新建：Excel 专家版「专业备注」→ `college_major_name.medical_note` 回填（7277 行，幂等 + dry-run） | 2026-08-21 |
| `deeptutor/services/custom/volunteer_scorer.py` | `generate_group_recommendations` 按用户勾选受限码剔除专业（`medical_note` hard 命中），整组全剔则移除组，返回 `medical_filtered` 统计 | 2026-08-21 |
| `deeptutor/api/routers/volunteer.py` | BrowseRequest 加 `medical_restrictions`；browse 透传 + `medical_filtered` 响应 | 2026-08-21 |
| `deeptutor/api/routers/volunteer_table.py` | CreatePlanRequest 加 `medical_restrictions`；create_plan 透传 + slot 专业带 medical_note；diagnose 读方案受限项按专业备注校验 | 2026-08-21 |
| `deeptutor/services/custom/db.py` | `college_major_name` 加 `medical_note` 列；`volunteer_plans` 加 `medical_restrictions` 列（幂等迁移） | 2026-08-21 |
| `deeptutor/services/custom/volunteer_table_dao.py` | create_plan/clone_plan 持久化 `medical_restrictions`；`_row_to_dict` 解析 | 2026-08-21 |
| `deeptutor/services/custom/volunteer_validator.py` | `_check_medical` 新增专业备注 note 路径（hard→error / soft→warning），保留 36 码路径 | 2026-08-21 |
| `web/app/(workspace)/volunteer/page.tsx` | browse/create 透传体检受限项；专业行红字显示备注限制原文（`MedicalNote` 组件）；浏览头部剔除统计提示；deps 补 medicalRestrictions | 2026-08-21 |
| `tests/services/custom/test_medical_note.py` | 新建：备注提取/分类/`major_medical_status` 测试；scorer 组级医学过滤 + 整组剔除 + 软提醒保留测试 | 2026-08-21 |

### 新增文件

| 目录 | 说明 |
|------|------|
| `deeptutor/services/custom/` | 数据层：db 管理、数据模型、院校 DAO、导师评价 DAO、学习记录 DAO、多因子评分模型 |
| `deeptutor/tools/custom/` | 7 个自定义工具（upload_exam, study_dashboard, gap_analysis, college_search, volunteer_score, volunteer_recommend, advisor_search） |
| `deeptutor/capabilities/volunteer/` | 志愿填报 LoopCapability + 中英提示词 |
| `deeptutor/capabilities/career/` | 生涯规划 LoopCapability + 中英提示词 |
| `web/app/(workspace)/volunteer/` | 志愿填报前端页面 |
| `web/app/(workspace)/study-lab/` | 学习分析前端页面 |
| `scripts/seed_college_data.py` | 从 Excel 导入 2769 所院校数据 |
| `scripts/seed_advisor_data.py` | 从 Excel 导入 39317 条导师评价 |
| `scripts/seed_college_scores.py` | 院校评分自动生成（dorm/city/cost/employment/salary） |
| `scripts/import_admission_ranks.py` | 通用 Excel/CSV 导入器（admission_ranks 表） |
| `deeptutor/services/custom/subject_major_map.py` | 学科-专业映射（36 个专业 × 学科权重） |
| `deeptutor/services/custom/adaptive_weights.py` | 自适应权重模型（根据学习记录自动调优权重） |
| `deeptutor/services/custom/volunteer_table_dao.py` | 志愿表 CRUD 数据层 |
| `deeptutor/api/routers/volunteer_table.py` | 志愿表 REST API + 省份规则 + 一键调序 + 诊断 |
| `scripts/import_guangdong_data_v3.py` | 广东含专业组代码导入器（2710 物理 + 1627 历史） |
| `web/app/(workspace)/volunteer/table/page.tsx` | 志愿表管理前端页面 |
| `deeptutor/services/custom/export_service.py` | PDF/Excel 导出 |
| `deeptutor/services/custom/volunteer_chat_service.py` | AI 对话代理（LLM 会话管理）|
| `deeptutor/api/routers/volunteer_chat.py` | 志愿 AI 对话 API |
| `web/components/volunteer/VolunteerChatDrawer.tsx` | 志愿 AI 对话抽屉组件 |
| `deeptutor/services/custom/rag/` | RAG 知识库子包（embed/chunker/store/indexer/retriever）|
| `deeptutor/services/custom/holland_assessment.py` | 霍兰德 RIASEC 测评 |
| `web/components/volunteer/AdmissionCountdown.tsx` | 录取日程倒计时组件 |
| `scripts/seed_rag_from_db.py` | RAG 种子脚本（新建）——从 DB 生成 FAQ/院校/专业/录取数据灌入向量库，2667 条 |
| `deeptutor/services/custom/art_sports.py` | 艺体类填报框架（8 类类别 + 综合分公式 + 本科批 20 组规则） |
| `scripts/import_art_sports_2026.py` | 2026 艺体类本科投档导入器（7 附件 1347 组 + 新院校补库） |
| `scripts/parse_art_catalog.py` | 2026 招生专业目录（体育艺术版）DOCX 解析器 + 组内专业明细写库 |
| `scripts/import_art_segments_2026.py` | 2026 艺体类一分一段表导入器（14 个文件含方向细分） |

## 架构图

```
用户入口: CLI / WebSocket / 前端
         │
         ▼
  ChatOrchestrator ─→ UnifiedContext
         │
         ├── 原生 Capability (chat/deep_solve/...)
         │
         └── 自定义 LoopCapability (volunteer / career)
                  │
                  ├── owned_tools
                  │    ├── college_search → college_dao → SQLite
                  │    ├── volunteer_score → volunteer_scorer
                  │    ├── volunteer_recommend → scorer + DAO
                  │    ├── upload_exam → study_dao → SQLite
                  │    ├── study_dashboard → study_dao
                  │    ├── gap_analysis → study_dao
                  │    └── advisor_search → advisor_dao → SQLite
                  │
                  └── data/user/custom/deeptutor_custom.db
```

## 开发进度

### Phase 1 ✅ 数据层

- [x] `db.py` — SQLite 管理（colleges/majors/college_majors/study_records/advisor_evaluations/admission_ranks/user_settings 七张表）
- [x] `models.py` — College, Major, CollegeMajor, StudyRecord, AdmissionRank 数据模型
- [x] `college_dao.py` — 院校多条件搜索、详情查询、数据导入
- [x] `study_dao.py` — 学习记录上传、时间线查询、薄弱知识点汇聚 + 建议生成
- [x] `admission_dao.py` — 按省份/院校/专业的录取位次查询与导入
- [x] `volunteer_scorer.py` — 六维度多因子评分模型（学业匹配度/录取概率/宿舍/城市/成本/就业），支持省域位次优先查询

### Phase 2 ✅ 工具层

- [x] `upload_exam` — 上传并解析考试/作业成绩
- [x] `study_dashboard` — 查看学习概览和各科正确率趋势
- [x] `gap_analysis` — 分析薄弱知识点并生成针对性建议
- [x] `college_search` — 按省份/层次/类型/关键词搜索院校
- [x] `volunteer_score` — 计算院校-专业综合匹配分
- [x] `volunteer_recommend` — 生成冲-稳-保梯度志愿推荐方案
- [x] `advisor_search` — 按学校/学院/姓名搜索导师评价

### Phase 3 ✅ Capability 层

- [x] `VolunteerLoopCapability` — `volunteer_mode` 激活，挂在 `deeptutor/capabilities/volunteer/`
- [x] `CareerLoopCapability` — `career_mode` 激活，挂在 `deeptutor/capabilities/career/`

### Phase 4 ✅ 前端

- [x] `/volunteer` — 志愿填报助手页面（考生信息输入 + 冲/稳/保三栏 + 评分说明）
- [x] `/study-lab` — 学习分析实验室页面（概览卡片 + 使用指引 + 趋势示例）

### Phase 5 ✅ 数据填充

- [x] `scripts/seed_college_data.py` — 从 Excel 导入 2769 所院校数据
- [x] `scripts/seed_advisor_data.py` — 从 Excel 导入 39317 条导师评价
- [x] `scripts/seed_major_data.py` — 36 个标准本科专业（教育部专业目录）
- [x] `scripts/seed_college_major_data.py` — 按学校类型关联 31278 条 college-major 记录
- [x] `scripts/seed_sample_rank_data.py` — 59 条省域录取位次样例数据（9 所 × 5 省份 × 3 年）

### Phase 6 ✅ 测试覆盖

- [x] **数据层测试（7 文件）**: `test_db.py`（幂等性/外键/索引/行工厂）、`test_college_dao.py`（搜索过滤器/嵌套查询/CRUD）、`test_study_dao.py`（上传/时间线/汇总/薄弱点分析）、`test_advisor_dao.py`（搜索/统计/bulk_import 容错）、`test_admission_dao.py`（CRUD/省域查询/bulk_import）、`test_volunteer_scorer.py`（归一化边界/录取概率/六维度评分/分档阈值/省域优先）
- [x] **工具层测试（3 文件）**: `test_exam_tools.py`（upload_exam/study_dashboard/gap_analysis 参数透传与异常安全）、`test_volunteer_tools.py`（college_search/volunteer_score/volunteer_recommend 输入输出）、`test_advisor_tools.py`（advisor_search 截断/空结果/统计行）
- [x] **Capability 层测试（2 文件）**: `test_volunteer_capability.py` 和 `test_career_capability.py`（is_active 开关/提示词加载/override 机制/augment_kwargs 注入）
- [x] **测试总数**: 59 passed in 1.36s（服务层核心测试）

### Phase 7 ✅ 基础设施完善

- [x] 多因子权重调优与用户可配置 — `user_settings` 表 + `user_settings_dao` + `VolunteerWeightsTool` + REST API + 前端滑块面板（2026-07-22）
- [x] 周期性查缺补漏提醒（集成 cron） — `cron_router.py` REST API + 前端 `/study-lab` 定时提醒开关（2026-07-23）
- [x] 录取位次数据基础设施 — `admission_ranks` 表 + `admission_dao.py` + scorer 省域优先查询 + seed 脚本 + 59 条样例数据（2026-07-23）

### Phase 8 🚀 综合完善

- [x] 学业匹配度评分 — 科目-专业映射 + `_calc_academic_fit` 重写对接学习数据（2026-07-23）
- [x] 自适应权重自动调优 — 数学模型 + REST API + 前端自动调优按钮（2026-07-23）
- [x] 广东位次数据含科类导入 — 一分一段 + 投档数据按物理/历史分类（2026-07-24）
- [x] 录取概率算法重写 — 百分位 + math.erf 正态 CDF + 跨年加权（2026-07-24）
- [x] 推荐三档均衡分布 — 冲/稳/保 各取 top N（2026-07-24）

#### 方向 A：录取位次数据扩充 ✅

**A1 — 通用 Excel/CSV 导入器**
- 新建 `scripts/import_admission_ranks.py`，支持从 Excel/CSV 批量导入
- 自动列名映射（支持中英文列名，如 `院校ID`/`college_id`、`省份`/`province`、`最低位次`/`min_rank`）
- 校验逻辑：college_id/major_id 外键检查、年份范围、排名合理性
- 命令行接口：`python scripts/import_admission_ranks.py --file data.xlsx --sheet Sheet1`
- 成功/失败计数 + 错误报告输出

**A2 — 数据填充（已完成）**
- `scripts/import_guangdong_data_v2.py` — 广东专用导入器（一分一段 + 投档含科类）
- 导入结果：
  - 一分一段 `score_rank_segments`：物理 1194 条 + 历史 1144 条，含 batch_category（本科/专科）
  - 投档 `admission_ranks`：物理 884 条 + 历史 757 条（dedup 后按院校最低位次），全部含 `exam_category` 字段
  - `colleges` 表 province 回填 2770/2770（`scripts/fill_province_from_city.py`）
- 数据范围：rank 跨度 99-276185（`admission_ranks`），总分 100-696（`score_rank_segments`）
- 已修正：PRIMARY KEY 碰撞（多专业组 -> dedup）；get_total_candidates 缺失年份回退

> **如果你有其他省/市的位次数据文件**，可用通用导入器：
> `python scripts/import_admission_ranks.py --file data.xlsx`
> 支持的列名：`college_id`/`院校ID`、`major_id`/`专业ID`、`province`/`省份`、
> `year`/`年份`、`batch`/`批次`、`min_rank`/`最低位次`、`min_score`/`最低分数`、`enrollment_count`/`招生人数`

#### 方向 H：录取概率算法 & 推荐均衡（新增）

**H1 — 百分位 + 正态 CDF 概率模型**
- 弃用原始 rank 比值，改用 `rank / total_candidates` 百分位
- 跨年加权：2026 × 0.5, 2025 × 0.35, 2024 × 0.15
- `math.erf` 实现正态 CDF（无 scipy 依赖）
- `sigma_g` 最小值 0.02（多数据点）或 0.05（单点）
- 冲/稳/保阈值：0.8/0.45
- `score_college_major` 在 major=None 时以 `major_id="GEN"` 查询院校级录取数据

**H2 — `generate_recommendations` 三档均衡**
- 不再仅按总分行排序取 top N，改为：全量分类 → 每档各取 `top_n // 3` 个
- 剩余名额从次优院校补充
- 确保冲/稳/保三列都有结果显示

**H3 — API 院校搜索优化**
- `search_colleges` 新增 `college_ids` 参数过滤
- `/volunteer/recommend` 改为从 `admission_ranks` 取有广东数据的 college_ids，而非仅 college.province="广东"
- 解决 156 所 vs 884 所的数据差异

| 文件 | 说明 |
|------|------|
| `scripts/import_guangdong_data_v2.py` | 广东含科类导入器（新增） |
| `deeptutor/services/custom/volunteer_scorer.py` | `_calc_admission_prob` 重写 + `generate_recommendations` 三档均衡 |
| `deeptutor/services/custom/admission_dao.py` | `get_admission_ranks`/`get_admission_ranks_by_college` 支持 `exam_category` 过滤 |
| `deeptutor/services/custom/college_dao.py` | `search_colleges` 新增 `college_ids` 参数 |
| `deeptutor/api/routers/volunteer.py` | 推荐端点搜索逻辑改为 `admission_ranks` 表驱动 |
| `tests/services/custom/conftest.py` | seed 数据增加 `exam_category` + `score_rank_segments` + 年份调整 |
| `tests/services/custom/test_volunteer_scorer.py` | 断言适配新概率模型 |

#### 方向 B：学业匹配度评分 ✅

**B1 — 学科-专业映射** ✅
- 定义各专业所需的学科权重（如计算机 → 数学 0.5, 英语 0.2, 物理 0.3）

**B2 — `_calc_academic_fit` 重写** ✅
- 从 `study_records` 读取用户各科成绩/正确率
- 计算用户学科画像与专业要求的加权匹配分
- 无学习记录时回退到默认 0.5

| 文件 | 说明 |
|------|------|
| `deeptutor/services/custom/volunteer_scorer.py` | `_calc_academic_fit` 重写 |
| `deeptutor/services/custom/subject_major_map.py` | 学科-专业映射配置（新增） |

#### 方向 C：院校评分字段填充（优先级：中）

**C1 — 自动评分脚本 `scripts/seed_college_scores.py`**
- 基于院校层次（985/211/双一流/普通）、所在城市（一线/二线/三线）、院校类型（综合/理工/师范）自动生成合理评分
- 规则示例：
  - `dorm_score`: 985 ≥ 7, 211 ≥ 5, 普通 ≥ 3（一线城市再 +1）
  - `city_vitality`: 一线 9, 新一线 7, 二线 5, 三线 3
  - `cost_index`: 一线 1.5, 新一线 1.2, 二线 1.0, 三线 0.7
  - `employment_rate`: 985/211 ≥ 0.90, 普通 ≥ 0.80, 理工 +0.05
  - `avg_salary`: 985 ≥ 12k, 211 ≥ 9k, 普通 ≥ 6k（一线城市上浮）

| 文件 | 说明 |
|------|------|
| `scripts/seed_college_scores.py` | 院校评分自动生成（新增） |

#### 方向 D：前端体验增强（优先级：中）

**D1 — `/volunteer` 页面改进**
- 推荐结果可视化：冲/稳/保三栏卡片展示，显示匹配分进度条
- 院校对比功能：选中 2-3 所院校并排对比各维度得分
- 省份+位次筛选联动

**D2 — `/study-lab` 页面改进**
- 学习趋势折线图
- 薄弱知识点标签云展示
- exam_date 筛选器

| 文件 | 说明 |
|------|------|
| `web/app/(workspace)/volunteer/page.tsx` | 推荐结果可视化 + 院校对比 |
| `web/app/(workspace)/study-lab/page.tsx` | 趋势图 + 知识点云 |

#### 方向 F：品牌改版 — "DeepTutor" → "伴学tutor"（优先级：中）

**F1 — 前端 logo/图标替换**
- 重新制作 `web/public/logo.png`（方形图标 22×22）
- 重新制作 `web/public/logo_black.png`（深色版方形图标）
- 重新制作 `web/public/banner.png`（"伴学tutor" 文字横幅）
- 重新制作 `web/public/favicon-16x16.png` / `favicon-32x32.png`
- 重新制作 `web/public/apple-touch-icon.png`

> **需要你提供的图片资源：**
>
> | # | 文件 | 用途 | 要求 |
> |---|------|------|------|
> | 1 | `web/public/logo.png` | 侧边栏方形图标 22×22 | 正方形，透明背景，建议 512×512 |
> | 2 | `web/public/logo_black.png` | 空屏欢迎页 + 加载遮罩 | 同上，深色/白色版本 |
> | 3 | `web/public/banner.png` | 侧边栏展开文字横幅 | 宽高比 ~3.8:1，"伴学tutor" 横排文字 |
> | 4 | `web/public/favicon-16x16.png` | 浏览器标签图标 | 16×16 清晰可辨 |
> | 5 | `web/public/favicon-32x32.png` | 浏览器标签图标 | 32×32 |
> | 6 | `web/public/apple-touch-icon.png` | iOS 主屏幕图标 | 180×180，圆角 |
>
> 放置路径：全部放入 `web/public/` 目录，同名覆盖原 DeepTutor 图标即可。

**F2 — 页面标题 & 文案替换**（12 处）
- `web/app/layout.tsx` — title/metadata
- `web/app/(auth)/login/page.tsx` — `<h1>` + 副标题
- `web/app/(auth)/register/page.tsx` — `<h1>` + 副标题
- `web/components/sidebar/SidebarShell.tsx` × 4 — alt 属性
- `web/app/(workspace)/home/[[...sessionId]]/page.tsx` — alt 属性
- `web/components/chat/home/SessionLoadingView.tsx` — alt 属性
- `web/app/(admin)/admin/users/page.tsx` — 标题

**F3 — 系统提示词替换**（约 30+ yaml 文件）
- ZH prompts: `你是 DeepTutor` → `你是 伴学tutor`
- EN prompts: `You are DeepTutor` → `You are Banxue Tutor`

**F4 — 前端 i18n 替换**（`web/locales/{en,zh}/app.json`，约 20 处）
- "Welcome to DeepTutor" → "欢迎使用伴学tutor"
- "DeepTutor Logo" → "伴学tutor Logo"
- "DeepTutor Planning..." → "Planning..."（状态标签去品牌化）
- 等

**F5 — CLI/后端文案替换**（8 处）
- `deeptutor/runtime/banner.py` — ASCII art + title 标签
- `deeptutor/api/main.py` — API 标题 + 欢迎消息
- `deeptutor_cli/main.py` — CLI help 文本
- `deeptutor/tools/web_fetch.py` — User-Agent

**F6 — README 文档配图**
- `assets/figs/logo/*.png` — 截图替换（上线后做）
- `README.md` + 10 种翻译版 — 标题和 alt 文本

**F7 — 版本号重置 + ASCII 改版（2026-07-26）**
- `deeptutor/__version__.py` — `1.5.1` → `1.0.0`，重置为伴学tutor独立版本起点
- `deeptutor/runtime/banner.py` — ASCII 字母图案改为 `━━━ 伴学tutor ━━━` 简洁装饰线

| 文件 | 说明 |
|------|------|
| `web/public/*.png` | 前端 logo/图标（替换） |
| `deeptutor/agents/*/prompts/{en,zh}/*.yaml` | 提示词品牌名（约 30 文件） |
| `deeptutor/runtime/banner.py` | ASCII art + 标题 |
| `deeptutor/api/main.py` | API 元信息 |
| `web/locales/{en,zh}/app.json` | 前端文案 |
| `deeptutor_cli/main.py` | CLI 描述 |
| `assets/figs/logo/` | 文档配图（延期） |

#### 方向 G：自适应权重自动调优（优先级：中）

**G1 — 权重调优数学模型**

定义 `compute_adaptive_weights(user_id, base_weights)`：
- **数据置信度** `λ = min(1.0, records/50) × min(1.0, subjects/4)` — 数据越充分调整幅度越大
- **学科分类**：按 stem / liberal / art 三类计算平均正确率
- **调整向量 δ**：
  - `academic_fit ↑` 当 STEM 成绩显著优于文科时
  - `employment ↑` 当 STEM 优势时同步提升
  - `career_alignment ↑` 当文科显著优于理科时
  - `dorm_quality / city_vitality ↓` 小幅调低（资源重分配）
- **边界保护**：各维度调幅不超过 ±40%~50%
- **数据不足**（<10 条记录 / <2 个学科）直接返回默认权重

**G2 — REST API**

- `POST /api/v1/volunteer/weights/auto-tune/{user_id}` — 触发自动调优，写入 user_settings 并返回新权重
- `auto_tuned` 字段标记是否为调优状态

**G3 — 前端集成**

- 权重配置区新增紫色"自动调优"按钮（Zap 图标）
- 调优成功后滑块实时反映新权重
- 手动保存/重置后清除 auto_tuned 标记

| 文件 | 说明 |
|------|------|
| `deeptutor/services/custom/adaptive_weights.py` | 自适应权重模型（新增） |
| `deeptutor/api/routers/volunteer.py` | `auto-tune` 端点（修改） |
| `web/app/(workspace)/volunteer/page.tsx` | 自动调优按钮 + 错误提示修复（修改） |

#### 执行路线

```
Phase 8 执行顺序:
  1. A1/A2 (数据导入+含科类) ✅ — 2026-07-24
  2. B1/B2 (学业匹配度) ✅ — 2026-07-23
  3. H1/H2/H3 (概率算法+推荐均衡) ✅ — 2026-07-24
  4. C1 (院校评分) — 待定
  5. D1/D2 (前端) — 待定
  6. F1-F6 (品牌改版) — 部分完成
  7. E (测试) — 伴随各方向
  8. G1/G2/G3 (自动调优) ✅ — 2026-07-23
```

#### 测试覆盖（Phase 6-8）

- [x] **现有测试**: 329 passed（服务层核心 + 工具层 + Capability 层）
- [ ] 导入器测试（CSV 解析/校验/边界）
- [ ] 学业匹配度测试（各学科权重计算/无数据回退）
- [ ] 院校评分种子脚本测试（规则一致性）
- [ ] 前端组件测试

### Phase 9 🚀 专业推荐 + 志愿表系统

> 状态：第 1-7 段全部完成

#### 方向 I：数据层改造 — 专业组级别录取位次 ✅

**I1 — `admission_ranks` 加 `group_code` 字段** ✅
- `ALTER TABLE admission_ranks ADD COLUMN group_code TEXT DEFAULT ''`（迁移已运行）
- PRIMARY KEY 改为 `(college_id, major_id, province, year, exam_category, group_code)`

**I2 — 导入脚本升级** ✅
- `scripts/import_guangdong_data_v3.py` — 保留原始 专业组代码，不再 dedup
- 导入结果：物理 2710 条 + 历史 1627 条，含 group_code

**I3 — admission_dao 升级** ✅
- 所有查询函数增加 `group_code` 参数（`None`=不限, `""`=匹配空, `"xxx"`=匹配特定）
- 新增 `get_college_group_ranks(college_id)` 按 group 查询
- scorer 按年取最佳位次（多 group 选最低位次）

| 文件 | 说明 |
|------|------|
| `deeptutor/services/custom/db.py` | schema 升级（ALTER TABLE + migration） |
| `deeptutor/services/custom/admission_dao.py` | 查询函数增加 group_code 参数 |
| `scripts/import_guangdong_data_v3.py` | 含专业组代码导入器（2710 物理 + 1627 历史） |
| `deeptutor/services/custom/volunteer_scorer.py` | `_calc_admission_prob` 按年取最佳位次 |

#### 方向 J：现有问题修复 ✅

**J1 — study-lab API URL 错误** ✅
- `web/app/(workspace)/study-lab/page.tsx:47-48`
- `/api/v1/volunteer/study/summary/default` → `/api/v1/study/summary/default`
- `/api/v1/volunteer/study/gap/default` → `/api/v1/study/gap/default`

**J2 — 省份语义修正** ✅
- 前端 label "省份" → "考生省份"
- API `admission_province`（考生省份）和 `college_province`（院校所在地）区分
- College search 不再用考生省份过滤院校 location

**J3 — 等位次换算端点** ✅
- `POST /api/v1/study/rank-convert` — 跨年分数/位次映射
- 基于 `score_rank_segments` 表

**J4 — 推荐卡片信息增强** ✅
- 录取概率显示具体百分比
- 可折叠位次趋势面板（历年数据）
- 院校地域信息

| 文件 | 说明 |
|------|------|
| `web/app/(workspace)/study-lab/page.tsx` | 修正 API URL（去掉 `/volunteer/` 段） |
| `web/app/(workspace)/volunteer/page.tsx` | 省份标签 + 录取概率 + 位次趋势面板 |
| `deeptutor/api/routers/volunteer.py` | 省份参数拆分 + rank-convert + admission-history 端点 |

#### 方向 K：志愿表系统 ✅

**K1 — 数据层** ✅
- 新建 `volunteer_plans` 表（id, user_id, province, exam_category, rank, province_rules, slots, status, timestamps）
- `deeptutor/services/custom/volunteer_table_dao.py` — CRUD（create/get/update/delete/list）

**K2 — REST API** ✅
`deeptutor/api/routers/volunteer_table.py`：
```
POST   /api/v1/volunteer/plan/create        — 按省份规则 + 推荐引擎生成
GET    /api/v1/volunteer/plan/{id}          — 获取详情
PUT    /api/v1/volunteer/plan/{id}          — 更新 slots
DELETE /api/v1/volunteer/plan/{id}          — 删除
PUT    /api/v1/volunteer/plan/{id}/reorder  — 按 admission_prob 降序重排
GET    /api/v1/volunteer/plan/{id}/diagnose — 梯度评分 + 滑档风险
GET    /api/v1/volunteer/plan/list         — 用户志愿表列表
```

**K3 — 省份规则配置** ✅
```python
PROVINCE_RULES = {
    "江苏": {"groups": 40, "mode": "院校专业组", "ratio": [3, 3, 4]},
    "浙江": {"groups": 80, "mode": "专业", "ratio": [3, 4, 3]},
    "广东": {"groups": 45, "mode": "院校专业组", "ratio": [3, 4, 3]},
    "北京": {"groups": 30, "mode": "院校专业组", "ratio": [3, 3, 4]},
    "上海": {"groups": 24, "mode": "院校专业组", "ratio": [3, 3, 4]},
    "default": {"groups": 30, "mode": "院校", "ratio": [3, 3, 4]},
}
```

**K4 — 一键调序** ✅
- 按 `admission_prob` 降序排列 slots
- 自动修复倒序，输出概率区间报告

**K5 — AI 一键调整** ⏳（待实现）
- 调用 LLM 在真实候选池中重排/替换/补充
- 约束：不得虚构院校，每条变更输出理由
- 需集成 `ChatOrchestrator`

**K6 — 模拟投档 + 诊断** ✅
- 梯度评分（0-100）：比例合理性 30' + 趋势 30' + 无倒序 20' + 三档覆盖 20'
- 滑档风险：保底档最弱概率判定 "低/中/高"

**K7 — 前端志愿表页面** ✅
- 新页面 `web/app/(workspace)/volunteer/table/page.tsx`
- 布局：考生信息输入 → 一键生成 → 调序/诊断操作栏 → slots 列表（每格含概率进度条）
- 侧边栏新增 "智能推荐" + "志愿表" 导航

| 文件 | 说明 |
|------|------|
| `deeptutor/services/custom/volunteer_table_dao.py` | 志愿表数据层 CRUD（新建） |
| `deeptutor/api/routers/volunteer_table.py` | 志愿表 REST API + 规则 + 调序 + 诊断（新建） |
| `web/app/(workspace)/volunteer/table/page.tsx` | 志愿表前端页面（新建） |
| `web/components/sidebar/SidebarShell.tsx` | 侧边栏新增志愿表子导航 |

#### 执行路线

```
Phase 9 执行顺序:
  1. I1+I2+I3 (数据层改造 + 重新导入) — 第 1 段 ✅
  2. J1+J2+J3+J4 (修复现有问题) — 第 2 段 ✅
  3. K1+K2+K3 (志愿表数据层 + API + 规则) — 第 3 段 ✅
  4. K4+K5+K6 (调序 + AI + 诊断) — 第 4 段 (K5 待实现)
  5. K7 (前端志愿表页面) — 第 5 段 ✅
  6. 测试覆盖 — 贯穿各段
```

#### 测试覆盖

- [ ] `test_admission_dao.py` — group_code 查询/导入测试
- [ ] `test_volunteer_table_dao.py` — 志愿表 CRUD 测试
- [ ] `test_volunteer_table_service.py` — 补齐/调序/AI/诊断测试
- [ ] 前端组件测试（志愿表页面）

---

### Phase 10 🚀 数据基建 + RAG 知识库 + 推荐引擎增强

> 状态：全部 6 段完成，2026-07-24 启动

#### 架构

```
文档源: 招生章程 / 政策文件 / 专业介绍 / 就业报告 / FAQ (持续增长)
         │
  ┌──────▼─────────────────────────────────────────┐
  │          Document Ingestion Pipeline            │
  │  规则+LLM 提取 → SQLite 结构化字段               │
  │  chunk + embedding → sqlite-vec 向量库          │
  │  冲突仲裁 → conflict_log / need_review          │
  └──────┬─────────────────────┬────────────────────┘
         │                     │
  ┌──────▼──────┐      ┌──────▼──────┐
  │   SQLite     │      │  sqlite-vec │
  │   16+ 张表   │      │  doc_chunks │
  └──────┬──────┘      └──────┬──────┘
         │                     │
  ┌──────▼─────────────────────▼────────────────────┐
  │              应用层                               │
  │  推荐引擎 (SQLite 直读)  AI对话抽屉 (RAG 检索增强) │
  │  冲突检测(体检/单科/性别/选科)  FAQ自动回答         │
  └─────────────────────────────────────────────────┘
```

#### 执行路线（6 段）

##### 第 1 段：考生档案 + 体检限制 ✅（已完成）

| 任务 | 文件 | 说明 |
|---|---|---|
| 1a | `services/custom/student_profile.py` | `StudentProfile` dataclass — 省/年/首选/再选/分数/位次/加分/特殊资格/体检受限/性别/偏好 |
| 1b | `services/custom/medical_dao.py` + `db.py` 加表 | `medical_restrictions` 表 + 报考专业限制映射 + 冲突检测 |
| 1c | `services/custom/volunteer_validator.py` | 体检/单科/性别/选科四类冲突检查 |
| 1d | `api/routers/volunteer.py` + `volunteer_tools.py` | 推荐 API 接入 `StudentProfile` |
| 1e | `web/app/(workspace)/volunteer/page.tsx` | 表单加体检/加分/再选字段 |
| 1f | `tests/services/custom/test_student_profile.py` | dataclass 序列化/校验测试 |
| 1g | `tests/services/custom/test_volunteer_validator.py` | 四类限制检测测试 |

##### 第 2 段：院校 & 专业库增强 ✅（已完成）

| 任务 | 文件 | 说明 |
|---|---|---|
| 2a | `db.py` ALTER + `college_dao.py` + `models.py` | `colleges` 扩字段：保研率、硕博点数、双一流学科(JSON)、软科排名、校友会排名、招生章程URL、转专业政策、奖助学金 |
| 2b | `db.py` ALTER + 新建 `major_dao.py` + `models.py` | `majors` 扩字段：课程简介、考研方向(JSON)、薪酬区间、学科评估等级 |
| 2c | `api/routers/volunteer.py` 新增 endpoint | `GET /volunteer/subject-match` 选科适配查询 |
| 2d | 新建 `user_favorites_dao.py` + API | 院校/专业收藏、浏览历史 |

##### 第 3 段：推荐引擎升级 + 志愿表增强 ✅（已完成）

| 任务 | 文件 | 说明 |
|---|---|---|
| 3a | `volunteer_scorer.py` | 多策略推荐：院校优先/专业优先/城市优先（`STRATEGY_PRESETS` + `strategy` 参数）|
| 3b | `volunteer_scorer.py` | 捡漏推荐：`_calc_bargain_score` 大小年波动检测（< 均值 - 1.5σ）|
| 3c | `volunteer_scorer.py` | 推荐透明化：`_calc_admission_prob` 返回 `(prob, evidence)` 元组 |
| 3d | `volunteer_table.py` | 冲突检测接入志愿表 diagnose（`validate_all` + profile 构建）|
| 3e | `volunteer_table_dao.py` + API | 多方案管理（clone/rename/list/compare）|
| 3f | `export_service.py` + API + frontend | PDF/Excel 导出 |

##### 第 4 段：AI 对话抽屉 ✅（已完成）

| 任务 | 文件 | 说明 |
|---|---|---|
| 4a | `api/routers/volunteer_chat.py` + `services/custom/volunteer_chat_service.py` | `POST /volunteer/chat` 对话代理，使用 `complete()` LLM 调用 + 会话管理 |
| 4b | `web/components/volunteer/VolunteerChatDrawer.tsx` | slide-over 抽屉面板（FilePreviewDrawer 模式）|
| 4c | `web/app/(workspace)/volunteer/page.tsx` | 推荐卡片"AI 咨询"按钮 → 自动注入 college/tier 上下文 |
| 4d | `web/app/(workspace)/volunteer/page.tsx` | 浮动聊天按钮 + 抽屉集成 |

##### 第 5 段：RAG 知识库 ✅（已完成）

| 任务 | 文件 | 说明 |
|---|---|---|
| 5a | `services/custom/rag/store.py` | `sqlite-vec` 集成：`doc_chunks_v2` 向量表 + `doc_meta_v2` 元数据表 + `conflict_log_v2` 冲突日志 |
| 5b | `services/custom/rag/` 子包 | `embed.py`（hash 384维向量）/ `chunker.py`（段落切割+正则提取）/ `indexer.py`（管道）/ `retriever.py`（对话检索） |
| 5c | `services/custom/rag/chunker.py` + `indexer.py` | 正则提取（学费/住宿/区位/招生人数）+ LLM 兜底（GPT-4o-mini） |
| 5d | `services/custom/rag/store.py` | `conflict_log_v2` 表 + 优先级链（教育部>章程>专业介绍>就业报告>LLM） |
| 5e | `services/custom/rag/store.py` + `volunteer_chat_service.py` | `add_faq()` 增量入库 + RAG 上下文注入 chat 服务 |

##### 第 6 段：测评 + 可靠性 + 运营 ✅（已完成）

| 任务 | 文件 | 说明 |
|---|---|---|
| 6a | `services/custom/holland_assessment.py` + API | 霍兰德 RIASEC 6 维度测评 → 专业权重映射 + 免责提示 |
| 6b | — | 历史回测框架（待实现）|
| 6c | — | `_calc_admission_prob` 校准（待回测数据）|
| 6d | `volunteer_scorer.py` | 防滑档硬约束（`min_safe` 参数，默认至少 2 保底）|
| 6e | `volunteer_table.py` ai-tune | K5 AI 一键调整（LLM 重排，虚构院校过滤）|
| 6f | `AdmissionCountdown.tsx` | 5 省录取日程倒计时组件 |

#### 关键设计决策

- **向量库**: `sqlite-vec`（纯 SQLite 扩展，零新增依赖）
- **提取策略**: 规则优先 + LLM (GPT-4o-mini) 兜底，年成本 ~¥24
- **冲突仲裁**: 教育部>章程>专业介绍>就业报告>LLM 推理，置信度>0.9 自动合并，否则 `need_review`
- **AI 对话位置**: `/volunteer` 页面右滑抽屉（非独立页面，与卡片联动）
- **RAG 用途**: 在 AI 对话抽屉中，用户提问时自动从 `doc_chunks_v2` 向量库检索最相关文档（招生章程/政策/FAQ），注入 LLM 的 system prompt 作为参考资料。通过 `add_faq()` API 可增量入库常见问答。目前向量库需手动种子导入。

#### 测试覆盖

- [x] `test_student_profile.py` — dataclass 序列化/校验/边界（32 tests）
- [x] `test_volunteer_validator.py` — 四类限制检测 + 组合场景
- [x] `test_college_dao_enhanced.py` — 新增字段查询/筛选
- [x] `test_volunteer_scorer.py` — 多策略/捡漏/evidence 输出（已修复）
- [ ] `test_recommend_strategies.py` — 三策略输出一致性
- [ ] `test_bargain_recommend.py` — 捡漏检测逻辑
- [ ] `test_rag_pipeline.py` — 文档解析→提取→写入闭环
- [ ] `test_conflict_resolution.py` — 多源冲突仲裁
- [ ] `test_backtest_scorer.py` — 回测结果正确性

---

### Phase 11 🚀 专业组级志愿表 + Excel 全量导入

> 状态：设计完成，待实施

#### 目标

1. **导入 37k 行 Excel 全量数据**（广东2026高考志愿大数据专家版）
2. **志愿表改为专业组级**：一个专业组算一个志愿，组内专业可排序+打标签
3. **修复 SQL 不读专业组/专业的问题**

#### Excel 数据源

文件：`广东2026高考志愿大数据专家版0626.xlsx`（37079 行 × 67 列）

| 范围 | 内容 | 列 |
|------|------|----|
| 2026年招生计划 | 院校/专业组/专业/批次/选科/计划/学制/学费/门类/专业类 | 1-25 |
| 2025年录取 | 录取人数/最低分/最低位次 | 26-32 |
| 2024年录取 | 录取人数/最低分/最低位次 | 33-36 |
| 2023年录取 | 录取人数/最低分/最低位次/最高分/最高位次 | 37-42 |
| 院校基础信息 | 所在省/城市/标签/水平/保研率/排名/转专业/硕博点/章程 | 43-61 |
| 专业基础信息 | 软科评级/排名/学科评估/专业水平/硕博点 | 62-67 |

#### Slot 数据结构（专业组级）

```python
{
  "college_id": "10378",
  "college_name": "安徽财经大学",
  "group_code": "201",
  "group_name": "201组",
  "group_prob": 0.72,
  "tier": "steady",
  "order": 1,
  "adjustable": True,        # 是否服从调剂
  "majors": [
    {"major_id": "001", "major_name": "经济学", "admission_prob": 0.72, "order": 1, "tag": "推荐"},
    {"major_id": "002", "major_name": "保险学", "admission_prob": 0.68, "order": 2, "tag": "优选"},
  ]
}
```

#### 执行路线（Phase 11）

| # | 文件 | 说明 | 状态 |
|---|------|------|------|
| 1 | `scripts/import_excel_v3.py` | 导入器：37k 行 → admission_ranks(含group_code+3年数据) | ✅ 已完成 |
| 2 | `admission_dao.py` | `get_college_groups()` + `get_group_majors()` | ✅ 已完成 |
| 3 | `volunteer_scorer.py` | `score_group()` + `generate_group_recommendations()` | ✅ 已完成 |
| 4 | `volunteer_table.py` | `create_plan` 专业组级 slot | ✅ 已完成 |
| 5 | `volunteer/page.tsx` | Slot 卡片显示专业组+专业列表+调剂框 | ✅ 已完成 |

> **2026-07-26 修正**：以上实现有三个 bug 需修复

#### 修正方案（2026-07-26）

**问题**：
1. `_calc_admission_prob` 未按 `group_code` 过滤 → 专业组概率混用
2. `generate_group_recommendations` 先推荐 college 再查 group → 同校多组合容易被截断
3. 组内专业排序未考虑兴趣权重

**修正逻辑**

| 步 | 改动 | 说明 |
|----|------|------|
| A | `_calc_admission_prob` 加 `group_code` 参数 | 查询 `admission_ranks` 时按 `group_code` 过滤，只取该专业在该组的位次 |
| B | 新建 `generate_group_recs()` | 直接 `SELECT DISTINCT college_id, group_code FROM admission_ranks` → 对每个组合评分 → 分档 → top_n |
| C | `score_group` 组内排序 | 改为 `admission_prob × 0.6 + academic_fit × 0.4` 复合排序 |
| D | `create_plan` | 改用 `generate_group_recs` + `top_n=100` |
| E | `export_service.py` | `admission_prob` → `group_prob` 兼容 |
| F | `get_group_ranks_agg()` | 按 college+group 聚合各专业位次，每年取最低位次作为组级位次 |
| G | `volunteer_table.py` | `create_plan` slot 分配改为：按 ratio 取 min(计算值, 可用数)；缺口从剩余候选中按分档补齐至总数 = 45 |

#### Slot 数据结构

```python
{
  "college_id": "10558",
  "college_name": "中山大学",
  "group_code": "202",
  "group_prob": 0.72,            # 组级录取概率（按 GROUP 级别的位次算）
  "tier": "steady",
  "order": 1,
  "adjustable": True,
  "majors": [
    {"major_id": "001", "major_name": "经济学", "admission_prob": 0.72, "sort_score": 0.75, "tag": "推荐"},
    {"major_id": "002", "major_name": "金融学", "admission_prob": 0.65, "sort_score": 0.68, "tag": "优选"},
  ]
}
```

同院校不同专业组 → 独立的卡片：
```
中山大学 202组 [冲刺]  中山大学 203组 [稳妥]  中山大学 204组 [保底]
```

#### 标签规则

- 组内第一且 prob > 0.8 → `推荐`
- 组内第一且 prob 0.45-0.8 → `优选`
- 其余 → `可选`

#### 排序规则

- 主要按 `admission_prob` 降序
- prob 差值 < 0.05 时，参考学科兴趣权重（`academic_fit`）

#### 数据存储策略

- **SQL 主力存储**：admission_ranks, colleges, majors, college_majors
- **向量库辅助检索**：组内专业描述文本 + 转专业政策 → `doc_chunks_v2`（AI 对话抽屉用）

#### 三栏视图改造（2026-07-26）

- 删除 plan section 中独立的 slots 列表
- 三栏 `TierCard` 的数据源从 `reach/steady/safe`（college 级）改为按 `slot.tier` 过滤 `plan.slots`（专业组级）
- `TierCard` 渲染适配 `SlotItem`：显示 group_code, group_prob, majors[], adjustable

#### 性能优化：SQL 重写评分引擎 ✅（2026-07-27）

**问题**：Python 循环评分 7,979 个专业组需 **115s**，API 超时。

**方案**：录取概率 ≈ `user_rank / group_min_rank` 比值，纯 SQL 单查询可算，无需 115s 的 Python `math.erf` 循环。

```sql
SELECT college_id, group_code, AVG(best_rank) AS avg_rank,
       user_rank / AVG(best_rank) AS prob_ratio,
       CASE WHEN user_rank / AVG(best_rank) < 0.45 THEN 'reach'
            WHEN user_rank / AVG(best_rank) < 0.8 THEN 'steady'
            ELSE 'safe' END AS tier
FROM (SELECT college_id, group_code, year, MIN(min_rank) AS best_rank
      FROM admission_ranks WHERE province=? AND exam_category=?
        AND group_code!='' AND min_rank > 0
      GROUP BY college_id, group_code, year)
CROSS JOIN (SELECT ? AS user_rank)
GROUP BY college_id, group_code
```

| 改动 | 文件 | 说明 |
|------|------|------|
| 重写评分引擎 | `volunteer_scorer.py` | 删除 Python 循环评分，改为纯 SQL + 比值概率（~24k rows vs 82k+），预期 < 2s |
| `score_group` 简化 | `volunteer_scorer.py` | 去掉所有内部 DB 调用，接收预计算概率参数，改为 rank-ratio 概率 |
| `_compute_rank_ratio_prob` | `volunteer_scorer.py` | 新增函数：`1.0 - min(0.9, max(0.05, user_rank / weighted_avg_rank))` |
| 组内专业排序 | `volunteer_scorer.py` | 使用 `user_rank / major_best_rank` 算专业级 prob，无需 `_calc_admission_prob` |
| 向量库用途 | `doc_chunks_v2` | 不变，仅用于 AI 对话抽屉正文检索 |

### Phase 12 🚀 推荐准确性修正 (2026-07-27)

> 修复 rank 公式方向 + academic_fit 冷启动 + 分档阈值调整

**2026-07-27 修正（0.65/0.35 分档阈值）**：
- 原 0.8/0.45 仅覆盖 top 35% 考生（rank ≤ 176k），中低分考生 safe 常为空
- 改为 0.65/0.35：safe 需 `user ≤ 0.3×avg`，覆盖 rank ≤ 300k（约 70% 考生），三档始终非空

**问题清单**

| # | 问题 | 当前表现 | 修复 |
|---|------|---------|------|
| 1 | `_compute_rank_ratio_prob` 公式方向反 | rank 210k < 组 avg 450k，但算出低概率（210k 优于 450k 应为高概率） | `if user_rank <= avg: prob = 0.5 + 0.5*(avg-user)/avg else: prob = 0.5*avg/user` |
| 2 | major_prob 同样方向反 | 同上, 组内专业排序错误 | 同上公式 |
| 3 | `_calc_academic_fit` 无学习数据时回退 0.5 | 所有专业无区分度 | 用 `elective_subjects` 做冷启动（选了的科目推定 0.65，没选的 0.40）|

| 文件 | 改动 |
|------|------|
| `volunteer_scorer.py` | `_compute_rank_ratio_prob` → `_compute_rank_prob` 公式重写 |
| `volunteer_scorer.py` | `score_group`/`generate_group_recommendations` 内 major_prob 同修 |
| `volunteer_scorer.py` | `_calc_academic_fit` 加 elective_subjects 冷启动 |
| `test_volunteer_scorer.py` | 追加 rank 方向 + 冷启动测试用例 |
|---------------------------|--------------------------------------------------|

| 测试 | 结果 |
|------|------|
| `pytest tests/services/custom/ tests/tools/custom/ tests/capabilities/` | 191 passed, 6671 组评分 0.42s |

**2026-07-28 五问题修复**：

| # | 问题 | 修复 | 文件 |
|---|------|------|------|
| 1 | 应用区间改变预估分数 | 删 `handleRangeChange` 中 `setScore(String(maxScore))`；Chart 初始区间改为 ±20 分 | `page.tsx` |
| 2 | 750分→位次32（应为1） | `score_to_rank` 顶部加 `if score >= rows[0]["score"]: return 1` | `admission_dao.py` |
| 3 | 专业名称不显示 | `major_ranks` SQL JOIN `majors` 取 `name`；`score_group` 输出加 `major_name` | `volunteer_scorer.py` |
| 4 | 保底志愿缺失 | 分档阈值 `0.8/0.45` → `0.65/0.35`，覆盖 rank≤300k（~70%考生） | `volunteer_scorer.py` |
| 5 | Browse 缺分数区间过滤 | `BrowseRequest` 加 `score_min`/`score_max`，透传 `score_rank_range` | `volunteer.py` + `page.tsx` |

**2026-07-28 后续修复**：

| # | 问题 | 修复 | 文件 |
|---|------|------|------|
| 1 | 保底为空（auto rank range） | 删 `generate_group_recommendations` 中自动 `score_rank_range`（仅 chart 明确设置时应用） | `volunteer_scorer.py` |
| 2 | 部分组无专业显示 | 前端 majors 为空时显示"无细分专业" | `page.tsx` |
| 3 | 2026官方数据用错年份 | `import_guangdong_data_v3.py` 物理文件路径从 2025 改为 2026，年份从 2025 改为 2026 | `import_guangdong_data_v3.py` |
| 4 | 数据不全 | 重新导入：先跑 `import_guangdong_data_v3.py`（官方 2026 GEN 数据），再跑 `import_excel_v3.py`（专家版 2023-2025 专业级数据），GEN-only 从 34% 降至 10.6% | 两者 |

**2026-07-28 分档过滤策略**：
- SQL 用 ±50 分过滤（保 safe 存活）
- steady 用 ±10 分 post-filter 收紧
- reach 不额外限制（用户位次本就低于组平均，收紧会误杀）
- 图表 `score_min/score_max` 显式设置时跳过自动过滤

### Phase 13 🚀 CRAG 风格工具调用 (2026-07-27)

在 `VolunteerChatService` 内增加轻量级意图分类 + 工具调用，不接入完整的 agent 循环。

**流程**

```
用户问题 → LLM 分类 → college_search/admission_query/major_query/general_qa
                ↓ 需要查库
           调 DAO 查真实数据
                ↓
           LLM 综合 数据 + RAG 上下文 → 最终回答
```

| 文件 | 改动 |
|------|------|
| `volunteer_chat_service.py` | 新增 `_classify()` + `_execute_tool()` + `_build_prompt()` 修改 `chat()` |
| `test_volunteer_chat_service.py` | 追加工具调用 + 意图分类测试 |

> 已实现：意图分类 → 工具执行 → RAG 上下文 → LLM 综合回答（CRAG 风格）

### Phase 14 🚀 推荐系统功能增强

> 状态：Step 1-3 完成（2026-07-27），Step 4-6 待实施

**目标**：将推荐流程从"自动生成 45 格"改为"用户筛选自选 + 保留一键生成备选"

**流程**

```
输入分数 → ±10 分位次区间 + 学科/省份/层次筛选 + 策略权重
    ↓
符合条件的冲/稳/保院校列表（不自动填入）
    ↓
用户逐一点"加入志愿表" → 拖拽排序 → 诊断 → 导出
    ↓
[一键生成 45 格] 保留，备选
```

**实施步骤**

| Step | 内容 | 后端文件 | 前端文件 | 状态 |
|---|---|---|---|---|
| 1 | 策略预设 + 六维度进 `score_group`，替换 `is_elite` 硬编码 | `volunteer_scorer.py` | 无 | ✅ |
| 2 | 学科筛选：`generate_group_recommendations` 的 SQL 加 `major_id IN (子查询)` | `volunteer_scorer.py` + `volunteer.py` | `page.tsx` 加多选下拉 | ✅ |
| 3 | 分数输入 + 位次换算：`score_to_rank` 算 ±10 分 rank 区间，传给 SQL WHERE | `volunteer_scorer.py` + `volunteer_table.py` | `page.tsx` 表单重构 | ✅ |
| 4 | 自选流程：卡片加"加入志愿表"按钮 + 志愿表区域的 slot 列表 + 拖拽排序 + 单专业组删除 | 无 | `page.tsx` | ✅ |
| 5 | 捡漏标记：`generate_group_recommendations` 调 `_calc_bargain_score` | `volunteer_scorer.py` | `page.tsx` 卡片加标签 | ✅ |
| 6 | 分数分布曲线 chart.js + 可拖动区间手柄 0-750 | `volunteer.py` 加端点 | `page.tsx` | ✅ |

**Step 1 实现细节**：
- `score_group` 新增 `strategy` 参数，计算 dorm/city/cost/employment/academic_fit 六维度，用 `_resolve_strategy_weights` 加权
- 删除 `is_elite` 硬编码（`rank < 1000 → admission_only`），改用 `STRATEGY_PRESETS` 可配置策略
- `generate_group_recommendations` 同样删除 `is_elite`，透传 strategy 到 score_group
- `volunteer_table.py` 的 `create_plan` 透传 `body.strategy`

**Step 2 实现细节**：
- `generate_group_recommendations` 新增 `major_categories: list[str]` 参数
- SQL 查 `majors` 表取 category 对应的 major_id 集合，过滤 `major_ranks` 和 `group_agg`
- API: `volunteer.py` 新增 `GET /volunteer/major-categories` 端点；`volunteer.py RecommendRequest` 和 `volunteer_table.py CreatePlanRequest` 都加 `major_categories` 字段
- 前端：表单区域新增多选学科门类按钮行，从 API 加载分类列表

**Step 3 实现细节**：
- `generate_group_recommendations` 新增 `score_rank_range: tuple[int, int]` 参数
- 传入后 SQL 加 `EXISTS (SELECT 1 ... min_rank BETWEEN ? AND ?)` 子查询过滤 group
- 未传但 `user_profile` 含 score 时自动用 `score_to_rank(±10)` 计算
- 前端：分数输入时自动调用 `/study/rank-convert` 换算显示 ≈位次

**已有基础设施支撑**

| 之前做的 | 这次用在哪 |
|---|---|
| `score_rank_segments` 表 (2338 行) + `score_to_rank()` | Step 3 分数→位次换算 |
| `admission_ranks` 表 (82k 行) | Step 2/3 筛选+推荐数据源 |
| `STRATEGY_PRESETS` 权重预设 | Step 1 策略选择 |
| `search_colleges(province=, level=)` | Step 2 省份+层次筛选 |
| `majors.category` 字段 | Step 2 学科筛选 |
| `_calc_bargain_score()` | Step 5 捡漏标记 |
| `generate_group_recommendations` + `score_group` | Step 1-3 评分引擎 |
| `volunteer_table_dao` CRUD + 诊断 + 导出 | Step 4 志愿表管理 |
| `VolunteerChatDrawer` + CRAG | 问 AI 对话 |


### Phase 14.5 🚀 浏览推荐增强 + 专业级勾选 (2026-07-27)

**需求**：
1. 浏览模式不按省份规则截断，但按档设上限（冲50/稳100/保80）
2. 浏览卡片展示组内全部专业 + 录取概率进度条
3. 专业级 checkbox → 按勾选生成志愿表

| # | 内容 | 后端文件 | 前端文件 | 状态 |
|---|------|---------|---------|------|
| 1a | `generate_group_recommendations` 加 `per_tier_caps` 参数控制各档上限 | `volunteer_scorer.py` | — | ✅ |
| 1b | 新建 `POST /volunteer/browse` 端点，调用 `generate_group_recommendations(top_n=9999, per_tier_caps=...)` | `volunteer.py` | — | ✅ |
| 1c | `handleRecommend` 改调 `/browse` | — | `page.tsx` | ✅ |
| 2 | 浏览卡片展开全部专业行 + 录取概率进度条 | — | `page.tsx` | ✅ |
| 3 | `checkedMajors` 状态 + checkbox → `addToPlan` 仅入勾选专业 | — | `page.tsx` | ✅ |

**改动范围**：后端 2 文件 + 前端 1 文件，无数据库迁移，无新依赖。

**实现说明**：
- 浏览端 `POST /volunteer/browse` 返回三档，上限 冲50/稳100/保80，不按省份比例截断
- 每个专业组卡片内展示全部专业，每行：checkbox + 专业名 + 标签 + 概率进度条 + 百分比
- 顶部"全选"checkbox 一键切换
- "加入志愿表"按钮状态联动：未勾选专业时显示"请勾选专业"，已加入过显示"已加入"
- `_calc_bargain_score` 已接入 group 管道，捡漏标记在卡片上展示
- slot 的 `majors` 仅含勾选的专业

### Phase 15 🚀 双向记忆融合：志愿模块 ↔ L3 Memory（2026-07-27）

> 志愿填报模块与 DeepTutor L3 长期记忆系统深度对接，实现学习者画像的双向读写。

#### 架构

```
L3 memory (profile.md / preferences.md)
    ▲                        │
    │ MemoryStore.read_doc() │ MemoryStore.write_preference()
    │                        ▼
┌───┴───────────────────────────────┐
│        memory_bridge.py           │
│   extract_learner_profile()       │
│   write_preference_signal()       │
└───────┬───────────────────┬───────┘
        │ 读                │ 写
        ▼                   │
┌────────────────┐  ┌───────┴────────────┐
│  loop.py       │  │ volunteer_chat_    │
│  pre_loop →    │  │ service.py         │
│  context.meta  │  │ → 对话后写回偏好     │
│  augment_kwargs│  └────────────────────┘
└───────┬────────┘          │
        │                   │
┌───────▼────────┐  ┌───────▼────────────┐
│  volunteer_    │  │  volunteer_tools    │
│  scorer.py     │  │  → weights 写回 L3  │
│  _calc_academic│  └────────────────────┘
│  _fit 优先链    │
└────────────────┘
```

#### 改动文件

| 文件 | 操作 | 行数 | 说明 |
|------|------|------|------|
| `deeptutor/services/custom/memory_bridge.py` | **新建** | ~100 | `extract_learner_profile()` 解析 L3 Markdown → 结构化 dict；`format_learner_briefing()` 生提示块；`write_preference_signal()` L3 写回封装 |
| `deeptutor/capabilities/volunteer/loop.py` | **改** | +60 | 新增 `pre_loop` async 钩子读 L3 → 注入 `context.metadata["_volunteer_learner_profile"]` + 返回 PromptBlock；`augment_kwargs` 透传 `_subjects` 和 `_learner_profile` |
| `deeptutor/services/custom/volunteer_scorer.py` | **改** | +25 | `_calc_academic_fit` 优先链：注入数据 → L3 learner_profile 冷启动 → study_dao 回退 |
| `deeptutor/tools/custom/volunteer_tools.py` | **改** | +20 | `VolunteerWeightsTool` set mode 成功后写回 L3 preferences |
| `deeptutor/services/custom/volunteer_chat_service.py` | **改** | +45 | 接受 `learner_profile` 参数注入提示；对话后检测偏好关键词并写回 L3 |
| `deeptutor/api/routers/volunteer_chat.py` | **改** | +15 | 透传 `learner_profile` 到 service |

#### 数据流

**读方向（L3 → volunteer）：**
1. `pre_loop` 钩子 → `MemoryStore.read_doc("L3", "profile")` + `.read_doc("L3", "preferences")`
2. `extract_learner_profile()` → `{strengths, weaknesses, goals, career_interests, location_prefs}`
3. 合并 `study_dao.get_subject_summary()` → `_subjects`
4. 写入 `context.metadata["_volunteer_learner_profile"]`
5. 返回 `PromptBlock("learner_profile", ...)` → system prompt
6. `augment_kwargs` 透传到 volunteer tool 的 kwargs
7. `_calc_academic_fit` 优先用注入数据 (1), 次优 L3 冷启动 (2), 回退 DB (3)

**写方向（volunteer → L3）：**
1. `weight tool set` → `write_preference_signal(text="调权重: ...")`
2. `chat 服务检测偏好关键词` → `write_preference_signal(text="志愿咨询: ...")`
3. 通过 `MemoryStore.write_preference(op="add", ...)` 写入 L3 `preferences.md`

#### 限制

- 仅读 L3 `profile` + `preferences` 两个 slot，不读 `recent`/`scope`
- 写回仅通过 `write_preference`（不直接操作 Markdown）
- `study_records` 保持在 `custom.db`，不做数据迁移

#### 测试

- `test_memory_bridge.py` — profile doc 解析/空文档/写回异常安全
- `test_volunteer_capability.py` — pre_loop 注入后 metadata 含 profile、PromptBlock 内容
- `test_volunteer_scorer.py` — _calc_academic_fit 三优先链
- `test_volunteer_tools.py` — weights set 后 L3 写回

### Phase 16 🚀 地域选择 + 策略多选 + 保存管理（2026-07-28 实施）

> 全部已完成

#### 方向 A：地域选择插件 ✅

| 任务 | 文件 | 说明 | 状态 |
|------|------|------|------|
| A1 | `db.py` + 迁移 | `colleges` 表加 `city_tier`（一线/新一线/二线/三线/其他）和 `region`（华东/华南/华北/华中/西南/西北/东北）字段；migration 用 `ALTER TABLE` + `COALESCE` | ✅ |
| A2 | 数据回填 | `scripts/seed_region_data.py` 用 `CITY_TIER` 映射 + 省份→大区映射，回填 4588 所院校 | ✅ |
| A3 | `college_dao.py` | `search_colleges` 加 `city_tier`/`region`/`cities`（LIKE 前缀匹配）过滤参数 | ✅ |
| A4 | `volunteer.py` API | Browse/Recommend 端点加 `city_tier`/`region`/`cities` 参数 | ✅ |
| A5 | 前端 | 城市等级下拉（一线/新一线/二线/三线/不限）、地域大区单选（华东/华南/华北…）、城市多选 tag（按大区分组，scrollable，清除按钮） | ✅ |

**城市重复修复**：`GET /volunteer/cities` SQL `RTRIM(city, '市')` 去重（668→418 个城市）

#### 方向 B：策略多选组合 ✅

| 任务 | 文件 | 说明 | 状态 |
|------|------|------|------|
| B1 | `volunteer_scorer.py` | `_resolve_strategy_weights` 支持 `list[str]` 多选融合（逐维度取均值，总和归一化） | ✅ |
| B2 | `volunteer.py` + `volunteer_table.py` | API `strategy`(deprecated) → `strategies: list[str]` 兼容旧参数 | ✅ |
| B3 | `page.tsx` | dropdown → checkbox 多选组（含权重预览百分比环）；策略名：院校优先/专业优先/城市优先/综合推荐 | ✅ |

**权重融合算法**：
- 选中 N 个策略，每个维度取 N 个策略在该维度的均值
- 例：院校优先{admission:0.5, academic:0.3} + 专业优先{academic:0.35, employment:0.2}
  → 融合 {admission:0.25, academic:0.325, employment:0.1, cost:0.05, ...}
- 未选中任何策略时默认 `["default"]`

#### 方向 C：历史志愿表管理 ✅

| 任务 | 文件 | 说明 | 状态 |
|------|------|------|------|
| C1 | `page.tsx` | `savePlan` 回调（PUT plan/{id} slots）+ "保存"按钮（蓝色Save图标） | ✅ |
| C2 | `page.tsx` | `loadSavedPlans` + `loadPlan` + `deleteSavedPlan` 回调；可折叠"历史方案"面板（关闭/加载/删除） | ✅ |

### Phase 17 🚀 编码归一：全面官方码化（B 方案，2026-08-08 记录，实施中）

> 状态：数据调查**已完成**，方向确认 **B（全面官方码化）**，实施中。
> 用户决策：① 同名 CU 删除 ② 变体挂"主校码+后缀" ③ 多省扩展 → 主键全面改官方码 ④ admission_ranks 本次一并官方码化
> **2026-08-12 更新：迁移已执行并验证通过 🎉。** 「实施中」→「已完成」。见下「迁移结果」。

#### 背景：3 套编码 → 1 套主键 + 映射

| 编码 | 样子 | 示例 | 现状用途 | 处置 |
|------|------|------|---------|------|
| 地方码 | 5 位 | `10558` 中山 | `admission_ranks.college_id` / `colleges.id` | 降级为省别名存映射表 |
| **官方码** | 10 位 | `4144010558` | 教育部全国名单 | **统一为主键** |
| 合成码 | `CU000xx` | `CU01903` 中山 | 全国补充库 | **清零** |

**核心关系**：官方码 10 位后 5 位 = 广东地方码（`4144010574` 华师大 → `10574`）。

#### 数据事实（已核实）

- `colleges`：numeric（广东地方码）**1819** / CU（合成码）**2769**
- numeric 1766/1819 按名匹配官方码（53 变体：北大医学部/哈工深/军校等）
- CU 2499/2769 精确匹配官方码；270 不匹配

**CU 2769 分解**：

| 类别 | 数量 | 处置 |
|------|------|------|
| 同名 numeric（重复） | 1581 | 删除 |
| 独有、有官方码 | 925 | CU→官方码 |
| 无官方码（军校/分校区/医学院） | 263 | 主校码+后缀 |

**残留 CU 引用面（改/删需迁移）**：
- `college_majors.college_id` CU → 31278 行（同名 18065 / 独有 13213）
- `volunteer_plans.slots`（JSON）CU → 175 槽 / 20 校（用户已生成方案，**必须迁移**）
- `admission_ranks.college_id` CU → 9 行；**非广东省份测试数据（北京/浙江/湖北/四川/福建）全用 CU 码**
- `admission_ranks_old`（全 CU 1672 行）→ 删除

**变体全库精确集合 = 15 所**（官方名单无码，挂主校码+后缀）：
北大医学部/复旦医学院/上交医学院/浙大医学院/东北大学秦皇岛/人大苏州校区/中石油克拉玛依/北交威海/北师大珠海/**华师大汕尾**/合工大宣城/大工盘锦/山大威海/电子科大沙河/西南大学荣昌 等（省市校区类通用 `主校官方码-XX` 规则）

**多省扩展机制**（重点）：任何省数据导入时先查 `college_code_map`（`official_code, province, province_code`）转官方码再入库。广东用规则自动生成映射；其他省按名称匹配；与教育部码无关的省份同样"加一行映射"即可。

#### 实施步骤

0. 备份：`cp deeptutor_custom.db deeptutor_custom.db.bak_before_code`
1. `ALTER TABLE colleges ADD COLUMN official_code TEXT`（幂等）
2. 建 `college_code_map` 表：`(official_code, province_code, province, school_name, source, PRIMARY KEY(official_code, province_code))`
3. 写 `scripts/migrate_college_codes.py`（含 `--dry-run`）：官方名单→name→官方码；遍历 CU+numeric 分类 `mapped`/`dupe_delete`/`variant`
4. **dry-run 审计报告** → 用户核对 → 真跑
5. 数据迁移：numeric 回填 official_code；同名 CU 1581 删除（先迁引用）；独有 CU 925 id=官方码；变体 263 主校码+后缀；`admission_ranks`/`college_majors` 地方码→官方码；`volunteer_plans.slots` 重写 college_id；删 `admission_ranks_old`
6. 代码适配：**无需额外过滤** —— 迁移后 `colleges.id` 即官方码，`search_colleges(college_ids=...)` 走 `c.id IN(...)` 已等官方码过滤；`official_code` 列与 id 冗余，仅作溯源存档
7. 回归验证：`generate_group_recommendations(广东,物理)` 改码前后对比 = 零回归；`pytest`；复跑 `ai_tune_plan`

#### 迁移结果（2026-08-12 已执行 ✅）

**分类落地**：

| 类别 | 计划 | 实际 |
|------|------|------|
| numeric → 官方码 | 1766 | 1795＋2（括号全/半角漏网补齐） |
| numeric 变体（主校码+后缀） | 24 | 24＋1（`19414 中石油克拉玛依` 并入 `4111011414-KLM`） |
| CU 同名删除 | 1581 | 1581 |
| CU → 官方码 | 925 | 925 |
| CU 变体 | 8 | 8 |
| CU 冲突保留 | 255 | 255（军校/军医/公安类，官方无码） |

- **执行脚本**：`scripts/migrate_college_codes.py`（FK OFF → 改名 → 引用 remap → map 填充 → FK ON）
- **补迁脚本**：`scripts/backfill_missing_official_codes.py`（括号归一化漏网 8 行；两次运行已清零）
- **引用迁移**：`admission_ranks`/`college_majors` 用 `INSERT OR REPLACE … SELECT(换college_id)` + `DELETE`（同校对同一官方码时 PK 合并，唯一一次合并是北大 `EN001` 同名重复行，非数据丢失）；`volunteer_plans.slots` JSON、`doc_meta_v2.metadata` 均重写
- **净行数**：`admission_ranks` 83635（不变）、`college_majors` 68350→68349（合并去重 1）、`colleges` 4588→3000
- **完整性**：孤儿引用 0、FK check 0、`admission_ranks_old` 已删
- **关键坑**：官方名单用全角括号（`中国石油大学（华东）`）而库里是半角 —— `_lookup_official` 做括号归一化匹配，否则 8 所院校漏网
- **回归**：`generate_group_recommendations(广东,物理)` 0.9s，三档 33/33/33，样例与迁移前一致；`pytest tests/services/custom tests/tools/custom tests/capabilities` = **191 passed**
- **备份**：`data/user/custom/deeptutor_custom.db.bak_before_code_20260811_235309` + 补迁前备份存在，可回滚

#### 关键风险

- `volunteer_plans` 175 槽必须备份迁移，失败可回滚
- 非广东测试数据（CU 码）必须一并迁移，否则 join 孤儿
- 全程 dry-run → 审计 → 实跑；每步可逆

#### 相关文件

| 文件 | 说明 |
|------|------|
| `deeptutor/services/custom/db.py` | 加列 + 建映射表 |
| `scripts/migrate_college_codes.py` | 迁移脚本（新建，含 dry-run；2026-08-12 完善 FK OFF / 引用 remap / FK check） |
| `scripts/backfill_missing_official_codes.py` | 括号归一化漏网补迁脚本（新建） |
| `deeptutor/services/custom/volunteer_scorer.py` | 验证用（零改动，回归通过） |
| `deeptutor/services/custom/college_dao.py` | 验证用（id 即官方码，search 无需改动） |
| `全国高等院校名单2026.xls` / `广东2026高考志愿大数据专家版0626.xlsx` | 数据源 |

### Phase 18 🚀 军警校国标码化（2026-08-12 记录，实施中）

> 状态：查证**已完成**，迁移计划**已定稿**，实施中。
> 用户决策：① 军警校 CU **全部清零**（一个不留）② 军改合并校 → 并入新校删除原名称 ③ 不合并校 → 统一改国标码 ④ 92036 联勤保障部队工程大学官方自述即国标，保留 ⑤ 普通 ~220 所 CU **本次不动**（另行决定）。
> **2026-08-13 更新：迁移已执行并验证通过 🎉。** 「实施中」→「已完成」。见下「迁移结果」。

#### 背景：军校 3 套编码并存

| 编码 | 来源 | 现状 | 处置 |
|------|------|------|------|
| `9xxxx`（92002 等） | 专家版 Excel「院校代码」列 / 广东招生系统 | `colleges.id` 20 所 | 归国标码，地方码登记 `college_code_map` |
| `CU0xxxx` | 全国补充库 | 军警校 31 所 | 全部迁移，CU 清零 |
| `91xxx` **国标码** | 教育部（国防部/考试院/官方简章） | 库中不存在 | **统一为主键** |

**关键认知**：`92xxx` = 广东/招生系统代码（用户拍板，如国防科大 `92002`→国标 `91002`）；`91xxx` = 教育部国标码（如国防科大 `91002`）。2026 广东军检表证实 `92002/92004/92005` 均为“陆军兵种大学[国防科大等]在广东的代码”。

#### 权威国标码（多源交叉验证）

国防部 2026 军招政策解读、浙江考试院 2024 选考要求、新浪广东投档表、武警警官学院官方简章（明示“国标代码 91040”）、globalsecurity/jamestown 军研所 37 校表、路灯考研、研招网等多源一致：

`91001国防大学 91002国防科大 91003陆军指挥 91004陆军工程 91005步院 91006装甲兵[旧]→91006陆军兵种大学[新] 91007炮兵防空兵 91009特战 91010边海防 91011防化 91012陆军军医 91013军事交通 91014勤务 91015海军指挥 91016海工 91017大连舰艇 91018潜艇 91019海航 91020海医 91021海军勤务 91022海士官 91023空军指挥 91024空工 91025空航 91026预警 91027哈尔滨飞院 91028石家庄飞院 91029西安飞院 91030空医 91031空军勤务 91032空通信士官 91033火箭军指挥 91034火箭军工程 91035火箭军士官 91036航天 91037信息工程 91038武警指挥 91039武警工程 91040武警警官 91041特警 91042武警后勤 91044海警`

#### 迁移映射（已定稿）

**A. `9xxxx` → 国标（改 id 重命名，18 所）**

| 库 id | 现名 | → 国标 |
|---|---|---|
| 92002 | 国防科技大学 | 91002 |
| 92004 | 陆军工程大学 | 91004 |
| 92005 | **陆军兵种大学** | **91006**（继承装甲兵国标） |
| 92006 | 陆军步兵学院 | 91005 |
| 92010 | 陆军防化学院 | 91011 |
| 92011 | 陆军军医大学 | 91012 |
| 92013 | 海军工程大学 | 91016 |
| 92014 | 大连舰艇学院 | 91017 |
| 92022 | 空军工程大学 | 91024 |
| 92023 | 空军预警学院 | 91026 |
| 92027 | 空军军医大学 | 91030 |
| 92031 | 火箭军工程大学 | 91034 |
| 92033 | 军事航天·航天工程大学 | 91036 |
| 92034 | 网络空间·信息工程大学 | 91037 |
| 92038 | 武警工程大学 | 91039 |
| 92039 | 武警警官学院 | 91040 |
| 90046 | 空军航空大学 | 91025 |
| 90050 | 海军航空大学 | 91019 |

**B. CU 同名 → 并入对应国标行（迁移后删旧，12 所）**
`CU00793→91004` `CU01301→91005` `CU00081→91011` `CU01691→91016` `CU00480→91017` `CU01424→91019` `CU00578→91025` `CU02591→91024` `CU01700→91026` `CU02272→91040` `CU00073→91036` `CU01527→91037`

**C. 军改合并校（并入新校 + 删原名称，4 所）**
- `CU00060 陆军装甲兵` + `CU01104 炮兵防空兵` → **91006 陆军兵种大学**
- `CU00132 陆军军事交通` + `CU02201 陆军勤务` → **92036 联勤保障部队工程大学**（92036 官方自述即国标，主键不动）

**D. 独立 CU → 国标码（直接改 id，14 所）**
`CU00095→91001国防大学` `CU00097→91041特警` `CU00156→91038武警指挥` `CU00157→91021海军勤务` `CU00281→91028石家庄飞院` `CU00529→91032空通信士官` `CU00704→91020海医` `CU00907→91015海军指挥` `CU00945→91044海警` `CU01138→91022海士官` `CU01472→91018潜艇` `CU01485→91035火箭军士官` `CU02054→91009特战` `CU02625→91010边海防`

**E. 警校 CU（6 所，查证后迁移）**
`CU00778 南京森林警察→4132012213南京警察学院`（库已有）、`CU01541 铁道警察→4141012735郑州警察学院`（库已有）、`CU00135 天津公安警官职院`、`CU00395 内蒙古警察职院`、`CU02581 陕西警官职院`、`CU02654 甘肃警察职院`

#### 实施步骤

0. 备份 `deeptutor_custom.db`
1. 写 `scripts/migrate_military_codes.py`（含 `--dry-run`，复用 Phase 17 模式：FK OFF → 改名 → 引用 remap → map 填充 → FK ON）
2. dry-run 审计报告 → 核对 → 实跑
3. 引用迁移：`admission_ranks`（军校 421 行 = 物理 410 + 历史 11）、`college_majors`、`volunteer_plans.slots` JSON、`doc_meta_v2.metadata` 重写
4. `college_code_map` 登记全部 92xxx/90xxx 地方码（`official_code=91002, province_code=92002, province='广东', source='gd_gaokao2026'`）
5. 孤儿引用=0、FK check、军警 CU 清零
6. 回归：`generate_group_recommendations(广东,物理)` 三档零回归；`ai_tune_plan` 冒烟；`pytest`（191 passed 目标）
7. AGENTS.md 迁移结果 + 单独 commit

#### 相关文件

| 文件 | 说明 |
|------|------|
| `deeptutor/services/custom/db.py` | college_code_map 表（Phase 17 已建，复用） |
| `scripts/migrate_military_codes.py` | 军警校迁移脚本（新建，含 dry-run） |
| `scripts/migrate_college_codes.py` | Phase 17 模板（FK OFF/remap/FK check） |
| `全国军警校国标代码表_整理版.xlsx` | 用户提供（注意：15/20 与权威源冲突，已弃用表中军校码改按权威） |
| `广东2026高考志愿大数据专家版0626.xlsx` / 国防部 2026 军招解读 | 9xxxx 来源 + 军改官方依据 |

#### 迁移结果（2026-08-13 已执行 ✅）

**分类落地**：

| 类别 | 数量 | 说明 |
|------|------|------|
| A. 9xxxx → 国标（改 id） | 18 | 92002→91002 国防科大 等；92005→91006 陆军兵种大学 |
| B. CU 同名并入国标 | 12 | 迁移引用后删 CU 行 |
| C. CU 军改合并校并入新校 | 4 | 装甲兵+炮兵防空兵→91006；军事交通+勤务→92036 |
| D. CU 独立军校 → 国标 | 14 | 91001 国防大学 / 91041 特警 等 |
| E. 警校 CU | 6 | 4 所并入库中升格新校 + 2 所改新标识码并更名 |
| **合计迁移** | **54** | 军警 CU 清零 |

- **执行脚本**：`scripts/migrate_military_codes.py`（幂等，FK OFF → 改名/删行 → 引用 remap → map 填充 → FK ON）
- **警校细节**：`CU00135 天津公安警官职院→4112012723 天津警察学院`、`CU02654 甘肃警察职院→4162012834 甘肃警察学院`、`CU00778 南京森林警察→4132012213 南京警察学院`、`CU01541 铁道警察→4141012735 郑州警察学院`（均已入库，仅迁引用删 CU）；`CU00395 内蒙古警察职院→4115012797 内蒙古警察学院`、`CU02581 陕西警官职院→4161013819 陕西警察学院`（未入库，直接改 id+更名）
- **净行数**：`admission_ranks` 83635（不变，军警 421 行全量保留）、`college_majors` 68350→68343（军警并入去重 7）、`colleges` 3000→2980（军警净删 20）、CU 255→219（36 所军警清零，219 普通 CU 保留另行处理）
- **完整性**：孤儿引用 admission_ranks=0 / college_majors=0、FK check=0、军警 CU 残留=0、旧 9xxxx 行=0
- **college_code_map**：登记 20 条 `gd_gaokao2026`（official_code=91xxx ↔ province_code=92xxx/90xxx，province='广东'）+ 2 条 `official_rename`（内蒙古/陕西警校）
- **回归**：`generate_group_recommendations(广东,物理)` rank=25000 5.93s 三档 80/100/50（评分正常，军警在 91x 下与迁移前 9xxxx 行为一致）；ai_tune top_n=45 三档 15/15/15 无孤儿；`pytest tests/services/custom tests/tools/custom tests/capabilities` = **191 passed**
- **备份**：`data/user/custom/deeptutor_custom.db.bak_before_military_20260812_235906`（可回滚）
- **踩坑**：① 首次执行第 4 步 college_code_map 的 POLICE_DIRECT 循环 tuple 未解包报错，colleges/引用已提交、脚本幂等重跑补齐 map；② 推荐引擎键名是 `result['college']['id']` 非 `college_id`（回归脚本需按此读取）
- **范围外**：普通 CU 219 所（CU00062 北京电子科技职业学院 等，含 17 专业 college_majors 引用）本次未动，另行决定

### Phase 19 🚀 普通 CU 国标码化（2026-08-13 记录，已完成）

> 状态：迁移已执行并验证通过 🎉。军警 CU 清零后，处理剩余 219 所普通 CU（合成码，全国补充库）。
> 用户决策：① 确认转设/更名/升格的 183 所 -> 迁移官方码 ② 撤销/停办/并入的 7 所 -> 删除（并入的 remap 引用）③ 无官方码的 29 所 -> 保留不动。

#### 背景：普通 CU 219 所 3 类处置

| 类别 | 数量 | 处置 |
|------|------|------|
| 转设/更名/升格（有官方码） | 183 | CU → 官方码（目标存在则并入，缺失则改 id + 更名） |
| 撤销/停办/并入 | 7 | 并入 2 所 remap 引用；其余 5 所删行 + 清 college_majors 引用 |
| 无官方码（KEEP） | 29 | 保留 CU 码不动 |

**处置依据**（教育部 2024-2026 官方名单交叉核对）：
- 2025 更名：淮安大学（CU00791 淮阴工学院）、苏州工学院（CU00792 常熟理工）、绍兴大学（CU00935 绍兴文理）、闽江大学（CU01146 闽江学院）、江西水利电力大学（CU01237 南昌工程）、顺德职业技术大学（CU01959 顺德职院）等
- 升格：包头师范学院（CU00378，原包头师院）、佛山大学（CU01929，原佛山科技）、深圳职业技术大学（CU01940）、深圳信息职业技术大学（CU01972）等
- 并入：CU02080 广西大学行健文理学院 → 广西民族大学 4145010608、CU02395 贵州师大求是学院 → 贵阳康养职业大学 4152016206
- 撤销/停办：山东杏林科技职院（CU01479）、湖北青年职院（CU01765）、鄂东职院（CU01766）、西北师大知行学院（CU02653）、兰财长青学院（CU02657）

**关键坑**：
- 4 个目标码缺失且多 CU 指向同一新校（合并校）：浙江药科职业大学 4133016207（CU00966+975）、安徽应用技术职业大学 4134012072（CU01047+069+087）、云南交通职业技术大学 4153012357（CU02473+516）、新疆工业职业技术大学 4165012514（CU02726+749）——脚本用第一个 CU 改 id 建行，其余并入
- 纯删除 CU 的 college_majors 引用需显式 DELETE，否则孤儿

#### 迁移结果（2026-08-13 已执行 ✅）

| 类别 | 数量 | 说明 |
|------|------|------|
| 并入目标行（目标码存在） | 109 | remap 引用后删 CU 行（含 4 组合并校的第二行起） |
| 改 id + 更名（目标码缺失） | 76 | 其中 4 组合并校首个 CU 建行 |
| 删除 | 7 | 5 所删行+清引用，2 所 remap 后删 |
| KEEP 保留 | 29 | 邢台职院/内地高校+中外合作/军校分院 等 |

- **净行数**：`colleges` 2861（军警后 2980 − 净删 119）、`college_majors` 68179（2231 CU 引用 remap/清理，merge 去重）、`admission_ranks` 83635（不变，CU 引用为 0）
- **完整性**：孤儿引用 admission_ranks=0 / college_majors=0、FK check=0、非 KEEP CU 残留=0、KEEP 29 所全部保留（college_majors 323 行 CU 引用全属 KEEP）
- **回归**：`generate_group_recommendations(广东,物理)` rank=25000 0.36s 三档 15/15/15 无 CU 混入；`pytest tests/services/custom tests/tools/custom tests/capabilities` = **191 passed**
- **备份**：`data/user/custom/deeptutor_custom.db.bak_before_cu_20260813_224952`（可回滚）
- **剩余 CU**：29 所（`CU00212` 邢台职院、`CU01933` 北师大-浸会联合、`CU02350` 电子科大格拉斯哥 等），官方名单无码，保留作备用

| 文件 | 说明 |
|------|------|
| `scripts/migrate_remaining_cu.py` | 普通 CU 迁移脚本（新建，含 --dry-run；KEEP/DELETE/MIG 三表配置） |

### Phase 19.5 🚀 剩余 29 所普通 CU 最终清零（2026-08-13 记录，已完成）

> 状态：迁移已执行并验证通过 🎉。Phase 19 保留的 29 所"无码" CU 全部找到最终处置，合成码彻底清零。
> 用户决策：① 25 所核实官方码 → 迁移（并入 11 / 改 id+更名 14）② 4 所中外合作办学二级学院 → 删除 ③ 2 所干部学院 → 迁移（成人高校 42 段标识码）。

#### 处置清单（29 → 0）

| 类别 | CU 数 | 明细 |
|------|------|------|
| 并入已有官方行 | 11 | CU00212→河北科技工程职大、CU00628→哈尔滨建筑科技职大、CU01575→郑州健康学院、CU01933→北师香港浸会大学（UIC 双码消除）、CU02289→成都轻工职大、CU02403→贵州轻工职大、CU02475→曲靖健康医学院、CU02487→昆明科技职大、CU02670→甘肃工业职大、CU02747+CU02752→新疆和田学院 |
| 改 id+更名建行（目标缺失） | 14 | CU00322→山西文化旅游职大 4114013696（建行）、CU00342/344/349/350→并入该行、CU00386→内蒙古建筑职大、CU00390→呼和浩特职大、CU00398→兴安职大、CU00587→长春医药职院、CU01066→合肥理工学院（江淮学院转设）、CU02530→西藏农牧大学、CU02758→新疆工程职大、**CU00276→河北青年管理干部学院 4213051802**、**CU00586→吉林省经济管理干部学院 4222051243** |
| 删除（中外合作二级学院） | 4 | CU02350 电子科大格拉斯哥、CU02341 西南财大特拉华、CU02440 贵州财大西密歇根、CU02231 重庆移通中德（46 行 college_majors 清理） |

**官方码来源**：教育部设置/更名函（山西文化旅游职大 4114013696、内蒙古建筑 4115010871、呼和浩特 4115012670、兴安 4115012443、西藏农牧 4154010693、新疆工程 4165014523、合肥理工 4134013612）+ 掌上高考国标码（长春医药 4122012306）+ 教育部成人高校标识码（河北青年 4213051802、吉林经管 4222051243）。

#### 迁移结果

- **净行数**：`colleges` 2842（2857 − 4 删除 − 11 并入合并）、`college_majors` 68101（323 CU 引用 remap/清理，merge 去重）、`admission_ranks` 83635（不变，CU 引用为 0）
- **完整性**：孤儿引用 admission_ranks=0 / college_majors=0、FK check=0、**CU 残留 = 0（合成码彻底清零）**、UIC 双码消除（4144016401 唯一）
- **回归**：`generate_group_recommendations(广东,物理)` rank=25000 0.33s 三档 15/15/15 无 CU 混入；`pytest tests/services/custom tests/tools/custom tests/capabilities` = **191 passed**
- **备份**：`data/user/custom/deeptutor_custom.db.bak_before_cu_final_20260813_234728`（可回滚）
- **坑**：干部学院用 `42` 段（成人高校）而非普通高校 `41` 段标识码，属正常；山西文旅职大 4 所并入需先由 CU00322 建行再 remap（复用 Phase 19 多 CU 同码逻辑）

| 文件 | 说明 |
|------|------|
| `scripts/migrate_remaining_cu.py` | 处置表改写为最终版（MIG=25 / DELETE=4 / KEEP=0），复用 Phase 19 迁移逻辑 |

### Phase 20 🚀 专业元数据（学制/校区/学费）+ 2026 官方专业目录比对

> 状态：方向 A（元数据）已完成；方向 B（比对 + 提前批 + 批次选择）**已完成**（2026-08-17）。

#### 方向 A：志愿专业行加 学制/校区/学费 ✅（2026-08-17）

**背景**：PDF 目录每专业含「学制：4年 / 学费：xxx元/学年 / 办学地点：xx校区」，Excel 已有结构化列但未入库。用户要求这三个字段展示在志愿（方案 slot + 浏览卡片）的每个专业行。

**实施**：
| 文件 | 说明 |
|------|------|
| `deeptutor/services/custom/db.py` | `college_major_name` 加 `years`/`campus` 列（幂等 ALTER + CREATE 同步） |
| `scripts/backfill_major_meta.py` | **新建**——从 Excel 回填：学制 36827 行（col17），校区 31434 行（col12 备注正则 `[（(](xx校区/校本部/xx区)[）)]` 提取）；学费列原有 |
| `deeptutor/services/custom/volunteer_scorer.py` | `major_ranks` JOIN 带出 `years`/`campus`/`tuition` → `majors_per_group` → `score_group` 写入 `scored_majors` |
| `deeptutor/api/routers/volunteer_table.py` | `create_plan` slot majors 透传三字段；**顺带修复** major_name 取错源（原来查全局 `majors` 表 → 改用 scorer 的 `college_major_name.major_name`） |
| `web/app/(workspace)/volunteer/page.tsx` | `SlotMajor` 类型 + `formatMajorMeta()` helper（`3年 · 仙溪校区 · 4980元/年`）；浏览卡片 + slot 专业行均展示 |

**验证**：浏览推荐 `广州城建职业学院 g507 智能交通技术: 学制3 校区清远校区 学费20000`；plan slot 三字段完整；`tsc --noEmit` 无错；pytest 191 passed。

#### 方向 B：2026 官方专业目录比对（PDF vs 库）✅

**数据源**：`/home/sunnyxuan2/桌面/data for agent/` — 物理版 672 页 / 历史版 376 页（文字型，已全量解析）+ 志愿指南 684 页（纯扫描图，OCR 待装）+ `2026广东专业目录更正表.xlsx`（12 校勘误）。

**已完成**：
- `scripts/parse_gd_pdf.py` — 按列切分解析器（x 区域归属 + 组头 + 跨页 merge + 跳过目录页）；物理 1708 校/4373 组/16953 专业、历史 1463 校/1811 组/7546 专业 → `data/user/custom/pdf_parse/gd_2026_{physics,history}.json`
- `scripts/parse_correction_table.py` — 更正表解析（已修复：同校多代码行 blocks 累积 + 组头同行 `专业组204 23`）；哈理工 g208-213 官方组号与库中已补明细**完全一致**（9 组补对了）
- 更正表勘误语义确认：**非重编号**，是「原刊登组号错版 → 更正后组号」（如哈理工 PDF g203/204/205 是错版，库 GEN g208-213 才是权威最终版）
- 更正表仅 12 校；**佛山(11847)/广技师(10588)不在其中** → 三组明细只能从 PDF 定向精解
- **佛山 g205/g210 定向精解**（409 页三栏，计划数与 GEN 吻合）：
  - g205 = 029动物医学(5年)160 + 030动物科学35 + 031生物工程40 + 032交通工程80 + 033新能源材料与器件130 + 034储能科学与工程80 + 035材料化学25 + 036材料科学与工程40 + 037化学工程与工艺15 + 038食品科学与工程60 + 039食品质量与安全35（合计 700 = GEN）
  - g210 = 047机械设计制造及其自动化80 + 048自动化80（合计 160 = GEN）
- **广技师 g204** = 014电气工程及其自动化(职教师资创新实验班) 30 人（291 页，单专业组）
- **佛山/广技师明细入库**：扩展 `scripts/backfill_group_majors.py`，46 条专业行写入（g205=700✓ / g210=160✓ / g204=30✓，字段含学制/校区/学费）
- **中外合作大学缺失修复**：根因是 `import_guangdong_data_v3.py` 名称匹配 `split("(")[0]` 留尾空格导致精确匹配失败；改为**代码映射优先 + strip 回退**，6 所补回（广东以色列 1、宁波诺丁汉 4、香港城市东莞 1、西交利物浦 3、深圳北理 4、北师香港 3）。**注意**：重跑官方投档表会清空广东全部 admission_ranks，需用 `import_excel_v3.py` 恢复历史 + 重跑 `backfill_group_majors.py`
- **提前批本科六类导入**：新建 `scripts/import_advance_batch.py`（723 GEN 组 + 1286 专业行）：
  - 军检类 57校382组1493行 / 非军检类 89校245组735行 / 特殊类型 112校232组608行 / 卫生专项 12校318组636行 / 教师专项 21校247组501行 / 招飞 4校4组8行 / 本科批 1061校5966组6035行
  - 组号规则：普通批 `2xx`、提前批 `1xx`、特殊类型 `70x`，主键无冲突
  - 坑：`college_major_name` 无 created_at 列；code_map 需含全部 colleges.id（补 81002/92036）
- **批次选择功能**（后端 + 前端）：
  - `generate_group_recommendations` 加 `batch="本科批"` 参数，SQL 过滤 `(year < 2026 OR batch = ?)`（2026 限定目标批次，历史年全保留）
  - `volunteer.py` BrowseRequest/RecommendRequest 加 `batch`；`volunteer_table.py` CreatePlanRequest 加 `batch`，ai_tune 读 `plan.get("batch")`；`volunteer_plans` 表加 `batch` 列；`volunteer_table_dao.py` create_plan/clone_plan 支持
  - 前端 `page.tsx`：考生信息加"招生批次"下拉（7 批次值）；browse / plan/create 请求体带 `batch`；非本科批显示专项报考限制提示
- **双轨编码修复**：`import_excel_v3.py`（2023-2025 历史）用 Excel 地方码写入，而 2026 用官方码 → 同一校历史/新数据分裂。新建 `scripts/migrate_hist_ranks_to_official.py`：77740 历史行改官方码 + 2111 重复行删除，地方码行残留 = 0，孤儿引用 = 0（备份 `bak_before_histcode_20260817_110302`）
- **2026 本科批专业明细补全**：官方投档表只有组级 GEN 位次（本科批 99.7% 组 GEN-only，无组内专业）。新建 `scripts/import_batch_majors_2026.py` 从专家版 Excel 本科批次（`本科批次`→DB `本科批`）导入 21655 专业行 + 21655 `college_major_name` 行（含 学制/学费/计划数，min_rank=0 靠组级 GEN 兜底）。**关键前提**：Excel 组号与官方投档表组号 100% 一致（dry-run 核验 21697 行仅 5 行无 GEN 组）。补入后本科批 GEN-only 从 99.7% → **0.1%（物理）/ 0.2%（历史）**，45 个 slot 全部带组内专业明细
- **三个缺组补入 + rank_source 预估标记**：组级差异穷尽发现 3 个真实缺组（官方投档表有组但 DB 缺失）：
  - 哈理工 **g215**（英语，联合培养麦考瑞"2+2"）——官方投档表已有 GEN 位次 266942，仅补专业明细
  - 成信 **g212**（环境科学，联合培养兰卡斯特"2+2"）——官方投档 0 人无位次 → **预估 118244**（取校最低位次=最差组 g214）
  - 中南 **g216**（护理学，高校专项）——官方投档 0 人无位次 → **预估 24936**（取校最低位次=最差组 g207）
  - 预估规则（用户决策）：① 同校其他正常收分组相同专业位次优先 ② 无同专业 → 取该校所有专业组最低位次 ③ 分数用 2025 分数段换算（2026 无分段数据）
  - `admission_ranks` 加 **`rank_source`** 列（`official`=官方投档位次 / `estimated`=预估位次，幂等 ALTER）；`generate_group_recommendations` + browse/create_plan 透传 `rank_source`；前端卡片/志愿槽显示"预估位次"紫色徽标
  - 脚本 `scripts/backfill_missing_groups.py`（幂等）；备份 `bak_before_missing_groups_20260817_152911`
  - 验证：rank=150000 时中南 g216 reach 0.083 / 成信 g212 steady 0.394 / 哈理工 g215 safe 0.719，rank_source 全部正确；`pytest` 191 passed；`tsc --noEmit` 无错
- **GEN-only 残留清零（第二批 6 组）**：本科批 GEN-only 从 物理 2 + 历史 4 归零。补齐组明细：
  - 哈理工 **g214**（物理·联合培养 8人）= 038 信息与计算科学（麦考瑞 2+2，46300元）；**g207**（历史·联合培养 5人）= 003 英语（麦考瑞 2+2，46900元）——来源更正表
  - 川师 **g218**（历史·联合培养 1人）= 016 英语（中外高水平 3+2 麦考瑞，38300元）——与物理 g223 同构
  - 香港珠海 **g201**（历史 6人）= 文学与社会科学院 + 商学院；**g202**（物理 10人）= 文学与社科 + 商学院 + 理工学院（104750元/年）——Excel 明细，**根因**：`college_code_map` 缺 81012 映射导致 import_batch_majors_2026.py 跳过
  - 中南财 **g211**（历史·中外合作 5人）= 040 国际经贸规则（罗马一大中外合作，75000元）——用户确认
  - `scripts/backfill_missing_groups.py` 扩展：支持多科类（GROUPS 增 exam_category）+ college_major_name 幂等（已存在则跳过，保留原有明细）；补 campus 空值（哈理工校本部/川师成龙/中南财校本部）
  - 备份 `bak_before_genonly6_20260817_162046`
  - 验证：物理/历史 GEN-only=0；全量推荐 6 组全出现（中南财 g211 reach 0.109 / 川师 g218 reach 0.320 / 哈理工 g207 safe 0.910 / 香港珠海 g201 safe 0.780 / g202 steady 0.394 / 哈理工 g214 safe 0.691）；`pytest` 191 passed；`tsc --noEmit` 无错

**比对结果（2026-08-17 补入后）**：
- `scripts/compare_db_pdf.py` 只比**本科普通批**（load_db 加 `batch='本科批'` 过滤，提前批不参与——PDF 是普通批目录，避免提前批校误报）
- 物理：PDF 1666 校 / DB 1036 校 / 真缺校 **0** / 有校无 2026 数据 661（92-94% 为专科+军警校）/ 多校 31
- 历史：PDF 1443 校 / DB 833 校 / 真缺校 **0** / 有校无 2026 数据 630 / 多校 20
- 剩余"本科缺数据"核实：A 类提前批院校（外交/警校/港中深/西湖大学等）在提前批已有数据，非缺漏；B 类纯专科（用户决定先不做）；C 类真缺（太原师范等特殊类型）已核实 Excel 批次归属
- 组级差异 966/769 校（PDF 独有组 1522/602、库独有组 2314/1185）——受解析器跨列串扰 + 跨页续段丢失限制（如三明学院 header 在页底、续段跨页丢失），组级差异仅标记不穷尽；组内专业明细以 Excel 权威补全为主，PDF 仅作校级存在性校验

**验证**：本科批推荐 33/33/33；提前批军检 15/15/15（样例 北航 g101 0.44）、非军检 15/15/15（中国传媒 g207 0.648）、卫生专项 6校、教师专项 10校；API create_plan 提前批军检 45 slots（13/18/14）batch 持久化 ✓；本科批 create 45 slots 全部带组内专业明细（中央民族 g205 环境科学与工程类等，含 学制/学费/概率）✓；`pytest` 191 passed；`tsc --noEmit` 无错。

**待办**：
- [ ] 解析器已知限制：组级专业跨列串扰 + 跨页续段丢失（623 校 PDF 组数 < 库）——比对以校级存在性为准，组级差异单独标记
- [ ] tesseract OCR 装志愿指南核对批次规则（指南 684 页全扫描）

#### 遗留知识

- `college_major_name` 现在有 7 列：major_name/full_name/category/subject_requirement/tuition/**years**/**campus**；full_name 仍含 `(5年)(xx校区)` 旧文本，新列优先
- PDF 解析器性能 ~0.5min/672 页；`college_for_x` 区域重叠时取最近标题（修复东软 g201 识别）
- **批次过滤约定**：推荐/浏览/建表 SQL 统一 `(year < 2026 OR batch = ?)`——2026 数据按所选批次过滤，历史年（2023-2025）全保留参与概率计算
- **数据写入必须用官方码**：`import_excel_v3.py` 等历史导入脚本写入前需经 `college_code_map` 转官方码（2026-08-17 已迁移修复）；2026 官方投档表/提前批用官方码直写
- **2026 专业明细统一 min_rank=0**：2026 各组只有 GEN 行带真实位次，专业明细（Excel/提前批/backfill）一律 min_rank=0，组内专业排序/概率靠组级 GEN 位次兜底
- **rank_source 预估位次约定**：`admission_ranks.rank_source` 标记组级 GEN 位次来源（`official`=官方投档 / `estimated`=预估）；预估位次规则 = 同校同专业位次优先，无则取该校所有专业组最低位次；预估组概率可进推荐但综合分通常低，per_tier_caps 下可能被截断属正常；前端"预估位次"徽标仅预估组显示

#### 方向 C：缺学费专业定向回填 ✅（2026-08-17）

**背景**：全量核验发现 108 个 `college_major_name.tuition=0` 专业行（物理 77 + 历史 31）。排查结论：绝大多数源数据（Excel col18 与官方 PDF）本身即"待定"或特殊（中外合作拟收费/厦大马来西亚分校林吉特/双学士/预科班），非导入丢失。

**可提取清单（PDF 权威值）**：
| college_id | 专业 | 科类/组 | 学费 | 校区 |
|-----------|------|---------|------|------|
| 4122010202 通化师范学院 | 001 智能制造工程技术 | 物理 g201 | 5400 | 长吉校区 |
| 4122010202 通化师范学院 | 002 无人机系统应用技术 | 物理 g201 | 5400 | 长吉校区 |
| 4154010694 西藏大学 | 008 地理科学 | 历史 g205 | 2800 | 纳金校区 |
| 4136013440 南昌应师院 | 001 法学 | 历史 g201 | 20000 | 主校区 |
| 4136013440 南昌应师院 | 002 小学教育 | 历史 g201 | 20000 | 主校区 |
| 4136013440 南昌应师院 | 003 汉语言文学 | 历史 g201 | 20000 | 主校区 |
| 4136013440 南昌应师院 | 004 财务管理 | 历史 g201 | 20000 | 主校区 |

**已确认不提取**：哈尔滨商大（供应链/人工智能/新能源）、黑河（网络与新媒体×2）、沈阳理工、黑龙江大学、东北林业 g204、南昌物理 g202、成都中医药 等 PDF 明示"待定"；西藏大学/新疆师大 5 个"免费"专业因 tuition 为数值列（REAL，评分引擎依赖 cost_index 用院校级）无法存"免费"，用户决策留空（tuition=0 前端不显示，full_name 已含说明）。

**实施**：直接 SQL UPDATE `college_major_name` 7 行（tuition + campus）；缺学费 108 → 101（物理 75 + 历史 26）。**注意**：通化师范 g201（001/002/003 同组）组级学费=5400，但 003 互联网金融库里 4800 属 g205（再选：化学），两者不同组不同价，勿混淆。

**验证**：历史推荐端到端核验（南昌 g201 四专业 20000/主校区、西藏 g205 地理科学 2800/纳金校区 均正确带出）；`pytest` 191 passed；`tsc --noEmit` 无错。无 DB schema 变更，无备份（仅 7 行 UPDATE 可逆）。

#### 方向 D：志愿填报指南 OCR 基建 + 政策灌入 RAG（2026-08-18）

**数据源**：`广东省2026年普通高等学校志愿填报指南2026.6.10.pdf`（684 页纯扫描件，RICOH 扫描，无文本层）。用户用 WPS 转出**部分 OCR 产物 DOCX**（173KB，含正文 1-4 章：考试科目/批次投档/体检/志愿填报，约 22 页；不含后续 600+ 页 2025 录取排位表）。

**OCR 环境结论**：本机仅 `libtesseract4`（无 CLI/chi_sim 语言包）、无 paddle/rapidocr；PyMuPDF 1.28.0 可用于渲染。本次走 DOCX 通道，未装新 OCR 引擎。**684 页 PDF 仍无文本层**，排位表部分需用户后续继续转换。

**新增文件**：
| 文件 | 说明 |
|------|------|
| `scripts/extract_guide_policy.py` | DOCX → 政策章节/批次规则/体检规则 JSON（`data/user/custom/ocr_guide/`） |
| `scripts/seed_guide_policy.py` | 政策正文灌入 RAG（`source="广东2026志愿指南"`, `doc_type="policy"`，幂等：先 `delete_source` 再灌，14 条 chunk） |
| `scripts/compare_batch_rules.py` | 指南批次分类 vs 系统硬编码核对报告 |

**RAG 检索改进**（`store.py` + `retriever.py`）：
- `search_by_keywords`：SQL 由 `ORDER BY id` 改为 `ORDER BY 关键词命中数 DESC, id ASC`（相关度优先）
- `retrieve_for_chat`：keyword 结果按 `doc_type` 排序（`policy` 官方内容优先于 FAQ）
- 验证：`高考总分怎么构成`/`体检受限专业`/`提前批有哪些类型` 均正确命中 policy chunk
- **已知局限**：hash embedding（384 维）无语义能力，`search_chunks` 向量检索对同义改写无效，仅 keyword 有效；FAQ 精确标题多词命中时仍可能排前（合理）

**批次规则核对结论**：指南批次分类（军检/非军检/教师/卫生/特殊类型/招飞）与前端 7 个选项**一一对应**，投档模式"院校专业组"与 `PROVINCE_RULES` 一致——**无需改代码**。45 组数/ratio 指南未提供（正文"具体时间及安排另行通知"），时间表无法从本书提取，`AdmissionCountdown.tsx` 硬编码日期保留。

**验证**：`pytest` 191 passed；`tsc --noEmit` 无错；RAG 检索冒烟通过；seed 幂等重跑 OK。

#### 方向 E：指南排位表试点解析 + 交叉验证（2026-08-18）

**背景**：用户更新完整版 DOCX（`..._20260818095218.docx`，57.8MB，document.xml 135MB / 10480 文件 / 9772 图），含第六章 2025 排位表（物理 0-80MB / 历史 80-120MB / 艺体 119-135MB，1690 表格 29 万单元格）。用户选择"尝试解析排位表"（试点+交叉验证，不写库）。

**乱码结论**：全文档仅 4 个替换字符（�），**乱码可忽略**。

**DOCX 结构**：`<w:tbl>` 是空壳，真实数据在表格后独立段落流。排位表每页 = 页眉 + 表头碎片 + 记录段（左右列交织）：
- **行式记录**（`10004北京交通大学 107` / `208 专业组208 90` / `007 与智能制造) 19`）→ 可解析
- **列式区块**（清华等：先全代码再全名称再全数字）→ 按列对齐复杂，跳过
- 数据列（`95 689`=最低排位 最低分）与左列交错，行级对齐不可靠

**试点结果**（`scripts/parse_guide_ranks.py`，物理本科普通批段 8053-65970）：
- 解析出 **256 院校 / 1147 组 / 3251 专业**（4654 条）→ `data/user/custom/ocr_guide/guide_ranks_pilot.json`
- 院校级：国标码→官方码 248/256，库 2025 广东物理有数据 244/256（**95% 吻合**）
- 组号体系：**指南排位表组号 ≠ 库组号**（北交大指南 208/209 vs 库 g202/g203），但专业代码+计划数与库完全吻合（指南 007 计划19 = 库 g203 007 计划19）
- 专业级：(college, major_code)+计划匹配 37.4%，受限原因=专业代码组内序号跨组重复

**结论**：物理/历史本科批 2025 已完整（Excel 导入组号更规范），指南排位表行级对齐成本高且组号不同源；**不投入全量解析**。排位表可作院校名单第三方校验（95% 吻合），未来做历史回测（Phase 10 6b）时可参考。报告见 `data/user/custom/ocr_guide/guide_ranks_report.md`。

| 文件 | 说明 |
|------|------|
| `scripts/parse_guide_ranks.py` | 试点解析器 + `--report` 交叉验证（新建） |
| `data/user/custom/ocr_guide/guide_ranks_pilot.json` | 4654 条试点记录（新建） |
| `data/user/custom/ocr_guide/guide_ranks_report.md` | 验证报告（新建） |

### Phase 21 🚀 中央部署 SaaS 化（2026-08-18 规划，待与同学商议）

> 状态：方案已定，**未实施**。待团队确认后执行。

#### 目标

从"本机自用"升级为**中央部署的 SaaS 网站**：
- 任何人可自助注册账号登录使用（内置多用户认证，首注册者为 admin）
- API 由部署方统一托管，用户仅用浏览器访问，无需本地安装
- 每个用户的学习记录/志愿表/权重/收藏等数据相互隔离

#### 现状调研结论

| 维度 | 现状 | 结论 |
|------|------|------|
| 认证 | 内置多用户 JWT（auth.json，默认关闭） | ✓ 支持，开启即可 |
| 部署 | Docker（compose.yaml / docker-compose.yml）+ 裸机两种 | 裸机可行（磁盘仅剩 2.7G） |
| 公网 | 本机 IP 113.105.235.136（疑似运营商 NAT/封端口） | 用 Cloudflare Tunnel 穿透 + HTTPS |
| 数据隔离（chat/ws） | `get_current_user().id` 正确隔离 | ✓ 已支持 |
| **数据隔离（志愿模块）** | **`user_id` 是路径参数默认 "default"，前端硬编码 `USER_ID="default"`** | ✗ **所有用户共享同一份数据，必须改造** |

#### 实施计划

**阶段 1 — 多用户数据隔离改造（核心代码改动）**
- 后端：`volunteer.py` + `volunteer_table.py` 的 `user_id` 路径参数改为从 `get_current_user().id` 提取，保留向后兼容、杜绝越权；同步检查 `volunteer_chat` / study summary/gap / weights auto-tune
- 前端：`volunteer/page.tsx` + `study-lab/page.tsx` 的 `USER_ID="default"` 改为 `useAuthStatus()` 动态取
- 验证：注册 A/B 两用户，互相看不到对方数据

**阶段 2 — 部署上线**
1. 依赖修复：`sqlite-vec` 加入 `requirements/server.txt` + `pyproject.toml`（`rag/store.py` 硬依赖）
2. 启用认证：`auth.json` `enabled=true` + 清空单用户字段 + `cookie_secure=true`
3. 密钥保护：`model_catalog.json` 明文 DeepSeek/Aliyun key 改环境变量注入 + `chmod 600`
4. 数据备份：`deeptutor_custom.db`
5. 生产构建：web `npm run build` + systemd 守护后端(8001)/前端(3782)
6. Cloudflare Tunnel：cloudflared 建隧道，ingress → 3782，公网 HTTPS
7. 端到端验收

**现实约束（需团队知晓）**
- 共享 API key 成本：所有用户共用一个 DeepSeek key（部署方付费），需监控用量，后续可做 BYOK
- 磁盘：本机仅剩 2.7G，裸机方案不构建镜像够用

#### 待团队确认项

- [ ] 部署形态：本机裸机 + Cloudflare Tunnel vs 云服务器（~¥50-100/月）
- [ ] 认证：开放注册 or 邀请制/审核制
- [ ] API 计费：部署方统一付费 or 用户自带 key（BYOK）
- [ ] 志愿模块数据隔离改造是否本轮做（不做则多用户无意义）

### Phase 22 🚀 系统评测体系（2026-08-18 规划，待实施）

> 状态：方案已定，**未实施**。三个方向 + 个性化论证。用户确认三方向都要，方向 3 已从"公开基准集跑分"改为"架构消融实验"（裸模型跑 C-Eval 测的是 DeepSeek 的成绩，无差异化价值；数据/RAG 别人也能堆；**真正差异化是架构设计**——确定性引擎算数值不幻觉、LLM 只做表达）。

#### 目标

拿我们的系统（伴学tutor）与外部基线对比，产出可量化报告/宣传背书。产出：报告/论文/上线宣传/内部了解。

#### 三个方向

| 方向 | 内容 | 数据/基线 | 成本 | 优先 |
|------|------|----------|------|------|
| 1 推荐引擎回测 | 用历史录取数据预演推荐，真实投档验证命中率 | 库内 2023-2026 `admission_ranks` + 桌面 2025/2026 官方投档表 | 零 API 成本 | 高 |
| 2 AI 对话评测 | 志愿咨询问题集 + LLM-as-Judge 打分 | 30 题左右，pro 评 flash，可人工复核 | 低（¥几元） | 中 |
| 3a 架构消融实验 | A裸LLM / B+RAG / C+工具 / D完整系统，逐层量化增益 + 事实性自动核验 | 自建志愿专属题集，对照 DB 自动判定 | 低 | 中 |
| 3b 个性化增益 | 带画像 vs 去画像对照 + 冷启动曲线 + 论文口径映射 | 合成画像 + seed 学习记录（用户拍板：先造，真实数据后续再换） | 低 | 中 |

#### 方向 1 关键设计决策（回测）

- **batch 归一化**：历史年份 batch="本科批次"，2026="本科批"，回测脚本必须归一
- 跨年验证（2023+2024 → 推荐 → 2025 真实验证）比同年级卷更客观
- 指标：冲/稳/保命中率、录取概率误差、滑档率
- 纯脚本 `scripts/backtest_scorer.py`，不碰现有代码
- 排位表（`parse_guide_ranks.py` 试点）可为院校名单提供第三方校验（95% 吻合）

#### 方向 3a 消融实验设计

对应 `volunteer_chat_service.py` 编排层，逐层叠加看增益：

| 变体 | 含义 | 给 LLM 提供什么 |
|------|------|----------------|
| A 裸 LLM | 直接提问，零辅助 | 只有用户问题本身 |
| B +RAG | A + 知识库 | `doc_chunks_v2` 检索到的政策/章程/FAQ 上下文 |
| C +工具 | A + 工具调用 | `college_search`/`admission_query` 等真实 DB 数据（不注入 RAG 文本） |
| D 完整系统 | 现状 CRAG 编排 | 工具数据 + RAG 上下文 + 学习者画像（`learner_profile`），即生产链路 |

- **量化口径**：B−A = RAG 增益；C−A = 真实数据/工具增益；C−B = 哪种辅助更有效；**D−C = 个性化 + 综合编排增量**（连接 3b）
- **指标**：事实性题对照 DB 答案自动核验（命中/幻觉率），看幻觉率逐层下降
- 题集：志愿专属 30-50 题（`data/user/custom/benchmark/questions.json`），兼顾事实性/数值/策略题

#### 方向 3b 个性化增益论证（论文支撑已查证）

**主线**：领域研究证明"个性化录取概率 + 画像融合推荐"显著改善录取结果 → 我们的系统正是这类 "ML-assisted personalized advising"，且比论文实现多三层个性化（学习记录驱动的学业匹配 / 自适应权重 / L3 长期画像）。

| 文献 | 核心数据 | 对应我们的能力 |
|------|---------|---------------|
| Ye, "Choice"（中国集中录取 ML 辅助志愿咨询 field experiment） | ML 个性化咨询：录取概率 **+24.4pp**（TOT）、录取院校质量 **+0.598 SD**（TOT）；ML ≈ 专家咨询但可规模化 | `volunteer_scorer` 个性化录取概率 + 冲稳保推荐 |
| Chile NBER w34164（全国规模化信息干预） | 未录取者 **+44%** 获录取、匹配更高排名项目 **+20%**、两年后续读 **+34%** | 个性化概率 + AI 对话抽屉专业推荐 |
| Ye, EFP（中国穷省 RCT, N=32,834） | 精准预测干预提升学术匹配 0.1-0.2 SD（compilers），指南+工作坊 TOT ≈ 0.18 SD | 等位次换算 + 冲稳保策略诊断 |
| MDPI Applied Sciences 2024（211） | 融合学业+社经画像的推荐优于纯学业数据；XAI 解释提升信任 | `_calc_academic_fit` + `adaptive_weights` + evidence 透明化 |
| bjet.13116 meta-analysis | 自适应式个性化学习效应量 **0.35**（15 RCT / 53,029 学习者） | study_records → 自适应权重调优 |
| LettinGo arXiv:2506.18309 | LLM 生成用户画像用于推荐，处理冷启动 | `memory_bridge.py` L3 learner_profile + 冷启动 |

**量化实验**：
- **P 对比**：`D带画像` vs `D'去画像(默认权重)` → 推荐集合 Jaccard 差异率、slots 个性化比例、academic_fit 覆盖率、概率 rank 相关性
- **冷启动曲线**：学习记录 0 → 10 → 50+ 条时推荐方案演化（对应 LettinGo / 元分析自适应增益）
- **画像来源**：基准脚本内置确定性合成画像（如"理科强/数学物理弱/就业导向"多组 + 对应 seed 学习记录），可复现；留 `--use-real-profile` 开关，真实 `default` 用户有数据后一键切换

#### 现实约束

- 磁盘仅剩 2.7G：方向 1 零 API 成本优先；3a/3b 纯 API 调用无磁盘压力
- 方向 2/3 消耗 DeepSeek 额度，需监控
- 底层是 DeepSeek v4 API（非自训模型），评测本质是"系统化 Prompt+RAG+工具叠加后 vs 原始模型"

#### 实施顺序（已确认）

① 更新 AGENTS.md（本记录）→ ② 方向 1 回测 `scripts/backtest_scorer.py` → ③ 方向 3a+3b 消融+个性化（`scripts/benchmark_ablation.py` + 题集 + 报告）→ ④ 方向 2 对话评测

### Phase 22.5 🚀 志愿表历史管理重构（2026-08-19 已实施）

> 状态：已完成 ✅（200 tests passed + tsc 通过）。在历史志愿表功能上重构为 **弹窗 + 回收站 + 去重** 模式。

#### 需求（用户拍板）

- **命名**：`志愿表{月日时分}` 紧凑式（如 `志愿表06281626`），年月日不在名字里，年份用**独立小标签**展示
- **志愿数量**：`{slots_count}/{groups}`（`groups` 取 `province_rules.groups`，广东 45）
- **排序**：越新越靠上（`created_at DESC`），无序号、删除不重编号
- **去重**：内容完全相同（保留顺序，顺序不同即不同）不保存并提示"与志愿表X完全相同"
- **回收站**：删除进回收站保留 7 天，含恢复 / 永久删除，过期惰性清理

#### 改动

| 文件 | 说明 |
|------|------|
| `deeptutor/services/custom/db.py` | `volunteer_plans` 加 `deleted_at REAL DEFAULT NULL`（幂等 ALTER + CREATE 同步） |
| `deeptutor/services/custom/volunteer_table_dao.py` | 新增 `soft_delete_plan`/`restore_plan`/`purge_plan`/`list_trash`/`find_duplicate`（`json.dumps` 保序比对）；`list_trash` 惰性清理超 7 天；`list_plans` 仅活跃 + `created_at DESC` |
| `deeptutor/api/routers/volunteer_table.py` | `DELETE /plan/{id}` 改软删除；新增 `POST /plan/{id}/restore`、`POST /plan/{id}/purge`、`GET /plan/trash`；`clone` + `create` 去重 409；`_plan_label` 生成紧凑命名；**修复路由遮蔽 bug**（`/plan/list`、`/plan/trash` 静态路由移到 `{plan_id}` 之前）；`SlotItem` 补 `province_code`/`bargain_score`/`rank_source`；`create_plan` 按 `body.province` 查 `college_code_map` 注入 `province_code` |
| `web/app/(workspace)/volunteer/page.tsx` | 历史方案改 Modal 弹窗（`@/components/common/Modal`），两 Tab 志愿表/回收站；命名+年份标签+`N/45`+剩余天数；叉叉软删/恢复/永久删除；去重 409 提示；`savePlan` 前端防呆（与最近保存一致不另存）；SlotItem 卡片学校全名 + `代码{province_code}` 徽标（去 truncate）；`addToPlan` 透传 `province_code` |
| `tests/services/custom/test_volunteer_table_dao.py` | 新建：create/list、保序去重、软删/恢复/永久删、7 天惰性清理、回收站不参与去重、`_plan_label` |

#### 关键设计

- **去重语义**：`clone` 排除源方案自身（"保存"= 对当前方案做新快照）；`create` 全量比对；前端防呆覆盖"与最近保存一致"场景 → 三者配合无重复快照
- **回收站天数**：`remaining_days = (deleted_at + 7d - now) // 86400`
- **路由顺序坑**：`/volunteer/plan/list`、`/trash` 必须注册在 `/volunteer/plan/{plan_id}` 之前，否则被 catch-all 遮蔽（原代码即有此 bug，前端历史列表一直 404 靠静默容错）

### Phase 22.6 🚀 2026 一分一段导入 + 分数入库 + 去重含 rank（2026-08-19 已实施）

> 状态：已完成 ✅（202 passed + tsc 通过）。用户提供 2026 官方分数段 Excel → 导入 `score_rank_segments`；志愿表 `score` 列入库；去重纳入 rank；历史列表 + 当前表头部显示分数/位次。

#### 改动

| 文件 | 说明 |
|------|------|
| `scripts/import_2026_segments.py` | **新建**：2026 分数段 Excel（物理 1200 + 历史 1140 条，含本科/专科两档）导入 `score_rank_segments`，仅 `year=2026`（INSERT OR REPLACE 不动 2025）；表头 5 行、数据从 r6 起；首行 `"669（含以上）"` 剥离括号保留（v2 用 `int()` 会丢首行） |
| `deeptutor/services/custom/admission_dao.py` | 新增 `rank_to_score_latest`/`score_to_rank_latest`/`get_total_candidates_latest` —— 优先 2026 分段，无数据回退 2025 |
| `deeptutor/services/custom/volunteer_scorer.py` | `_calc_admission_prob`/`generate_group_recommendations` 硬编码 `2025` → `_latest` 兜底函数 |
| `deeptutor/api/routers/volunteer.py` | browse/recommend 的 score→rank 换算改用 `score_to_rank_latest` |
| `deeptutor/services/custom/db.py` | `volunteer_plans` 加 `score REAL DEFAULT NULL`（幂等 ALTER + CREATE 同步） |
| `deeptutor/services/custom/volunteer_table_dao.py` | `create_plan`/`clone_plan` 透传 `score`；`find_duplicate(user_id, slots, rank, exam_category)` 把 **rank + 选科纳入身份**（同 slots 不同 rank = 不同方案可并存） |
| `deeptutor/api/routers/volunteer_table.py` | create 传 `body.score` + `find_duplicate(rank=..., exam_category=...)`；clone 同样带 rank/exam_category |
| `web/app/(workspace)/volunteer/page.tsx` | `formatScoreRank()` helper；历史弹窗行显示 `585分/位次14362` 蓝色徽标；当前志愿表头部加 `志愿表06281626 · 622分/位次14362 · (N 个)`；`addToPlan` create 分支补传 `score`；`SavedPlanSummary`/`PlanData` 加 `score`；savePlan 前端防呆加入 rank 比较 |
| `tests/services/custom/test_volunteer_table_dao.py` | 新增 `test_find_duplicate_rank_sensitive`（同 slots 不同 rank 判不同）+ `test_create_plan_with_score`（入库 + clone 继承） |

#### 数据回填

- 42 条旧活跃方案无 score：用 2026 分段 `rank_to_score` 回填（42/42 成功，无跳过）
- 回填后 `score IS NULL` 活跃方案 = 0

#### 验证

- `score_to_rank(广东,2026,物理,585)` = 46000；`rank_to_score(广东,2026,物理,14362)` = 622；考生总数 2026 物理 433366
- API 冒烟：create score=622 入库 → clone 继承 score → 同 slots 同 rank 409 拒绝、clone 重复 409 正确
- `pytest tests/services/custom tests/tools/custom tests/capabilities` = **202 passed**；`tsc --noEmit` 无错

#### 关键设计

- **去重语义升级**：身份 = slots（保序）+ rank + exam_category。rank 不同视为不同方案（同份志愿不同位次场景可并存）
- **年份切换策略**：2026 分段导入后评分引擎/换算默认 2026，无数据回退 2025（防御，正常不触发）
- **2026 分段特点**：物理 max 699 / 历史 max 669，首行"（含以上）"已保留（对比 2025 版 max 697/672 是丢首行结果）

### Phase 23 🚀 艺体类填报框架 + 2026 投档数据导入（2026-08-19 已实施）

> 状态：框架 + 数据导入均已完成 ✅（220 passed + tsc 通过）。用户提供 2026 广东艺体类本科投档 7 个附件（附件3-9），已全部导入，推荐/浏览/建表可直接使用真实数据。

#### 官方规则（2026 广东，用户提供）

- **志愿设置**：1 个平行志愿组，共 **20 个院校专业组志愿**；每组内 **6 个专业志愿** + 1 个服从调剂
- **划线**：不分物理/历史，按专业类别（音乐/美术/体育等）统一划线、一起投档录取
- **投档**：分数优先、遵循志愿，按合成总分（含加分）排位；同分 7 项排序，艺体类比专业省统考
- **综合分**（术科满分 300，综合分满分 750）：
  - 音乐/舞蹈/表（导）演/美术与设计/书法/戏曲：总分 = 文化×50% + 术科×2.5×50%
  - 播音与主持：总分 = 文化×60% + 术科×2.5×40%
  - 体育：总分 = 文化×40% + 术科×2.5×60%
- **双上线**：文化与专业省统考须同时达省控线方可投档
- **不得兼报**：本科批艺体类不得兼报普通类

#### 数据模型约定（已落地）

- `exam_category = "艺体类"`（统一，不分物理/历史）+ 独立 `art_category` 字段（8 类）
- `batch = "艺体类本科批"`（区别于普通类"本科批"）
- 投档数据入 `admission_ranks`：`exam_category='艺体类'` + `batch='艺体类本科批'` + `group_code` 用投档表组号（纯数字，如 `201`）+ `art_category` 列记录类别 + `rank_source='official'`；组内专业行 major_id 用真实专业码（非 GEN）
- `admission_ranks` 加 `art_category` 列（幂等 ALTER），**PK 纳入 art_category**（重建迁移：`college_id, major_id, province, year, exam_category, group_code, art_category`）——艺体类同校同组号跨类别共存，旧 PK 会被 INSERT OR REPLACE 吞并

#### 改动文件

| 文件 | 说明 |
|------|------|
| `deeptutor/services/custom/art_sports.py` | **新建**：`ART_CATEGORIES`（8 类）、`calc_composite_score`（三类公式 + 术科 300/文化 750 校验）、`ART_SPORTS_RULES`（本科批 20 组/6 专业/ratio [3,4,3]）、`is_art_sports`、`art_batch_for`、`ART_CATEGORY_KEYWORDS` |
| `deeptutor/services/custom/volunteer_scorer.py` | `generate_group_recommendations` 加 `art_category` 参数；艺体类分支：SQL 按 `exam_category='艺体类'` + `art_category` **列**过滤（新增），专业名关键词过滤仅兜底（GEN-only 组保留）；无数据返回 `data_status:"no_data"` + message；有数据 cap=20（6 冲/8 稳/6 保） |
| `deeptutor/services/custom/db.py` | `admission_ranks` 加 `art_category` 列（幂等 ALTER）+ PK 重建迁移纳入 art_category |
| `deeptutor/api/routers/volunteer.py` | `BrowseRequest`/`RecommendRequest` 加 `art_category`/`culture_score`/`major_score`；`RecommendResponse` 加 `data_status`；新增 `GET /volunteer/art-sports/categories`、`POST /volunteer/art-sports/composite-score`；browse 艺体类时注入 composite_score 到 profile |
| `deeptutor/api/routers/volunteer_table.py` | `CreatePlanRequest` 加 art 字段；艺体类建表：batch 强制 `艺体类本科批`、cap=20、每组 majors 截断 6、综合分校验；`data_status=no_data` 时 400 |
| `web/app/(workspace)/volunteer/page.tsx` | 选考科目加"艺体类"radio；艺体类时显示专业类别下拉/文化分/专业统考分/实时综合分；批次加"本科批（艺体类）"选项 + 20 组规则提示；再选科目隐藏；browse/create 透传 art 字段；no_data 提示"艺体类投档数据待补充" |
| `scripts/import_art_sports_2026.py` | **新建**：导入 7 个附件（体育 170/音乐 402/舞蹈 53/美术与设计 488/书法 30/播音与主持 98/表(导)演 106，共 1347 行）到 `admission_ranks`；地方码→官方码映射（college_code_map → id 尾码 → 新院校）；`VARIANT_MAP` 覆盖校区变体（19027 北师大珠海→`4111010027-ZH`）；缺失 3 所 2026 新设院校自动补 colleges 行 + map；幂等（重复跳过） |
| `tests/services/custom/test_art_sports.py` | **新建**：综合分三类公式/边界/缺失、类别清单、无数据 no_data、有数据 20 组 cap 分配、art_category 列跨类别隔离（同校同组号音乐/美术共存互不干扰） |

#### 数据导入结果

- **7 附件共 1347 组**（组级 GEN 投档：计划数/投档人数/最低分/最低排位）：美术与设计 488/369 校、音乐 401/158、体育 169/139、表(导)演 106/73、播音与主持 98/90、舞蹈 53/45、书法 30/30
- **3 所新设院校补库**：郑州美术学院 `4141014831`、河南体育学院 `4141014879`、成都美术学院 `4151014985`（官方码从 `全国高等院校名单2026.xls` 查证；防灾科技学院 `4113011775` 仅在 2025 附件2 普通类出现、未在艺体附件，保留映射备用未建行）
- **踩坑修复**：① 附件投档最低分/排位有 `-` 空值 → 解析 `_num()` 兜底 0；② `19027` 北师大(珠海校区) 被 college_code_map 误映射到本部 `4111010027` → 美术 g212 吞并音乐 g212、书法 g211 吞并体育 g211 共丢 2 行 → 修 map 到 `4111010027-ZH` + 补 3 行 + 脚本加 `VARIANT_MAP`；③ PK 缺 art_category → 重建迁移
- **min_rank=0 组**（投档人数 0/未招满）保留入库但不参与评分（SQL `min_rank > 0` 过滤），共 29 组

#### 验证

- 综合分：美术(400,250)=512.5 / 播音=490 / 体育=535；超限 301 → 400 错误
- browse 艺体类：`data_status:ok`，美术与设计 rank=5000 → 冲50/稳100/保80 三档正常；rank=30000 → 冲50/稳47/保0（位次驱动分档正确）
- 建表：艺体类本科批 create 20 slots（cap=20，6 冲/8 稳/6 保），prob/tier 正常
- `pytest tests/services/custom tests/tools/custom tests/capabilities` = **220 passed**（+18 新）；`tsc --noEmit` 无错

#### 关键设计

- **艺体类与普通类隔离**：科类 `艺体类` + 批次 `艺体类本科批` 双重标识，与物理/历史普通类互不混入（官方不得兼报）
- **art_category 列优先过滤**：投档数据按列精确过滤类别（推荐/浏览/建表），专业名关键词（`ART_CATEGORY_KEYWORDS`）仅作无列时的兜底；GEN-only 组（无组内专业明细）不过滤
- **无数据不报错**：无投档数据时返回 `data_status:"no_data"` + 明确提示，前端友好展示
- **位次晚点给出**（用户口风）：艺体类综合分只进 profile，不驱动位次推荐；本次投档表自带最低排位，位次驱动已可用（前端当前用 `user_rank` 字段驱动分档）

### Phase 23.1 🚀 体育艺术版目录组内专业明细 + 艺体类一分一段方向换算（2026-08-19 已实施）

> 状态：均已完成 ✅（226 passed + tsc 通过）。用户提供 2026 招生专业目录（体育艺术版）DOCX + 14 个艺体类一分一段表，补全组内专业明细并支持方向级位次换算。

#### 方向 A：组内专业明细导入（`scripts/parse_art_catalog.py`）

- **数据源**：`（已压缩）2026年广东省招生专业目录 体育艺术版.docx`（物理+历史普通类目录 672+376 页解析在前，本脚本解析艺体 7 类段落）
- **SECTIONS 段落范围**：体育 2109–3055、音乐 4359–6611、舞蹈 7198–7912、美术 8475–11758、书法 12658–12828、播音 12921–13455、表导 13623–14166
  - **坑**：p11732 是误置的"专科"页眉，p11759 才是真专科标题；p11735–11758 含 4 所变体院校（19027 北师大珠海/80002 华南师大汕尾/80003 广工揭阳/80004 广技师河源）本科·统考内容 → 美术段扩到 11758
- **`工` 占位符**：PDF 转换丢失数字的渲染残渣（85 行，如 `专业组252 工`、`145 音乐表演(古筝) 工`）；MAJOR_CELL_RE 加 `|\s+工(?:\s|$)` 终止符防吞字
- **major_id 命名空间**：目录专业码是"组内 local 码"（如 005），与普通类 `college_major_name`（PK 仅 college_id+major_id）冲突且同校跨组重码 → 写入用 `{group_code}-{local_code}`（如 `207-008`、`212-023`），验证 0 冲突、2084 唯一组合
- **CAT_DB 映射**：美术→美术与设计、播音→播音与主持、表导→表（导）演（全角括号，与 DB art_category 一致）
- **写入**：仅写 DB 已有 GEN 行的组（has_gen 检查）；结果：命中组 1284、admission_ranks +1964、college_major_name +1964（含学制/学费/校区）
- **覆盖率**：DB 1349 组，65 组未覆盖（4.8%，多为投档表组号与目录不一致或列换行分裂，如同济 g208 目录组头被拆行）——保留 GEN-only 兜底
- **验证**：普通类未污染（山东建筑大学 005 仍=英语）；北师大珠海 212-023/024 正确；中山大学 音乐 250–260 全部 11 组正确；browse 端到端 majors 带 years/tuition/campus

#### 方向 B：一分一段方向换算（14 文件导入 + API + 前端）

- **方向码**：`score_rank_segments.exam_category` 存方向细分码：体育、美术与设计、音乐教育类、音乐教育(声乐主项)、音乐教育(器乐主项)、音乐表演(声乐)、音乐表演(器乐)、舞蹈、表(导)演(戏剧影视表演/服装表演/戏剧影视导演)、播音与主持(普通话/粤语)、书法（**戏曲无分段数据**，score_to_rank 返回 0）
- **映射**：`ART_DIRECTIONS` = 音乐 5 表、表（导）演 3 表、播音与主持 2 表，其余类别单元素 `[类别码]`；`default_art_direction` 取第一项
- **导入**：`scripts/import_art_segments_2026.py` 14 文件全部导入（year=2026，本科/专科 batch_category）：体育 494、美术与设计 644、音乐教育类 572、音乐教育(声乐主项) 518、音乐教育(器乐主项) 566、音乐表演(声乐) 564、音乐表演(器乐) 592、舞蹈 530、表导 3 方向 294/292/332、播音 2 方向 456/350、书法 272 条
- **API**：BrowseRequest/CompositeScoreRequest/RecommendRequest 加 `art_direction`；browse 综合分→位次换算（方向段优先，无数据回退类别码）；composite-score 响应含 `rank`+`direction`；categories 接口返回每类 `directions`；volunteer_table 建表无位次时自动换算
- **前端**：艺体类方向下拉（按类别过滤，默认第一项，切换类别时重置）；综合分旁显示 `· 位次 ≈ N`
- **验证**：音乐(400,250)=512.5 综合分 → 音乐表演(声乐) 1044 / 音乐表演(器乐) 1395 / 音乐教育(声乐主项) 366 位次各异；browse 端到端 213 组、冲50/稳83/保80
- **测试**：`TestArtDirections`（映射/默认方向/未知回退）7 例；pytest 226 passed；tsc --noEmit 无错


## 使用方式

```bash
# 在 chat 中通过意图自动激活，或手动指定：
deeptutor run chat "推荐广东省的985理工院校" --config volunteer_mode=true
deeptutor run chat "分析我的数学薄弱点" --config career_mode=true
```

## License 声明

本项目基于 [DeepTutor](https://github.com/HKUDS/DeepTutor) (Apache 2.0, Copyright HKUDS) 二次开发。
所有修改和新增文件均以 Apache 2.0 许可发布，保留原始版权声明。

详见 [LICENSE](LICENSE)。
