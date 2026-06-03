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
- LivingMemory 状态、面板入口和开发 API 列表。
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
| `dashboard` | 面板 URL、AstrBot 页面 URL、入口类型 |
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

- `GET /astrbot_plugin_livingmemory/page/stats`
- `GET /astrbot_plugin_livingmemory/page/memories`
- `POST /astrbot_plugin_livingmemory/page/memories/update`
- `POST /astrbot_plugin_livingmemory/page/memories/batch-delete`
- `POST /astrbot_plugin_livingmemory/page/recall/test`
- `GET /astrbot_plugin_livingmemory/page/graph/overview`
- `POST /astrbot_plugin_livingmemory/page/graph/query`

AstrBot 页面入口:

```text
http://<astrbot-dashboard-host>:<astrbot-dashboard-port>/api/plugin/page/content/LivingMemory/dashboard/
```

Self Learning 的独立 WebUI 会把旧入口
`/api/plugin/page/content/astrbot_plugin_livingmemory/dashboard/`
重定向到 AstrBot Dashboard 的正式页面，避免在 `web_interface_port` 上返回 404。

注意: AstrBot 官方插件页路由使用插件运行名 `LivingMemory`，不是安装目录名 `astrbot_plugin_livingmemory`。LivingMemory 自己注册的 Page API 仍使用 `/astrbot_plugin_livingmemory/page/...` 前缀。AstrBot Plugin Page 带有同源 iframe 限制，所以 Self Learning 只把它作为新窗口入口；可嵌入 iframe 的优先入口仍是 LivingMemory 自己启用的独立 WebUI。

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
| 面板入口为空 | 目标插件 Web 面板是否开启，或是否只提供 AstrBot Pages 入口 |
| API 列表不匹配 | 以目标插件当前开发 API 为准，更新 `webui/services/integration_service.py` |

## 测试

```powershell
python -m pytest tests\unit\test_feature_delegation.py tests\unit\test_integration_service.py tests\integration\test_webui_static_assets.py
```
