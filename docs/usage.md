# 使用指南

本文按当前代码行为描述。当前 WebUI 免密访问，打开 Dashboard 后直接进入页面。

## 安装

进入 AstrBot 插件目录:

```powershell
cd C:\path\to\AstrBot\data\plugins
git clone https://github.com/EterUltimate/self_learning_EterU.git astrbot_plugin_self_learning
```

重启 AstrBot 或在插件管理页重新加载插件。

## 依赖安装

当前代码不会在插件安装或启动阶段自动安装 pip 依赖。

安装完成后:

1. 打开 AstrBot 插件管理。
2. 进入 self-learning 设置页或 WebUI 系统设置。
3. 点击 `基础能力依赖` 或 `全能力依赖`。

依赖档位:

| 档位 | 用途 |
| --- | --- |
| 基础能力依赖 | WebUI、SQLite/PostgreSQL、人格审查、黑话学习、表达方式学习 |
| 全能力依赖 | 基础能力 + MySQL、监控指标、图谱、LightRAG、mem0 |

依赖安装接口只接受设置页确认请求:

```json
{"manual_confirmed": true, "source": "system_settings", "tier": "basic"}
```

如果部署环境禁止 WebUI 安装依赖:

```powershell
$env:ASTRBOT_ENABLE_WEB_DEP_INSTALL="false"
```

## 启动 WebUI

默认地址:

```text
http://127.0.0.1:7833
```

如果 `web_interface_host=0.0.0.0`，局域网内可用服务器 IP 访问:

```text
http://<server-ip>:7833
```

WebUI 相关配置:

- `enable_web_interface`
- `web_interface_host`
- `web_interface_port`

修改 host/port 后需要重启插件。

## 基础配置顺序

### 1. 备份人格

使用前先在 AstrBot 原生人格管理中手动备份当前人格。人格学习和审查虽然有保护，但仍建议保留外部备份。

### 2. 设置学习目标

`Target_Settings.target_qq_list`:

- 默认全量学习: 为空、空行或填写 `all`/`*`/`全部`/`全量` 时学习所有非黑名单消息。
- 填用户 QQ: 只学习指定用户。
- 填群组格式: 按当前代码的 QQ 过滤规则处理群组目标。

`Target_Settings.target_blacklist`:

- 排除指定用户或群组。

### 3. 设置 Provider

至少建议配置一个 AstrBot Provider:

- `filter_provider_id`: 轻量筛选。
- `refine_provider_id`: 深度提炼。
- `reinforce_provider_id`: 强化学习。

未配置 Provider 时插件仍可加载，但 LLM 相关功能会降级。

### 4. 配置数据库

默认 PostgreSQL:

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

插件会在启动时自动创建缺失的 PostgreSQL 数据库、schema 和 ORM 表。默认数据库用户需要具备连接 `postgres` 维护库、创建数据库、创建 schema 和建表权限。

SQLite 回退:

```json
{
  "Database_Settings": {
    "db_type": "sqlite"
  }
}
```

MySQL:

```json
{
  "Database_Settings": {
    "db_type": "mysql",
    "mysql_host": "localhost",
    "mysql_port": 3306,
    "mysql_user": "root",
    "mysql_password": "password",
    "mysql_database": "astrbot_self_learning"
  }
}
```

数据库类型和连接参数修改后需要重启。

## 常用开关

| 功能 | 配置 |
| --- | --- |
| 消息采集 | `enable_message_capture` |
| 自动学习 | `enable_auto_learning` |
| 实时学习 | `enable_realtime_learning` |
| 表达模式 | `enable_expression_patterns` |
| 黑话学习 | `enable_jargon_learning` |
| WebUI | `enable_web_interface` |
| 好感度 | `enable_affection_system` |
| 目标驱动对话 | `enable_goal_driven_chat` |
| 记忆图 | `enable_memory_graph` |
| 知识图谱 | `enable_knowledge_graph` |

## 管理命令

所有命令需要 AstrBot 管理员权限。

| 命令 | 说明 |
| --- | --- |
| `/learning_status` | 查看学习状态和统计 |
| `/start_learning` | 手动启动学习 |
| `/stop_learning` | 停止学习 |
| `/force_learning` | 强制执行一次学习 |
| `/remember <引用或上下文> => <表达示例>` | 手动记住对话上下文，并链入表达方式和对话示例 |
| `/affection_status` | 查看好感度状态 |
| `/set_mood <类型>` | 设置 Bot 情绪 |

