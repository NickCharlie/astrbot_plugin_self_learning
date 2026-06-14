# WebUI API

WebUI 使用 Quart 蓝图，静态页面在 `web_res/static/html`，静态资源在 `web_res/static`。当前认证中间件直接放行，Dashboard 打开后免密访问。

## 应用创建

入口:

- `webui/manager.py`: 生命周期管理。
- `webui/server.py`: Hypercorn 守护线程。
- `webui/app.py`: Quart app factory。
- `webui/dependencies.py`: WebUI 服务容器。

根路径:

```http
GET /
```

重定向到:

```http
GET /api/
```

## Auth

蓝图: `webui/blueprints/auth.py`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/` | Dashboard 入口 |
| GET | `/api/login` | 登录页，当前免密 |
| POST | `/api/login` | 免密登录兼容接口 |
| GET | `/api/index` | Dashboard 页面 |
| GET | `/api/plugin_change_password` | 修改密码页兼容入口 |
| POST | `/api/plugin_change_password` | 当前返回无需修改密码 |
| POST | `/api/logout` | 登出兼容接口 |

认证实现:

- `webui/services/auth_service.py`
- `webui/middleware/auth.py`

当前 `require_auth` 不做拦截，`is_authenticated()` 恒为 `True`。

## 配置和依赖

蓝图: `webui/blueprints/config.py`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/config` | 获取当前扁平配置 |
| GET | `/api/config/schema` | 获取 Dashboard 全量设置 schema |
| POST | `/api/config` | 更新配置 |
| POST | `/api/dependencies/install` | 手动安装插件依赖 |

依赖安装必须由设置页手动确认:

```json
{"manual_confirmed": true, "source": "system_settings", "tier": "full"}
```

`tier`:

- `basic`: 基础能力依赖。
- `full`: 全能力依赖。

可通过环境变量关闭:

```powershell
$env:ASTRBOT_ENABLE_WEB_DEP_INSTALL="false"
```

## 功能融合

蓝图: `webui/blueprints/integrations.py`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/integrations/status` | 获取 Self Learning、LivingMemory、Group Chat Plus 的委托状态、面板入口和开发 API 列表 |

返回字段:

| 字段 | 说明 |
| --- | --- |
| `delegation.memory_delegated` | 长期记忆是否委托给 LivingMemory |
| `delegation.memory_plugin` | 检测到的 LivingMemory 名称 |
| `delegation.reply_delegated` | 回复是否委托给 Group Chat Plus |
| `delegation.reply_plugin` | 检测到的 Group Chat Plus 名称 |
| `settings` | 当前 `Integration_Settings` |
| `dashboards` | 三个插件的面板入口、运行状态和 API 列表 |

详见 [功能融合](integrations.md)。

## Self Learning Hub API

蓝图: `webui/blueprints/hub.py`

Hub API 是给其他 AstrBot 插件调用的稳定中枢接口。它把本插件的学习、上下文构建、显式记忆、审查、图谱和指标能力按 MVC 拆分为:

- Controller: `webui/blueprints/hub.py`
- Service: `webui/services/hub_service.py`
- AOP 横切层: `webui/middleware/hub_aspects.py`

所有 Hub 响应都使用稳定 envelope:

```json
{"success": true, "message": "ok", "data": {}}
```

错误响应:

```json
{
  "success": false,
  "message": "Unauthorized",
  "error": {"code": "unauthorized", "message": "Unauthorized"}
}
```

鉴权:

- 当 `API_Settings.enable_api_auth=false` 时放行，便于本地同源插件调用。
- 当 `API_Settings.enable_api_auth=true` 时，必须发送 `Authorization: Bearer <api_key>` 或 `X-Self-Learning-Key: <api_key>`。
- 动态响应统一带 `Cache-Control: no-store`，避免 CDN 或浏览器缓存敏感数据。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/hub/v1/manifest` | 获取版本、能力、鉴权方式、endpoint 列表和示例 payload |
| GET | `/api/hub/v1/status` | 获取运行健康、数据库降级状态、功能委托状态和可用能力 |
| POST | `/api/hub/v1/context` | 为伴随插件构建 prompt-ready 上下文 |
| POST | `/api/hub/v1/memories/remember` | 写入手动选择的记忆，并链入表达方式和对话示例 |
| POST | `/api/hub/v1/messages/ingest` | 将外部插件消息写入学习链路 |
| POST | `/api/hub/v1/learning/trigger` | 触发指定群组渐进式学习 |
| GET | `/api/hub/v1/reviews` | 获取待审队列 |
| POST | `/api/hub/v1/reviews/<review_id>/decision` | 审查通过或拒绝队列项 |
| GET | `/api/hub/v1/graphs/memory` | 获取记忆图谱 |
| GET | `/api/hub/v1/graphs/knowledge` | 获取知识图谱 |
| GET | `/api/hub/v1/metrics` | 获取智能、多样性、好感度指标 |

