# 架构与实现

插件按 AstrBot 插件形态实现，入口类是 `SelfLearningPlugin(star.Star)`。主类只保留框架 hook、命令和生命周期委托，具体业务由 `PluginLifecycle`、工厂和服务层完成。

## 模块分层

| 层级 | 路径 | 职责 |
| --- | --- | --- |
| 插件入口 | `main.py` | 配置加载、AstrBot hook、命令入口、后台任务追踪 |
| 配置 | `config.py`, `_conf_schema.json` | Pydantic 配置模型、AstrBot 配置组、WebUI schema 源 |
| 生命周期 | `core/plugin_lifecycle.py` | bootstrap、on_load、shutdown |
| 功能融合 | `core/feature_delegation.py` | 检测 LivingMemory / Group Chat Plus 并决定是否跳过本地重叠能力 |
| 工厂 | `core/factory.py` | 创建和缓存服务实例，避免循环导入 |
| 接口模型 | `core/interfaces.py`, `exceptions.py`, `constants.py` | 数据结构、异常、学习类型常量 |
| 学习服务 | `services/core_learning/`, `services/learning/`, `services/analysis/`, `services/quality/` | 消息采集、实时学习、批量学习、质量控制、表达模式 |
| 状态服务 | `services/state/`, `services/social/`, `services/persona/` | 好感度、心理状态、社交关系、临时人格 |
| 黑话 | `services/jargon/` | 统计预筛、候选挖掘、含义推断、查询注入 |
| LLM Hook | `services/hooks/` | 并行拉取上下文并注入 LLM 请求 |
| 数据库 | `services/database/`, `core/database/`, `models/orm/` | SQLAlchemy async engine、ORM、Facade 路由 |
| WebUI | `webui/`, `web_res/` | Quart API、Dashboard 静态资源、服务容器 |
| 测试 | `tests/unit/`, `tests/integration/` | 单元测试、蓝图集成测试、启动导入回归测试 |

## 启动流程

### 1. AstrBot 实例化插件

`SelfLearningPlugin.__init__` 做以下事情:

1. 预置关键属性为 `None`，避免 bootstrap 失败后 hook 绑定异常。
2. 从 AstrBot 数据路径或 `Storage_Settings.data_dir` 解析插件数据目录。
3. 调用 `PluginConfig.create_from_config()` 把 AstrBot 分组配置展平为运行时配置。
4. 填充 `messages_db_path` 和 `learning_log_path`。
5. 创建 `PluginLifecycle` 并调用 `bootstrap()`。

### 2. bootstrap 同步组装服务

`PluginLifecycle.bootstrap()` 不启动数据库连接和 Web 服务器，只创建对象并注入到插件实例:

- `FactoryManager`
- `SQLAlchemyDatabaseManager`
- `MessageCollectorService`
- `MultidimensionalAnalyzer`
- `StyleAnalyzerService` 或 MaiBot 适配器
- `LearningQualityMonitor`
- `ProgressiveLearningService`
- `LightweightMLAnalyzer`
- `PersonaManagerService`
- `ResponseDiversityManager`
- `AdvancedLearningService`
- `EnhancedInteractionService`
- `IntelligenceEnhancementService`
- `AffectionManager`
- `SocialContextInjector`
- `JargonQueryService`
- `JargonMinerManager`
- `JargonStatisticalFilter`
- `FeatureDelegation`
- 可选 `V2LearningIntegration`
- `RealtimeProcessor`
- `GroupLearningOrchestrator`
- `LLMHookHandler`
- `MessagePipeline`
- `PluginCommandHandlers`
- `WebUIManager`

Provider 初始化是宽容的。没有可用 Provider 时，`FrameworkLLMAdapter` 不会让插件加载失败，会标记为延迟初始化。

如果检测到 LivingMemory 已加载，`V2LearningIntegration` 和 `LLMHookHandler` 会跳过本插件本地长期记忆写入与注入，保留知识图谱、few-shot 和风格上下文。若检测到 Group Chat Plus 已加载，`PluginLifecycle` 会跳过本地 `IntelligentResponder`，让回复决策和生成由 Group Chat Plus 处理。

功能融合的完整配置、API 和排查见 [功能融合](integrations.md)。

### 3. initialize 异步启动

