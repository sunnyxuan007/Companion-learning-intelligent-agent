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
