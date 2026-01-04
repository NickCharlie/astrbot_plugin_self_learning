# 数据库迁移系统 - 本地测试指南

## 🧪 测试准备

### 测试环境
- 分支: `next-gen-develop`
- 数据库类型: SQLite / MySQL
- Python 环境: 需要安装 aiosqlite / aiomysql

---

## 📋 测试场景

### 场景 1: 全新安装测试 ✨

**目的**: 验证全新安装时，系统直接创建新表结构，不执行迁移

**步骤**:
1. 确保没有旧的数据库文件
```bash
# 备份现有数据库（如果存在）
mv data/database.db data/database.db.old_backup 2>/dev/null || true
```

2. 启动插件，观察日志

**预期日志输出**:
```
📦 [数据库] 使用 SQLAlchemy 版本的数据库管理器（支持自动迁移）
✅ 数据库文件不存在,这是全新安装,无需迁移
======================================================================
🔍 开始数据库表结构验证
======================================================================
需要验证 21 个表
🆕 新建 21 个表: user_affections, affection_interactions, memories, ...
======================================================================
✅ 所有表结构验证通过
======================================================================
```

**验证要点**:
- ✅ 日志显示"使用 SQLAlchemy 版本的数据库管理器（支持自动迁移）"
- ✅ 日志显示"数据库文件不存在,这是全新安装,无需迁移"
- ✅ 直接创建 21 个新表
- ✅ 没有执行迁移流程

---

### 场景 2: 从旧版本升级测试 🔄

**目的**: 验证从旧版本数据库升级时，系统能正确迁移数据

**步骤**:

1. 准备旧版本数据库
```bash
# 方法 1: 使用旧版本备份
cp /path/to/old/database.db data/database.db

# 方法 2: 使用 astrbot_plugin_self_learning-main 的数据库
cp ../astrbot_plugin_self_learning-main/data/database.db data/database.db
```

2. 检查旧数据库中是否有需要迁移的表
```bash
sqlite3 data/database.db "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('persona_update_reviews', 'style_learning_reviews', 'expression_patterns');"
```

3. 启动插件，观察迁移流程

**预期日志输出**:
```
📦 [数据库] 使用 SQLAlchemy 版本的数据库管理器（支持自动迁移）
🔍 检测到需要数据库迁移,开始执行...
======================================================================
🔄 开始数据库迁移流程
======================================================================
[步骤 1/5] 备份数据库 (强制执行)...
  ✅ SQLite 数据库已备份 (125.34 KB)
✅ 数据库已备份到: data/backups/database.db.backup_20251231_123456

[步骤 2/5] 检查现有表...
  📋 已存在的表: persona_update_reviews, style_learning_reviews, expression_patterns

[步骤 3/5] 创建新表结构...
  ✅ 所有新表结构已创建

[步骤 4/5] 迁移兼容数据...
  🔄 迁移表: persona_update_reviews -> persona_update_reviews
    - 找到 15 条记录
    ✅ 成功迁移 15 条记录
  🔄 迁移表: style_learning_reviews -> style_learning_reviews
    - 找到 8 条记录
    ✅ 成功迁移 8 条记录
  🔄 迁移表: expression_patterns -> expression_patterns
    - 找到 20 条记录
    ✅ 成功迁移 20 条记录

[步骤 5/5] 验证迁移结果...
  📊 迁移统计:
    - persona_update_reviews: 15 条记录
    - style_learning_reviews: 8 条记录
    - expression_patterns: 20 条记录
  ✅ 总计迁移: 43 条记录
======================================================================
✅ 数据迁移完成! 耗时: 2.34 秒
======================================================================

======================================================================
🔍 开始数据库表结构验证
======================================================================
需要验证 21 个表
✅ 验证 21 个已存在的表
✅ 所有表结构验证通过
======================================================================
```

**验证要点**:
- ✅ 检测到需要迁移
- ✅ 强制执行备份（即使 backup=False 也会备份）
- ✅ 备份文件保存在 `data/backups/` 目录
- ✅ 迁移 3 个关键表的数据
- ✅ 迁移记录数正确
- ✅ 表结构验证通过

**验证备份文件**:
```bash
# 检查备份文件是否存在
ls -lh data/backups/

# 验证备份文件可用性
sqlite3 data/backups/database.db.backup_* "SELECT count(*) FROM persona_update_reviews;"
```

---

### 场景 3: 重新启动测试 🔁

**目的**: 验证已迁移的数据库重新启动时，不会重复迁移

**步骤**:

1. 在场景 2 完成后，直接重启插件

2. 观察日志

**预期日志输出**:
```
📦 [数据库] 使用 SQLAlchemy 版本的数据库管理器（支持自动迁移）
✅ 表 persona_update_reviews 已有数据,可能已迁移,跳过迁移
✅ 数据库结构已是最新,无需迁移

======================================================================
🔍 开始数据库表结构验证
======================================================================
需要验证 21 个表
✅ 验证 21 个已存在的表
✅ 所有表结构验证通过
======================================================================
```