AstrBot 完成 handler 绑定后调用 `initialize()`，它委托给 `PluginLifecycle.on_load()`:

1. `db_manager.start()` 最多重试 3 次。
2. 创建数据库引擎、建表、自动补齐缺失列、健康检查。
3. 启动好感度服务。
4. 启动可选 V2 学习集成，并异步预热活跃群组。
5. debug 模式下启用函数级性能监控。
6. 注册 WebUI 服务容器并启动 Hypercorn 线程。

### 4. terminate 有序关停

`PluginLifecycle.shutdown()` 按顺序关闭:

1. 标记 `_shutting_down=True`，阻止新后台任务。
2. 停止群组学习任务。
3. 停止学习调度器。
4. 取消 `MessagePipeline` 子任务。
5. 取消插件后台任务集合。
6. 停止 V2 集成。
7. 清理服务工厂和单例缓存。
8. 清理临时人格。
9. flush 消息收集器状态。
10. 停止 WebUI。
11. 保存配置到数据目录。

每个关停步骤都有超时保护，避免插件卸载卡死。

## 事件 Hook

### `on_message`

装饰器: `@filter.event_message_type(filter.EventMessageType.ALL)`

处理逻辑:

1. 跳过关停状态、空消息、数据库未启动状态。
2. 对 at/唤醒消息触发好感度后台处理。
3. 检查 `enable_message_capture`。
4. 过滤 AstrBot 命令。
5. 检查 QQ 白名单/黑名单。
6. 创建后台任务执行 `MessagePipeline.process_learning()`。

### `inject_diversity_to_llm_request`

装饰器: `@filter.on_llm_request()`

处理逻辑:

1. 委托 `LLMHookHandler.handle(event, req)`。
2. 并行拉取社交上下文、V2 上下文、多样性提示、黑话解释、已批准 few-shot。
3. 优先写入 `req.extra_user_content_parts`。
4. 旧版 AstrBot 缺少 `extra_user_content_parts` 时回退追加 `req.system_prompt`。

### `on_bot_message_sent`

装饰器: `@filter.after_message_sent()`

处理逻辑:

1. 从发送结果中提取 `Plain` 文本。
2. 保存到 `BotMessage` 表。
3. 后续表达学习会把用户消息和 Bot 消息按时间线合并，提取 user -> bot 对话对。

## 管理命令

| 命令 | 权限 | 实现 |
| --- | --- | --- |
| `/learning_status` | ADMIN | `PluginCommandHandlers.learning_status` |
| `/start_learning` | ADMIN | `PluginCommandHandlers.start_learning` |
| `/stop_learning` | ADMIN | `PluginCommandHandlers.stop_learning` |
| `/force_learning` | ADMIN | `PluginCommandHandlers.force_learning` |
| `/affection_status` | ADMIN | `PluginCommandHandlers.affection_status` |
| `/set_mood` | ADMIN | `PluginCommandHandlers.set_mood` |

## 服务创建规则

`ServiceFactory` 用 `@cached_service(key)` 缓存 create 方法结果。新增服务时优先遵守以下规则:

1. 服务构造放在 `create_xxx()` 中。
2. 复杂导入放在方法内部，降低循环导入概率。
3. 创建成功后注册到 `ServiceRegistry`，方便统一关停和健康检查。
4. WebUI 需要访问的服务通过 `webui/dependencies.py` 的 `ServiceContainer` 暴露。

## 线程和事件循环边界

WebUI 使用 Hypercorn 跑在独立守护线程。数据库层必须支持跨事件循环访问，因此 `DatabaseEngine` 会为非主 event loop 创建独立 async engine 和 session factory，避免 SQLAlchemy async 对象跨 loop 复用导致的 `Future attached to a different loop`。

## 依赖策略

当前代码不会在插件安装或加载阶段自动安装依赖。依赖安装只通过 WebUI 设置页的手动确认接口触发:

```http
POST /api/dependencies/install
```

请求必须包含:

```json
{"manual_confirmed": true, "source": "system_settings", "tier": "basic"}
```

`tier` 可选:

- `basic`: 人格审查、黑话、表达方式学习、SQLite、WebUI 基础能力。
- `full`: 基础能力 + MySQL/PostgreSQL、监控、图谱、V2 记忆/知识引擎。

这避免 AstrBot 安装插件时被 pip 阻塞。