## Dashboard 使用

### 总览

查看消息数、学习状态、待审数量、图谱数据和性能指标。

### 全量设置

通过系统设置页读取 `/api/config/schema`，可编辑所有公开配置项。

注意:

- 标记为只读的字段不应编辑。
- 标记为重启生效的字段保存后需要重启插件。
- 日志等级可立即生效。

### 功能融合

入口: `#/integrations`

用途:

- 查看 Self Learning、LivingMemory、Group Chat Plus 状态。
- 打开各插件 Dashboard 或 AstrBot Pages。
- 查看 companion 插件开发 API。
- 编辑 `Integration_Settings`。

默认策略:

- LivingMemory 存在时，长期记忆写入和注入交给 LivingMemory。
- Group Chat Plus 存在时，回复决策和生成交给 Group Chat Plus。
- 目标插件不存在时，本插件自动使用本地降级能力。

### 待审人格

用于审查人格学习结果:

- 批准: 应用或进入后续应用流程。
- 拒绝: 标记为 rejected。
- 批量审查: 对多条记录执行同一操作。
- 删除: 删除审查记录。
- 回滚: 对支持回滚的记录恢复旧内容。

### 风格审查

用于审查表达模式和 few-shot 对话:

- 批准后会成为 LLM Hook 可注入的 few-shot。
- 拒绝后不会参与注入。

### 黑话

用于管理候选黑话:

- 查看候选词、含义、计数和群组。
- 审查候选是否成立。
- 设置为全局黑话。
- 同步全局黑话到指定群组。

### 学习内容查看

`/api/style_learning/content_text` 汇总展示学习链路中的具体内容，包括:

- 原始消息。
- 筛选消息。
- 表达模式。
- 风格学习记录。
- 人格审查记录。
- 学习批次和会话。

用于定位学习没有产出时卡在哪一层。

### 图谱

Dashboard 支持:

- 记忆图: `/api/graphs/memory`
- 知识图谱: `/api/graphs/knowledge`
- 社交关系图谱和分享链接。

返回数据是节点、边、分类结构，前端按可视化图渲染。

## 日志等级

配置:

```json
{"Advanced_Settings": {"log_level": "debug"}}
```

可选值:

- `error`: 最少，仅错误。
- `warning`: 警告和错误。
- `info`: 关键学习事件。
- `debug`: 最详细，包含候选、注入、耗时和内部状态。

排查学习链路时建议临时设置为 `debug`。

## 常见问题

### 插件加载失败: 缺少依赖

确认已经通过设置页手动安装依赖。安装阶段不会自动 pip install。

### WebUI 打不开

检查:

1. `enable_web_interface=True`
2. 端口 `7833` 是否被占用。
3. AstrBot 日志中是否有 `[WebUI] Web服务器启动成功`。
4. 如果改过 host/port，重启插件。

### 学不到内容

检查:

1. `enable_message_capture=True`
2. 当前用户未被黑名单排除。
3. `RawMessage` 是否增长。
4. 消息长度是否满足阈值。
5. `enable_expression_patterns=True`
6. Bot 是否有出站文本进入 `BotMessage`。
7. 群组消息是否达到 `min_messages_for_learning`。
8. 是否有待审记录未批准。
9. Provider 是否可用。

### 功能融合未生效

检查:

1. Dashboard `功能融合` 页是否检测到目标插件。
2. 目标插件是否已启用且加载成功。
3. `Integration_Settings` 中两个委托开关和两个禁用本地能力开关是否为 `true`。
4. 插件名是否与实际 AstrBot star 名称匹配。
5. 日志等级设为 `debug` 后查看 `[功能融合]` 和 `[V2Integration]` 日志。

### 数据库建表失败

检查:

1. 数据库驱动是否已安装。
2. 用户是否有创建数据库和 schema 的权限。
3. PostgreSQL schema 名称不为空且不包含非法字符。
4. SQLite 数据目录可写。

### 修改配置后没变化

数据库、WebUI host/port、数据目录等配置需要重启。日志等级和大部分学习阈值可立即生效。
