# Changelog

所有重要更改都将记录在此文件中。

## [Next-1.1.5] - 2026-01-17

### 🎯 新功能

#### 目标驱动对话系统
- **38种预设对话目标类型**，涵盖情感支持、知识问答、日常对话等8大类场景
- **智能目标识别与切换**，自动分析用户意图并调整对话策略
- **动态阶段规划**，根据对话进展自动调整互动流程
- **会话隔离机制**，基于 `MD5(group_id + user_id + date)` 实现24小时独立会话
- **完整的WebUI管理界面**，支持会话查看、目标统计、历史追踪
- **RESTful API接口**，提供对话目标管理的编程接口

详细说明：
- 对话目标类型包括：情感支持（安慰、共情、鼓励等）、知识交流（答疑、科普、推荐等）、日常互动（闲聊、玩笑、吐槽等）
- 自动检测对话主题变化和阶段完成信号，智能切换目标
- 集成到主消息流程，通过社交上下文注入器自动增强对话上下文

#### Guardrails-AI 集成
- **Pydantic模型验证**，为 LLM 输出提供类型安全保障
- **GoalAnalysisResult 模型**，验证对话目标分析结果（目标类型、话题、置信度）
- **ConversationIntentAnalysis 模型**，验证对话意图分析（目标切换、阶段完成、用户参与度等9个字段）
- **自动类型转换**，兼容 guardrails-ai 返回的多种数据类型（dict/Pydantic实例）
- **增强错误诊断**，详细的验证失败日志和响应预览

### 🔧 重要修复

#### LLM适配器延迟初始化
- **非阻塞式加载**：插件加载时 Provider 未就绪不再抛出异常
- **延迟初始化机制**：首次 LLM 调用时自动尝试初始化 Provider
- **优雅降级**：Provider 配置失败时只记录 WARNING，不影响插件其他功能
- 修复了 "创建框架LLM适配器失败：无法配置任何LLM提供商" 错误

#### 字符串索引越界修复
- 修复 `prompt_sanitizer.py` 中 LCS 算法的索引错误
- 添加空字符串检查和实际长度重新计算
- 解决了 `string index out of range` 崩溃问题

#### Pydantic 类型错误修复
- 修复 `'dict' object has no attribute 'goal_type'` 错误
- 在 `parse_json_direct`、`parse_goal_analysis`、`parse_intent_analysis` 中添加类型检查
- 自动将 dict 转换为 Pydantic 模型实例

#### 参数传递修复
- 修复 `goal_manager` 未传递到 `SocialContextInjector` 的问题
- 确保对话目标上下文能正确注入到 LLM 请求中

### 📝 文档更新

- **README.md 完整重构**（+175行）
  - 添加目标驱动对话系统详细说明
  - 38种对话目标类型列表和示例
  - 工作流程图和API端点文档
  - 配置项说明（Goal_Driven_Chat_Settings）
- **GitHub 项目描述优化**，突出目标驱动、俚语理解、社交关系管理等核心功能

### 🐛 Bug修复与优化

- **异常处理增强**：为对话目标管理器的3个 LLM 调用方法添加独立 try-except 块
- **日志优化**：关键步骤从 DEBUG 提升到 INFO 级别，添加对话目标上下文注入验证日志
- **JSON 解析改进**：添加空响应检查、响应长度记录、失败时显示前200字符预览
- **配置加载修复**：正确加载 `Goal_Driven_Chat_Settings` 到 `PluginConfig`
- **Guardrails 参数修复**：移除 `validate_and_clean_json()` 的错误 `fallback` 参数

### 🔨 技术改进

- **模型策略**：对话目标分析统一使用提炼（refine）模型，提升准确性
- **类型安全**：全面采用 Pydantic 验证替代简单 JSON 清洗
- **诊断能力**：添加目标驱动对话系统初始化诊断日志
- **代码质量**：改进错误处理、日志记录、参数验证

### 📊 统计

- **18个提交**，涵盖新功能开发、Bug修复、文档更新
- **核心文件变更**：
  - 新增 `services/conversation_goal_manager.py`（对话目标管理器）
  - 新增 `repositories/conversation_goal_repository.py`（数据访问层）
  - 增强 `utils/guardrails_manager.py`（Pydantic模型集成）
  - 优化 `core/factory.py`（延迟初始化）
  - 优化 `core/framework_llm_adapter.py`（重试机制）

---

## [Previous Versions]

更早版本的更新日志请参考 Git 历史记录。
