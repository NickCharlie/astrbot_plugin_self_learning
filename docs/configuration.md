# 配置

配置来源有两层:

1. AstrBot 插件配置: `_conf_schema.json`
2. 运行时 Pydantic 模型: `config.py::PluginConfig`

`PluginConfig.create_from_config()` 从 AstrBot 的分组配置读取字段，生成扁平化运行时对象。WebUI 设置页通过 `webui/services/config_service.py` 暴露完整 schema 和当前值。

> 本章只展开常用配置组；**全部 143 个配置项**的权威参考见文末「[完整配置参考](#完整配置参考)」（由 `.github/scripts/gen_config_reference.py` 从 `_conf_schema.json` 生成，与插件配置页一致）。

## 基础学习设置

配置组: `Self_Learning_Basic`

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `enable_message_capture` | `true` | 是否采集用户消息 |
| `enable_auto_learning` | `true` | 是否定时自动学习 |
| `enable_realtime_learning` | `false` | 是否每条消息实时进入筛选学习 |
| `enable_realtime_llm_filter` | `false` | 实时学习时是否调用 LLM 筛选 |
| `enable_jargon_learning` | `true` | 是否启用黑话学习 |
| `jargon_websearch_enabled` | `true` | 黑话联网释义补充：低提及词条复用搜索密钥检索公开释义（4.2.3 起） |
| `jargon_websearch_provider` | `""` | 手动指定联网释义搜索厂商（tavily/bocha/exa/baidu）；留空跟随 AstrBot 全局配置。AstrBot 联网搜索走 MCP 等插件无法调用的方式时在此手动选择（4.7.4 起，issue #293） |
| `jargon_websearch_api_key` | `""` | 手动输入上方厂商的 API Key，优先于 AstrBot 全局搜索密钥（4.7.4 起） |
| `enable_style_learning` | `true` | 是否启用风格学习 |
| `enable_web_interface` | `true` | 是否启动独立 WebUI |
| `web_interface_port` | `7833` | 独立 WebUI 端口 |
| `web_interface_host` | `127.0.0.1` | 独立 WebUI 监听地址（默认仅本机；局域网访问改 `0.0.0.0` 并开启登录密码） |
| `enable_webui_password` | `false` | 独立 WebUI 登录密码开关（内嵌插件页走 AstrBot 自身登录，无需此开关） |
| `webui_initial_password` | `""` | 密码首次启用时的一次性初始密码 |

## 目标设置

配置组: `Target_Settings`

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `target_qq_list` | `[]` | 白名单。默认全量学习；为空、空行或 `all`/`*`/`全部`/`全量` 时学习所有非黑名单消息 |
| `target_blacklist` | `[]` | 黑名单。条目为用户 ID，或 `group_<群号>` 表示整群排除；入站采集与学习取数两层都生效（issue #284） |
| `current_persona_name` | `""` | 当前要优化的人格名称 |

## 模型配置

配置组: `Model_Configuration`

| 字段 | 说明 |
| --- | --- |
| `filter_provider_id` | 筛选模型 Provider ID |
| `refine_provider_id` | 提炼模型 Provider ID |
| `reinforce_provider_id` | 强化学习模型 Provider ID |

Provider 未配置不会阻止插件加载。`FrameworkLLMAdapter` 会延迟重试初始化，实际 LLM 相关功能在没有 Provider 时会降级或失败并写日志。

WebUI 会按 AstrBot Provider 类型过滤选项:

- `filter_provider_id`, `refine_provider_id`, `reinforce_provider_id`: `chat_completion`
- `embedding_provider_id`: `embedding`
- `rerank_provider_id`: `rerank`

如果下拉为空，先在 AstrBot Provider 管理里创建对应类型的 Provider。

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
| `save_raw_messages` | `true` | 保存原始消息；关闭后依赖 `raw_messages` 表的学习功能（渐进学习、黑话挖掘等）将没有新数据 |
| `auto_backup_interval_days` | `7` | 自动备份间隔 |
| `auto_apply_approved_persona` | `false` | 批准后自动应用到默认人格，风险较高 |

日志等级会通过 `utils/logging_utils.py` 同步到 AstrBot logger。

## 数据库配置

配置组: `Database_Settings`

默认 `postgresql`。插件启动时会连接 PostgreSQL 维护库 `postgres`，自动创建缺失的目标数据库、schema 和 ORM 表。

PostgreSQL 支持 `postgresql_schema`，非 `public` 时会自动创建 schema 并设置 search path。

如果部署环境没有 PostgreSQL 服务，可显式设置 `db_type=sqlite` 回退到本地文件数据库。MySQL 仍作为兼容后端保留。

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
| `context_injection_position` | `end` | 社交上下文拼接位置，默认尾部拼接以更好地保留 prompt cache 命中率 |

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
| `lightrag_enable_llm_cache` | `false` | LightRAG 缓存 LLM 响应（实体抽取与查询）。缓存文件无上限且拖慢冷加载，聊天场景重复率低，默认关闭；开启后可用 `/clean_rag_cache` 清理 |
| `memory_engine` | `legacy` | `legacy` 或 `mem0` |

成本提示: 当 `knowledge_engine="lightrag"` 且 `lightrag_query_mode` 为
`hybrid` 或 `mix` 时，如果同时允许 `delegate_memory_to_livingmemory`，
LivingMemory 已加载后会叠加 LightRAG 全局/混合检索与记忆检索，可能明显增加
LLM 调用和 token 消耗。优先建议使用 `local`/`naive`，或只保留一种记忆/检索策略。

`lightrag_enable_llm_cache` 关闭时（默认），插件会在启动与各群实例创建时自动
删除残留的 `kv_store_llm_response_cache.json`（纯缓存数据，不影响图谱/向量）；
也可随时用管理员命令 `/clean_rag_cache` 手动清理。若开启缓存导致该文件增长过
大引发冷加载变慢与 LLM Hook 超时，可关闭该开关后重启，或适当调大
`llm_hook_context_timeout` 作为缓解。

只有 `knowledge_engine != "legacy"` 或 `memory_engine != "legacy"` 时才创建 `V2LearningIntegration`。

`embedding_provider_id` 只显示 Embedding Provider，`rerank_provider_id` 只显示 Reranker Provider。聊天模型不会混入这两个下拉框。

## 功能融合

配置组: `Integration_Settings`

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `delegate_memory_to_livingmemory` | `true` | 检测到 LivingMemory 时，将长期记忆写入和注入交给 LivingMemory |
| `livingmemory_plugin_name` | `LivingMemory` | 用于匹配 LivingMemory 插件 |
| `disable_local_memory_when_delegated` | `true` | 委托生效时跳过本插件本地长期记忆能力 |
| `delegate_reply_to_group_chat_plus` | `true` | 委托开关开启时，将回复决策和生成交给 Group Chat Plus；关闭后可由已开启委托的 LivingHello 接管 |
| `group_chat_plus_plugin_name` | `astrbot_plugin_group_chat_plus` | 用于匹配 Group Chat Plus 插件 |
| `delegate_reply_to_livinghello` | `false` | 开启后，Group Chat Plus 委托未生效时由 LivingHello 接管接话判定 |
| `livinghello_plugin_name` | `LivingHello` | 用于匹配 LivingHello 插件 |
| `disable_local_reply_when_delegated` | `true` | 委托生效时跳过本插件本地回复器 |

委托只在目标插件已加载、激活且对应委托开关开启时生效。两个回复目标都开启时 Group Chat Plus 优先；只加载但未开启委托的插件不算已委托。目标插件缺失、禁用或尚未实例化时，本插件保留原有本地降级能力。

完整运行边界见 [功能融合](integrations.md)。

## 运行与内部

配置组: `Runtime_Internal_Settings`

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `llm_hook_injection_target` | `extra_user_content_parts` | LLM Hook 注入目标。推荐保持默认: 动态上下文追加到用户消息尾部并标记为临时内容，不改动 system_prompt，避免影响 provider 前缀缓存。`system_prompt`/`prompt` 仅作为旧版 AstrBot 回退 |
| `enable_llm_hooks` | `false` | LLM Hook 上下文注入总开关。开启后每次回复前并行拉取社交上下文、记忆、黑话、few-shot 和影子模式档案并注入请求 |
| `llm_hook_context_timeout` | `3.0` | LLM Hook 读取单个上下文源的超时秒数，超时的上下文源会被跳过并记录警告 |

`enable_llm_hooks` 是所有 LLM 注入能力（含影子模式）的前置开关，默认关闭以避免高频模型调用。在 WebUI 设置页修改后立即生效，无需重启。

该组其余字段（消息库路径、学习日志路径、内存清理、关停超时等）通常保持默认即可；`use_sqlalchemy` 当前固定为 `true` 且只读。

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

<!-- CONFIG-REFERENCE:START 由 .github/scripts/gen_config_reference.py 生成，请勿手改 -->

## 完整配置参考

以下 151 个配置项按 24 个配置组列出，内容与 AstrBot 插件配置页一致。

### 依赖安装

配置组：`Dependency_Install_Guide`

> 依赖不会在插件安装或启动时自动安装。请进入插件 WebUI Dashboard 的全量设置顶部，手动点击基础能力依赖或全能力依赖。

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `dependency_install_entry` | 长文本 | `打开 WebUI Dashboard -> 全量设置 -> 手动安装依赖，选择“基础能力依赖”或“全能力依赖”。` | **手动安装入口**：基础能力依赖：人格审查、黑话学习、表达方式学习与 WebUI 所需依赖。全能力依赖：在基础能力上增加图谱、监控、外部数据库、LightRAG 与 Mem0 等完整能力依赖。<br>（只读） |

### 基础学习设置

配置组：`Self_Learning_Basic`

> 控制插件的基本学习行为

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `enable_message_capture` | 布尔 | `true` | **启用消息抓取**：是否抓取用户消息用于学习。关闭后插件将停止收集新消息 |
| `enable_auto_learning` | 布尔 | `true` | **启用自动学习**：是否启用定时自动学习。关闭后需要手动触发学习 |
| `enable_realtime_learning` | 布尔 | `false` | **启用实时学习**：是否在收到消息时立即进行筛选处理。会增加实时负载 |
| `enable_jargon_learning` | 布尔 | `true` | **启用黑话学习**：是否启用黑话统计预筛、黑话挖掘和黑话上下文能力 |
| `jargon_websearch_enabled` | 布尔 | `true` | **黑话联网释义补充**：低提及词条无法从群聊上下文推断含义时，复用 AstrBot 联网搜索配置（provider_settings 中的搜索密钥）检索公开释义，交由筛选模型归纳后写回词条，防止释义空缺；未配置任何搜索密钥时自动不生效 |
| `jargon_websearch_provider` | 文本 | `""` | **黑话联网释义搜索厂商**：手动指定黑话联网释义使用的搜索厂商。AstrBot 侧联网搜索走 MCP 等插件无法直接调用的方式、或未配置搜索密钥时，可在此手动选择厂商并填入下方 API Key（issue #293）<br>可选：`""`（跟随 AstrBot 配置） / `tavily`（Tavily） / `bocha`（博查） / `exa`（Exa） / `baidu`（百度千帆） |
| `jargon_websearch_api_key` | 文本 | `""` | **黑话联网释义搜索 API Key**：手动输入上方所选厂商的 API Key，优先于 AstrBot 全局搜索密钥；留空则复用 AstrBot 联网搜索配置。仅在搜索厂商有效时使用 |
| `enable_style_learning` | 布尔 | `true` | **启用对话风格学习**：是否启用自动风格学习、表达模式和相关学习批次处理 |
| `enable_realtime_llm_filter` | 布尔 | `false` | **启用实时LLM筛选**：是否对每条实时消息都使用LLM进行筛选。关闭可减少LLM调用频率 |
| `enable_web_interface` | 布尔 | `true` | **启用Web管理界面**：是否启用Web界面用于查看和管理学习数据 |
| `enable_webui_password` | 布尔 | `false` | **启用WebUI登录密码**：默认关闭，WebUI 免密访问；开启后访问 WebUI 需要登录密码。首次开启前请填写下方一次性初始密码，或设置环境变量 ASTRBOT_WEBUI_INITIAL_PASSWORD |
| `webui_initial_password` | 文本 | `""` | **WebUI一次性初始密码**：仅在首次启用 WebUI 登录密码且尚未生成 password.json 时使用。保存后会写入哈希密码并清空，不会回显明文<br>（敏感信息，界面中隐藏显示） |
| `web_interface_port` | 整数 | `7833` | **Web界面端口**：Web管理界面的访问端口号 |
| `web_interface_host` | 文本 | `127.0.0.1` | **Web界面监听地址**：Web管理界面绑定的地址。0.0.0.0 表示监听所有网卡（局域网可访问），127.0.0.1 表示仅本机可访问。局域网访问时必须开启登录密码，免密模式下局域网请求会被拒绝 |

### 抓取目标设置

配置组：`Target_Settings`

> 配置要学习哪些用户的消息

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `target_qq_list` | 列表 | `[]` | **目标QQ号列表**：默认全量学习：留空、空行或填写 all/*/全部/全量 时学习所有非黑名单消息。也可填写个人QQ号或群聊格式 group_群号 作为白名单。 |
| `target_blacklist` | 列表 | `[]` | **学习黑名单**：黑名单内的成员消息不进行学习。为空则没有黑名单。支持个人QQ号和群聊格式group_群号 |
| `current_persona_name` | 文本 | `""` | **当前目标人格**：插件将学习并优化此人格的对话风格。留空或填 default 表示跟随 AstrBot 当前人格；填写具体 ID 时需在人格设置中存在 |

### 模型配置

配置组：`Model_Configuration`

> 配置用于筛选和提炼的AI模型提供商

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `filter_provider_id` | 文本 | `null` | **筛选模型提供商**：用于消息筛选的提供商，建议选择速度快、成本低的模型如gpt-4o-mini |
| `refine_provider_id` | 文本 | `null` | **提炼模型提供商**：用于深度分析和提炼对话风格的提供商，建议选择能力强的模型如gpt-4o |
| `reinforce_provider_id` | 文本 | `null` | **强化模型提供商**：用于强化学习的提供商，建议选择能力强的模型 |

### 学习参数

配置组：`Learning_Parameters`

> 控制学习过程的各种参数

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `learning_interval_hours` | 整数 | `6` | **学习间隔(小时)**：自动学习的时间间隔，单位为小时 |
| `enable_learning_sweep` | 布尔 | `false` | **启用周期学习巡检**：默认关闭。开启后，插件在启动时启动学习调度器：每 learning_interval_hours 小时巡检活跃群组并触发自动学习；每群仍受学习间隔和最少消息数量限制。开关变更需重启插件生效。 |
| `min_messages_for_learning` | 整数 | `50` | **最少学习消息数量**：开始学习所需的最少消息数量 |
| `max_messages_per_batch` | 整数 | `200` | **每批处理的最大消息数量**：单次学习处理的最大消息数量，避免一次处理过多消息 |
| `expression_learning_trigger_messages` | 整数 | `10` | **表达方式学习触发消息数**：每个群每新增多少条原始消息才触发表达方式学习。调大可降低筛选/分析模型调用频率 |
| `expression_learning_min_interval_seconds` | 整数 | `3600` | **表达方式学习最小间隔(秒)**：同一群两次表达方式学习之间的最小间隔。默认3600秒，避免实时模式下频繁生成审查/人格更新 |
| `topic_detection_interval_messages` | 整数 | `10` | **话题检测触发消息数**：每个群每新增多少条消息才进行一次LLM话题检测。调大可降低筛选模型调用频率 |
| `topic_detection_min_interval_seconds` | 整数 | `300` | **话题检测最小间隔(秒)**：同一群两次LLM话题检测之间的最小间隔。默认300秒，避免活跃群在消息增量很快满足时高频调用筛选模型，0为禁用 |

### 筛选参数

配置组：`Filter_Parameters`

> 控制消息筛选的参数

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `message_min_length` | 整数 | `5` | **消息最小长度**：参与学习的消息最小字符长度 |
| `message_max_length` | 整数 | `500` | **消息最大长度**：参与学习的消息最大字符长度 |
| `confidence_threshold` | 小数 | `0.7` | **筛选置信度阈值**：消息筛选的置信度阈值，0-1之间，越高越严格 |

### 风格分析参数

配置组：`Style_Analysis`

> 控制对话风格分析的参数

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `style_analysis_batch_size` | 整数 | `100` | **风格分析批次大小**：单次风格分析处理的消息数量 |
| `style_update_threshold` | 小数 | `0.8` | **风格更新阈值**：触发人格风格更新的置信度阈值，0-1之间 |

### 高级设置

配置组：`Advanced_Settings`

> 高级用户配置选项

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `debug_mode` | 布尔 | `false` | **调试模式**：启用函数级性能指标采集，并在未指定日志等级时自动使用 debug |
| `log_level` | 文本 | `info` | **AstrBot日志等级**：控制插件在 AstrBot 日志中的详细程度。error 最少，trace 会输出函数级进入/退出和耗时日志<br>可选：`error` / `warning` / `info` / `debug` / `trace` |
| `save_raw_messages` | 布尔 | `true` | **保存原始消息**：是否保存未经处理的原始消息。关闭后 raw_messages 表不再写入，渐进学习、黑话挖掘、社交分析等依赖该表的学习功能将没有新数据 |
| `auto_backup_interval_days` | 整数 | `7` | **自动备份间隔(天)**：学习数据自动备份的间隔天数，0为禁用 |
| `auto_apply_approved_persona` | 布尔 | `false` | **⚠️ 审查批准后自动应用到默认人格**：【危险功能 - 谨慎开启】批准人格审查后自动将内容直接应用到当前使用的默认人格，而非创建新人格副本。开启后将直接覆盖正在使用的默认人格的系统提示词，此操作不可逆（除非从备份恢复）。强烈建议同时开启人格自动备份功能以防止数据丢失 |

### 机器学习设置

配置组：`Machine_Learning_Settings`

> 轻量级机器学习分析配置

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `enable_ml_analysis` | 布尔 | `true` | **启用ML分析**：是否启用scikit-learn进行文本聚类和行为分析 |
| `max_ml_sample_size` | 整数 | `100` | **ML样本最大数量**：机器学习分析的最大样本数量，控制资源使用 |
| `ml_cache_timeout_hours` | 整数 | `1` | **ML缓存超时(小时)**：机器学习分析结果的缓存时间 |

### 人格备份设置

配置组：`Persona_Backup_Settings`

> 人格数据备份和恢复配置

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `auto_backup_enabled` | 布尔 | `true` | **启用自动备份**：是否在人格更新前自动创建备份 |
| `backup_interval_hours` | 整数 | `24` | **备份间隔(小时)**：自动备份的时间间隔 |
| `max_backups_per_group` | 整数 | `10` | **每群最大备份数**：每个群保留的最大备份数量 |

### 目标驱动对话系统设置

配置组：`Goal_Driven_Chat_Settings`

> 智能对话目标管理系统，支持动态目标检测和阶段规划

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `enable_goal_driven_chat` | 布尔 | `false` | **启用目标驱动对话**：是否启用智能对话目标系统。启用后会自动检测对话目标并动态调整回复策略 |
| `goal_session_timeout_hours` | 整数 | `24` | **会话超时时间(小时)**：对话目标会话的超时时间，超过该时间未活跃的会话将被自动清理 |
| `goal_auto_detect` | 布尔 | `true` | **自动检测对话目标**：是否自动使用LLM分析用户消息检测对话目标类型。关闭后使用默认的闲聊模式 |
| `goal_max_conversation_history` | 整数 | `40` | **最大对话历史记录数**：保留在会话中的最大对话轮次（用户消息+Bot回复=1轮）。建议20-40轮 |

### 好感度系统设置

配置组：`Affection_System_Settings`

> 用户好感度和bot情绪管理配置

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `enable_affection_system` | 布尔 | `true` | **启用好感度系统**：是否启用用户好感度和情绪响应系统 |
| `max_total_affection` | 整数 | `250` | **总好感度上限**：bot对所有用户的总好感度上限值 |
| `max_user_affection` | 整数 | `100` | **单用户好感度上限**：单个用户可获得的最大好感度 |
| `affection_decay_rate` | 小数 | `0.95` | **好感度衰减比例**：好感度重新分配时的衰减比例，0-1之间 |
| `daily_mood_change` | 布尔 | `true` | **启用每日情绪变化**：是否每天随机更换bot的情绪状态 |
| `mood_affect_affection` | 布尔 | `true` | **情绪影响好感度变化**：当前情绪是否影响好感度变化幅度 |
| `affection_scope` | 文本 | `per_group` | **好感度存储维度**：per_group：每个群各存一份，同一个群里的表现不同；per_user：所有会话共用一份，私聊和群里看到的是同一个好感度。切换后历史数据不会自动合并。<br>可选：`per_group`（按群分开） / `per_user`（按 QQ 号统一） |

### 情绪系统设置

配置组：`Mood_System_Settings`

> bot情绪状态管理配置

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `enable_daily_mood` | 布尔 | `true` | **启用每日情绪**：是否启用每日随机情绪系统 |
| `enable_startup_random_mood` | 布尔 | `true` | **启用启动时随机情绪**：插件启动时是否为活跃群组设置随机初始情绪 |
| `mood_change_hour` | 整数 | `6` | **情绪更新时间**：每日更新情绪的小时(0-23) |
| `mood_persistence_hours` | 整数 | `24` | **情绪持续时间**：每次情绪状态持续的小时数 |
| `mood_half_life_minutes` | 小数 | `0` | **情绪强度半衰期（分钟）**：大于 0 时，情绪强度按半衰期自然衰减（例如 12 表示每 12 分钟减半）。0 表示保持原来的行为：整个持续时间内强度不变。 |
| `mood_fade_threshold` | 小数 | `0` | **情绪消退阈值**：大于 0 时，衰减后的强度低于该值就认为情绪已经过去，不再注入提示词。建议配合半衰期使用，例如 0.15。0 表示只按时长过期。 |
| `mood_max_concurrent` | 整数 | `1` | **并存情绪条数**：1 表示保持原行为：新情绪直接顶掉旧情绪。设为 2 时，旧情绪会留一条作为底色，用来表达「赌气 + 黏人」这类复合状态。 |
| `mood_startup_respect_existing` | 布尔 | `false` | **启动时保留未过期的情绪**：开启后，插件启动时若该群还有未过期、但强度已经淡到阈值以下的情绪，会继续沿用（不再注入提示词），而不是马上换一个随机情绪。适合配合情绪半衰期使用。 |

### 情绪与学习联动设置

配置组：`Emotion_Learning_Settings`

> 情绪/好感度加权闸门与三阶段遗忘，保持表达的新鲜性和得体性

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `enable_emotion_learning_gate` | 布尔 | `true` | **启用情绪学习闸门**：按好感度(35%)、消息情感(25%)、Bot心情(20%)、用户情绪稳定性(20%)加权打分，低于阈值时跳过该条消息的表达/黑话学习（原始消息采集不受影响） |
| `emotion_gate_threshold` | 小数 | `0.3` | **学习放行阈值**：0.05~0.95，加权分低于该值跳过本次学习。调低更宽松、调高更严格，默认 0.3 只拦截明显负面的组合 |
| `enable_expression_forgetting` | 布尔 | `true` | **启用三阶段遗忘**：按周期清理长期未使用/被反感的表达与黑话：连续三个周期无使用或正向反馈即删除；使用或正向反馈会立即重置 |
| `forgetting_cycle_days` | 整数 | `7` | **遗忘周期**：每多少天执行一次遗忘检查并推进阶段（1-90） |
| `forgetting_grace_days` | 整数 | `14` | **新条目宽限期**：新建的表达/黑话在多少天内不参与遗忘（1-365） |
| `forgetting_protect_global_jargon` | 布尔 | `true` | **全局黑话不遗忘**：全局共享黑话视为公共资产，不参与三阶段遗忘 |
| `forgetting_negative_fast_track` | 布尔 | `true` | **反感快速遗忘**：生成结果收到负反馈或手动标记反感时，直接进入遗忘二期，再有一个空周期即删除 |

### 社交上下文注入设置

配置组：`Social_Context_Settings`

> 控制向LLM prompt注入社交关系、好感度和情绪信息

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `enable_social_context_injection` | 布尔 | `true` | **启用社交上下文注入**：是否向LLM prompt中注入用户社交关系、好感度和情绪信息 |
| `include_social_relations` | 布尔 | `true` | **注入用户社交关系**：是否在prompt中包含用户的社交关系网络信息 |
| `include_affection_info` | 布尔 | `true` | **注入好感度信息**：是否在prompt中包含对该用户的好感度信息 |
| `include_mood_info` | 布尔 | `true` | **注入Bot情绪信息**：是否在prompt中包含Bot当前的情绪状态信息 |
| `expression_patterns_hours` | 整数 | `24` | **风格特征提取时间范围(小时)**：从多少小时内提取学到的表达风格特征注入到prompt中，默认24小时，可设置为7*24=168小时(一周) |
| `context_injection_position` | 文本 | `end` | **上下文注入位置**：社交上下文注入到prompt的位置，可选值：start(开头)、end(结尾)。默认 end 可减少动态上下文破坏 provider prompt/prefix cache 的概率 |

### 存储路径设置

配置组：`Storage_Settings`

> 自定义插件数据存储位置

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `data_dir` | 文本 | `./data/plugin_data/astrbot_plugin_self_learning` | **数据存储目录**：插件数据存储的根目录路径。默认位于 AstrBot 数据目录的 plugin_data/astrbot_plugin_self_learning 下；可以改为绝对路径 |

### 数据库配置

配置组：`Database_Settings`

> 配置数据库类型和连接参数。默认使用 PostgreSQL；插件会尝试自动创建 PostgreSQL 数据库、schema 和 ORM 表。SQLite 和 MySQL 可作为显式配置的兼容后端。

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `db_type` | 文本 | `postgresql` | **数据库类型**：填写 postgresql、pgsql、sqlite 或 mysql。默认使用 PostgreSQL，启动时会先建库和 schema，再同步 ORM 表；单机无 PostgreSQL 服务时可显式改为 sqlite |
| `mysql_host` | 文本 | `localhost` | **MySQL服务器地址**：MySQL服务器的IP地址或域名，如：localhost 或 192.168.1.100（仅当db_type为mysql时需要填写） |
| `mysql_port` | 整数 | `3306` | **MySQL端口**：MySQL服务器的端口号，通常为3306（仅当db_type为mysql时需要填写） |
| `mysql_user` | 文本 | `root` | **MySQL用户名**：MySQL数据库的用户名，如：root 或 astrbot（仅当db_type为mysql时需要填写） |
| `mysql_password` | 文本 | `""` | **MySQL密码**：MySQL数据库的密码（仅当db_type为mysql时需要填写）<br>（敏感信息，界面中隐藏显示） |
| `mysql_database` | 文本 | `astrbot_self_learning` | **MySQL数据库名**：MySQL数据库名称。使用MySQL 自动创建数据库以及数据库表 |
| `postgresql_host` | 文本 | `localhost` | **PostgreSQL服务器地址**：PostgreSQL服务器的IP地址或域名（仅当db_type为postgresql时需要填写） |
| `postgresql_port` | 整数 | `5432` | **PostgreSQL端口**：PostgreSQL服务器的端口号，通常为5432（仅当db_type为postgresql时需要填写） |
| `postgresql_user` | 文本 | `postgres` | **PostgreSQL用户名**：PostgreSQL数据库的用户名，如：postgres 或 astrbot（仅当db_type为postgresql时需要填写） |
| `postgresql_password` | 文本 | `""` | **PostgreSQL密码**：PostgreSQL数据库的密码（仅当db_type为postgresql时需要填写）<br>（敏感信息，界面中隐藏显示） |
| `postgresql_database` | 文本 | `astrbot_self_learning` | **PostgreSQL数据库名**：PostgreSQL数据库名称。插件会尝试自动创建数据库以及数据库表 |
| `postgresql_schema` | 文本 | `public` | **PostgreSQL Schema**：PostgreSQL schema 名称。默认 public；填写其他名称时插件会自动创建并使用该 schema |
| `max_connections` | 整数 | `10` | **最大连接数**：数据库连接池的最大连接数，高并发场景可适当增加 |
| `min_connections` | 整数 | `2` | **最小连接数**：数据库连接池的最小连接数，保持一定预热连接提高性能 |

### 外部API设置

配置组：`API_Settings`

> 外部API接口的安全配置

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `api_key` | 文本 | `""` | **API访问密钥**：外部API接口的访问密钥。留空则不需要密钥认证。建议设置一个强密码保护API安全<br>（敏感信息，界面中隐藏显示） |
| `enable_api_auth` | 布尔 | `false` | **启用API认证**：是否启用API密钥认证。关闭后任何人都可以访问外部API接口 |

### 数据访问层配置

配置组：`Repository_Settings`

> 配置SQLAlchemy Repository数据访问的默认参数和限制

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `default_review_limit` | 整数 | `50` | **默认审查记录查询数量**：获取待审查的人格学习/风格学习记录时的默认数量限制 |
| `default_pattern_limit` | 整数 | `10` | **默认表达模式查询数量**：获取表达模式时的默认数量限制 |
| `default_memory_limit` | 整数 | `50` | **默认记忆查询数量**：获取记忆记录时的默认数量限制 |
| `default_affection_limit` | 整数 | `50` | **默认好感度记录查询数量**：获取好感度交互记录时的默认数量限制 |
| `default_social_limit` | 整数 | `50` | **默认社交记录查询数量**：获取社交关系记录时的默认数量限制 |
| `default_psychological_limit` | 整数 | `20` | **默认心理状态记录查询数量**：获取心理状态记录时的默认数量限制 |
| `max_interaction_batch_size` | 整数 | `100` | **最大交互批处理数量**：批量处理交互记录时的最大数量限制，避免单次处理过多数据 |
| `top_patterns_limit` | 整数 | `10` | **顶级模式查询数量**：获取权重最高的表达模式时的默认数量限制 |
| `recent_interactions_limit` | 整数 | `20` | **近期交互查询数量**：获取近期交互记录时的默认数量限制 |
| `trend_analysis_days` | 整数 | `7` | **趋势分析天数**：进行趋势分析时默认查询的天数范围 |

### 功能融合

配置组：`Integration_Settings`

> 与专门插件协同：记忆交给 LivingMemory；回复决策和生成可交给 Group Chat Plus，也可把回复决策交给 LivingHello。本插件保留学习、审查、黑话、表达方式和上下文注入能力。若同时使用 LightRAG hybrid/mix 查询与 LivingMemory 委托，可能显著增加 LLM 调用与 token 消耗。

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `delegate_memory_to_livingmemory` | 布尔 | `true` | **记忆委托给 LivingMemory**：开启后，检测到 LivingMemory 插件已加载时，本插件不再写入或注入本地长期记忆，避免双重记忆系统互相污染。若 V2 知识引擎使用 LightRAG 且查询模式为 hybrid/mix，建议评估调用量与 token 成本。 |
| `livingmemory_plugin_name` | 文本 | `LivingMemory` | **LivingMemory 插件名**：用于检测 LivingMemory 插件是否已加载。通常保持默认值即可。 |
| `disable_local_memory_when_delegated` | 布尔 | `true` | **委托时禁用本地记忆**：开启后，只有检测到 LivingMemory 时才禁用本插件本地长期记忆；LivingMemory 未加载时自动保留本地降级能力。 |
| `delegate_reply_to_group_chat_plus` | 布尔 | `true` | **回复交给 Group Chat Plus**：开启后，检测到 Group Chat Plus 插件已加载时，本插件不再接管回复决策和回复生成，只负责学习上下文增强。关闭后，若 LivingHello 已加载并开启委托，则由 LivingHello 接管回复决策。 |
| `group_chat_plus_plugin_name` | 文本 | `astrbot_plugin_group_chat_plus` | **Group Chat Plus 插件名**：用于检测 Group Chat Plus 插件是否已加载。通常保持默认值即可。 |
| `disable_local_reply_when_delegated` | 布尔 | `true` | **委托时禁用本地回复**：开启后，只有检测到 Group Chat Plus 或已开启委托的 LivingHello 时才禁用本插件本地回复器；目标插件未加载或委托未开启时保留兼容降级。 |
| `delegate_reply_to_livinghello` | 布尔 | `false` | **回复决策交给 LivingHello**：开启后，检测到 LivingHello 插件已加载且 Group Chat Plus 委托未生效时，本插件不再接管回复决策，由 LivingHello 判断是否接话。默认关闭，避免升级后静默改变现有行为。Group Chat Plus 已加载且其委托开关开启时优先。 |
| `livinghello_plugin_name` | 文本 | `LivingHello` | **LivingHello 插件名**：用于检测 LivingHello 插件是否已加载。通常保持默认值即可。 |

### MaiBot 增强

配置组：`MaiBot_Enhancement`

> 启用表达模式、记忆图和知识图谱等扩展能力

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `enable_maibot_features` | 布尔 | `true` | **启用 MaiBot 增强功能**：开启后会启用 MaiBot 风格的扩展功能总开关 |
| `enable_expression_patterns` | 布尔 | `true` | **启用表达模式学习**：学习并维护群聊中的表达模式和常见句式 |
| `enable_expression_user_scope` | 布尔 | `false` | **表达模式按用户个性化**：开启后表达模式会按 sender_id 建立可选 user_id 维度；默认关闭以保持旧的群组/人格级学习与缓存行为 |
| `enable_expression_pair_llm_verify` | 布尔 | `false` | **表达样本 LLM 语义校验**：默认关闭。开启后，规则抽出的相邻对话对在保存前最多取 10 条交给筛选模型，判断「回应是否真的在回应情境」；只保留确认的样本。筛选模型不可用、调用失败或返回无法解析时保留原候选，不会静默丢弃。会增加筛选模型调用。 |
| `enable_realtime_expression_learning` | 布尔 | `false` | **实时表达方式学习**：实时学习关闭时，是否仍按消息增量触发表达方式学习。默认关闭以避免旁听群聊时产生高频 LLM 调用和审查记录 |
| `enable_memory_graph` | 布尔 | `true` | **启用记忆图系统**：开启记忆关系图与关联记忆能力 |
| `enable_knowledge_graph` | 布尔 | `true` | **启用知识图谱**：开启知识关系图谱与实体关联增强 |
| `enable_time_decay` | 布尔 | `true` | **启用时间衰减**：让旧数据随时间自动弱化权重 |

### 人格演化

配置组：`Persona_Evolution_Settings`

> 控制人格合并、自动应用和更新备份

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `persona_merge_strategy` | 文本 | `smart` | **人格合并策略**：控制人格更新时的合并方式<br>可选：`replace`（替换） / `append`（追加） / `prepend`（前置） / `smart`（智能） |
| `max_mood_imitation_dialogs` | 整数 | `20` | **最大对话风格模仿数量**：单次模仿训练最多处理的对话轮数 |
| `enable_persona_evolution` | 布尔 | `true` | **启用人格演化跟踪**：开启后会记录人格变化轨迹并参与后续更新 |
| `persona_compatibility_threshold` | 小数 | `0.6` | **人格兼容性阈值**：用于判断更新内容是否与当前人格兼容 |
| `use_persona_manager_updates` | 布尔 | `true` | **使用 PersonaManager 更新**：开启后优先通过 PersonaManager 进行人格更新 |
| `auto_apply_persona_updates` | 布尔 | `true` | **自动应用人格更新**：仅在 PersonaManager 更新模式下生效 |
| `persona_update_backup_enabled` | 布尔 | `true` | **启用人格更新备份**：更新前自动创建备份，降低误操作风险 |

### 运行与内部

配置组：`Runtime_Internal_Settings`

> 运行时注入、内存清理和内部路径

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `llm_hook_injection_target` | 文本 | `extra_user_content_parts` | **LLM Hook 注入目标**：推荐保持 extra_user_content_parts：动态上下文会追加到用户消息尾部并标记为临时内容，避免改动 system_prompt 影响 provider prefix cache。system_prompt/prompt 仅作为旧版 AstrBot fallback<br>可选：`extra_user_content_parts`（extra_user_content_parts（推荐）） / `system_prompt`（system_prompt（旧版 fallback）） / `prompt`（prompt（旧版 fallback）） |
| `enable_llm_hooks` | 布尔 | `false` | **启用 LLM Hook 上下文注入**：开启后每次回复前会并行拉取社交、记忆、黑话、few-shot 等上下文；默认关闭以避免高频模型调用 |
| `enable_command_pass_through` | 布尔 | `true` | **命令消息直接放行**：开启后，以系统级命令前缀（/ ! # . 等）开头的命令消息会跳过 LLM Hook 上下文注入直接处理，避免功能命令响应被拉长 |
| `use_sqlalchemy` | 布尔 | `true` | **强制使用 SQLAlchemy ORM**：当前版本固定为 true，用于统一 SQLite / MySQL / PostgreSQL 表结构<br>（只读） |
| `enable_memory_cleanup` | 布尔 | `true` | **启用记忆自动清理**：开启后会定期清理过旧或低重要度的记忆数据 |
| `memory_cleanup_days` | 整数 | `30` | **记忆保留天数**：低于该天数阈值的旧记忆会被清理 |
| `memory_importance_threshold` | 小数 | `0.3` | **记忆重要性阈值**：0-1 浮点，低于该值的旧记忆会被清理；记忆按 0-10 整数存储，内部会换算（如 0.3 → 低于 3 的旧记忆被清理） |
| `shutdown_step_timeout` | 整数 | `8` | **关停步骤超时**：每个关停步骤的最大等待时间（秒） |
| `task_cancel_timeout` | 整数 | `3` | **任务取消超时**：后台任务取消时的等待超时（秒） |
| `service_stop_timeout` | 整数 | `5` | **服务停止超时**：单个服务停止时的等待超时（秒） |
| `llm_hook_context_timeout` | 小数 | `3.0` | **LLM Hook 上下文超时**：LLM Hook 读取单个上下文源的最大等待时间（秒） |
| `messages_db_path` | 文本 | `null` | **消息数据库路径**：自动生成的消息数据库路径，通常无需修改<br>（只读） |
| `learning_log_path` | 文本 | `null` | **学习日志路径**：自动生成的学习日志路径，通常无需修改<br>（只读） |
| `total_messages_collected` | 整数 | `0` | **累计消息数**：当前运行周期内累计收集到的消息数量<br>（只读） |

### v2架构升级配置

配置组：`V2_Architecture_Settings`

> 高级功能配置：Embedding向量化、Reranker重排序、知识引擎和记忆引擎。需要先在AstrBot中配置对应类型的Provider

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `embedding_provider_id` | 文本 | `""` | **Embedding 提供商 ID**：填写Embedding提供商的完整ID（如 'openai/text-embedding-3-large'）。需要先在AstrBot的Provider管理中创建Embedding类型的提供商，然后将其ID填写到此处。格式通常为 '来源名/模型名' |
| `rerank_provider_id` | 文本 | `""` | **Reranker 提供商 ID**：填写Reranker提供商的完整ID（如 'openai/qwen3-rerank'）。需要先在AstrBot的Provider管理中创建Reranker类型的提供商，然后将其ID填写到此处。格式通常为 '来源名/模型名' |
| `rerank_top_k` | 整数 | `5` | **重排序保留结果数**：Reranker重排序后保留的Top-K结果数量，值越小越精准但可能遗漏 |
| `rerank_min_candidates` | 整数 | `3` | **触发重排序的最低候选文档数**：当知识+记忆候选文档数量低于此阈值时，跳过Reranker以节省延迟。设为0则始终执行重排序 |
| `provider_retry_interval_seconds` | 小数 | `10.0` | **Provider 重试间隔(秒)**：AstrBot 冷启动时 Provider 注册表可能尚未就绪。插件会按此间隔重试绑定 Embedding/Reranker Provider。 |
| `enable_realtime_v2_processing` | 布尔 | `false` | **启用 V2 实时逐消息处理**：实时学习关闭时，是否仍按每条消息触发 V2 分层处理。V2 会按短冷却批量触发 LightRAG/Mem0/黑话推理等高成本模型调用；默认关闭以遵守实时学习开关和学习间隔。 |
| `knowledge_engine` | 文本 | `legacy` | **知识引擎**：知识存储引擎类型。legacy=现有NetworkX实现，lightrag=使用LightRAG进行向量+图谱混合检索（需配置Embedding提供商） |
| `lightrag_query_mode` | 文本 | `local` | **LightRAG 查询模式**：LightRAG检索模式。local=仅实体邻域检索（低延迟），hybrid=实体邻域+全局社区聚合（高质量但慢约4-5秒），naive=纯向量检索，global=仅全局社区，mix=混合模式。若同时委托 LivingMemory，hybrid/mix 会叠加记忆检索与融合上下文，可能显著增加 LLM 调用与 token 消耗，优先建议 local/naive。 |
| `lightrag_enable_llm_cache` | 布尔 | `false` | **LightRAG 缓存 LLM 响应**：开启后 LightRAG 会缓存实体抽取与查询的 LLM 响应（kv_store_llm_response_cache.json）。该文件无上限且会拖慢冷加载；自然语言聊天查询重复率低，默认关闭。开启后可在群内用 /clean_rag_cache 清理。 |
| `memory_engine` | 文本 | `legacy` | **记忆引擎**：记忆管理引擎类型。legacy=现有实现，mem0=使用mem0进行自动记忆提取和检索（需配置Embedding提供商） |

<!-- CONFIG-REFERENCE:END -->
