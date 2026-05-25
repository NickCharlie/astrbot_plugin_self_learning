# 数据库

数据库层使用 SQLAlchemy async ORM，统一支持 SQLite、MySQL 和 PostgreSQL。对业务层暴露的是 `SQLAlchemyDatabaseManager`，内部是 DomainRouter，具体领域操作委托给 Facade。

## 支持的数据库

| 类型 | Driver | 默认用途 |
| --- | --- | --- |
| PostgreSQL | `postgresql+asyncpg` | 默认后端，多实例、schema 隔离、长期运行 |
| SQLite | `sqlite+aiosqlite` | 显式配置的单机回退 |
| MySQL | `mysql+aiomysql` | 显式配置的兼容后端 |

配置字段位于 `Database_Settings`:

- `db_type`: `postgresql`, `pgsql`, `sqlite`, `mysql`
- `mysql_host`, `mysql_port`, `mysql_user`, `mysql_password`, `mysql_database`
- `postgresql_host`, `postgresql_port`, `postgresql_user`, `postgresql_password`, `postgresql_database`, `postgresql_schema`
- `max_connections`, `min_connections`

## 启动流程

入口: `services/database/sqlalchemy_database_manager.py::start`

1. 标准化 `db_type`。
2. 构造数据库 URL；未配置 `db_type` 时默认使用 PostgreSQL。
3. MySQL: 连接服务器并创建缺失数据库。
4. PostgreSQL: 连接 `postgres` 数据库并创建缺失数据库，再创建缺失 schema。
5. 创建 `DatabaseEngine`。
6. 调用 `create_tables(enable_auto_migration=True)`。
7. 执行 `SELECT 1` 健康检查。
8. 初始化 11 个 Facade。

## 默认 PostgreSQL

默认配置等价于:

```json
{
  "Database_Settings": {
    "db_type": "postgresql",
    "postgresql_host": "localhost",
    "postgresql_port": 5432,
    "postgresql_user": "postgres",
    "postgresql_password": "",
    "postgresql_database": "astrbot_self_learning",
    "postgresql_schema": "public"
  }
}
```

启动时会先连接维护库 `postgres`，如果 `postgresql_database` 不存在则执行 `CREATE DATABASE`；随后连接目标数据库，创建缺失 schema，最后由 SQLAlchemy ORM 同步所有表。

运行默认配置的数据库用户必须具备:

- 连接 `postgres` 维护库的权限。
- 创建目标数据库的权限。
- 在目标数据库内创建 schema 和表的权限。

没有本地 PostgreSQL 服务时，可显式设置 `db_type=sqlite` 使用文件数据库。

## SQLite 路径规则

SQLite 数据库路径来源:

1. `plugin_config.messages_db_path`
2. 未设置时使用 `plugin_config.data_dir/messages.db`

路径处理规则:

- 支持环境变量和 `~`。
- 相对路径会转换为绝对路径。
- URL 使用 `sqlite+aiosqlite`。
- SQLite engine 使用 `NullPool`。
- 每次连接设置 WAL、foreign keys、mmap 等 pragma。

## PostgreSQL schema

PostgreSQL 支持非 `public` schema:

1. `SQLAlchemyDatabaseManager._ensure_postgresql_schema_exists()` 自动创建 schema。
2. URL query 里通过 `search_path` 传给 `DatabaseEngine`。
3. `DatabaseEngine._create_postgresql_engine()` 把 `search_path` 转成 asyncpg `server_settings`。

示例配置:

```json
{
  "Database_Settings": {
    "db_type": "postgresql",
    "postgresql_host": "localhost",
    "postgresql_port": 5432,
    "postgresql_user": "postgres",
    "postgresql_password": "password",
    "postgresql_database": "astrbot_self_learning",
    "postgresql_schema": "self_learning"
  }
}
```

## Engine 设计

`core/database/engine.py::DatabaseEngine` 负责:

- 根据 URL backend 创建 async engine。
- 创建 async session factory。
- `Base.metadata.create_all` 建表。
- 自动补齐缺失列。
- 跨线程和跨 event loop 访问。
- 健康检查。
- 关闭主 engine 和 per-loop engine。

WebUI 在独立线程运行，因此 `get_session()` 会根据当前 event loop 返回对应 engine。主 event loop 使用主 engine，其他 event loop 自动创建独立 engine。

## 自动建表和轻量迁移

建表入口:

```python
await engine.create_tables(enable_auto_migration=True)
```

行为:

1. 执行 `Base.metadata.create_all`。
2. 检查数据库实际表和列。
3. 创建 ORM 中存在但数据库缺失的表。
4. 对已有表补齐缺失列。

限制:

- 只做列级新增，不做字段删除、重命名、类型变更。
- MySQL 的 `TEXT`、`BLOB`、`JSON` 类型不会携带 default，避免 DDL 失败。
- 自动迁移失败会写 warning，一般不阻断插件继续运行。

## DomainRouter 和 Facade