### 构建上下文

```http
POST /api/hub/v1/context
Authorization: Bearer <api_key>
Content-Type: application/json
```

```json
{
  "group_id": "group_123",
  "user_id": "user_456",
  "query": "最近这句话该怎么接？",
  "include": {
    "social": true,
    "jargon": true,
    "few_shots": true,
    "v2": true
  },
  "top_k": 5
}
```

返回 `data.context_text`、`data.parts[]`、`data.v2` 和 `data.few_shots`。社交上下文默认拼到调用方 prompt 的尾部更利于缓存命中。

### 显式记忆

```http
POST /api/hub/v1/memories/remember
```

```json
{
  "group_id": "group_123",
  "sender_id": "user_456",
  "content": "A: 这事怎么说？\nB: 可以这样接。"
}
```

该接口会复用 `RememberService`，把用户明确引用的片段写入手动记忆，同时尽量保存表达方式样本、few-shot exemplar 和风格审查记录。它适合其他插件实现“引用这段并学习”的交互。

### 消息接入

```http
POST /api/hub/v1/messages/ingest
```

```json
{
  "group_id": "group_123",
  "sender_id": "user_456",
  "sender_name": "Alice",
  "message": "今晚继续测试自学习。",
  "platform": "companion_plugin",
  "message_id": "optional",
  "reply_to": "optional",
  "process_v2": true
}
```

Hub 会优先复用插件运行态的 `message_collector`，否则回退到数据库 `save_raw_message`。`process_v2=true` 时还会把标准 `MessageData` 交给 V2 学习集成。

### 审查和学习

触发学习:

```json
{"group_id": "group_123", "wait": false}
```

审查决定:

```json
{"decision": "approve", "comment": "确认采用", "modified_content": null}
```

## 学习内容和风格审查

蓝图: `webui/blueprints/learning.py`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/style_learning/results` | 风格学习结果 |
| GET | `/api/style_learning/reviews` | 待审风格记录 |
| POST | `/api/style_learning/reviews/<review_id>/approve` | 批准风格学习 |
| POST | `/api/style_learning/reviews/<review_id>/reject` | 拒绝风格学习 |
| GET | `/api/style_learning/patterns` | 表达模式列表 |
| GET | `/api/style_learning/content_text` | 查看具体学习内容 |
| POST | `/api/relearn` | 触发重新学习 |

`content_text` 用于 Dashboard 查看原始消息、筛选消息、表达模式、风格审查、人格审查等具体学习材料。

## 人格管理和人格审查

蓝图:

- `webui/blueprints/personas.py`
- `webui/blueprints/persona_reviews.py`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/persona_management/list` | 人格列表 |
| GET | `/api/persona_management/get/<persona_id>` | 人格详情 |
| POST | `/api/persona_management/create` | 创建人格 |
| POST | `/api/persona_management/update/<persona_id>` | 更新人格 |
| POST | `/api/persona_management/delete/<persona_id>` | 删除人格 |
| GET | `/api/persona_management/default` | 默认人格 |
| GET | `/api/persona_management/export/<persona_id>` | 导出人格 |
| POST | `/api/persona_management/import` | 导入人格 |
| GET | `/api/persona_updates` | 待审人格更新 |
| POST | `/api/persona_updates/<update_id>/review` | 审查人格更新 |
| GET | `/api/persona_updates/reviewed` | 已审人格更新 |
| POST | `/api/persona_updates/<update_id>/revert` | 回滚人格更新 |
| POST | `/api/persona_updates/<update_id>/delete` | 删除人格更新 |
| POST | `/api/persona_updates/batch_delete` | 批量删除 |
| POST | `/api/persona_updates/batch_review` | 批量审查 |

人格审查服务会统一处理传统人格更新、渐进式人格学习和风格学习来源。

## 黑话

蓝图: `webui/blueprints/jargon.py`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/jargon/stats` | 黑话统计 |
| GET | `/api/jargon/list` | 黑话列表 |
| GET | `/api/jargon/search` | 搜索黑话 |
| DELETE | `/api/jargon/<jargon_id>` | 删除黑话 |
| POST | `/api/jargon/<jargon_id>/review` | 审查候选黑话 |
| POST | `/api/jargon/<jargon_id>/toggle_global` | 切换全局状态 |
| GET | `/api/jargon/groups` | 有黑话数据的群组 |
| POST | `/api/jargon/sync_to_group` | 同步全局黑话到群 |
| GET | `/api/jargon/global` | 全局黑话列表 |
| POST | `/api/jargon/<jargon_id>/set_global` | 设置全局状态 |

## 图谱

蓝图: `webui/blueprints/graphs.py`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/graphs/memory` | 记忆图数据 |
| GET | `/api/graphs/knowledge` | 知识图谱数据 |

