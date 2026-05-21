# 配置

配置来源有两层:

1. AstrBot 插件配置: `_conf_schema.json`
2. 运行时 Pydantic 模型: `config.py::PluginConfig`

`PluginConfig.create_from_config()` 从 AstrBot 的分组配置读取字段，生成扁平化运行时对象。WebUI 设置页通过 `webui/services/config_service.py` 暴露完整 schema 和当前值。

## 基础学习设置

配置组: `Self_Learning_Basic`

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `enable_message_capture` | `true` | 是否采集用户消息 |
| `enable_auto_learning` | `true` | 是否定时自动学习 |
| `enable_realtime_learning` | `false` | 是否每条消息实时进入筛选学习 |
| `enable_realtime_llm_filter` | `false` | 实时学习时是否调用 LLM 筛选 |
| `enable_jargon_learning` | `true` | 是否启用黑话学习 |
| `enable_style_learning` | `true` | 是否启用风格学习 |
| `enable_web_interface` | `true` | 是否启动 WebUI |
| `web_interface_port` | `7833` | WebUI 端口 |
| `web_interface_host` | `0.0.0.0` | WebUI 监听地址 |

## 目标设置

配置组: `Target_Settings`

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `target_qq_list` | `[]` | 白名单。为空时学习所有用户 |
| `target_blacklist` | `[]` | 黑名单。支持用户或群组格式 |
| `current_persona_name` | `default` | 当前要优化的人格名称 |

## 模型配置

配置组: `Model_Configuration`

| 字段 | 说明 |
| --- | --- |
| `filter_provider_id` | 筛选模型 Provider ID |
| `refine_provider_id` | 提炼模型 Provider ID |
| `reinforce_provider_id` | 强化学习模型 Provider ID |

Provider 未配置不会阻止插件加载。`FrameworkLLMAdapter` 会延迟重试初始化，实际 LLM 相关功能在没有 Provider 时会降级或失败并写日志。

## 学习参数

配置组: `Learning_Parameters`

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `learning_interval_hours` | `6` | 同群组批量学习间隔 |
| `min_messages_for_learning` | `50` | 群组开始批量学习所需最小消息数 |
| `max_messages_per_batch` | `200` | 单次学习最多处理消息数 |

## 筛选参数

配置组: `Filter_Parameters`

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `message_min_length` | `5` | 参与学习的最小文本长度 |
| `message_max_length` | `500` | 参与学习的最大文本长度 |
| `confidence_threshold` | `0.7` | 筛选置信度阈值 |
| `relevance_threshold` | `0.6` | 相关性阈值，WebUI schema 额外补充 |

## 风格分析

配置组: `Style_Analysis`

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `style_analysis_batch_size` | `100` | 风格分析批次大小 |
| `style_update_threshold` | `0.8` | 风格更新质量阈值 |

注意: `PluginConfig` 类内字段默认值是 `0.6`，但 `create_from_config()` 从 AstrBot 配置读取时默认使用 `_conf_schema.json` 的 `0.8`。

## 高级设置

配置组: `Advanced_Settings`

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `debug_mode` | `false` | 启用性能监控；未指定日志等级时使用 debug |
| `log_level` | `info` | `error`, `warning`, `info`, `debug` |
| `save_raw_messages` | `true` | 保存原始消息 |
| `auto_backup_interval_days` | `7` | 自动备份间隔 |
| `auto_apply_approved_persona` | `false` | 批准后自动应用到默认人格，风险较高 |

日志等级会通过 `utils/logging_utils.py` 同步到 AstrBot logger。

## 数据库配置

配置组: `Database_Settings`

默认 `sqlite`，无需额外服务。MySQL 和 PostgreSQL 会尝试自动创建数据库和表。

PostgreSQL 支持 `postgresql_schema`，非 `public` 时会自动创建 schema 并设置 search path。

修改以下字段需要重启:

- `db_type`
- `mysql_*`
- `postgresql_*`
- `data_dir`

## 社交上下文

配置组: `Social_Context_Settings`

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `enable_social_context_injection` | `true` | 是否注入社交上下文 |
| `include_social_relations` | `true` | 注入社交关系 |
| `include_affection_info` | `true` | 注入好感度 |
| `include_mood_info` | `true` | 注入情绪信息 |
| `expression_patterns_hours` | `24` | 表达模式统计窗口 |
| `context_injection_position` | `start` | 社交上下文拼接位置 |

当前 LLM Hook 中 `include_mood=False`，情绪信息主要由其他上下文服务提供。

## 目标驱动对话

配置组: `Goal_Driven_Chat_Settings`

默认关闭。启用后会创建 `ConversationGoalManager`，消息流水线会为用户会话维护目标和阶段。

## V2 架构

配置组: `V2_Architecture_Settings`

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `embedding_provider_id` | `""` | Embedding Provider |
| `rerank_provider_id` | `""` | Reranker Provider |
| `rerank_top_k` | `5` | 重排序保留数量 |
| `rerank_min_candidates` | `3` | 候选数低于该值跳过 rerank |
| `knowledge_engine` | `legacy` | `legacy` 或 `lightrag` |
| `lightrag_query_mode` | `local` | LightRAG 查询模式 |
| `memory_engine` | `legacy` | `legacy` 或 `mem0` |

只有 `knowledge_engine != "legacy"` 或 `memory_engine != "legacy"` 时才创建 `V2LearningIntegration`。

## WebUI 全量设置

接口:

```http
GET /api/config/schema
POST /api/config
```

`ConfigService.get_config_schema()` 合并:

1. `_conf_schema.json`
2. `_EXTRA_SCHEMA_DEFINITION`
3. 当前 `PluginConfig`
4. Provider 下拉选项

字段会被标记:

- `widget`: `toggle`, `number`, `select`, `provider`, `textarea`, `readonly`
- `editable`
- `nullable`
- `restart_required`

`POST /api/config` 支持直接提交扁平字段，也支持包裹在 `config`, `new_config`, `settings`, `data` 下。

## 立即生效和重启生效

立即生效:

- 日志等级。
- 大多数学习开关。
- Provider 重新初始化。
- 阈值类配置。

需要重启:

- 数据目录。
- 数据库类型和连接参数。
- WebUI host/port。
- WebUI 开关。
- ORM 强制开关。

WebUI 更新配置后如果包含重启项，响应消息会提示部分变更重启后生效。
