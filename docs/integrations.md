# 功能融合

Self Learning 负责学习、审查、黑话、表达方式和 LLM 上下文注入。长期记忆交给 LivingMemory，回复决策和生成交给 Group Chat Plus。

## 职责边界

| 能力 | 默认归属 | 委托后行为 |
| --- | --- | --- |
| 消息采集 | Self Learning | 保持不变 |
| 人格审查 | Self Learning | 保持不变 |
| 风格审查 | Self Learning | 保持不变 |
| 黑话学习 | Self Learning | 保持不变 |
| few-shot 注入 | Self Learning | 保持不变 |
| 长期记忆写入 | Self Learning | LivingMemory 已加载时跳过本地写入 |
| 长期记忆注入 | Self Learning | LivingMemory 已加载时跳过本地 V2 记忆注入 |
| 回复决策 | Self Learning 兼容回复器 | Group Chat Plus 已加载时跳过本地回复器 |
| 回复生成 | Self Learning 兼容回复器 | Group Chat Plus 已加载时跳过本地回复器 |

## 配置

配置组: `Integration_Settings`

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `delegate_memory_to_livingmemory` | `true` | 允许把长期记忆委托给 LivingMemory |
| `livingmemory_plugin_name` | `LivingMemory` | LivingMemory 检测名 |
| `disable_local_memory_when_delegated` | `true` | 委托生效时禁用本地长期记忆写入和注入 |
| `delegate_reply_to_group_chat_plus` | `true` | 允许把回复决策和生成委托给 Group Chat Plus |
| `group_chat_plus_plugin_name` | `astrbot_plugin_group_chat_plus` | Group Chat Plus 检测名 |
| `disable_local_reply_when_delegated` | `true` | 委托生效时禁用本地回复器 |

检测别名:

- LivingMemory: `LivingMemory`, `astrbot_plugin_livingmemory`
- Group Chat Plus: `astrbot_plugin_group_chat_plus`, `Group Chat Plus`, `ChatPlus`

委托只在目标插件已加载、激活且存在 `star_cls` 时生效。未检测到目标插件时，本插件自动回退到本地能力。

## 运行路径

### 记忆委托

```python
feature_delegation.should_delegate_memory()
```

调用点:

- `services/core_learning/v2_learning_integration.py`: 跳过本地 memory engine 写入和检索。
- `services/hooks/llm_hook_handler.py`: 跳过本地 V2 记忆上下文注入。
- `services/persona/persona_updater.py`: 跳过本地记忆图谱更新。

### 回复委托

```python
feature_delegation.should_delegate_reply()
```

调用点:

- `core/plugin_lifecycle.py`: 跳过本地 `IntelligentResponder` 创建和启动。

## Dashboard

入口:

```text
Dashboard -> 功能融合
```

页面内容:

- Self Learning 当前面板。
- LivingMemory 状态、外部面板入口和本地图谱适配 API 列表。
- Group Chat Plus 状态、面板入口和开发 API 列表。
- `Integration_Settings` 快速编辑。

## WebUI API

### `GET /api/integrations/status`

返回:

```json
{
  "delegation": {
    "memory_delegated": true,
    "memory_plugin": "LivingMemory",
    "reply_delegated": true,
    "reply_plugin": "Group Chat Plus"
  },
  "settings": {
    "delegate_memory_to_livingmemory": true,
    "livingmemory_plugin_name": "LivingMemory",
    "disable_local_memory_when_delegated": true,
    "delegate_reply_to_group_chat_plus": true,
    "group_chat_plus_plugin_name": "astrbot_plugin_group_chat_plus",
    "disable_local_reply_when_delegated": true
  },
  "dashboards": []
}
```

`dashboards[]` 字段:

| 字段 | 说明 |
| --- | --- |
| `id` | `self_learning`, `livingmemory`, `group_chat_plus` |
| `title` | 面板标题 |
| `role` | 插件职责 |
| `active` | 是否检测到插件 |
| `delegated` | 当前能力是否已委托 |
| `plugin` | AstrBot star 元信息 |
| `dashboard` | 面板 URL、本地图谱路由、入口类型 |
| `dev_api` | 该插件公开 API 列表 |
| `settings_group` | 相关配置组 |

## Companion API 列表

### Self Learning

- `GET /api/integrations/status`
- `GET /api/config/schema`
- `POST /api/config`
- `GET /api/metrics`
- `GET /api/graphs/memory`
- `GET /api/graphs/knowledge`
- `GET /api/persona_updates`
- `GET /api/jargon/list`
- `GET /api/style_learning/content_text`

### LivingMemory

Self Learning 不再调用 LivingMemory 的 Page 图谱 API。Dashboard 的
`#/graphs` 模块会在 LivingMemory 已加载时直读其
`initializer.memory_engine.graph_store` 后端对象，并通过本插件接口暴露
ECharts 图谱 payload。记忆图和知识图谱都会优先读取 LivingMemory 后端；
当后端不可用或快照为空时，仍保留 Self Learning 本地记忆、LightRAG 和
本地 KG 表回退:

- `GET /api/graphs/memory`
- `GET /api/graphs/knowledge`

### Group Chat Plus

- `POST /api/auth/login`
- `GET /api/auth/status`
- `GET /api/config`
- `PUT /api/config`
- `POST /api/config/reload`
- `GET /api/data/overview`
- `GET /api/data/status`
- `GET /api/session/list`
- `POST /api/session/clean-ghosts`
- `GET /api/security/access-log`

## 排查

| 现象 | 检查 |
| --- | --- |
| Dashboard 显示未委托 | 目标插件是否已加载、启用、名称是否匹配 |
| LivingMemory 已安装但仍写入本地记忆 | `delegate_memory_to_livingmemory` 和 `disable_local_memory_when_delegated` 是否为 `true` |
| Group Chat Plus 已安装但仍创建本地回复器 | `delegate_reply_to_group_chat_plus` 和 `disable_local_reply_when_delegated` 是否为 `true` |
| 面板入口为空 | 目标插件 Web 面板是否开启；图谱模块仍可通过本插件 `/api/graphs/*` 查看 |
| API 列表不匹配 | 以目标插件当前开发 API 为准，更新 `webui/services/integration_service.py` |

## 测试

```powershell
python -m pytest tests\unit\test_feature_delegation.py tests\unit\test_integration_service.py tests\integration\test_webui_static_assets.py
```
