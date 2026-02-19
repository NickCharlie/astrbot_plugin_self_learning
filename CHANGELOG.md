# 🧧 新年快乐！Happy Lunar New Year!

> 祝所有用户和社区贡献者马年大吉、万事如意！

---

# Changelog

所有重要更改都将记录在此文件中。

## [Next-1.2.8] - 2026-02-19

### 🔧 Bug 修复

#### WebUI 服务器端口占用
- 将 WebUI 服务器从 `asyncio.create_task` 改为独立守护线程模式运行 Hypercorn
- 采用旧版经过验证的线程方案，确保 Windows/macOS/CentOS/Ubuntu 等系统上重启时端口可靠释放
- 使用 `SecureConfig` 创建带 `SO_REUSEADDR` + `SO_REUSEPORT` + `set_inheritable(False)` 的 socket
- 保留跨平台端口清理（Windows `taskkill` / Linux `lsof` + `kill -9`）

#### 单例重启问题
- 插件 `terminate()` 时重置 `MemoryGraphManager` 单例状态，防止重启后使用失效的 LLM 适配器
- `Server.stop()` 重置单例状态，确保重新初始化

#### WebUI 学习按钮异常
- 修复 `trigger_learning` 方法不存在的错误，改为正确的 `start_learning` 方法

#### MemoryGraphManager 空指针
- 为 `llm_adapter` 增加二次空值检查，防止并发场景下 `generate_response` 调用失败

### 📝 其他

- README（中英文）重写为卖点导向，突出功能价值，移除技术实现细节
- `persona_web_manager` 常规日志从 INFO 降级为 DEBUG，减少日志噪音
- 版本号更新至 Next-1.2.8

---

## [Next-1.2.5] - 2026-02-19

### 🎯 新功能

#### MacOS-Web-UI 桌面框架迁移
- 前端从 ModderUI 整体重写为 macOS 风格桌面模拟器
- 每个管理页面变为独立 macOS「应用窗口」，支持拖拽、缩放、最小化、最大化、层叠
- 基于 Vue 3 + Element Plus + Vuex 4 自托管加载（无 Node.js 构建步骤）
- 9 个业务应用：仪表盘、系统设置、学习状态、人格审查、人格管理、对话风格、社交关系、黑话学习、Bug反馈
- macOS 风格 Dock 栏、启动台、菜单栏、启动动画、登录界面

#### 状态栏实时指标
- 菜单栏实时显示消息总数和学习效率
- 每 30 秒自动刷新

#### 人格审查服务端分页
- 后端接受 `limit`/`offset` 参数，返回分页数据和 `total` 总数
- 前端仅加载当前页数据，翻页时按需加载
- 消除一次性加载全部记录的性能问题

#### 多配置人格支持
- 支持多份人格配置并行管理，可选自动应用
- 审批流程和批量审查接口中集成自动应用逻辑

### 🔧 Bug 修复

#### 前端运行时错误
- 修复 `styleProgress.map is not a function`：SQLAlchemy `get_style_progress_data()` 错误返回 Dict 而非 List，重写为通过 ORM 查询 `learning_batches` 表
- 修复 `id.substring is not a function`：`shortId()`、`escapeHtml()`、`truncateText()`、`getContentPreview()`、`getProposedPreviewHtml()` 统一增加 `String()` 类型转换
- 修复 `SocialRelationAnalyzer.analyze_group_relations` 方法名错误，改为 `analyze_group_social_relations`
- 修复 `get_jargon_statistics()` 传入无效 `chat_id` 参数
- 在 StyleLearning.js 和 Dashboard.js 中增加 `Array.isArray()` 防御检查

#### 后端与数据库
- 解决跨线程数据库访问时的 asyncio 事件循环冲突
- 处理 MySQL Boolean 列类型和默认值兼容问题
- 将 `kg_relations` VARCHAR 缩短至 191 以适配 MySQL utf8mb4 索引限制
- WebUI 数据库方法委托到 ORM 版本
- 修复知识图谱、记忆图谱、WebUI 服务器初始化错误
- 所有入口路由统一指向 `macos.html`

