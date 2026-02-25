# Changelog

所有重要更改都将记录在此文件中。

## [Next-2.1.0] - 2026-02-26

### 新功能

#### ACE 模式集成（借鉴 [ACE](https://github.com/ace-agent/ace) 项目设计思路）

##### PersonaCurator — 人设 Prompt 自动整理
- 新增 `PersonaCurator` 服务，定期对人设 prompt 进行结构化整理
- 将人设 prompt 解析为多个 section（基础描述、增量更新、群组标记、学习增强特征），由 LLM 提出 KEEP/MERGE/UPDATE/DELETE 操作
- 通过 Guardrails-AI Pydantic 模型（`CurationOperationItem`/`CurationOperationList`）验证 LLM 输出，替代手动 JSON 解析
- Token 预算机制：超过配置阈值（默认 4000 token）时自动触发整理，支持 CJK/ASCII 混合文本的 token 估算
- 整理失败时自动回退到截断策略，保留最新内容
- 集成到 `PersonaUpdater`，每次增量更新后自动检查是否需要整理

##### Fewshot 样本有效性追踪
- `Exemplar` ORM 新增 `helpful_count` 和 `harmful_count` 双计数器列，使用 Laplace 平滑（`(h+1)/(h+m+2)`）避免冷启动偏差
- 新增 `effectiveness_ratio` 和 `effective_weight` 属性，将基础权重与反馈信号融合
- `ExemplarLibrary` 新增 `record_helpful()`、`record_harmful()`、`record_feedback_batch()` 反馈接口
- 新增 `get_few_shot_examples_with_ids()` 方法，返回 `(id, content)` 元组用于反馈追踪
- 向量相似度搜索的权重计算融合 effectiveness ratio，高质量样本排名更靠前
- `V2LearningIntegration` 在上下文检索时自动记录使用的样本 ID，供后续反馈循环消费
- `LLMHookHandler` 将使用的样本 ID 写入 CacheManager，打通反馈链路

##### ExemplarDeduplicator — Fewshot 样本语义去重
- 新增 `ExemplarDeduplicator` 服务，基于 Union-Find 聚类算法对语义相似的样本进行合并
- 余弦相似度矩阵计算支持 numpy 加速（无 numpy 时自动回退纯 Python）
- 大聚类（≥3 条）通过 LLM 生成合并文本，小聚类选取最高权重样本为代表
- 自动为缺失 embedding 的样本批量补充向量
- 注册为 V2 Tier-2 批量操作（每 100 条消息或 30 分钟触发一次）

##### Guardrails-AI 扩展
- `GuardrailsManager` 新增 `CurationOperationItem`、`CurationOperationList` Pydantic 模型
- 新增 `get_curation_guard()` 和 `parse_curation_operations()` 方法
- 支持将 LLM 返回的裸 JSON 数组自动包装为 Guard 可解析的对象信封

#### 数据库 Schema 自动迁移
- `ExemplarLibrary` 新增 `_migrate_schema()` 方法，使用 SQLAlchemy Inspector 检测并添加缺失列
- 方言感知：SQLite 和 MySQL 分别处理，MySQL 自动升级 `embedding_json` 为 `MEDIUMTEXT`
- 每进程仅执行一次迁移检查，避免重复开销

### 新增配置项

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `enable_persona_curation` | `true` | 启用人设 prompt 自动整理 |
| `persona_prompt_token_budget` | `4000` | 人设 prompt token 上限，超过触发整理 |
| `persona_curation_min_sections` | `3` | 最少增量段数才触发整理 |
| `enable_exemplar_effectiveness` | `true` | 启用 fewshot 样本有效性追踪 |
| `enable_exemplar_dedup` | `true` | 启用 fewshot 样本语义去重 |
| `exemplar_dedup_threshold` | `0.85` | 去重余弦相似度阈值 |

### 致谢

