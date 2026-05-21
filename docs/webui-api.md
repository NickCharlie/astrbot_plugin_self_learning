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
{"manual_confirmed": true, "source": "system_settings"}
```

可通过环境变量关闭:

```powershell
$env:ASTRBOT_ENABLE_WEB_DEP_INSTALL="false"
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
| GET | `/api/monitoring/profile/<session_id>` | 获取 profiling 会话 |
| DELETE | `/api/monitoring/profile/<session_id>` | 停止 profiling |

## 数据管理

蓝图: `webui/blueprints/data_management.py`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/data/statistics` | 数据表统计 |
| DELETE | `/api/data/clear/messages` | 清空消息 |
| DELETE | `/api/data/clear/persona_reviews` | 清空人格审查 |
| DELETE | `/api/data/clear/style_learning` | 清空风格学习 |
| DELETE | `/api/data/clear/jargon` | 清空黑话 |
| DELETE | `/api/data/clear/learning_history` | 清空学习历史 |
| DELETE | `/api/data/clear/all` | 清空全部插件数据 |

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
