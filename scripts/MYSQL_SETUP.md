# MySQL 数据库表结构初始化指南

## 问题说明

由于已废弃自动迁移功能，MySQL 数据库表需要手动创建。本文档提供了从 ORM 模型生成的完整建表 SQL 脚本。

## 表结构来源

所有表结构统一由 SQLAlchemy ORM 模型定义，位于：

- `models/orm/message.py` - 消息相关表
- `models/orm/psychological.py` - 心理状态表
- `models/orm/social_relation.py` - 社交关系表
- `models/orm/affection.py` - 好感度表
- `models/orm/memory.py` - 记忆表
- `models/orm/learning.py` - 学习记录表
- `models/orm/expression.py` - 表达模式表
- `models/orm/jargon.py` - 黑话表
- `models/orm/social_analysis.py` - 社交分析表
- `models/orm/performance.py` - 性能记录表

## 初始化步骤

### 方法 1: 执行完整建表脚本（推荐）

```bash
# 1. 执行 ORM 模型表（27个表）
mysql -h 47.121.138.217 -P 13307 -u root -p < scripts/mysql_schema.sql

# 2. 执行传统表（23个表）
mysql -h 47.121.138.217 -P 13307 -u root -p < scripts/mysql_schema_additional.sql
```

**说明**:
- `mysql_schema.sql` 包含从 ORM 模型生成的 27 个核心表
- `mysql_schema_additional.sql` 包含尚未迁移到 ORM 的 23 个传统表

### 方法 2: 通过 MySQL 客户端导入

```bash
# 登录 MySQL
mysql -h 47.121.138.217 -P 13307 -u root -p

# 执行脚本
mysql> source /path/to/scripts/mysql_schema.sql;
```

### 方法 3: 重新生成 SQL 脚本

如果修改了 ORM 模型，需要重新生成 SQL：

```bash
# 运行生成脚本
python scripts/generate_mysql_schema.py

# 执行新生成的 SQL
mysql -h 47.121.138.217 -P 13307 -u root -p < scripts/mysql_schema.sql
```

## 包含的表（共 27 个）

### 消息系统 (3)
- `raw_messages` - 原始消息
- `filtered_messages` - 筛选后消息
- `bot_messages` - Bot 消息

### 好感度系统 (4)
- `user_affections` - 用户好感度
- `affection_interactions` - 好感度交互记录
- `user_conversation_history` - 对话历史
- `user_diversity` - 用户多样性

### 记忆系统 (3)
- `memories` - 记忆
- `memory_embeddings` - 记忆向量
- `memory_summaries` - 记忆摘要

### 心理状态系统 (3)
- `composite_psychological_states` - 复合心理状态
- `psychological_state_components` - 心理状态组件
- `psychological_state_history` - 心理状态历史

### 社交关系系统 (6)
- `social_relations` - 社交关系
- `user_social_profiles` - 用户社交档案
- `user_social_relation_components` - 用户社交关系组件
- `social_relation_history` - 社交关系历史
- `social_relation_analysis_results` - 社交关系分析结果
- `social_network_nodes` - 社交网络节点
- `social_network_edges` - 社交网络边

### 学习系统 (4)
- `persona_update_reviews` - 人格更新审查
- `style_learning_reviews` - 风格学习审查
- `style_learning_patterns` - 风格学习模式
- `interaction_records` - 交互记录

### 其他系统 (4)
- `expression_patterns` - 表达模式
- `jargon` - 黑话
- `learning_performance_history` - 学习性能历史

## 验证安装

执行 SQL 后，验证表是否创建成功：

```sql
-- 查看所有表
SHOW TABLES;

-- 应该看到 27 个表

-- 检查某个表的结构
DESC raw_messages;
DESC composite_psychological_states;
```

## 注意事项

1. **字符集**: 所有表使用 `utf8mb4` 字符集，支持完整的 Unicode 字符（包括 emoji）
2. **引擎**: 所有表使用 `InnoDB` 引擎，支持事务和外键
3. **索引**: SQL 脚本包含所有必要的索引，无需手动添加
4. **外键**: 部分表有外键约束，删除表时需注意顺序

## 故障排除

### 问题 1: 表已存在

如果表已存在，SQL 脚本会先执行 `DROP TABLE IF EXISTS`，自动删除旧表。

**警告**: 这会删除所有数据！如需保留数据，请先备份：

```bash
mysqldump -h 47.121.138.217 -P 13307 -u root -p astrbot_self_learning > backup.sql
```

### 问题 2: 权限不足

确保 MySQL 用户有足够权限：

```sql
GRANT ALL PRIVILEGES ON astrbot_self_learning.* TO 'root'@'%';
FLUSH PRIVILEGES;
```

### 问题 3: 连接失败

检查配置文件 `_conf_schema.json` 中的 MySQL 连接参数：

```json
{
  "mysql_host": "47.121.138.217",
  "mysql_port": 13307,
  "mysql_user": "root",
  "mysql_password": "your_password",
  "mysql_database": "astrbot_self_learning"
}
```

## 更新表结构

如果未来修改了 ORM 模型（添加/删除字段），需要：

1. 重新生成 SQL 脚本：
   ```bash
   python scripts/generate_mysql_schema.py
   ```

2. **手动迁移数据**（如果需要保留数据）：
   - 导出旧数据
   - 执行新的 SQL 脚本
   - 导入数据（可能需要调整）

3. 或者删除重建（**会丢失所有数据**）：
   ```bash
   mysql -h 47.121.138.217 -P 13307 -u root -p < scripts/mysql_schema.sql
   ```
