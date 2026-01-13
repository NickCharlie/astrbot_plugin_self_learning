<div align="center">

# AstrBot 自主学习插件 Next-Gen 🧠✨


---

[![Version](https://img.shields.io/badge/version-Next--1.0.0-blue.svg)](https://github.com/NickCharlie/astrbot_plugin_self_learning)
[![License](https://img.shields.io/badge/license-GPLv3-green.svg)](LICENSE)
[![AstrBot](https://img.shields.io/badge/AstrBot-%3E%3D4.0.0-orange.svg)](https://github.com/Soulter/AstrBot)
[![Python](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)

**让你的 AI 聊天机器人像真人一样学习、思考和对话**

[功能特性](#-核心特性) • [快速开始](#-快速开始) • [架构设计](#-技术架构) • [文档](#-文档导航) • [贡献指南](#-贡献指南)

> **⚠️ 使用前必读：请务必先手动备份人格到本地，以防出现BUG导致人格混乱**

> ## ⚖️ 免责声明与用户协议
>
> **使用本项目即表示您已阅读、理解并同意以下条款：**
>
> 1. **合法使用承诺**
>    - 本项目仅供学习、研究和合法用途使用
>    - **严禁将本项目直接或间接用于任何违反当地法律法规的用途**
>    - 包括但不限于：侵犯隐私、非法采集数据、恶意传播信息、违反平台服务条款等行为
>
> 2. **隐私保护责任**
>    - 使用者需遵守《中华人民共和国网络安全法》《个人信息保护法》等相关法律法规
>    - 在收集和处理用户消息数据时，必须取得用户明确同意
>    - 不得将收集的数据用于商业目的或泄露给第三方
>    - 建议仅在私有环境或已获得所有参与者同意的群组中使用
>
> 3. **使用风险声明**
>    - 本项目按"原样"提供，不提供任何明示或暗示的保证
>    - 开发者不对使用本项目造成的任何直接或间接损失负责
>    - 使用者需自行承担数据丢失、人格错误、系统崩溃等风险
>    - **强烈建议在生产环境使用前进行充分测试**
>
> 4. **开发者免责**
>    - 开发者不对用户的违法违规行为承担任何责任
>    - 因用户违规使用导致的法律纠纷，由用户自行承担全部责任
>    - 开发者保留随时修改或终止本项目的权利
>
> 5. **协议变更**
>    - 本协议可能随时更新，恕不另行通知
>    - 继续使用本项目即表示接受更新后的协议条款
>
> **📌 重要提示：下载、安装、使用本项目的任何功能，即视为您已完全理解并同意遵守以上所有条款。如不同意，请立即停止使用并删除本项目。**


</div>

---

## 🌟 项目概述

AstrBot 智能自主学习插件是一个全功能 AI 自主学习 聊天拟人化 解决方案。通过实时消息捕获、多维度数据分析、表达模式学习和动态人格优化，让聊天机器人能够：

- 📖 **学习特定用户的对话风格** - 自动模仿学习对象的表达方式
- 🎯 **智能黑话理解系统** - 自动学习群组特定用语，避免误解
- ❤️ **管理社交关系和好感度** - 追踪用户互动，动态调整回复策略
- 🎭 **自适应人格演化** - 根据学习成果智能更新 AI 人格设定
- 🌐 **可视化管理界面** - 通过 WebUI 实时监控学习进度和效果


### 社区交流
- QQ 群: **1021544792**
  (ChatPlus 插件用户 + 本插件用户)
- 反馈 Bug 和使用问题

### 🤝 推荐搭配

**[群聊增强插件 (Group Chat Plus)](https://github.com/Him666233/astrbot_plugin_group_chat_plus)**

两者完美互补：
- 本插件负责 **AI学习与人格优化**
- 群聊增强插件负责 **智能回复决策与读空气能力**

配合使用可以让你的 Bot 既有学习能力，又有"读空气"的社交智能！

---

## 💡 核心特性

### 🎯 智能学习系统

#### 1. 表达模式学习
```
场景 → 表达模式 映射
"当需要表达肯定时" → "可以使用'确实如此呢'这样的表达"
```
- 自动识别对话中的场景-表达关系
- 15天时间衰减机制，优先保留高质量模式
- Few-Shot 对话示例生成，提升模仿准确度

#### 2. 记忆图系统
- 基于 NetworkX 构建知识关联网络
- 自动提取实体和关系，形成长期记忆
- 支持记忆检索和知识推理

#### 3. 社交关系分析
- 实时追踪用户互动关系
- 可视化社交网络图谱
- 好感度系统（单用户上限100分，总分250分）
- 动态情绪管理（10种情绪类型）

#### 4. 黑话挖掘与理解
```python
# 自动学习群组特定用语
"发财了" → "表示惊喜或获得好处"
"下次一定" → "委婉拒绝的表达"
"🦌" → "xxxxx"
```
- 自动检测候选黑话
- LLM 智能推断含义
- 实时注入对话理解

### 🏗️ 架构特性

#### 工厂模式 (Factory Pattern)
```python
# 统一的服务创建和管理
factory_manager = FactoryManager()
factory_manager.initialize_factories(config, context)

# 服务工厂
service_factory = factory_manager.get_service_factory()
db_manager = service_factory.create_database_manager()

# 组件工厂
component_factory = factory_manager.get_component_factory()
expression_learner = component_factory.create_expression_pattern_learner()
```

#### 策略模式 (Strategy Pattern)
```python
# 灵活的学习策略
learning_strategy = StrategyFactory.create_strategy(
    LearningStrategyType.BATCH,  # INCREMENTAL / REINFORCEMENT
    config={'batch_size': 100}
)
```

#### 依赖注入 (Dependency Injection)
```python
# 服务间松耦合
class MultidimensionalAnalyzer:
    def __init__(self, config, db_manager, llm_adapter, ...):
        self.config = config
        self.db = db_manager
        self.llm = llm_adapter
```

#### 仓储模式 (Repository Pattern)
```python
# 数据访问层抽象
affection_repo = AffectionRepository(session)
user_affection = await affection_repo.get_user_affection(group_id, user_id)
```

### 🗄️ 多数据库支持

```yaml
Database_Settings:
  db_type: "mysql"  # sqlite / mysql / postgresql(该功能暂时没有开放使用)

  # MySQL 配置
  mysql_host: "localhost"
  mysql_port: 3306
  mysql_user: "root"
  mysql_password: "your_password"
  mysql_database: "astrbot_self_learning"

  # 自动连接池管理
  max_connections: 10
  min_connections: 2
```

支持的数据库：
- **SQLite** - 开箱即用，适合单机部署
- **MySQL** - 高性能，适合生产环境
- **PostgreSQL** - 企业级，支持高级特性

### 📊 数据可视化

#### WebUI 管理界面 (端口: 7833)

**1. 数据统计页面**
![数据统计页面](https://github.com/NickCharlie/astrbot_plugin_self_learning/blob/develop/image/%E6%95%B0%E6%8D%AE%E7%BB%9F%E8%AE%A1%E9%A1%B5%E9%9D%A2.png?raw=true)
- 消息收集统计、学习进度跟踪
- 系统运行状态、数据库使用情况

**2. 人格管理页面**
![人格管理页面](https://github.com/NickCharlie/astrbot_plugin_self_learning/blob/develop/image/%E4%BA%BA%E6%A0%BC%E7%AE%A1%E7%90%86%E9%A1%B5%E9%9D%A2.png?raw=true)
- 人格列表查看、一键切换
- 人格编辑、备份与恢复
- 自动保护当前使用的人格

**3. 人格审查页面**
![人格审查页面](https://github.com/NickCharlie/astrbot_plugin_self_learning/blob/develop/image/%E4%BA%BA%E6%A0%BC%E5%AE%A1%E6%9F%A5%E9%A1%B5%E9%9D%A2.png?raw=true)
- 审查 AI 自动生成的人格更新建议
- 对比显示原始内容和建议修改
- 批准或拒绝更新，人工把关质量

**4. 风格学习页面**
![对话风格学习页面](https://github.com/NickCharlie/astrbot_plugin_self_learning/blob/develop/image/%E5%AF%B9%E8%AF%9D%E9%A3%8E%E6%A0%BC%E5%AD%A6%E4%B9%A0%E9%A1%B5%E9%9D%A2.png?raw=true)
- 学习进度可视化图表
- 场景-表达模式映射展示
- 质量评分和时间衰减管理

**5. 社交关系分析页面**
![社交关系页面](https://github.com/NickCharlie/astrbot_plugin_self_learning/blob/develop/image/%E7%A4%BE%E4%BA%A4%E5%85%B3%E7%B3%BB%E9%A1%B5%E9%9D%A2.png?raw=true)
- 力导向图展示成员互动关系
- 节点大小表示活跃度
- 连线粗细表示互动频率
- 颜色表示好感度等级

**6. 系统设置页面**
![配置页面](https://github.com/NickCharlie/astrbot_plugin_self_learning/blob/develop/image/%E9%85%8D%E7%BD%AE%E9%A1%B5%E9%9D%A2.png?raw=true)
- 学习参数配置
- 模型配置管理
- 好感度和情绪系统开关
- 数据管理和调试模式

---

## 🚀 快速开始

### 环境准备

```bash
# Python 版本要求
Python 3.8+

# 安装依赖
pip install -r requirements.txt
```

### 安装步骤

1. **将插件添加到 AstrBot 插件目录**
   ```bash
   cd /path/to/astrbot/data/plugins
   git clone https://github.com/NickCharlie/astrbot_plugin_self_learning.git
   ```

2. **启动 AstrBot**
   - 插件将自动加载并初始化

3. **访问 WebUI 管理界面**
   ```
   http://localhost:7833
   ```
   - 默认密码: `self_learning_pwd`
   - **⚠️ 首次登录后务必修改密码！**

4. **配置插件**
   - 在 AstrBot 后台插件管理中设置配置项
   - 或通过 WebUI 系统设置页面配置

### 基础配置示例

```yaml
# 基础开关
Self_Learning_Basic:
  enable_message_capture: true
  enable_auto_learning: true
  enable_realtime_learning: false
  enable_web_interface: true
  web_interface_port: 7833

# 目标设置
Target_Settings:
  target_qq_list: []  # 留空则学习所有用户
  current_persona_name: "default"

# 模型配置
Model_Configuration:
  filter_provider_id: "provider_id_1"  # 筛选模型
  refine_provider_id: "provider_id_2"  # 提炼模型

# 学习参数
Learning_Parameters:
  learning_interval_hours: 6
  min_messages_for_learning: 50
  max_messages_per_batch: 200

# 数据库配置
Database_Settings:
  db_type: "sqlite"  # 或 mysql / postgresql
```

---

## 🏛️ 技术架构

### 项目结构

```
astrbot_plugin_self_learning/
├── core/                          # 核心架构层
│   ├── factory.py                # 工厂管理器（依赖注入容器）
│   ├── interfaces.py             # 接口定义（抽象基类）
│   ├── patterns.py               # 设计模式实现（策略、观察者等）
│   ├── framework_llm_adapter.py  # LLM 框架适配器
│   └── database/                 # 数据库抽象层
│       ├── backend_interface.py  # 数据库接口
│       ├── sqlite_backend.py     # SQLite 实现
│       ├── mysql_backend.py      # MySQL 实现
│       └── postgresql_backend.py # PostgreSQL 实现
│
├── services/                      # 服务层（业务逻辑）
│   ├── message_collector.py      # 消息收集服务
│   ├── multidimensional_analyzer.py  # 多维度分析
│   ├── style_analyzer.py         # 风格分析服务
│   ├── progressive_learning.py   # 渐进式学习服务
│   ├── persona_manager.py        # 人格管理服务
│   ├── expression_pattern_learner.py  # 表达模式学习器
│   ├── affection_manager.py      # 好感度管理服务
│   ├── jargon_miner.py          # 黑话挖掘服务
│   ├── jargon_query.py          # 黑话查询服务
│   ├── social_context_injector.py  # 社交上下文注入器
│   └── response_diversity_manager.py  # 响应多样性管理器
│
├── models/                        # 数据模型层
│   └── orm/                      # ORM 模型（SQLAlchemy）
│       ├── base.py               # 基础模型
│       ├── expression.py         # 表达模式模型
│       ├── affection.py          # 好感度模型
│       ├── learning.py           # 学习记录模型
│       └── social_relation.py    # 社交关系模型
│
├── repositories/                  # 仓储层（数据访问）
│   ├── base_repository.py        # 基础仓储
│   ├── expression_repository.py  # 表达模式仓储
│   ├── affection_repository.py   # 好感度仓储
│   └── social_repository.py      # 社交关系仓储
│
├── webui/                         # Web 界面
│   ├── app.py                    # Quart 应用主入口
│   └── blueprints/               # 路由蓝图
│       ├── auth.py               # 认证路由
│       ├── persona.py            # 人格管理路由
│       └── analytics.py          # 数据分析路由
│
├── utils/                         # 工具类
│   ├── cache_manager.py          # 缓存管理
│   ├── migration_tool_v2.py      # 数据库迁移工具
│   └── security_utils.py         # 安全工具
│
├── config.py                      # 配置管理
├── main.py                        # 插件主入口
└── README.md                      # 项目文档
```

### 核心设计模式

#### 1. 工厂模式 (Factory Pattern)

**目的**: 统一管理服务创建，降低耦合

```python
class FactoryManager:
    """全局工厂管理器 - 单例模式"""

    def initialize_factories(self, config, context):
        self._service_factory = ServiceFactory(config, context)
        self._component_factory = ComponentFactory(config, self._service_factory)

    def get_service_factory(self) -> ServiceFactory:
        # 服务工厂：创建业务服务（数据库、学习、分析等）
        return self._service_factory

    def get_component_factory(self) -> ComponentFactory:
        # 组件工厂：创建轻量级组件（过滤器、调度器等）
        return self._component_factory
```

**优势**:
- ✅ 集中管理服务实例，避免循环依赖
- ✅ 服务缓存和单例模式，提升性能
- ✅ 支持服务注册和依赖注入

#### 2. 策略模式 (Strategy Pattern)

**目的**: 灵活切换学习策略

```python
class StrategyFactory:
    @staticmethod
    def create_strategy(strategy_type: LearningStrategyType, config: dict):
        strategies = {
            LearningStrategyType.BATCH: BatchLearningStrategy,
            LearningStrategyType.INCREMENTAL: IncrementalLearningStrategy,
            LearningStrategyType.REINFORCEMENT: ReinforcementLearningStrategy
        }
        return strategies[strategy_type](config)
```

**学习策略类型**:
- **批量学习** (Batch) - 定期批量处理消息
- **增量学习** (Incremental) - 实时逐条学习
- **强化学习** (Reinforcement) - 基于反馈优化

#### 3. 仓储模式 (Repository Pattern)

**目的**: 抽象数据访问层，支持多种数据库

```python
class BaseRepository:
    """基础仓储 - 提供通用 CRUD 操作"""

    async def get(self, id: int):
        async with self.session() as session:
            return await session.get(self.model, id)

    async def save(self, entity):
        async with self.session() as session:
            session.add(entity)
            await session.commit()

class ExpressionRepository(BaseRepository):
    """表达模式仓储 - 专门处理表达模式数据"""

    async def get_patterns_by_group(self, group_id: str, limit: int = 10):
        # 特定业务逻辑
        ...
```

#### 4. 观察者模式 (Observer Pattern)

**目的**: 事件驱动架构，解耦组件

```python
class EventBus:
    """事件总线 - 发布/订阅模式"""

    def subscribe(self, event_type: str, handler: Callable):
        self._handlers[event_type].append(handler)

    async def publish(self, event_type: str, data: Any):
        for handler in self._handlers[event_type]:
            await handler(data)

# 使用示例
event_bus.subscribe("learning_completed", on_learning_completed)
await event_bus.publish("learning_completed", learning_result)
```

### 数据流架构

```
┌─────────────────┐
│  消息接收层      │  on_message() - 监听所有消息
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  过滤器层        │  QQFilter + MessageFilter
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  数据收集层      │  MessageCollector - 存储原始消息
└────────┬────────┘
         │
         ├──────────────────┐
         │                  │
         ▼                  ▼
┌─────────────────┐  ┌─────────────────┐
│  分析层          │  │  学习层          │
│  - 多维度分析    │  │  - 表达模式学习  │
│  - 风格分析      │  │  - 黑话挖掘      │
│  - 社交关系分析  │  │  - 记忆图构建    │
└────────┬────────┘  └────────┬────────┘
         │                    │
         └──────────┬─────────┘
                    ▼
         ┌─────────────────┐
         │  人格更新层      │
         │  - PersonaUpdater│
         │  - 审查机制      │
         └────────┬────────┘
                  │
                  ▼
         ┌─────────────────┐
         │  LLM注入层       │  inject_diversity_to_llm_request()
         │  - 表达模式注入  │
         │  - 社交上下文    │
         │  - 黑话理解      │
         │  - 多样性增强    │
         └─────────────────┘
```

---

## 📖 详细功能说明

### 表达模式学习系统

**工作原理**:

1. **消息收集** - 每收集 10-25 条消息触发一次学习
2. **场景识别** - 使用 LLM 分析对话场景和上下文
3. **表达提取** - 提取目标用户的特定表达方式
4. **模式存储** - 保存"场景→表达"映射关系
5. **时间衰减** - 15天衰减周期，质量分数随时间降低
6. **Prompt注入** - 将高质量模式注入 LLM 请求

**示例**:
```
场景: "用户需要表达赞同"
表达: "确实是这样呢"
质量分数: 0.85
创建时间: 2025-11-20
衰减后分数: 0.78 (5天后)
```

### 黑话挖掘系统

**工作流程**:

```python
# 1. 候选词提取
candidates = await jargon_miner.extract_candidates(recent_messages)
# 输出: ["发财了", "下次一定", "真香"]

# 2. LLM 推断含义
meanings = await jargon_miner.infer_meanings(candidates, context)
# 输出: {
#   "发财了": "表示惊喜或获得好处",
#   "下次一定": "委婉拒绝的表达"
# }

# 3. 保存到数据库
await db.save_jargon_batch(chat_id, meanings)

# 4. LLM 请求时注入理解
jargon_explanation = await jargon_query.check_and_explain_jargon(
    text="今天真是发财了！",
    chat_id=group_id
)
# 注入到 LLM prompt: "文本中包含的黑话: 「发财了」: 表示惊喜或获得好处"
```

**特点**:
- ✅ 自动检测高频词汇和新词
- ✅ 上下文理解，精准推断含义
- ✅ 60秒 TTL 缓存，提升性能
- ✅ 实时注入 LLM 理解，避免误解

### 社交关系分析

**关系追踪**:
```python
# 自动记录用户互动
await social_relation_manager.record_interaction(
    group_id="123456",
    user_a="10001",
    user_b="10002",
    interaction_type="mention"  # at / reply / topic_discussion
)

# 分析关系强度
strength = await social_relation_manager.calculate_relationship_strength(
    group_id, user_a, user_b
)
# 输出: 0.75 (基于互动频率、类型、时间衰减)
```

**好感度管理**:
```python
# 处理用户消息互动
result = await affection_manager.process_message_interaction(
    group_id, user_id, message_text
)

# 自动识别互动类型
interaction_types = {
    "praise": +10,      # 称赞
    "encourage": +5,    # 鼓励
    "insult": -15,      # 侮辱
    "harass": -20       # 骚扰
}

# 好感度限制
- 单用户上限: 100分
- 群组总分上限: 250分
- 超额时自动衰减旧好感度
```

### 人格更新机制

**两种更新模式**:

#### 1. PersonaManager 模式 (推荐)
```python
# 直接在原人格末尾增量更新
await persona_manager_updater.apply_incremental_update(
    group_id=group_id,
    update_content="【学习成果】\n新增表达模式: ..."
)

# 优势:
# ✅ 自动创建备份人格
# ✅ 无需手动执行应用命令
# ✅ 更好的版本管理
```

#### 2. 传统文件模式
```python
# 临时存储到 persona_updates.txt
await temporary_persona_updater.write_to_updates_file(content)

# 手动审查后应用
/apply_persona_updates

# 优势:
# ✅ 人工审核把关
# ✅ 批量应用更新
```

**人格审查流程**:
```
1. AI 生成更新建议 → 保存到 style_learning_reviews 表
2. 管理员登录 WebUI → 人格审查页面
3. 查看对比（原始 vs 建议） → 红色高亮显示修改
4. 决策：批准 / 拒绝
5. 批准后自动应用到人格
```

---

## 📋 命令手册

### 基础学习管理

| 命令 | 权限 | 说明 |
|------|------|------|
| `/learning_status` | 管理员 | 查看学习状态和统计信息 |
| `/start_learning` | 管理员 | 手动启动学习批次 |
| `/stop_learning` | 管理员 | 停止自动学习循环 |
| `/force_learning` | 管理员 | 强制执行一次学习周期 |
| `/clear_data` | 管理员 | 清空所有学习数据 (⚠️不可逆) |
| `/export_data` | 管理员 | 导出学习数据为 JSON |

### 好感度系统

| 命令 | 权限 | 说明 |
|------|------|------|
| `/affection_status` | 管理员 | 查看好感度状态和排行榜 |
| `/set_mood <类型>` | 管理员 | 设置 Bot 情绪状态 |

**情绪类型**: `happy` `sad` `excited` `calm` `angry` `anxious` `playful` `serious` `nostalgic` `curious`

### 人格管理

| 命令 | 权限 | 说明 |
|------|------|------|
| `/persona_switch <名称>` | 管理员 | 切换到指定人格 |
| `/persona_info` | 管理员 | 显示当前人格详细信息 |
| `/temp_persona apply` | 管理员 | 应用临时人格 |
| `/temp_persona status` | 管理员 | 查看临时人格状态 |
| `/temp_persona remove` | 管理员 | 移除临时人格 |
| `/temp_persona extend [分钟]` | 管理员 | 延长临时人格时间 |
| `/temp_persona backup_list` | 管理员 | 列出所有备份 |
| `/temp_persona restore <文件名>` | 管理员 | 从备份恢复人格 |

### 高级管理

| 命令 | 权限 | 说明 |
|------|------|------|
| `/apply_persona_updates` | 管理员 | 应用 persona_updates.txt 中的更新 |
| `/switch_persona_update_mode` | 管理员 | 切换人格更新方式 (manager/file) |
| `/clean_duplicate_content` | 管理员 | 清理重复的历史内容 |
| `/analytics_report` | 管理员 | 生成数据分析报告 |

---

## 🔧 配置详解

### 完整配置示例

```yaml
# ========================================
# 基础开关
# ========================================
Self_Learning_Basic:
  enable_message_capture: true      # 启用消息抓取
  enable_auto_learning: true        # 启用定时自动学习
  enable_realtime_learning: false   # 启用实时学习（每条消息）
  enable_web_interface: true        # 启用 Web 管理界面
  web_interface_port: 7833          # Web 界面端口

# ========================================
# 目标设置
# ========================================
Target_Settings:
  target_qq_list: []                # 学习目标 QQ 号列表（空=全部）
  target_blacklist: []              # 学习黑名单
  current_persona_name: "default"   # 当前人格名称

# ========================================
# 模型配置（使用 AstrBot Provider）
# ========================================
Model_Configuration:
  filter_provider_id: "provider_gpt4o_mini"  # 筛选模型（弱模型）
  refine_provider_id: "provider_gpt4o"       # 提炼模型（强模型）
  reinforce_provider_id: "provider_gpt4o"    # 强化模型

# ========================================
# 学习参数
# ========================================
Learning_Parameters:
  learning_interval_hours: 6        # 自动学习间隔（小时）
  min_messages_for_learning: 50     # 最少消息数才开始学习
  max_messages_per_batch: 200       # 每批处理的最大消息数

# ========================================
# 筛选参数
# ========================================
Filter_Parameters:
  message_min_length: 5             # 消息最小长度
  message_max_length: 500           # 消息最大长度
  confidence_threshold: 0.7         # 筛选置信度阈值
  relevance_threshold: 0.6          # 相关性阈值

# ========================================
# 风格分析
# ========================================
Style_Analysis:
  style_analysis_batch_size: 100    # 风格分析批次大小
  style_update_threshold: 0.6       # 风格更新阈值

# ========================================
# 好感度系统
# ========================================
Affection_System_Settings:
  enable_affection_system: true     # 启用好感度系统
  max_total_affection: 250          # Bot 总好感度上限
  max_user_affection: 100           # 单用户好感度上限
  affection_decay_rate: 0.95        # 好感度衰减比例
  daily_mood_change: true           # 启用每日情绪变化
  mood_affect_affection: true       # 情绪影响好感度变化

# ========================================
# 情绪系统
# ========================================
Mood_System_Settings:
  enable_daily_mood: true           # 启用每日情绪
  enable_startup_random_mood: true  # 启用启动时随机情绪
  mood_change_hour: 6               # 情绪更新时间（24小时制）
  mood_persistence_hours: 24        # 情绪持续时间（小时）

# ========================================
# 数据库设置
# ========================================
Database_Settings:
  db_type: "sqlite"                 # 数据库类型: sqlite / mysql / postgresql

  # MySQL 配置（db_type="mysql"时生效）
  mysql_host: "localhost"
  mysql_port: 3306
  mysql_user: "root"
  mysql_password: "your_password"
  mysql_database: "astrbot_self_learning"

  # PostgreSQL 配置（db_type="postgresql"时生效）
  postgresql_host: "localhost"
  postgresql_port: 5432
  postgresql_user: "postgres"
  postgresql_password: "your_password"
  postgresql_database: "astrbot_self_learning"
  postgresql_schema: "public"

  # 连接池配置
  max_connections: 10
  min_connections: 2

  # 重构功能配置
  use_sqlalchemy: false             # 使用 SQLAlchemy ORM
  use_enhanced_managers: false      # 使用增强型管理器

# ========================================
# 社交上下文设置
# ========================================
Social_Context_Settings:
  enable_social_context_injection: true  # 启用社交关系注入
  include_social_relations: true         # 注入用户社交关系
  include_affection_info: true           # 注入好感度信息
  include_mood_info: true                # 注入 Bot 情绪信息
  context_injection_position: "start"    # 注入位置: start / end

# ========================================
# 高级设置
# ========================================
Advanced_Settings:
  debug_mode: false                 # 调试模式
  save_raw_messages: true           # 保存原始消息
  auto_backup_interval_days: 7      # 自动备份间隔（天）
  use_enhanced_managers: false      # 使用增强型管理器
  enable_memory_cleanup: true       # 启用记忆自动清理
  memory_cleanup_days: 30           # 记忆保留天数
  memory_importance_threshold: 0.3  # 记忆重要性阈值

# ========================================
# 存储设置
# ========================================
Storage_Settings:
  data_dir: "./data/self_learning_data"  # 数据存储目录
```

---

## 🛠️ 技术栈

### AI/ML 技术栈
- **大型语言模型**: OpenAI GPT系列、兼容 OpenAI API 的任意模型
- **机器学习**: `scikit-learn` `numpy` `pandas`
- **情感计算**: 情绪识别、情感状态建模
- **知识图谱**: `networkx` - 关系网络分析
- **自然语言处理**: `jieba` - 中文分词

### 数据可视化
- **图表生成**: `plotly` `matplotlib` `seaborn`
- **网络可视化**: `bokeh` - 社交关系图
- **数据分析**: 多维度统计分析

### 系统架构
- **异步框架**: `asyncio` `aiohttp` `aiofiles`
- **数据库**: `aiosqlite` `aiomysql` `asyncpg` + `SQLAlchemy[asyncio]`
- **Web框架**: `quart` `quart-cors` - 异步 Flask-like 框架
- **缓存系统**: `cachetools` - TTL缓存
- **任务调度**: `apscheduler` - 定时任务

### 开发工具
- **数据库迁移**: `alembic` - SQLAlchemy 迁移工具
- **安全工具**: `guardrails-ai` - LLM 输出校验
- **测试框架**: `pytest` `pytest-asyncio`

---

## 📚 文档导航

### 用户文档
- [快速开始指南](#-快速开始)
- [WebUI 使用教程](#-数据可视化)
- [命令手册](#-命令手册)
- [配置详解](#-配置详解)

### 开发文档
- [架构设计](#-技术架构)
- [设计模式详解](#核心设计模式)
- [数据库迁移工具](utils/migration_tool_v2.py)
- [API 接口文档](webui/README.md)

### 进阶文档
- [表达模式学习原理](#表达模式学习系统)
- [黑话挖掘算法](#黑话挖掘系统)
- [社交关系分析](#社交关系分析)
- [人格更新机制](#人格更新机制)

---

## 🤝 贡献指南

欢迎开发者参与项目建设！

### 贡献方式
1. **Bug 反馈** - [提交 Issue](https://github.com/NickCharlie/astrbot_plugin_self_learning/issues)
2. **功能建议** - [Feature Request](https://github.com/NickCharlie/astrbot_plugin_self_learning/issues/new?template=feature_request.md)
3. **代码贡献** - Fork 项目并提交 Pull Request
4. **文档改进** - 完善文档和教程

### 开发规范
- 遵循现有的架构设计和设计模式
- 使用工厂模式统一管理服务
- 优先使用依赖注入，避免硬编码
- 每个功能分文件，每个模块分目录
- 导入自己的模块时使用相对导入
- 添加单元测试覆盖核心逻辑

---

## 📄 开源协议

本项目采用 [GPLv3 License](LICENSE) 开源协议。

### 致谢

感谢以下项目的启发和支持：

- **[MaiBot](https://github.com/Mai-with-u/MaiBot)** - 表达模式学习、时间衰减机制、知识图谱管理等核心设计思路
- **[AstrBot](https://github.com/Soulter/AstrBot)** - 优秀的聊天机器人框架

---

## ⚠️ 免责声明（详细版）

> **本节内容补充说明文档顶部的用户协议，两者具有同等法律效力**

### 1. 合法合规使用

- **严禁违法使用**：本项目严禁直接或间接用于任何违反当地法律法规的用途
- **遵守法律法规**：使用者必须遵守《中华人民共和国网络安全法》《个人信息保护法》《数据安全法》等相关法律
- **平台规则**：使用者需遵守 QQ、微信等即时通讯平台的服务条款和使用规范
- **获得授权**：在收集和处理任何用户数据前，必须获得明确的用户同意

### 2. 数据安全与隐私

- **本地存储**：所有学习数据本地化存储，开发者无法获取用户数据
- **定期备份**：请定期备份数据库和人格文件，防止数据丢失
- **密码保护**：强烈建议在生产环境修改 WebUI 默认密码
- **隐私保护**：
  - 插件会收集和分析用户消息用于学习
  - 使用者必须明确告知群组成员数据收集行为
  - 不得将收集的数据用于商业目的
  - 不得泄露数据给任何第三方
  - 建议仅在私有环境或已获得所有成员同意的群组使用

### 3. 使用风险

- **软件状态**：插件目前处于开发测试阶段，可能存在未知 Bug
- **数据风险**：使用前请务必备份人格文件，防止数据损坏或丢失
- **质量依赖**：AI 学习质量取决于学习样本的质量和数量
- **系统稳定性**：在生产环境使用前，强烈建议进行充分测试
- **网络安全**：不建议在公开环境暴露 WebUI 端口，避免安全风险

### 4. 开发者责任限制

- **按原样提供**：本项目按"原样"（AS-IS）提供，不提供任何形式的保证
- **无担保声明**：包括但不限于对适销性、特定用途适用性的暗示保证
- **免责范围**：
  - 开发者不对使用本项目造成的任何直接、间接、偶然、特殊或后果性损失负责
  - 包括但不限于：数据丢失、业务中断、利润损失、声誉损害等
  - 开发者不对用户的违法违规行为承担任何责任
  - 因用户违规使用导致的法律纠纷，由用户自行承担全部法律责任和经济损失

### 5. 其他条款

- **版权声明**：本项目采用 GPLv3 开源协议，使用者需遵守协议条款
- **修改权利**：开发者保留随时修改、更新或终止本项目的权利
- **协议更新**：本免责声明和用户协议可能随时更新，恕不另行通知
- **持续使用视为同意**：继续使用本项目即表示接受更新后的所有条款

### 6. 特别提醒

⚠️ **重要**：
- 如果您不同意以上任何条款，请立即停止使用并删除本项目
- 下载、安装、使用本项目的任何功能，即视为您已完全阅读、理解并同意遵守本免责声明及用户协议的所有内容
- 本声明的解释权归项目开发者所有

---

## 🎯 未来计划

### 即将推出
- [ ] 知识图谱和长期记忆系统（理解上下文关系，建立持久记忆）
- [ ] 多人格自动切换（根据对话场景）
- [ ] 高级情绪建模（情绪链和情绪转移）
- [ ] 强化学习优化（基于用户反馈）
- [ ] 多模态学习支持（图片、语音）

### 长期规划
- [ ] 联邦学习（跨群组知识共享）
- [ ] 自主对话发起（主动话题引导）

---

<div align="center">

**感谢使用 AstrBot 智能自主学习插件！**

如果觉得有帮助，欢迎 ⭐Star 支持！

[回到顶部](#astrbot-智能自主学习插件-next-gen-)

</div>