返回是 ECharts 风格结构:

```json
{
  "nodes": [],
  "links": [],
  "categories": []
}
```

蓝图: `webui/blueprints/graph_share.py`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/graph/share/<token>` | 分享页 |
| GET | `/api/public/social_graph/<token>` | 公开社交图谱数据 |

## 社交关系

蓝图: `webui/blueprints/social.py`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/social_relations/<group_id>` | 群组社交关系 |
| GET | `/api/social_relations/groups` | 可分析群组 |
| POST | `/api/social_relations/<group_id>/analyze` | 触发分析 |
| DELETE | `/api/social_relations/<group_id>/clear` | 清空群组社交关系 |
| GET | `/api/social_relations/<group_id>/user/<user_id>` | 用户关系 |
| POST | `/api/social_relations/<group_id>/share` | 创建分享链接 |

## 聊天记录

蓝图: `webui/blueprints/chat.py`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/chat/history` | 聊天记录列表 |
| GET | `/api/chat/history/<message_id>` | 单条消息详情 |
| DELETE | `/api/chat/history/<message_id>` | 删除单条消息 |
| GET | `/api/chat/statistics` | 聊天统计 |

## 指标和监控

蓝图:

- `webui/blueprints/metrics.py`
- `webui/blueprints/monitoring.py`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/intelligence_metrics` | 智能指标 |
| GET | `/api/diversity_metrics` | 多样性指标 |
| GET | `/api/affection_metrics` | 好感度指标 |
| GET | `/api/metrics` | Dashboard 汇总指标 |
| GET | `/api/metrics/trends` | 指标趋势 |
| GET | `/api/analytics/trends` | 分析趋势 |
| GET | `/api/monitoring/metrics` | Prometheus 文本指标 |
| GET | `/api/monitoring/metrics/json` | JSON 指标 |
| GET | `/api/monitoring/health` | 健康检查 |
| GET | `/api/monitoring/functions` | 函数级性能 |
| GET | `/api/monitoring/profile/backends` | profiling 后端 |
| POST | `/api/monitoring/profile/start` | 开始 profiling |

`/api/metrics` 会直接返回 `cache_hit_rates` 和 `cache_hit_summary`，数据来自
`CacheManager.get_hit_rates()`，前端无需从 Prometheus hits/misses 样本自行测算缓存命中率。
| GET | `/api/monitoring/profile/<session_id>` | 获取 profiling 会话 |
| DELETE | `/api/monitoring/profile/<session_id>` | 停止 profiling |

## 数据管理

蓝图: `webui/blueprints/data_management.py`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/data/statistics` | 数据表统计 |
| DELETE | `/api/data/clear/messages` | 清空消息 |
| DELETE | `/api/data/clear/persona_reviews` | 清空人格审查与人格学习 |
| DELETE | `/api/data/clear/style_learning` | 清空风格学习 |
| DELETE | `/api/data/clear/jargon` | 清空黑话 |
| DELETE | `/api/data/clear/learning_history` | 清空学习历史 |
| DELETE | `/api/data/clear/all` | 清空全部插件数据，包含记忆、知识图谱、人格学习、表达方式学习、黑话和运行态学习画像 |

`/api/data/statistics` 会返回 `messages`、`persona_reviews`、`style_learning`、`jargon`、`learning_history`、`memory`、`knowledge_graph`、`runtime_state` 等分类计数。

## Bug 报告

蓝图: `webui/blueprints/bug_report.py`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/bug_report/config` | Bug 上报配置 |
| POST | `/api/bug_report` | 提交 Bug |
| GET | `/api/bug_report/history` | 上报历史 |

WebUI 上传大小由 `WebUIConfig.max_upload_size` 控制，默认 8 MB。

## 目标驱动对话

蓝图: `webui/blueprints/intelligent_chat.py`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/intelligent_chat/chat` | 目标驱动聊天 |
| GET | `/api/intelligent_chat/goal/status` | 当前目标状态 |
| DELETE | `/api/intelligent_chat/goal/clear` | 清除目标 |
| GET | `/api/intelligent_chat/goal/statistics` | 目标统计 |
| GET | `/api/intelligent_chat/goal/templates` | 目标模板 |