- 感谢 [ACE (Agentic Context Engineering)](https://github.com/ace-agent/ace) 项目及论文 [arXiv:2510.04618](https://arxiv.org/abs/2510.04618) 提供的 Curator、helpful/harmful 双计数器和 BulletpointAnalyzer 设计模式参考

## [Next-2.0.5] - 2026-02-24

### Bug 修复

#### 插件卸载/重载 CPU 100%（间歇性）
- 修复 `on_message` 中 `asyncio.create_task()` 产生的后台任务（`process_learning`、`process_affection`、`mine_jargon`、`process_realtime_background`）未被跟踪的问题，卸载时无法取消导致僵尸任务持续消耗 CPU
- `main.py` 新增 `_track_task()` 方法，所有 fire-and-forget 任务注册到 `background_tasks` 集合
- `MessagePipeline` 新增 `_subtasks` 跟踪集合和 `_spawn()` 方法，替代裸 `asyncio.create_task()`
- 新增 `cancel_subtasks()` 方法，关停时批量取消流水线内部子任务
- 新增 `_shutting_down` 标志位，关停序列第一步即设置，阻止 `on_message` 继续产生新任务
- 修复 `asyncio.shield(task)` 反模式：`wait_for` 超时后只取消 shield 而非实际任务，导致超时后任务变为不可回收的僵尸。已从 `plugin_lifecycle.py` 和 `group_orchestrator.py` 中移除 `asyncio.shield`
- 调整关停顺序：V2LearningIntegration 在服务工厂之前停止，确保 buffer flush 可使用完整服务

#### 插件重启后每条消息都触发学习任务
- 修复 `GroupLearningOrchestrator` 中 `_last_learning_start` 时间戳为纯内存字典，插件重启后清空导致每个群的首条消息无条件触发学习的问题
- 新增 `_load_last_learning_ts()` 懒加载方法，从 `learning_batches` 表恢复上次学习时间戳，每个群仅查询一次
- 修复学习触发条件使用 `total_messages`（累计总数）而非 `unprocessed_messages`（未处理数），导致活跃群组阈值检查形同虚设的问题

#### 插件卸载时阻塞
- 修复 `V2LearningIntegration.stop()` 中 buffer flush 无超时保护，LLM API 无响应时无限阻塞关停流程的问题。每个群的 flush 现在受 `task_cancel_timeout` 限制，超时后丢弃缓冲区继续关停
- 修复 `DatabaseEngine.close()` 中 `engine.dispose()` 无超时保护，MySQL 连接池在有未完成查询时可能无限等待的问题。每个引擎 dispose 现在带 5 秒超时

#### Mem0 记忆引擎 API 调用失败
- 修复 Mem0 通过提取 API 凭证重建 LLM / Embedding 客户端的方式，当凭证提取失败或模型名不可用时报 `api_key client option must be set` 或 `Model does not exist` 错误
- LLM 和 Embedding 均改为直接桥接框架 Provider：自定义 `LLMBase` / `EmbeddingBase` 子类通过 `asyncio.run_coroutine_threadsafe()` 调用框架的 `text_chat()` / `get_embedding()` 方法，无需提取任何 API 凭证
- 移除 `_extract_llm_credentials()` 和 `_extract_embedding_credentials()` 方法

#### MySQL 连接 Packet sequence number wrong
- 修复 `DatabaseEngine` 的 MySQL 引擎使用 `NullPool`（无连接池），高并发下连接状态混乱导致 `Packet sequence number wrong` 错误
- 改为 SQLAlchemy 默认 `QueuePool`（pool_size=5, max_overflow=10），启用 `pool_pre_ping=True` 自动检测失效连接，`pool_recycle=3600` 防止 MySQL 超时断开

#### 黑话并发插入 IntegrityError
- 修复 `jargon_miner` 中 TOCTOU 竞态：`get_jargon()` 与 `insert_jargon()` 之间无原子保护，并发任务同时插入相同 `chat_id + content` 触发唯一约束冲突
- `JargonFacade.insert_jargon()` 新增 `IntegrityError` 捕获，冲突时回退查询已有记录并返回其 ID

### 性能优化

#### LightRAG 首次查询冷启动优化
- 新增 `LightRAGKnowledgeManager.warmup_instances()` 方法，在插件启动后异步预创建活跃群组的 LightRAG 实例（storage 初始化 + pipeline 初始化），消除首次用户查询时的冷启动延迟，首次查询延迟降低约 80%
- `V2LearningIntegration` 新增 `warmup()` 方法，由 `PluginLifecycle.on_load()` 在后台调用
- 自动学习启动的群组间等待缩短约 80%，减少启动阶段日志中的间隔

## [Next-2.0.3] - 2026-02-24

### 性能优化

#### V2 上下文检索延迟优化（LLM Hook 响应加速）
- 新增查询结果级 TTL 缓存（基于 CacheManager），`get_enhanced_context` 缓存命中时延迟降低约 40%
- LightRAG 默认查询模式从 `hybrid` 调整为 `local`，省去全局社区聚合步骤，单次查询延迟降低约 35-40%
- ExemplarLibrary 查询 embedding 结果缓存至 CacheManager，避免相同 query 重复调用 embedding API
- Rerank 改为条件执行：候选文档数低于 `rerank_min_candidates`（默认 3）时跳过，减少不必要的 API 调用

#### 消息摄入架构重构（process_message 加速）
- 将 LightRAG 知识图谱摄入和 Mem0 记忆摄入从 Tier 1（每条消息执行）降级为 Tier 2（批量执行）
- Tier 1 延迟降低约 47%，仅执行轻量缓冲操作，重量级 LLM 操作在 Tier 2 批量触发
- 批量策略：每 5 条消息或 60 秒触发一次 flush，知识和记忆引擎并发处理
- 短消息过滤：长度低于 15 字符的消息跳过 LLM 摄入，减少无效 API 调用
- 关停时自动 flush 残余缓冲，防止数据丢失

#### CacheManager 扩展
- 新增 `context` TTL 缓存（128 条目, 5 分钟），用于 V2 上下文检索结果
- 新增 `embedding_query` TTL 缓存（256 条目, 10 分钟），用于查询 embedding 向量

### 新增配置项

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `lightrag_query_mode` | `local` | LightRAG 检索模式（local/hybrid/naive/global/mix） |
| `rerank_min_candidates` | `3` | 触发 Reranker 的最低候选文档数 |

## [Next-2.0.2] - 2026-02-24

### Bug 修复

#### MySQL 方言兼容
- 修复 SQLAlchemy 列类型定义在 MySQL 方言下的兼容性问题

#### 监控模块可选依赖
- `prometheus_client` 导入失败时优雅降级，不再阻断插件启动

#### Windows 控制台兼容
- 新增 GBK 安全字符串转换辅助函数，防止 Windows 中文控制台输出含 emoji/特殊字符时崩溃

### 重构

#### 关停超时集中管理
- 将 `shutdown_step_timeout`、`task_cancel_timeout`、`service_stop_timeout` 三个超时参数集中到 `PluginConfig`

### CI/CD

- Issue triage workflow 重写为双段式报告格式

## [Next-2.0.1] - 2026-02-23

### 🔧 Bug 修复

#### 插件卸载/重载卡死 (100% CPU)
- 修复 5 个后台 `while True` 任务（`_daily_mood_updater`、`_periodic_memory_sync`、`_periodic_context_cleanup`、`_periodic_knowledge_update`、`_periodic_recommendation_refresh`）未被跟踪和取消的问题
- `plugin_lifecycle.py` 中 3 个 `asyncio.create_task()` 调用现在全部注册到 `background_tasks` 集合，确保关停时被取消
- 所有关停步骤添加 `asyncio.wait_for` 超时保护（每步 8s），避免单个服务阻塞整个关停流程
- `ServiceRegistry.stop_all_services()` 每个服务添加 5s 超时
- `GroupLearningOrchestrator.cancel_all()` 添加 per-task 超时
- `Server.stop()` 将 `thread.join()` 移至线程池执行器，避免阻塞事件循环
- `WebUIManager.stop()` 添加锁获取超时，防止死锁
- 关停时清理 `SingletonABCMeta._instances`，防止重载后单例残留

#### MySQL 兼容性修复
- 修复 `persona_content` 列 INSERT 时传入 `None` 导致 `IntegrityError (1048)` 的问题
- 修复 `TEXT` 列不能有 `DEFAULT` 值的 MySQL 严格模式错误
- 启用启动时自动列迁移，跳过 TEXT/BLOB/JSON 列的 DEFAULT 生成
- Facade 文件中 65 处方法内延迟导入移至模块级别，修复热重载后 `ModuleNotFoundError`

#### 人格审批修复
- 传统审批路径（纯数字 ID）改为通过 `PersonaWebManager` 路由，解决跨线程调用导致的卡死
- 修复 `save_or_update_jargon` 参数顺序和类型错误

## [Next-2.0.0] - 2026-02-22

### 🎯 新功能

#### Prometheus 性能监控模块
- 新增 `services/monitoring/` 子包，提供统一性能监控基础设施
- **指标收集** (`metrics.py`)：基于 `prometheus_client` 的 14 个预定义指标（LLM 延迟/调用/错误、消息处理、缓存命中、系统 CPU/内存、Hook 耗时等）
- **异步装饰器** (`instrumentation.py`)：`@timed`、`@count_errors`、`timer` 上下文管理器，兼容 `prometheus-async`，缺失时自动回退纯 Python 实现
- **函数级监控** (`instrumentation.py`)：`@monitored` 装饰器记录每函数调用次数、错误数、延迟直方图，通过 `debug_mode` 开关控制，关闭时零开销
- **指标采集器** (`collector.py`)：后台周期采集系统资源（CPU/内存）和缓存命中率，写入 Prometheus 注册表
- **健康检查** (`health_checker.py`)：5 项子系统健康检查（CPU/内存/LLM/缓存/服务注册表），返回 healthy/degraded/unhealthy 状态
- **性能分析** (`profiler.py`)：按需 CPU 分析（yappi/cProfile）和内存分析（tracemalloc），支持启动/停止会话式操作
- **REST API** (`webui/blueprints/monitoring.py`)：6 个端点 — `/metrics`（Prometheus 文本格式）、`/metrics/json`、`/health`、`/functions`（函数级指标）、`/profile/start`、`/profile/<id>`
- 新增 `prometheus_client` 和 `prometheus-async` 依赖
- `ServiceFactory` 注册 `MetricCollector` 和 `HealthChecker`，`ServiceContainer` 自动初始化

#### 性能监控 WebUI 应用
- 新增 macOS 风格「性能监控」应用，包含 3 个 Tab 页
- **系统概览**：5 个健康状态卡片（CPU/内存/LLM/缓存/服务）+ 2 个 ECharts 仪表盘图表
- **函数性能**（默认 Tab）：`el-table` 可排序表格，**默认按平均耗时降序排列**，实时展示最慢函数；支持搜索过滤、错误率颜色标签
- **性能分析**：CPU/内存分析启停控制，结果以表格展示 top 函数/分配热点
- 每 10 秒自动刷新数据
- `debug_mode` 关闭时函数性能 Tab 显示引导提示

#### 数据库自动列迁移
- 新增启动时自动检测并添加缺失列的机制
- ORM 模型新增列后无需手动迁移，`create_all` + `inspect` 自动补全
- 为 `PersonaBackup` 添加 `group_id`、`persona_content`、`backup_time` 列

### ⚡ 性能优化

#### 数据库引擎
- SQLite 连接池从 `NullPool` 切换为 `StaticPool`，复用单连接消除逐查询开销
- 启用 `mmap_size=256MB` 加速读取

#### 缓存系统
- `CacheManager.general_cache` 从无界 `dict` 改为 `LRUCache(maxsize=5000)`，防止内存无限增长
- 新增逐缓存命中/未命中计数和 `get_hit_rates()` API，供监控仪表盘消费
- `MultidimensionalAnalyzer` 分析缓存从无界 `dict` 改为 `TTLCache`（情感 15min、风格 30min）
- 新增社交关系 O(1) 索引（`(from_user, to_user, relation_type)` 元组键）

#### 社交上下文注入
- 5 个独立上下文查询改为 `asyncio.gather` 并发执行，总延迟降低
- 缓存 TTL 从 60 秒提升至 300 秒，匹配社交数据低频变更特性
- 新增 `invalidate_user_cache()` 主动失效机制

#### LLM 适配器
- Provider 延迟初始化从一次性尝试改为 30 秒冷却间隔重试，应对启动时 Provider 未就绪场景

#### 响应多样性
- 新增 5 秒去重缓存，同一群组短时间窗口内的重复调用直接返回缓存结果

#### 学习流程
- 表达模式保存从逐条 `session.add()` + `commit` 改为 `add_all()` 批量写入
- `_execute_learning_batch` 和 `reinforcement_memory_replay` 用显式 `from_force_learning` / `from_learning_batch` 参数替代 `inspect.currentframe()` 栈帧遍历

#### 模块生命周期
- `V2LearningIntegration` 的 `start()`/`stop()` 从串行 await 改为 `asyncio.gather` 并发
- `LightRAGKnowledgeManager` 新增统计结果缓存（TTL 5min），避免重复 GraphML 解析

### 🔧 Bug 修复

#### ORM 迁移后遗留修复
- `ExpressionPattern` Facade 查询列名修正
- `SocialContextInjector` 适配新 Facade 返回格式
- `SocialFacade` 的 `from_user`/`to_user` 映射到 ORM 列名
- 社交用户统计查询补充 `sender_name` 字段
- `CompositePsychologicalState` 模型补充缺失列
- `get_recent_week_expression_patterns` 补充 `hours` 参数
- `DatabaseManager` 别名兼容旧代码
- 学习会话记录改为 upsert 避免重复插入
- `MemoryGraphManager` 处理 dict 类型消息

#### 业务逻辑修复
- `LightRAGKnowledgeManager`：embedding 结果转换为 numpy array，避免类型错误
- `LightRAGKnowledgeManager`：缺失 embedding provider 时添加守护检查
- 黑话学习：`generate_response` 替代不存在的 `generate` 方法
- 黑话挖掘：增强过滤条件提升挖掘质量
- 社交关系：插入前先 get-or-create `UserSocialProfile`，避免外键约束失败
- 人格备份：`auto_backup_enabled` 作为唯一备份开关
- 插件初始化：bootstrap 异常不再阻断 handler 绑定
- 状态迭代：组件列表用 `list()` 迭代替代 dict 迭代

### 🔇 日志优化
- LLM Hook 注入流程的 10 处 `logger.info` 降级为 `logger.debug`，减少正常运行时的日志噪音

### 🗑️ 移除
- 删除未使用的 `DataAnalyticsService`
- 移除 `plotly`、`matplotlib`、`seaborn`、`wordcloud` 及 3 个未使用依赖

---

## [Next-2.0.0] - 2026-02-21

### 🏗️ 架构重构

#### 全量 ORM 迁移（消除所有硬编码 SQL）
- 将 7 个服务文件中残留的硬编码 raw SQL 全部迁移至 SQLAlchemy ORM
- `expression_pattern_learner`：`_apply_time_decay`、`_limit_max_expressions`、`get_expression_patterns` 改用 `ExpressionPatternORM` 模型
- `time_decay_manager`：完全重写，消除 f-string SQL 注入风险，用显式 ORM 模型处理器替代动态表名拼接，移除对不存在表的引用
- `enhanced_social_relation_manager`：4 个方法改用 `UserSocialProfile`、`UserSocialRelationComponent`、`SocialRelationHistory` 模型
- `intelligent_responder`：3 个方法改用 `FilteredMessage`、`RawMessage` 模型及 `func.count`/`func.avg` 聚合
- `multidimensional_analyzer`：2 个 GROUP BY/HAVING 查询改用 ORM `select().group_by().having()`
- `affection_manager`：3 层级联查询改用 `RawMessage`、`FilteredMessage`、`LearningBatch` 模型
- `dialog_analyzer`：`get_pending_style_reviews` 改用 `StyleLearningReview` 模型
- `progressive_learning`、`message_facade`、`webui/learning` 蓝图同步迁移

#### 遗留数据库层清理（-7600 行）
- 删除 `services/database/database_manager.py`（6035 行硬编码 SQL 单体）
- 删除 `core/database/` 下 5 个遗留后端文件：`backend_interface.py`、`sqlite_backend.py`、`mysql_backend.py`、`postgresql_backend.py`、`factory.py`（共 1530 行）
- DomainRouter 移除 `_legacy_db` 回退、`get_db_connection()`/`get_connection()` shim、`__getattr__` 安全网
- `core/database/__init__.py` 精简为仅导出 `DatabaseEngine`
- `services/database/__init__.py` 移除 `DatabaseManager` 导出

#### 未使用资源清理
- 删除 `web_res/static/MacOS-Web-UI/` 源码目录（已迁移至 `static/js/macos/` 和 `static/css/macos/`）

#### 服务层重组
- 将 `services/` 下 51 个平铺文件重组为 14 个领域子包，提升内聚性和可维护性
- 每个子包职责明确：`learning/`、`social/`、`jargon/`、`persona/`、`expression/`、`affection/`、`psychological/`、`reinforcement/`、`message/` 等

#### 主模块瘦身
- 将 `main.py` 业务逻辑提取至独立生命周期模块（`initializer`、`event_handler`、`learning_scheduler` 等）
- 代码量从 2518 行精简至 207 行（减少 92%）

#### 数据库单体拆分
- 将 4308 行的 `SQLAlchemyDatabaseManager` 重写为约 800 行的薄路由层（DomainRouter）
- 引入 `BaseFacade` 基类和 11 个领域 Facade，实现关注点分离
- 所有 62 个消费者方法显式路由到对应 Facade，消除隐式回退

#### 领域 Facade 清单
| Facade | 职责 | 方法数 |
|--------|------|--------|
| `MessageFacade` | 消息存储、查询、统计 | 17 |
| `LearningFacade` | 学习记录、审查、批次、风格学习 | 29 |
| `JargonFacade` | 黑话 CRUD、搜索、统计、全局同步 | 14 |
| `SocialFacade` | 社交关系、用户画像、偏好 | 9 |
| `PersonaFacade` | 人格备份、恢复、更新历史 | 4 |
| `AffectionFacade` | 好感度、Bot 情绪状态 | 6 |
| `PsychologicalFacade` | 情绪画像 | 2 |
| `ExpressionFacade` | 表达模式、风格画像 | 8 |
| `ReinforcementFacade` | 强化学习、人格融合、策略优化 | 6 |
| `MetricsFacade` | 跨域统计聚合 | 3 |
| `AdminFacade` | 数据清理与导出 | 2 |

#### Repository 层扩展
- 新增 10 个类型化 Repository 类，总数从 29 增至 39
- 新增：`RawMessageRepository`、`FilteredMessageRepository`、`BotMessageRepository`、`UserProfileRepository`、`UserPreferencesRepository`、`EmotionProfileRepository`、`StyleProfileRepository`、`BotMoodRepository`、`PersonaBackupRepository`、`KnowledgeGraphRepository`

### 🔧 重构

#### PluginConfig 迁移
- 从 `dataclass` 迁移至 pydantic `BaseModel`
- 采用 `ConfigDict(extra="ignore", populate_by_name=True)` 实现健壮验证和未知字段容忍

#### 服务缓存优化
- 新增 `@cached_service` 装饰器，消除冗余服务实例化
- 替换手工单例模式，减少样板代码

#### 数据库连接清理
- 移除旧版 `DatabaseConnectionPool`，改用 SQLAlchemy 异步引擎内置连接池管理
- 移除未使用的 `EventBus`、`EventType`、`EventManager` 等事件基础设施

### ⚡ 性能优化

#### LLM 缓存命中率提升
- 上下文注入从 `system_prompt` 拼接改为 AstrBot 框架 `extra_user_content_parts` API
- 动态上下文（社交关系、黑话、多样性、V2 学习）作为额外内容块附加在用户消息之后，不再修改系统提示词
- **system_prompt 保持稳定不变**，最大化 LLM API 前缀缓存（prefix caching）命中率，显著降低 token 消耗和响应延迟
- 旧版 AstrBot 自动回退到 system_prompt 注入（附带缓存命中率下降警告）

#### 上下文检索并行化
- LLM Hook 的 4 个上下文提供者（社交、V2 学习、多样性、黑话）通过 `asyncio.gather` 并行执行
- Hook 总延迟降低约 60-70%（从串行累加改为取最慢单项）
- 每个提供者独立计时，便于识别性能瓶颈

#### 服务实例化缓存
- 29 个服务方法通过 `@cached_service` 装饰器缓存，避免重复创建服务实例
- `ServiceFactory` 和 `ComponentFactory` 共享同一缓存字典，跨工厂复用

#### 数据处理流水线优化
- 消息批量写入改为 `asyncio.gather` 并发插入
- 渐进式学习中消息筛选与人格检索并行执行
- 强化学习与风格分析并行执行
- DomainRouter 显式方法路由消除 `__getattr__` 运行时属性查找开销

### 📊 统计
- **净代码减少**：约 21,700 行（ORM 迁移 + 遗留层删除 + 未使用资源清理）
- **遗留 SQL 层**：6035 + 1530 = 7565 行硬编码 SQL 代码删除
- **ORM 迁移**：7 个服务文件、约 800 行 raw SQL 替换为类型安全的 ORM 查询
- **安全修复**：`time_decay_manager` f-string SQL 注入漏洞已消除
- **新增文件**：11 个 Facade + 10 个 Repository + 1 个 BaseFacade = 22 个文件
- **`SQLAlchemyDatabaseManager`**：4308 行 → ~777 行（减少 82%），零遗留回退
- **变更文件**：51+ 个服务文件重组、`main.py` 重构、数据库层完全重写

---

## [Next-1.2.9] - 2026-02-19

### 🔧 Bug 修复

#### 多配置文件人格加载失败
- `PersonaManagerService` 调用 `get_default_persona_v3()` 未传入 `umo` 参数，导致始终返回 default 配置的人格
- 新增 `_resolve_umo()` 方法和 `group_id_to_unified_origin` 映射，正确解析当前活跃配置
- `main.py` 将映射表引用传递给 `PersonaManagerService`
- `compatibility_extensions.py` 透传 `group_id` 参数

#### WebUI 人格不随配置切换更新
- `PersonaWebManager.get_default_persona_for_web()` 硬编码 `get_default_persona_v3()` 无 UMO，切换配置后仍显示旧人格
- 改为从 `group_id_to_unified_origin` 映射中获取 UMO，加载当前活跃配置的人格
- 同步修复 `dependencies.py` 和 `webui_legacy.py` 的映射注入

#### PersonaWebManager 跨线程 DB 访问
- WebUI 运行在守护线程（独立事件循环），直接调用框架 PersonaManager 的异步 DB 方法会失败
- 新增 `_run_on_main_loop()` 将协程调度到主事件循环执行
- 缓存优先从 PersonaManager 内存列表同步（无需跨线程 DB 调用）

#### WebUI 人格详情查询错误
- `PersonaService` 使用了插件的 `PersonaManagerService` 而非框架的 `PersonaManager`，导致 `get_persona` 方法不存在
- 改为使用 `container.astrbot_persona_manager`

#### 框架移除 `curr_personality` 属性
- AstrBot 框架已完全移除 `provider.curr_personality`，5 个文件共约 40 处引用报 `AttributeError`
- 全部改为通过 `context.persona_manager` API 访问人格

#### `session_updates` 初始化不可达
- `TemporaryPersonaUpdater.session_updates` 初始化代码位于 `return` 语句之后，永远不会执行
- 移至 `__init__` 方法

### 📝 其他

- `memory_graph_manager` 和 `knowledge_graph_manager` 的 `db_manager` 空值检查日志从 WARNING 降级为 DEBUG
- 版本号更新至 Next-1.2.9

---

## [Next-1.2.8] - 2026-02-19

### 🔧 Bug 修复

#### WebUI 服务器端口占用
- 将 WebUI 服务器从 `asyncio.create_task` 改为独立守护线程模式运行 Hypercorn
- 采用旧版经过验证的线程方案，确保 Windows/macOS/CentOS/Ubuntu 等系统上重启时端口可靠释放
- 使用 `SecureConfig` 创建带 `SO_REUSEADDR` + `SO_REUSEPORT` + `set_inheritable(False)` 的 socket
- 保留跨平台端口清理（Windows `taskkill` / Linux `lsof` + `kill -9`）

#### 单例重启问题
- 插件 `terminate()` 时重置 `MemoryGraphManager` 单例状态，防止重启后使用失效的 LLM 适配器
- `Server.stop()` 重置单例状态，确保重新初始化

#### WebUI 学习按钮异常
- 修复 `trigger_learning` 方法不存在的错误，改为正确的 `start_learning` 方法

#### MemoryGraphManager 空指针
- 为 `llm_adapter` 增加二次空值检查，防止并发场景下 `generate_response` 调用失败

### 📝 其他

- README（中英文）重写为卖点导向，突出功能价值，移除技术实现细节
- `persona_web_manager` 常规日志从 INFO 降级为 DEBUG，减少日志噪音
- 版本号更新至 Next-1.2.8

---

## [Next-1.2.5] - 2026-02-19

### 🎯 新功能

#### MacOS-Web-UI 桌面框架迁移
- 前端从 ModderUI 整体重写为 macOS 风格桌面模拟器
- 每个管理页面变为独立 macOS「应用窗口」，支持拖拽、缩放、最小化、最大化、层叠
- 基于 Vue 3 + Element Plus + Vuex 4 自托管加载（无 Node.js 构建步骤）
- 9 个业务应用：仪表盘、系统设置、学习状态、人格审查、人格管理、对话风格、社交关系、黑话学习、Bug反馈
- macOS 风格 Dock 栏、启动台、菜单栏、启动动画、登录界面

#### 状态栏实时指标
- 菜单栏实时显示消息总数和学习效率
- 每 30 秒自动刷新

#### 人格审查服务端分页
- 后端接受 `limit`/`offset` 参数，返回分页数据和 `total` 总数
- 前端仅加载当前页数据，翻页时按需加载
- 消除一次性加载全部记录的性能问题

#### 多配置人格支持
- 支持多份人格配置并行管理，可选自动应用
- 审批流程和批量审查接口中集成自动应用逻辑

### 🔧 Bug 修复

#### 前端运行时错误
- 修复 `styleProgress.map is not a function`：SQLAlchemy `get_style_progress_data()` 错误返回 Dict 而非 List，重写为通过 ORM 查询 `learning_batches` 表
- 修复 `id.substring is not a function`：`shortId()`、`escapeHtml()`、`truncateText()`、`getContentPreview()`、`getProposedPreviewHtml()` 统一增加 `String()` 类型转换
- 修复 `SocialRelationAnalyzer.analyze_group_relations` 方法名错误，改为 `analyze_group_social_relations`
- 修复 `get_jargon_statistics()` 传入无效 `chat_id` 参数
- 在 StyleLearning.js 和 Dashboard.js 中增加 `Array.isArray()` 防御检查

#### 后端与数据库
- 解决跨线程数据库访问时的 asyncio 事件循环冲突
- 处理 MySQL Boolean 列类型和默认值兼容问题
- 将 `kg_relations` VARCHAR 缩短至 191 以适配 MySQL utf8mb4 索引限制
- WebUI 数据库方法委托到 ORM 版本
- 修复知识图谱、记忆图谱、WebUI 服务器初始化错误
- 所有入口路由统一指向 `macos.html`

#### WebUI 界面修复
- 修复登录卡片大小和布局溢出
- 修复人格审查、风格学习、社交关系数据获取
- 修复深色模式切换、壁纸上传、Bug反馈图标
- 全局替换 Apple 图标为项目 Logo
- 跳过启动动画直接进入登录页
- Dock 添加计算器、修复启动台图标

### 📱 移动端适配
- Dock 图标增大（768px 下 40px，480px 下 36px）
- 关闭/最小化/最大化按钮增大（768px 下 18px，480px 下 16px）
- 菜单栏和标题栏高度增加，改善触控体验
- 桌面和启动台改为单击打开应用（原为双击）

### 🔧 重构
- WebUI 中全部 legacy raw SQL 替换为 ORM 查询
- 新增强化学习和 ML 分析器的 ORM 方法
- 实现基于 ORM 的黑话 CRUD 方法
- Repository 层 dict/list 自动 JSON 序列化
- WebUI 蓝图拆分为模块化包（原为单体 webui.py）
- ModderUI CSS 框架（iOS 液态玻璃主题，迁移过渡阶段）

### 📝 其他
- 版本号更新至 Next-1.2.5
- 移除废弃的注册装饰器（@SXP-Simon）
- CI 提交信息长度限制提升至 128 字符

---

## [Next-1.2.0] - 2026-02-18

### 🔥 关键修复

#### WebUI 跨线程数据库访问崩溃 (Critical)
- **根因**：WebUI 运行在独立线程的独立事件循环中，调用 legacy `get_db_connection()` 时触发 `RuntimeError: Task got Future attached to a different loop`
- **修复**：为 `DatabaseEngine` 实现按事件循环隔离的引擎池，非主线程自动创建独立 SQLAlchemy 引擎（NullPool），WebUI 的所有数据库操作改用 ORM

#### 强化学习保存 TypeError (Critical)
- **根因**：ORM Repository 层将 dict/list 直接赋给 Text 列，触发 `TypeError: dict can not be used as parameter`
- **修复**：在 `ReinforcementLearningRepository`、`PersonaFusionRepository`、`StrategyOptimizationRepository` 中添加 `json.dumps()` 序列化

#### 黑话学习无法保存数据
- **根因**：`insert_jargon`/`update_jargon`/`get_jargon` 未在 `SQLAlchemyDatabaseManager` 中实现，通过 `__getattr__` 委托给 legacy 代码，datetime 对象与 BigInteger 列类型不兼容导致静默失败
- **修复**：在 `SQLAlchemyDatabaseManager` 中实现 ORM 版本的三个黑话 CRUD 方法，自动处理时间戳类型转换

### 🔧 重构

#### WebUI 全面 ORM 迁移
- 替换 `webui.py` 中全部 10 处 `get_db_connection()` 原始 SQL 为 ORM 查询
- 涉及路由：`relearn_all`、`get_groups_info`、`analyze_all_groups`、`style_learning_all`、`expression_patterns`、`clear_group_social_relations`、`toggle_jargon_global` 等

#### ML 分析器 ORM 迁移
- 替换 `ml_analyzer.py` 中 3 处 `get_db_connection()` 为 ORM 查询
- `_get_user_messages`、`_get_recent_group_messages`、`_get_most_active_users` 改用 `RawMessage` ORM 模型

#### 强化学习方法 ORM 实现
- 在 `SQLAlchemyDatabaseManager` 新增 10 个 ORM 方法，拦截原本会委托给 legacy 的调用
- 包括：`get_learning_history_for_reinforcement`、`save_reinforcement_learning_result`、`get_persona_fusion_history`、`save_persona_fusion_result`、`get_learning_performance_history`、`save_learning_performance_record`、`save_strategy_optimization_result`、`get_messages_for_replay`、`get_message_statistics`

### 📝 其他
- 新增 `CONTRIBUTING.md`，规范 Conventional Commits 提交格式
- 新增 PR 提交信息 lint CI
- 登录界面适配移动端（@Radiant303）
- 精简 metadata.yaml 描述
- 更新版本号至 Next-1.2.0

### 📊 统计
- **变更文件**：main.py、webui.py、ml_analyzer.py、sqlalchemy_database_manager.py、reinforcement_repository.py、engine.py
- **新增约 500 行 ORM 代码**，替代 legacy raw SQL 调用

---

## [Next-1.1.9] - 2026-02-17

### 🔥 关键修复

#### SQLite 模式完全不可用 (Critical)
- **根因**：`_check_and_migrate_database()` 在首次启动时对不存在的数据库执行迁移，导致 `on_load()` 崩溃，`db_manager.start()` 永远不会执行
- **表现**：所有数据库操作报错 `数据库管理器未启动，engine不存在`
- **修复**：彻底移除数据库迁移系统，表结构由 SQLAlchemy ORM `Base.metadata.create_all` 幂等创建

#### 群聊限制不生效 (#28)
- **根因**：`_get_active_groups()` 查询所有群组时未应用 `target_qq_list` 白名单和 `target_blacklist` 黑名单
- **修复**：为 `QQFilter` 新增 `get_allowed_group_ids()` / `get_blocked_group_ids()` 方法，在三级渐进查询（24h → 7d → 全量）中统一应用 `.in_()` / `.notin_()` 过滤

#### 命令报错 (#24)
- **根因**：`/persona_info` 等命令引用了不存在的方法 `PersonaUpdater.format_current_persona_display`
- **修复**：移除 11 个已废弃命令，保留 6 个核心命令

#### 启动竞态条件
- 为 `on_message()` 添加数据库就绪检查，在 `on_load()` 完成前跳过消息处理，防止 "engine不存在" 错误

#### LLM 空响应崩溃
- `prompt_sanitizer.sanitize_response()` 在 LLM 返回 `None` 时触发 `TypeError`，已添加空值保护

### 🗑️ 移除

#### 数据库迁移系统 (完整移除)
- 删除 `utils/migration_tool.py`（v1 迁移工具）
- 删除 `utils/migration_tool_v2.py`（SmartDatabaseMigrator）
- 删除 `test_migration_quick.py`（迁移测试）
- 移除 `engine.py` 中的 `migrate_schema()`、`_migrate_mysql()`、`_migrate_sqlite()`
- 移除 `sqlite_backend.py`、`mysql_backend.py` 中的迁移调用
- 移除 `main.py` 中的 `_check_and_migrate_database()`、`_get_database_url()`、`_mask_url()`

#### 废弃命令 (11 个)
- `clear_data`、`export_data`、`analytics_report`
- `persona_switch`、`persona_info`、`temp_persona`
- `apply_persona_updates`、`switch_persona_update_mode`
- `clean_duplicate_content`、`migrate_database`、`db_status`

### ✅ 保留命令 (6 个)
- `learning_status`、`start_learning`、`stop_learning`
- `force_learning`、`affection_status`、`set_mood`

### 📝 其他
- 更新 README 标题和版本徽章至 Next-1.1.9
- 更新 `.gitignore` 排除导出目录

### 🤝 致谢
- 感谢 @NieiR 和 @sdfsfsk 在早期版本中的社区贡献

### 📊 统计
- **净减少约 2600 行代码**，删除 3 个文件
- **变更文件**：main.py、engine.py、factory.py、sqlite_backend.py、mysql_backend.py、prompt_sanitizer.py

---

## [Next-1.1.5] - 2026-01-17

### 🎯 新功能

#### 目标驱动对话系统
- **38种预设对话目标类型**，涵盖情感支持、知识问答、日常对话等8大类场景
- **智能目标识别与切换**，自动分析用户意图并调整对话策略
- **动态阶段规划**，根据对话进展自动调整互动流程
- **会话隔离机制**，基于 `MD5(group_id + user_id + date)` 实现24小时独立会话
- **RESTful API接口**，提供对话目标管理的编程接口

详细说明：
- 预设对话目标类型包括：情感支持（安慰、共情、鼓励等）、知识交流（答疑、科普、推荐等）、日常互动（闲聊、玩笑、吐槽等）
  更多类型交由LLM自主创建
- 拆解对话目标为阶段性目标，引导聊天对话朝目标靠近
- 自动检测对话主题变化和阶段完成信号，智能切换目标
- 集成到主消息流程，通过社交上下文注入器自动增强对话上下文

#### Guardrails-AI 集成
- **Pydantic模型验证**，为 LLM 输出提供类型安全保障
- **GoalAnalysisResult 模型**，验证对话目标分析结果（目标类型、话题、置信度）
- **ConversationIntentAnalysis 模型**，验证对话意图分析（目标切换、阶段完成、用户参与度等9个字段）
- **自动类型转换**，兼容 guardrails-ai 返回的多种数据类型（dict/Pydantic实例）
- **增强错误诊断**，详细的验证失败日志和响应预览

### 🔧 重要修复

#### LLM适配器延迟初始化
- **非阻塞式加载**：插件加载时 Provider 未就绪不再抛出异常
- **延迟初始化机制**：首次 LLM 调用时自动尝试初始化 Provider
- **优雅降级**：Provider 配置失败时只记录 WARNING，不影响插件其他功能
- 修复了 "创建框架LLM适配器失败：无法配置任何LLM提供商" 错误

#### 字符串索引越界修复
- 修复 `prompt_sanitizer.py` 中 LCS 算法的索引错误
- 添加空字符串检查和实际长度重新计算
- 解决了 `string index out of range` 崩溃问题

#### Pydantic 类型错误修复
- 修复 `'dict' object has no attribute 'goal_type'` 错误
- 在 `parse_json_direct`、`parse_goal_analysis`、`parse_intent_analysis` 中添加类型检查
- 自动将 dict 转换为 Pydantic 模型实例

#### 参数传递修复
- 修复 `goal_manager` 未传递到 `SocialContextInjector` 的问题
- 确保对话目标上下文能正确注入到 LLM 请求中

### 📝 文档更新

- **README.md 完整重构**（+175行）
  - 添加目标驱动对话系统详细说明
  - 38种对话目标类型列表和示例
  - 工作流程图和API端点文档
  - 配置项说明（Goal_Driven_Chat_Settings）
- **GitHub 项目描述优化**，突出目标驱动、俚语理解、社交关系管理等核心功能

### 🐛 Bug修复与优化

- **异常处理增强**：为对话目标管理器的3个 LLM 调用方法添加独立 try-except 块
- **日志优化**：关键步骤从 DEBUG 提升到 INFO 级别，添加对话目标上下文注入验证日志
- **JSON 解析改进**：添加空响应检查、响应长度记录、失败时显示前200字符预览
- **配置加载修复**：正确加载 `Goal_Driven_Chat_Settings` 到 `PluginConfig`
- **Guardrails 参数修复**：移除 `validate_and_clean_json()` 的错误 `fallback` 参数

### 🔨 技术改进

- **模型策略**：对话目标分析统一使用提炼（refine）模型，提升准确性
- **类型安全**：全面采用 Pydantic 验证替代简单 JSON 清洗
- **诊断能力**：添加目标驱动对话系统初始化诊断日志
- **代码质量**：改进错误处理、日志记录、参数验证

### 📊 统计

- **18个提交**，涵盖新功能开发、Bug修复、文档更新
- **核心文件变更**：
  - 新增 `services/conversation_goal_manager.py`（对话目标管理器）
  - 新增 `repositories/conversation_goal_repository.py`（数据访问层）
  - 增强 `utils/guardrails_manager.py`（Pydantic模型集成）
  - 优化 `core/factory.py`（延迟初始化）
  - 优化 `core/framework_llm_adapter.py`（重试机制）

---

## [Previous Versions]

更早版本的更新日志请参考 Git 历史记录。
