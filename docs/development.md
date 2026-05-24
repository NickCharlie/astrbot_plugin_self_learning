# 开发指南

本文面向维护者。修改前先确认当前分支和工作区，不要提交 `coverage.xml`、`data/`、`vendor/`、`.agents/`、`skills-lock.json`。

## 环境

推荐 Python 3.11+。测试依赖在 `requirements-test.txt`。

安装测试依赖:

```powershell
python -m pip install -r requirements-test.txt
```

当前主线没有运行时 `requirements.txt`。运行时依赖由 WebUI 设置页手动安装接口维护，依赖列表在:

```text
webui/blueprints/config.py
```

依赖分两档:

- `BASIC_DEPENDENCY_PACKAGES`: WebUI、SQLite、人格审查、黑话和表达方式学习所需依赖。
- `FULL_DEPENDENCY_PACKAGES`: 基础依赖 + 数据库驱动、监控、图谱、V2 高级引擎依赖。

## 常用命令

运行全部测试:

```powershell
python -m pytest
```

运行学习链路回归:

```powershell
python -m pytest tests/unit/test_learning_chain_regressions.py
```

运行数据库测试:

```powershell
python -m pytest tests/unit/test_database_engine.py tests/unit/test_sqlalchemy_db_manager_contract.py
```

运行 WebUI 集成测试:

```powershell
python -m pytest tests/integration/test_auth_blueprint.py tests/integration/test_config_blueprint.py tests/integration/test_graph_blueprint.py tests/integration/test_learning_content_blueprint.py
```

检查包导入:

```powershell
python -m pytest tests/integration/test_package_imports.py
```

## 代码入口

新增功能时优先从这些入口定位:

- 插件 hook: `main.py`
- 服务初始化: `core/plugin_lifecycle.py`
- 服务创建: `core/factory.py`
- 学习流水线: `services/learning/message_pipeline.py`
- 实时表达学习: `services/learning/realtime_processor.py`
- 批量学习: `services/core_learning/progressive_learning.py`
- 数据库: `services/database/sqlalchemy_database_manager.py`
- ORM: `models/orm/`
- WebUI API: `webui/blueprints/`
- WebUI 服务层: `webui/services/`
- 功能融合: `core/feature_delegation.py`, `webui/services/integration_service.py`

## 添加服务

推荐步骤:

1. 在 `services/<domain>/` 添加服务类。
2. 在 `core/factory.py` 添加 `create_xxx_service()`。
3. 用 `@cached_service("xxx")` 缓存实例。
4. 构造时注入 `PluginConfig`、`db_manager`、`llm_adapter` 等依赖。
5. 如果服务需要统一关停，调用 `self._registry.register_service("xxx", service)`。
6. 在 `PluginLifecycle.bootstrap()` 中按依赖顺序创建。
7. 如果 WebUI 需要访问，在 `webui/dependencies.py` 的 `ServiceContainer.initialize()` 中暴露。
8. 添加对应单元测试或集成测试。

## 添加 WebUI API

推荐结构:

1. `webui/services/<name>_service.py`: 业务逻辑。
2. `webui/blueprints/<name>.py`: HTTP 参数解析和响应。
3. `webui/blueprints/__init__.py`: 注册蓝图。
4. `tests/integration/test_<name>_blueprint.py`: 覆盖路由。

响应建议:

- 成功用 `jsonify(...)`。
- 错误用 `webui/utils/response.py::error_response()`。
- 需要鉴权的路由加 `@require_auth`，即使当前免密，也保留装饰器用于未来恢复鉴权。

## 添加 companion 插件融合

推荐步骤:

1. 在 `core/feature_delegation.py` 添加检测别名和 `should_delegate_xxx()`。
2. 在调用点只跳过重叠能力，不影响学习、审查和上下文注入主链路。
3. 在 `webui/services/integration_service.py` 增加面板入口和开发 API 列表。
4. 在 Dashboard `#/integrations` 展示状态和配置入口。
5. 添加 `tests/unit/test_feature_delegation.py` 或 `tests/unit/test_integration_service.py` 覆盖。

不要复制 companion 插件内部实现。只使用其公开 Dashboard、AstrBot Pages 或开发 API。

## 添加配置项

需要同步修改:

1. `_conf_schema.json`: AstrBot 配置和 WebUI 基础 schema。
2. `config.py::PluginConfig`: Pydantic 字段和默认值。
3. `PluginConfig.create_from_config()`: 从分组配置读取。
4. `PluginConfig.validate_config()`: 必要时添加校验。
5. `webui/services/config_service.py`: 如果 schema 中没有覆盖，加入 `_EXTRA_SCHEMA_DEFINITION` 或枚举选项。
6. 测试: `tests/unit/test_config.py`, `tests/unit/test_config_service.py`。