#### WebUI 界面修复
- 修复登录卡片大小和布局溢出
- 修复人格审查、风格学习、社交关系数据获取
- 修复深色模式切换、壁纸上传、Bug反馈图标
- 全局替换 Apple 图标为项目 Logo
- 跳过启动动画直接进入登录页
- Dock 添加计算器、修复启动台图标

### 📱 移动端适配
- Dock 图标增大（768px 下 40px，480px 下 36px）
- 关闭/最小化/最大化按钮增大（768px 下 18px，480px 下 16px）
- 菜单栏和标题栏高度增加，改善触控体验
- 桌面和启动台改为单击打开应用（原为双击）

### 🔧 重构
- WebUI 中全部 legacy raw SQL 替换为 ORM 查询
- 新增强化学习和 ML 分析器的 ORM 方法
- 实现基于 ORM 的黑话 CRUD 方法
- Repository 层 dict/list 自动 JSON 序列化
- WebUI 蓝图拆分为模块化包（原为单体 webui.py）
- ModderUI CSS 框架（iOS 液态玻璃主题，迁移过渡阶段）

### 📝 其他
- 版本号更新至 Next-1.2.5
- 移除废弃的注册装饰器（@SXP-Simon）
- CI 提交信息长度限制提升至 128 字符

---

## [Next-1.2.0] - 2026-02-18

### 🔥 关键修复

#### WebUI 跨线程数据库访问崩溃 (Critical)
- **根因**：WebUI 运行在独立线程的独立事件循环中，调用 legacy `get_db_connection()` 时触发 `RuntimeError: Task got Future attached to a different loop`
- **修复**：为 `DatabaseEngine` 实现按事件循环隔离的引擎池，非主线程自动创建独立 SQLAlchemy 引擎（NullPool），WebUI 的所有数据库操作改用 ORM

#### 强化学习保存 TypeError (Critical)
- **根因**：ORM Repository 层将 dict/list 直接赋给 Text 列，触发 `TypeError: dict can not be used as parameter`
- **修复**：在 `ReinforcementLearningRepository`、`PersonaFusionRepository`、`StrategyOptimizationRepository` 中添加 `json.dumps()` 序列化

#### 黑话学习无法保存数据
- **根因**：`insert_jargon`/`update_jargon`/`get_jargon` 未在 `SQLAlchemyDatabaseManager` 中实现，通过 `__getattr__` 委托给 legacy 代码，datetime 对象与 BigInteger 列类型不兼容导致静默失败
- **修复**：在 `SQLAlchemyDatabaseManager` 中实现 ORM 版本的三个黑话 CRUD 方法，自动处理时间戳类型转换

### 🔧 重构

#### WebUI 全面 ORM 迁移
- 替换 `webui.py` 中全部 10 处 `get_db_connection()` 原始 SQL 为 ORM 查询
- 涉及路由：`relearn_all`、`get_groups_info`、`analyze_all_groups`、`style_learning_all`、`expression_patterns`、`clear_group_social_relations`、`toggle_jargon_global` 等

#### ML 分析器 ORM 迁移
- 替换 `ml_analyzer.py` 中 3 处 `get_db_connection()` 为 ORM 查询
- `_get_user_messages`、`_get_recent_group_messages`、`_get_most_active_users` 改用 `RawMessage` ORM 模型

#### 强化学习方法 ORM 实现
- 在 `SQLAlchemyDatabaseManager` 新增 10 个 ORM 方法，拦截原本会委托给 legacy 的调用
- 包括：`get_learning_history_for_reinforcement`、`save_reinforcement_learning_result`、`get_persona_fusion_history`、`save_persona_fusion_result`、`get_learning_performance_history`、`save_learning_performance_record`、`save_strategy_optimization_result`、`get_messages_for_replay`、`get_message_statistics`

### 📝 其他
- 新增 `CONTRIBUTING.md`，规范 Conventional Commits 提交格式
- 新增 PR 提交信息 lint CI
- 登录界面适配移动端（@Radiant303）
- 精简 metadata.yaml 描述
- 更新版本号至 Next-1.2.0