**验证要点**:
- ✅ 检测到已有数据，跳过迁移
- ✅ 没有创建新的备份文件
- ✅ 直接进入表结构验证
- ✅ 启动速度快

---

## 🔍 手动验证数据完整性

### 验证迁移后的数据

```bash
# 连接到数据库
sqlite3 data/database.db

# 检查表是否存在
.tables

# 验证迁移的数据
SELECT COUNT(*) FROM persona_update_reviews;
SELECT COUNT(*) FROM style_learning_reviews;
SELECT COUNT(*) FROM expression_patterns;

# 查看数据样例
SELECT * FROM persona_update_reviews LIMIT 3;

# 检查新表是否创建
SELECT COUNT(*) FROM memories;
SELECT COUNT(*) FROM user_affections;
SELECT COUNT(*) FROM composite_psychological_states;

# 退出
.exit
```

### 对比旧数据库和新数据库

```bash
# 查看旧数据库
sqlite3 data/backups/database.db.backup_* "SELECT COUNT(*) FROM persona_update_reviews;"

# 查看新数据库
sqlite3 data/database.db "SELECT COUNT(*) FROM persona_update_reviews;"

# 数量应该一致
```

---

## 🐛 故障排查

### 问题 1: 仍然使用传统数据库管理器

**症状**:
```
[Plug] [INFO] 📦 [数据库] 使用传统版本的数据库管理器
```

**原因**: 可能配置文件中还存在旧的 `use_sqlalchemy: false` 配置

**解决方案**:
```bash
# 检查配置文件
grep -r "use_sqlalchemy" .

# 删除旧配置，重新生成
rm config.json  # 备份后删除
# 重启插件会自动生成新配置
```

---

### 问题 2: 迁移失败

**症状**:
```
❌ 数据迁移失败: [错误信息]
💡 如果需要恢复数据,请使用备份文件: data/backups/database.db.backup_xxx
```

**排查步骤**:
1. 检查备份文件是否存在
```bash
ls -lh data/backups/
```

2. 恢复备份
```bash
cp data/backups/database.db.backup_* data/database.db
```

3. 查看详细错误日志
```bash
# 检查插件日志
tail -n 100 logs/astrbot.log
```

4. 手动测试迁移工具
```bash
cd /Users/nickmo/code/Astrbot-Projects/astrbot_plugin_self_learning
python -m utils.migration_tool sqlite:///./data/database.db sqlite
```

---

### 问题 3: 表结构验证失败

**症状**:
```
⚠️  发现 3 个表存在结构差异
⚠️  缺失字段: xxx
```

**原因**: 旧表结构与新 ORM 定义不一致

**解决方案**:
系统会自动尝试修复（添加缺失字段），如果无法自动修复：
```bash
# 方法 1: 手动运行表结构验证器
python -m utils.schema_validator sqlite:///./data/database.db sqlite

# 方法 2: 如果数据不重要，删除旧表，重新创建
# 注意：这会丢失数据！
```

---

## ✅ 测试检查清单

完成所有测试后，请确认：

- [ ] 场景 1（全新安装）- 日志正确，不执行迁移
- [ ] 场景 1 - 创建了 21 个新表
- [ ] 场景 2（升级）- 执行了备份
- [ ] 场景 2 - 备份文件存在且可用
- [ ] 场景 2 - 迁移了 3 个表的数据
- [ ] 场景 2 - 数据记录数一致
- [ ] 场景 2 - 创建了新表
- [ ] 场景 3（重启）- 跳过迁移
- [ ] 场景 3 - 没有创建新备份
- [ ] 所有场景日志显示"使用 SQLAlchemy 版本的数据库管理器（支持自动迁移）"
- [ ] 数据完整性验证通过
- [ ] 插件功能正常运行

---

## 📝 测试报告模板

完成测试后，可以使用以下模板记录结果：

```markdown
## 测试环境
- 系统: macOS / Linux / Windows
- Python 版本: 3.x.x
- 数据库类型: SQLite / MySQL
- 分支: next-gen-develop
- 测试时间: 2025-12-31

## 场景 1: 全新安装
- 状态: ✅ 通过 / ❌ 失败
- 日志: [贴上关键日志]
- 备注:

## 场景 2: 升级迁移
- 状态: ✅ 通过 / ❌ 失败
- 迁移记录数:
  - persona_update_reviews: xx 条
  - style_learning_reviews: xx 条
  - expression_patterns: xx 条
- 备份路径: data/backups/xxx
- 日志: [贴上关键日志]
- 备注:

## 场景 3: 重新启动
- 状态: ✅ 通过 / ❌ 失败
- 日志: [贴上关键日志]
- 备注:

## 数据验证
- 表数量: 21 个
- 数据完整性: ✅ 一致 / ❌ 有差异
- 备注:

## 问题和建议
[记录遇到的问题和改进建议]
```

---

**测试完成后，请将测试报告反馈，以便进一步优化！** 🎉