如果配置修改需要重启，在 `ConfigService._RESTART_REQUIRED_KEYS` 加字段名。

## 添加数据库表

步骤:

1. 在 `models/orm/<domain>.py` 添加 ORM 类。
2. 确认该模型被 `models/orm/__init__.py` 导入。
3. 选择或新增 Facade 方法。
4. 在 `SQLAlchemyDatabaseManager` 添加兼容委托方法。
5. 为 SQLite 建表添加测试。
6. 对 MySQL/PostgreSQL 注意索引名全局唯一。

当前迁移能力只会自动新增表和列，不支持删除列、重命名列和复杂类型迁移。复杂迁移需要显式 DDL 和回滚策略。

## 添加学习链路能力

优先判断能力属于哪一层:

| 能力 | 建议位置 |
| --- | --- |
| 每条消息轻量处理 | `MessagePipeline.process_learning` |
| 实时表达学习 | `RealtimeProcessor` |
| 群组级批量任务 | `GroupLearningOrchestrator` |
| 批量学习记录和审查 | `ProgressiveLearningService` |
| LLM 请求上下文 | `LLMHookHandler` |
| Dashboard 展示 | `webui/services/learning_service.py` 和对应蓝图 |

新增链路时要保证:

- 单个子任务异常不阻断消息采集。
- 长耗时逻辑后台运行。
- 关停时任务可取消。
- 结果可在 WebUI 或日志中定位。

## 日志

使用插件 logger 工具:

```python
from ...utils.logging_utils import get_astrbot_logger
logger = get_astrbot_logger("self_learning.domain")
```

日志等级来自 `PluginConfig.log_level`:

- `error`
- `warning`
- `info`
- `debug`

开发新链路时建议:

- 用户可见的状态变化用 `info`。
- 可恢复异常用 `warning`。
- 会导致功能失败的异常用 `error` 并带 `exc_info=True`。
- 高频内部细节用 `debug`。

## 依赖策略

不要在插件导入、安装或 bootstrap 阶段自动 pip install。

依赖安装只允许走:

```text
POST /api/dependencies/install
```

并要求设置页手动确认。新增依赖时同步更新:

- `webui/blueprints/config.py::BASIC_DEPENDENCY_PACKAGES` 或 `FULL_DEPENDENCY_PACKAGES`
- 相关导入的 optional fallback
- `tests/integration/test_package_imports.py`

可选依赖必须做到缺失时不阻断插件加载，除非该功能明确是核心必需。

## WebUI 静态资源

Dashboard 静态文件在:

```text
web_res/static/html/
web_res/static/vendor/
web_res/static/img/
web_res/static/fonts/
```

当前集成测试要求前端资源不要依赖外部 CDN:

```powershell
python -m pytest tests/integration/test_webui_static_assets.py
```

新增前端库时优先打包进 `web_res/static/vendor/`，不要引入大量运行时。

## 测试策略

最小测试集按修改范围选择:

| 修改范围 | 建议测试 |
| --- | --- |
| 配置 | `test_config.py`, `test_config_service.py`, `test_config_blueprint.py` |
| 数据库 | `test_database_engine.py`, `test_sqlalchemy_db_manager_contract.py` |
| 学习链路 | `test_learning_chain_regressions.py`, `test_learning_quality_monitor.py` |
| 功能融合 | `test_feature_delegation.py`, `test_integration_service.py` |
| WebUI API | 对应 `tests/integration/test_*_blueprint.py` |
| 导入和依赖 | `test_package_imports.py` |
| 静态资源 | `test_webui_static_assets.py` |

提交前至少运行与改动相关的测试。

## 常见开发坑

### 相对导入

插件运行在 AstrBot 包路径下，优先使用包内相对导入:

```python
from ...config import PluginConfig
```

兼容测试环境时可以保留 fallback，但不要只写顶层导入。

### WebUI 线程和数据库 session

WebUI 在独立线程运行，不能跨 event loop 复用 SQLAlchemy async session。必须通过 `db_manager.get_session()` 获取当前 loop 的 session。

### 服务初始化顺序

`SocialContextInjector` 依赖好感度、心理状态、社交关系和可选目标管理器。调整顺序时要确认 `PluginLifecycle.bootstrap()` 中依赖已经存在。

### Provider 时序

AstrBot Provider 可能在插件初始化时尚未完全就绪。不要因为 Provider 缺失让插件加载失败，应该延迟初始化并在实际使用时重试。

### 审查来源

人格审查、风格审查和表达学习存在多种历史来源。新增审查类型时同步更新:

- `constants.py`
- `webui/services/persona_review_service.py`
- `tests/unit/test_persona_review_service.py`
- Dashboard 展示逻辑