### 📊 统计
- **变更文件**：main.py、webui.py、ml_analyzer.py、sqlalchemy_database_manager.py、reinforcement_repository.py、engine.py
- **新增约 500 行 ORM 代码**，替代 legacy raw SQL 调用

---

## [Next-1.1.9] - 2026-02-17

### 🔥 关键修复

#### SQLite 模式完全不可用 (Critical)
- **根因**：`_check_and_migrate_database()` 在首次启动时对不存在的数据库执行迁移，导致 `on_load()` 崩溃，`db_manager.start()` 永远不会执行
- **表现**：所有数据库操作报错 `数据库管理器未启动，engine不存在`
- **修复**：彻底移除数据库迁移系统，表结构由 SQLAlchemy ORM `Base.metadata.create_all` 幂等创建

#### 群聊限制不生效 (#28)
- **根因**：`_get_active_groups()` 查询所有群组时未应用 `target_qq_list` 白名单和 `target_blacklist` 黑名单
- **修复**：为 `QQFilter` 新增 `get_allowed_group_ids()` / `get_blocked_group_ids()` 方法，在三级渐进查询（24h → 7d → 全量）中统一应用 `.in_()` / `.notin_()` 过滤

#### 命令报错 (#24)
- **根因**：`/persona_info` 等命令引用了不存在的方法 `PersonaUpdater.format_current_persona_display`
- **修复**：移除 11 个已废弃命令，保留 6 个核心命令

#### 启动竞态条件
- 为 `on_message()` 添加数据库就绪检查，在 `on_load()` 完成前跳过消息处理，防止 "engine不存在" 错误

#### LLM 空响应崩溃
- `prompt_sanitizer.sanitize_response()` 在 LLM 返回 `None` 时触发 `TypeError`，已添加空值保护

### 🗑️ 移除

#### 数据库迁移系统 (完整移除)
- 删除 `utils/migration_tool.py`（v1 迁移工具）
- 删除 `utils/migration_tool_v2.py`（SmartDatabaseMigrator）
- 删除 `test_migration_quick.py`（迁移测试）
- 移除 `engine.py` 中的 `migrate_schema()`、`_migrate_mysql()`、`_migrate_sqlite()`
- 移除 `sqlite_backend.py`、`mysql_backend.py` 中的迁移调用
- 移除 `main.py` 中的 `_check_and_migrate_database()`、`_get_database_url()`、`_mask_url()`

#### 废弃命令 (11 个)
- `clear_data`、`export_data`、`analytics_report`
- `persona_switch`、`persona_info`、`temp_persona`
- `apply_persona_updates`、`switch_persona_update_mode`
- `clean_duplicate_content`、`migrate_database`、`db_status`

### ✅ 保留命令 (6 个)
- `learning_status`、`start_learning`、`stop_learning`
- `force_learning`、`affection_status`、`set_mood`

### 📝 其他
- 更新 README 标题和版本徽章至 Next-1.1.9
- 更新 `.gitignore` 排除导出目录

### 🤝 致谢
- 感谢 @NieiR 和 @sdfsfsk 在早期版本中的社区贡献

### 📊 统计
- **净减少约 2600 行代码**，删除 3 个文件
- **变更文件**：main.py、engine.py、factory.py、sqlite_backend.py、mysql_backend.py、prompt_sanitizer.py

---

## [Next-1.1.5] - 2026-01-17

### 🎯 新功能

#### 目标驱动对话系统
- **38种预设对话目标类型**，涵盖情感支持、知识问答、日常对话等8大类场景
- **智能目标识别与切换**，自动分析用户意图并调整对话策略
- **动态阶段规划**，根据对话进展自动调整互动流程
- **会话隔离机制**，基于 `MD5(group_id + user_id + date)` 实现24小时独立会话
- **RESTful API接口**，提供对话目标管理的编程接口

详细说明：
- 预设对话目标类型包括：情感支持（安慰、共情、鼓励等）、知识交流（答疑、科普、推荐等）、日常互动（闲聊、玩笑、吐槽等）
  更多类型交由LLM自主创建
- 拆解对话目标为阶段性目标，引导聊天对话朝目标靠近
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
