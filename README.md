# AstrBot 智能自学习插件 🧠✨ (使用前一定要先手动备份人格到本地 以防出现BUG导致人格丢失或混乱)

## 🚀 项目概述

AstrBot 智能自学习插件是一个为 AstrBot 框架设计的**全功能 AI 自主学习解决方案**。以用户设置的学习对象的聊天消息为样本，让bot不断学习，实现更自然，更真实的消息对话。

**🤖 MaiBot功能参考**：本版本参考了 [Mai-with-u/MaiBot: 麦麦bot，一款专注于 群组聊天 的赛博网友（比较专注）多平台智能体](https://github.com/Mai-with-u/MaiBot)的学习算法和功能模块，参考MaiBot的表达模式学习、记忆图系统、知识图谱管理等先进技术，实现更加智能和自然的对话学习能力。

该插件通过机器学习、多维度数据分析、情感智能系统和动态人格优化，为聊天Bot提供了**完整的自主学习生态系统**。

> **🔧 说明**：本版本已由社区贡献者修复了插件的潜在问题，包括但不限于：
>
> - 修复了插件将命令消息视为聊天消息的问题
> - 修复了强制学习中无限循环调用提炼模型的问题
> - 解决了无缘无故报模型未配置的问题
> - 优化了插件的稳定性和性能表现
> - **新增**：集成MaiBot核心功能，实现智能表达模式学习

## 📜 开源协议变更说明 / Open Source License Change Notice

**中文说明**：

本项目协议已从 MIT 协议变更为 **GNU General Public License v3.0 (GPL v3)**。

**变更原因**：
- 为了确保开源项目的持续开放性和社区贡献的保护
- 防止商业实体封闭源码并从中获利而不回馈社区
- 保障用户的自由使用权和源码获取权

**GPL v3 协议要点**：
- ✅ 允许自由使用、修改、分发
- ✅ 要求衍生作品也必须开源（Copyleft）
- ✅ 提供源码访问保障
- ✅ 禁止添加额外限制性条款
- ⚠️ 商业使用时需遵循GPL v3协议要求

**English Notice**:

This project's license has been changed from MIT to **GNU General Public License v3.0 (GPL v3)**.

**Reasons for change**:
- To ensure continued openness of the open source project and protection of community contributions
- To prevent commercial entities from closing source code and profiting without giving back to the community
- To guarantee users' freedom to use and access source code

**GPL v3 Key Points**:
- ✅ Allows free use, modification, and distribution
- ✅ Requires derivative works to also be open source (Copyleft)
- ✅ Provides source code access guarantee
- ✅ Prohibits adding additional restrictive clauses
- ⚠️ Commercial use must comply with GPL v3 license requirements

---

## 目前插件正在测试阶段 有许多Bug还没有修好 webui暂时无法使用

## 欢迎加入QQ群聊 1021544792 反馈你所遇到的Bug

## 🤖 参考MaiBot的功能集成说明

本版本参考了 MaiBot 的先进实现，主要包含以下核心功能：

### 🎯 参考MaiBot的核心功能模块

#### 🗣️ 表达模式学习器 (ExpressionPatternLearner)
- **功能来源**: 参考 MaiBot 的表达模式学习机制
- **核心特性**: 
  - 采用"当...时，使用..."的场景-表达格式
  - 25条消息触发学习机制
  - 300秒学习间隔控制
  - 支持场景-表达映射和数据库持久化

#### 🧠 记忆图系统 (MemoryGraphManager)
- **功能来源**: 基于 MaiBot 的记忆管理架构
- **核心特性**:
  - 使用 NetworkX 构建对话上下文图
  - 智能记忆融合和关联分析
  - 支持LLM集成的记忆整合
  - 概念节点和关系边的动态管理

#### 🔗 知识图谱管理 (KnowledgeGraphManager)
- **功能来源**: 参考 MaiBot 的知识抽取方法
- **核心特性**:
  - RDF三元组的实体-关系提取
  - 支持知识图谱查询和QA功能
  - 实体识别和关系建立
  - 知识库的动态扩展和更新

#### ⏰ 时间衰减机制 (TimeDecayManager)
- **功能来源**: 采用 MaiBot 的15天衰减算法
- **核心特性**:
  - 二次函数衰减模型：quality = max(0, 1 - ((days/15)^2))
  - 跨多表的数据质量管理
  - 自动清理过期低质量数据
  - 学习效果的时间加权评估

#### 🎨 增强型Prompt工程
- **功能来源**: 采用 MaiBot 的场景-表达模式
- **核心特性**:
  - EXPRESSION_PATTERN_LEARNING_PROMPT 格式
  - "当...时，使用..."的学习模板
  - 场景化的表达方式训练
  - 自然语言的风格迁移学习

### 🔧 架构集成方式

#### 适配器模式集成
- **MaiBotStyleAnalyzer**: 实现 IStyleAnalyzer 接口
- **MaiBotLearningStrategy**: 实现 ILearningStrategy 接口  
- **MaiBotQualityMonitor**: 实现 IQualityMonitor 接口
- **无缝集成**: 遵循现有架构，不破坏原有功能

#### 工厂模式增强
- **智能选择**: 根据配置自动选择 MaiBot 功能或原有实现
- **优雅回退**: MaiBot 功能不可用时自动回退到原实现
- **配置驱动**: 通过 `enable_maibot_features` 控制功能启用

#### 学习流程优化
- **修复关键问题**: 将学习结果转换为增量特征而非原始对话
- **MaiBot集成**: 表达学习器、记忆图、知识图谱协同工作
- **质量提升**: 结合多种MaiBot算法提升学习效果

### 🚀 默认启用说明

MaiBot 功能在本版本中**默认启用**，无需额外配置：

```python
# 配置项（默认启用）
enable_maibot_features: bool = True      # 启用MaiBot增强功能
enable_expression_patterns: bool = True  # 启用表达模式学习
enable_memory_graph: bool = True         # 启用记忆图系统
enable_knowledge_graph: bool = True      # 启用知识图谱
enable_time_decay: bool = True           # 启用时间衰减机制
```

### 🎓 致谢声明

本项目的 MaiBot 功能集成**参考了** [MaiBot 项目](https://github.com/MaiM-with-u/MaiBot) 的以下核心设计思路和实现方法：

- 表达模式学习的场景-表达映射机制
- 15天时间衰减的质量管理算法  
- 基于NetworkX的记忆图构建方法
- 知识图谱的实体-关系提取策略
- 25条消息触发和300秒间隔的学习节奏控制

感谢 MaiBot 项目提供的优秀开源实现，为bot智能对话学习领域做出的贡献！

---

### 🌟 核心特性

- **🔄 全自动学习循环**: 实时消息捕获、智能筛选、风格分析、人格优化
- **🧠 情感智能系统**: 好感度管理、情绪状态、动态响应机制
- **📊 数据可视化分析**: 学习轨迹图表、用户行为分析、社交关系可视化
- **🤖 高级学习机制**: 人格切换、上下文感知学习、增量学习、对抗学习
- **💬 增强交互能力**: 多轮对话管理、跨群记忆、主动话题引导
- **🎯 智能化提升**: 知识图谱、个性化推荐、自适应学习率调整
- **🌐 Web 管理界面**: 完整的可视化管理控制台

## **<u>后台管理使用教程</u>**

### **<u>重要安全提醒</u>**

**<u>插件启动后请立即访问后台管理页面并修改默认密码！</u>**

### 🌐 访问后台管理

1. **启动插件后**，Web管理界面将在以下地址启动：
   ```
   http://localhost:7833 或 http://你的服务器IP:7833
   ```

2. **首次登录**：
   - 默认密码：`self_learning_pwd`
   - **<u>⚠️ 强烈建议：首次登录后立即修改密码！</u>**

### 🛡️ 安全说明

- **<u>请务必在生产环境中修改默认密码！</u>**

### 🎯 核心服务层 (`services/`)

#### 📊 数据分析与可视化服务
- **`data_analytics.py`**: 学习过程可视化、用户行为分析、社交网络图谱生成
- **功能**: 生成学习轨迹图表、用户活跃度热力图、话题趋势分析、社交关系可视化

#### 🧠 高级学习机制服务  
- **`advanced_learning.py`**: 人格切换、上下文感知学习、增量学习、对抗学习
- **功能**: 多场景人格自动切换、情境感知学习、知识增量更新、学习效果强化

#### 💬 增强交互服务
- **`enhanced_interaction.py`**: 多轮对话管理、跨群记忆、主动话题引导
- **功能**: 对话上下文跟踪、历史记忆管理、智能话题推荐、互动模式分析

#### 🎯 智能化提升服务
- **`intelligence_enhancement.py`**: 情感智能、知识图谱、个性化推荐、自适应学习
- **功能**: 情感状态识别、知识实体管理、智能推荐算法、学习率动态调整

#### ❤️ 好感度管理服务
- **`affection_manager.py`**: 用户好感度系统、bot情绪管理、动态情感响应
- **功能**: 
  - 用户好感度跟踪（单用户最大100分，总分250分上限）
  - 每日随机情绪系统（10种情绪类型）
  - 智能交互分析（称赞、鼓励、侮辱、骚扰等识别）
  - 动态情绪响应（根据用户行为自动调节bot情绪）
  - 好感度影响系统提示词（情绪状态融入AI回复）

#### 🔧 基础核心服务
- **`message_collector.py`**: 智能消息收集与预处理
- **`database_manager.py`**: 统一数据管理（全局+分群数据库架构）
- **`multidimensional_analyzer.py`**: 多维度消息分析与用户画像构建
- **`style_analyzer.py`**: 深度对话风格分析与量化
- **`learning_quality_monitor.py`**: 学习质量实时监控与评估
- **`progressive_learning.py`**: 渐进式学习流程协调
- **`ml_analyzer.py`**: 机器学习增强分析
- **`persona_manager.py`**: 动态人格管理
- **`persona_updater.py`**: 智能人格更新
- **`persona_backup_manager.py`**: 人格数据备份与恢复

## 📋 插件命令详细教程

本插件提供了丰富的命令接口，支持完整的学习管理、好感度系统、临时人格管理等功能。以下是所有可用命令的详细说明：

### 🎮 基础学习管理命令

#### `/learning_status` - 查看学习状态
**权限要求**: 管理员  
**功能说明**: 查看当前群组/用户的详细学习状态和统计信息

**显示内容**:
- 基础配置状态（消息抓取、自动学习、实时学习、Web界面）
- 抓取设置（目标QQ号、当前人格）
- 模型配置（筛选模型、提炼模型）
- 学习统计（总消息数、已筛选消息、风格更新次数、最后学习时间）
- 存储统计（原始消息、未处理消息、已筛选消息）
- 调度状态（学习器运行状态）

**使用示例**:
```
/learning_status
```

---

#### `/start_learning` - 启动学习
**权限要求**: 管理员  
**功能说明**: 手动启动当前群组的自动学习循环

**使用场景**:
- 插件刚启动时手动激活学习
- 学习被停止后重新启动
- 强制重启学习流程

**使用示例**:
```
/start_learning
```

**返回信息**:
- 成功: "群组 [群组ID] 的学习已启动"
- 已运行: "群组 [群组ID] 的学习已在运行中"

---

#### `/stop_learning` - 停止学习  
**权限要求**: 管理员  
**功能说明**: 停止当前群组的自动学习循环

**使用场景**:
- 暂时禁用自动学习
- 维护或调试时停止学习
- 避免过度学习

**使用示例**:
```
/stop_learning
```

---

#### `/force_learning` - 强制学习
**权限要求**: 管理员  
**功能说明**: 立即执行一次完整的学习周期，忽略时间间隔限制

**使用场景**:
- 测试学习效果
- 有大量新消息需要立即学习
- 调试学习流程

**使用示例**:
```
/force_learning
```

**执行流程**:
1. 筛选未处理的消息
2. 多维度分析消息质量
3. 提取对话风格特征
4. 更新人格设置
5. 质量评估和效果验证

---

### 📊 数据管理命令

#### `/clear_data` - 清空学习数据
**权限要求**: 管理员  
**功能说明**: 清空所有学习数据，包括原始消息、筛选消息、学习统计等

**⚠️ 重要警告**: 此操作不可逆，请谨慎使用！

**使用示例**:
```
/clear_data
```

**清空内容**:
- 所有收集的原始消息
- 已筛选的高质量消息
- 学习统计数据
- 缓存的分析结果

---

#### `/export_data` - 导出学习数据
**权限要求**: 管理员  
**功能说明**: 将学习数据导出为JSON格式文件，用于备份或分析

**使用示例**:
```
/export_data
```

**导出内容**:
- 原始消息数据
- 筛选结果
- 风格分析结果
- 学习统计信息
- 用户行为数据

**文件位置**: 插件数据目录下，文件名格式：`learning_data_export_YYYYMMDD_HHMMSS.json`

---

### ❤️ 好感度系统命令

#### `/affection_status` - 查看好感度状态  
**权限要求**: 管理员  
**功能说明**: 查看当前群组的好感度系统详细状态

**显示内容**:
- 当前用户好感度等级（满分100）
- 群组总好感度状态（满分250）
- 群组用户数量统计
- Bot当前情绪状态（情绪类型、强度、描述）
- 好感度排行榜（前3名用户）

**使用示例**:
```
/affection_status
```

**情绪类型说明**:
- **happy**: 心情很好，说话活泼开朗
- **sad**: 心情低落，说话温和需要安慰
- **excited**: 很兴奋，说话有活力
- **calm**: 心情平静，说话稳重
- **angry**: 心情不好，说话直接没耐心
- **anxious**: 紧张不安，说话谨慎
- **playful**: 调皮，喜欢开玩笑
- **serious**: 严肃认真，说话简洁直接
- **nostalgic**: 怀旧情绪，说话带回忆色彩
- **curious**: 好奇心强，喜欢提问探索

---

#### `/set_mood <情绪类型>` - 设置Bot情绪
**权限要求**: 管理员  
**功能说明**: 手动设置Bot的情绪状态，影响对话风格和回复语调

**使用示例**:
```
/set_mood happy
/set_mood sad  
/set_mood excited
/set_mood calm
/set_mood angry
/set_mood anxious
/set_mood playful
/set_mood serious
/set_mood nostalgic
/set_mood curious
```

**功能说明**:
- 设置后Bot的回复将体现相应情绪特征
- 情绪状态会持续24小时（可配置）
- 同时更新好感度系统和人格提示词
- 支持的情绪类型见上方情绪类型说明

---

### 📈 数据分析命令

#### `/analytics_report` - 生成数据分析报告
**权限要求**: 管理员  
**功能说明**: 生成当前群组的详细数据分析报告

**报告内容**:
- **学习统计**: 总消息数、学习会话数、平均质量分数
- **用户行为分析**: 活跃用户数、主要话题、情感倾向
- **优化建议**: 基于数据分析的学习模式建议

**使用示例**:
```
/analytics_report
```

**分析维度**:
- 消息质量趋势
- 用户参与度分析  
- 话题分布统计
- 情感状态变化
- 学习效果评估

---

### 🎭 人格管理命令

#### `/persona_switch <人格名称>` - 切换人格模式
**权限要求**: 普通用户  
**功能说明**: 切换到指定的人格模式

**使用示例**:
```
/persona_switch default
/persona_switch assistant
/persona_switch friend
```

**注意事项**:
- 人格名称需要在系统中已存在
- 切换后Bot的对话风格会发生变化
- 切换是永久性的，直到下次手动切换

---

### 🔧 临时人格管理命令

#### `/temp_persona` - 临时人格管理
**权限要求**: 管理员  
**功能说明**: 管理临时人格更新，支持多种操作

**支持的操作**:

##### 1. 应用临时人格
```bash
/temp_persona apply "特征1,特征2,特征3" "对话示例1|对话示例2|对话示例3" [持续时间分钟]
```

**参数说明**:
- `特征1,特征2`: 用逗号分隔的人格特征列表
- `对话示例1|对话示例2`: 用竖线分隔的对话示例
- `持续时间分钟`: 可选，默认60分钟

**使用示例**:
```bash
/temp_persona apply "幽默风趣,喜欢开玩笑,活泼开朗" "哈哈，你这个想法很有趣呢！|开什么玩笑，你太逗了哈哈" 120
```

##### 2. 查看临时人格状态
```bash
/temp_persona status
```

**显示信息**:
- 当前临时人格名称
- 剩余持续时间
- 特征数量和对话数量
- 备份文件信息

##### 3. 移除临时人格
```bash
/temp_persona remove
```
立即移除当前临时人格，恢复到原始状态。

##### 4. 延长临时人格时间
```bash
/temp_persona extend [分钟数]
```
延长当前临时人格的持续时间，默认延长30分钟。

**使用示例**:
```bash
/temp_persona extend 60
```

##### 5. 查看备份文件列表
```bash
/temp_persona backup_list
```
显示所有可用的人格备份文件（前10个）。

##### 6. 从备份恢复人格
```bash
/temp_persona restore <备份文件名>
```

**使用示例**:
```bash
/temp_persona restore persona_backup_20240101_120000.json
```

---

### 🛠️ 高级管理命令

#### `/apply_persona_updates` - 应用人格更新文件
**权限要求**: 管理员  
**功能说明**: 读取并应用`persona_updates.txt`文件中的增量人格更新

**使用场景**:
- 批量应用预设的人格更新
- 从外部文件导入人格调整
- 自动化人格优化流程

**使用示例**:
```
/apply_persona_updates
```

**文件格式**: `persona_updates.txt`中应包含要添加的人格特征和对话示例

---

#### `/clean_duplicate_content` - 清理重复内容
**权限要求**: 管理员  
**功能说明**: 清理历史重复的情绪状态和增量更新内容，优化人格提示词

**使用场景**:
- 人格提示词过长时进行优化
- 清理重复的情绪描述
- 保持提示词整洁高效

**使用示例**:
```
/clean_duplicate_content  
```

**清理效果**:
- 移除重复的情绪描述
- 清理冗余的人格特征
- 优化提示词结构
- 同时清空`persona_updates.txt`文件

---

## 💡 命令使用技巧

### 🎯 学习管理最佳实践

1. **定期检查状态**:
   ```bash
   /learning_status  # 每天检查一次学习状态
   ```

2. **数据备份**:
   ```bash
   /export_data     # 每周导出一次数据进行备份
   ```

3. **强制学习时机**:
   - 群聊活跃度突然增加时
   - 添加新的目标用户后
   - 修改学习配置后
   ```bash
   /force_learning
   ```

### ❤️ 好感度系统管理

1. **情绪设置策略**:
   ```bash
   # 早晨设置积极情绪
   /set_mood happy
   
   # 晚上设置平静情绪  
   /set_mood calm
   
   # 特殊活动时设置兴奋情绪
   /set_mood excited
   ```

2. **定期查看好感度**:
   ```bash
   /affection_status  # 了解用户互动情况
   ```

### 🎭 临时人格应用场景

1. **活动期间临时调整**:
   ```bash
   # 聚会时设置活泼人格
   /temp_persona apply "活泼开朗,善于活跃气氛" "大家一起玩游戏吧！|这个活动超级有趣的！" 180
   ```

2. **学习期间设置严肃人格**:
   ```bash
   # 学习讨论时
   /temp_persona apply "认真严谨,专业知识丰富" "让我们专心讨论这个问题|这个知识点很重要" 120
   ```

3. **临时人格管理**:
   ```bash
   # 检查当前状态
   /temp_persona status
   
   # 需要时延长时间
   /temp_persona extend 60
   
   # 活动结束后移除
   /temp_persona remove
   ```

### 🔍 故障排除

1. **学习不工作**:
   ```bash
   /learning_status    # 检查配置状态
   /start_learning     # 尝试手动启动
   /force_learning     # 强制执行一次学习
   ```

2. **数据异常**:
   ```bash
   /analytics_report   # 查看数据分析
   /export_data       # 备份当前数据
   /clean_duplicate_content  # 清理冗余内容
   ```

3. **人格问题**:
   ```bash
   /temp_persona backup_list  # 查看可用备份
   /temp_persona restore <文件名>  # 恢复到之前状态
   ```

---

## ⚠️ 注意事项

1. **权限说明**: 带有管理员权限要求的命令只能由Bot管理员使用
2. **数据安全**: `/clear_data`命令会永久删除数据，使用前请确保已备份
3. **资源消耗**: `/force_learning`和`/analytics_report`命令可能消耗较多计算资源
4. **临时人格**: 临时人格会在指定时间后自动过期，也可手动移除
5. **好感度系统**: 情绪设置会影响用户体验，建议根据群聊氛围合理设置

### 🔄 智能运行逻辑

#### 1. **消息处理流程**
```
用户消息 → QQ过滤 → 消息收集 → 好感度处理 → 增强交互更新 → 实时学习处理
```

#### 2. **好感度系统流程**
```
消息分析 → 交互类型识别 → 好感度计算 → 情绪状态更新 → 系统提示词调整
```

#### 3. **学习循环流程**  
```
消息筛选 → 多维度分析 → 风格提取 → 质量评估 → 人格更新 → 效果验证
```

#### 4. **情感智能流程**
```
情感识别 → 知识图谱更新 → 个性化推荐 → 自适应调整 → 响应生成
```

## 🛠️ 技术栈升级

### 🔥 AI/ML 技术栈
- **大型语言模型**: OpenAI GPT系列、自定义API支持
- **机器学习**: `scikit-learn`、`numpy`、`pandas`
- **情感计算**: 情绪识别、情感状态建模
- **知识图谱**: `networkx`、关系网络分析
- **自然语言处理**: `jieba`、`nltk`、`spacy`

### 📊 数据可视化
- **图表生成**: `plotly`、`matplotlib`、`seaborn`
- **网络可视化**: `bokeh`
- **数据分析**: 多维度统计分析

### 🏗️ 系统架构
- **异步框架**: `asyncio`、`aiohttp`、`aiofiles`
- **数据库**: `aiosqlite`、分布式数据存储
- **Web框架**: `quart`、`quart-cors`
- **缓存系统**: `cachetools`、`redis`

## 📋 详细配置参数解析

本插件提供了丰富的配置选项，支持高度自定义的学习和交互行为。

### 🔧 基础学习设置 (Self_Learning_Basic)

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enable_message_capture` | bool | true | 是否启用消息抓取功能，关闭后插件停止收集新消息 |
| `enable_auto_learning` | bool | true | 是否启用定时自动学习，关闭后需要手动触发学习 |
| `enable_realtime_learning` | bool | false | 是否在收到消息时立即处理，会增加实时负载 |
| `enable_web_interface` | bool | true | 是否启用Web管理界面用于查看和管理学习数据 |

### 🎯 目标设置 (Target_Settings)

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `target_qq_list` | list | [] | 指定要学习的QQ号列表，为空则学习所有用户消息 |
| `current_persona_name` | string | "default" | 插件将学习并优化此人格的对话风格 |

### 🤖 模型配置 (Model_Configuration)

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `filter_model_name` | string | "gpt-4o-mini" | 用于初步筛选消息的弱模型，建议使用速度快、成本低的模型 |
| `refine_model_name` | string | "gpt-4o" | 用于深度分析和提炼对话风格的强模型 |
| `reinforce_model_name` | string | "gpt-4o" | 用于强化学习的LLM模型 |
| `filter_provider_id` | string | null | 筛选模型的LLM提供商ID，为空使用默认提供商 |
| `refine_provider_id` | string | null | 提炼模型的LLM提供商ID，为空使用默认提供商 |
| `reinforce_provider_id` | string | null | 强化模型的LLM提供商ID，为空使用默认提供商 |
| `filter_api_url` | string | null | 自定义筛选模型的API接口地址 |
| `filter_api_key` | string | null | 自定义筛选模型的API密钥 |
| `refine_api_url` | string | null | 自定义提炼模型的API接口地址 |
| `refine_api_key` | string | null | 自定义提炼模型的API密钥 |
| `reinforce_api_url` | string | null | 自定义强化模型的API接口地址 |
| `reinforce_api_key` | string | null | 自定义强化模型的API密钥 |

### ⏰ 学习参数 (Learning_Parameters)

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `learning_interval_hours` | int | 6 | 自动学习的时间间隔，单位为小时 |
| `min_messages_for_learning` | int | 50 | 开始学习所需的最少消息数量 |
| `max_messages_per_batch` | int | 200 | 单次学习处理的最大消息数量，避免一次处理过多消息 |

### 🔍 筛选参数 (Filter_Parameters)

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `message_min_length` | int | 5 | 参与学习的消息最小字符长度 |
| `message_max_length` | int | 500 | 参与学习的消息最大字符长度 |
| `confidence_threshold` | float | 0.7 | 消息筛选的置信度阈值，0-1之间，越高越严格 |

### 🎨 风格分析 (Style_Analysis)

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `style_analysis_batch_size` | int | 100 | 单次风格分析处理的消息数量 |
| `style_update_threshold` | float | 0.8 | 触发人格风格更新的置信度阈值，0-1之间 |

### 🔬 机器学习设置 (Machine_Learning_Settings)

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enable_ml_analysis` | bool | true | 是否启用scikit-learn进行文本聚类和行为分析 |
| `max_ml_sample_size` | int | 100 | 机器学习分析的最大样本数量，控制资源使用 |
| `ml_cache_timeout_hours` | int | 1 | 机器学习分析结果的缓存时间 |


### 💾 人格备份设置 (Persona_Backup_Settings)

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `auto_backup_enabled` | bool | true | 是否在人格更新前自动创建备份 |
| `backup_interval_hours` | int | 24 | 自动备份的时间间隔 |
| `max_backups_per_group` | int | 10 | 每个群保留的最大备份数量 |

### ❤️ 好感度系统设置 (Affection_System_Settings)

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enable_affection_system` | bool | true | 是否启用用户好感度和情绪响应系统 |
| `max_total_affection` | int | 250 | bot对所有用户的总好感度上限值 |
| `max_user_affection` | int | 100 | 单个用户可获得的最大好感度 |
| `affection_decay_rate` | float | 0.95 | 好感度重新分配时的衰减比例，0-1之间 |
| `daily_mood_change` | bool | true | 是否每天随机更换bot的情绪状态 |
| `mood_affect_affection` | bool | true | 当前情绪是否影响好感度变化幅度 |

### 🎭 情绪系统设置 (Mood_System_Settings)

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enable_daily_mood` | bool | true | 是否启用每日随机情绪系统 |
| `mood_change_hour` | int | 6 | 每日更新情绪的小时(0-23) |
| `mood_persistence_hours` | int | 24 | 每次情绪状态持续的小时数 |

### ⚙️ 高级设置 (Advanced_Settings)

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `debug_mode` | bool | false | 启用详细的调试日志输出 |
| `save_raw_messages` | bool | true | 是否保存未经处理的原始消息用于分析 |
| `auto_backup_interval_days` | int | 7 | 学习数据自动备份的间隔天数，0为禁用 |

### 💡 配置建议

1. **生产环境建议**: 
   - 关闭 `debug_mode` 以提高性能
   - 适当调整 `learning_interval_hours` 避免过于频繁的学习
   - 根据服务器性能调整 `max_messages_per_batch`

2. **开发测试建议**:
   - 启用 `debug_mode` 便于调试
   - 降低 `min_messages_for_learning` 快速测试学习功能
   - 启用 `enable_realtime_learning` 实时查看效果

3. **资源优化建议**:
   - 合理设置 `max_ml_sample_size` 控制内存使用
   - 调整 `ml_cache_timeout_hours` 平衡性能与实时性
   - 定期清理过期备份，控制存储空间

### 新增配置项

#### 好感度系统配置
```python
enable_affection_system: bool = True      # 启用好感度系统
max_total_affection: int = 250           # bot总好感度上限
max_user_affection: int = 100            # 单用户好感度上限  
affection_decay_rate: float = 0.95       # 好感度衰减比例
daily_mood_change: bool = True           # 启用每日情绪变化
mood_affect_affection: bool = True       # 情绪影响好感度变化
```

#### 情绪系统配置
```python
enable_daily_mood: bool = True           # 启用每日情绪
mood_change_hour: int = 6                # 情绪更新时间（24小时制）  
mood_persistence_hours: int = 24         # 情绪持续时间
```

#### Web界面配置
```python
enable_web_interface: bool = True        # 启用Web管理界面
web_interface_port: int = 7833          # Web界面端口
```

## 💾 数据管理架构升级

### 🗄️ 数据库设计

#### 新增数据表
- **`user_affection`**: 用户好感度记录
- **`bot_mood`**: bot情绪状态历史  
- **`affection_history`**: 好感度变化记录
- **`emotion_profiles`**: 用户情感档案
- **`knowledge_entities`**: 知识实体库
- **`user_preferences`**: 用户偏好设置
- **`conversation_contexts`**: 对话上下文管理

### 🔐 数据隐私与安全
- **本地存储**: 所有数据本地化，确保隐私安全
- **数据加密**: 敏感信息加密存储
- **访问控制**: Web界面密码保护
- **数据备份**: 自动备份与恢复机制

## 🚀 部署与使用

### 环境准备
1. 确保已安装 Python 3.8+ 
2. 安装项目依赖：
   ```bash
   pip install -r astrabot_plugin_self_learning/requirements.txt
   ```

### 快速开始
1. 将插件添加到AstrBot插件目录
2. 启动AstrBot，插件将自动加载
3. 访问Web管理界面：`http://localhost:7833`
4. 使用默认密码登录并立即修改密码
5. 在Astrbot后台插件管理中设置插件配置项

## 🎯 智能特性展示

### ❤️ 情感智能系统
- **动态好感度**: 根据用户互动自动调节好感度
- **情绪识别**: 智能识别夸赞、鼓励、侮辱、骚扰等交互类型
- **情绪响应**: bot情绪会根据用户行为动态变化
- **情感融入**: 当前情绪状态影响AI回复的语调和内容

### 📊 数据可视化分析
- **学习轨迹图**: 可视化学习进度和质量变化
- **用户行为热力图**: 分析用户活跃模式
- **社交网络图**: 展示群内用户关系网络
- **情感趋势分析**: 跟踪群聊情感氛围变化

### 🧠 智能学习机制
- **场景感知**: 根据不同场景自动切换最适合的人格
- **增量学习**: 持续学习新知识，不遗忘历史经验  
- **质量监控**: 实时评估学习效果，自动调优
- **个性化推荐**: 基于用户偏好推荐话题和回复策略

## 🤝 贡献指南

欢迎开发者参与项目建设！
- **Bug反馈**: 使用GitHub Issues报告问题
- **功能建议**: 提交Feature Request  
- **代码贡献**: Fork项目并提交Pull Request
- **文档改进**: 帮助完善文档和教程