`SQLAlchemyDatabaseManager` 保持旧接口兼容，实际委托到以下 Facade:

| Facade | 文件 | 职责 |
| --- | --- | --- |
| `AffectionFacade` | `affection_facade.py` | 好感度、Bot 情绪 |
| `MessageFacade` | `message_facade.py` | 原始消息、筛选消息、Bot 消息、统计 |
| `LearningFacade` | `learning_facade.py` | 人格审查、风格审查、学习会话、性能 |
| `JargonFacade` | `jargon_facade.py` | 黑话 CRUD、全局黑话、群组同步 |
| `PersonaFacade` | `persona_facade.py` | 人格备份和历史 |
| `SocialFacade` | `social_facade.py` | 用户画像、偏好、社交关系 |
| `ExpressionFacade` | `expression_facade.py` | 表达模式、风格档案 |
| `PsychologicalFacade` | `psychological_facade.py` | 情绪画像和心理状态 |
| `ReinforcementFacade` | `reinforcement_facade.py` | 强化学习、人格融合、策略优化 |
| `MetricsFacade` | `metrics_facade.py` | 统计和趋势 |
| `AdminFacade` | `admin_facade.py` | 数据清理和导出 |

新增数据库方法时优先加到对应 Facade，再在 `SQLAlchemyDatabaseManager` 增加同名委托方法。

## ORM 模型分组

所有模型从 `models/orm/__init__.py` 导出到同一个 `Base.metadata`。

| 文件 | 主要模型 |
| --- | --- |
| `message.py` | `RawMessage`, `FilteredMessage`, `BotMessage`, `ConversationContext`, `ConversationTopicClustering`, `ConversationQualityMetrics`, `ContextSimilarityCache` |
| `learning.py` | `PersonaLearningReview`, `StyleLearningReview`, `StyleLearningPattern`, `InteractionRecord`, `LearningBatch`, `LearningSession`, `LearningReinforcementFeedback`, `LearningOptimizationLog` |
| `expression.py` | `ExpressionPattern`, `ExpressionGenerationResult`, `AdaptiveResponseTemplate`, `StyleProfile`, `StyleLearningRecord`, `LanguageStylePattern` |
| `jargon.py` | `Jargon`, `JargonUsageFrequency` |
| `memory.py` | `Memory`, `MemoryEmbedding`, `MemorySummary` |
| `knowledge_graph.py` | `KGEntity`, `KGRelation`, `KGParagraphHash` |
| `social_relation.py` | `SocialRelation`, `UserSocialProfile`, `UserSocialRelationComponent`, `SocialRelationHistory`, `UserProfile`, `UserPreferences` |
| `psychological.py` | `CompositePsychologicalState`, `PsychologicalStateComponent`, `PsychologicalStateHistory`, `PersonaDiversityScore`, `PersonaAttributeWeight`, `PersonaEvolutionSnapshot`, `EmotionProfile`, `BotMood`, `PersonaBackup` |
| `affection.py` | `UserAffection`, `AffectionInteraction`, `UserConversationHistory`, `UserDiversity` |
| `conversation_goal.py` | `ConversationGoal` |
| `reinforcement.py` | `ReinforcementLearningResult`, `PersonaFusionHistory`, `StrategyOptimizationResult` |
| `performance.py` | `LearningPerformanceHistory` |
| `social_analysis.py` | `SocialRelationAnalysisResult`, `SocialNetworkNode`, `SocialNetworkEdge` |
| `exemplar.py` | `Exemplar` |

## 关键数据流

### 入站消息

```python
MessageCollectorService.collect_message()
-> SQLAlchemyDatabaseManager.save_raw_message()
-> MessageFacade.save_raw_message()
-> RawMessage
```

### 筛选消息

```python
ProgressiveLearningService._execute_learning_batch()
-> message_collector.add_filtered_message()
-> SQLAlchemyDatabaseManager.add_filtered_message()
-> FilteredMessage
```

### Bot 出站消息

```python
SelfLearningPlugin.on_bot_message_sent()
-> SQLAlchemyDatabaseManager.save_bot_message()
-> BotMessage
```

### 审查记录

```python
ProgressiveLearningService._save_style_learning_record()
-> StyleLearningReview

ProgressiveLearningService._apply_learning_updates()
-> PersonaLearningReview
```

### LLM 注入

```python
LLMHookHandler._fetch_few_shots()
-> SQLAlchemyDatabaseManager.get_approved_few_shots()
-> LearningFacade.get_approved_few_shots()
```

## 测试关注点

数据库相关测试集中在:

- `tests/unit/test_database_engine.py`
- `tests/unit/test_sqlalchemy_db_manager_contract.py`
- `tests/unit/test_config.py`
- `tests/integration/test_package_imports.py`

建议修改数据库层后至少运行:

```powershell
python -m pytest tests/unit/test_database_engine.py tests/unit/test_sqlalchemy_db_manager_contract.py tests/unit/test_config.py
```
