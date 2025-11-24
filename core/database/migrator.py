"""
数据库迁移工具 - 自动迁移数据库数据
"""
import time
from typing import List, Dict, Any, Optional, Callable
from astrbot.api import logger

from .backend_interface import IDatabaseBackend, DatabaseType


class DatabaseMigrator:
    """数据库迁移器"""

    def __init__(
        self,
        source_backend: IDatabaseBackend,
        target_backend: IDatabaseBackend,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
        use_replace: bool = True
    ):
        """
        初始化迁移器

        Args:
            source_backend: 源数据库后端
            target_backend: 目标数据库后端
            progress_callback: 进度回调函数 (table_name, current, total)
            use_replace: 是否使用 REPLACE INTO（MySQL）解决主键冲突
        """
        self.source = source_backend
        self.target = target_backend
        self.progress_callback = progress_callback
        self.use_replace = use_replace

    async def migrate_all(self, skip_tables: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        迁移所有表

        Args:
            skip_tables: 要跳过的表名列表

        Returns:
            迁移结果报告
        """
        start_time = time.time()
        skip_tables = skip_tables or []

        report = {
            'success': False,
            'tables_migrated': 0,
            'tables_failed': 0,
            'total_rows': 0,
            'errors': [],
            'duration': 0,
            'details': []
        }

        try:
            # 获取源数据库的所有表
            source_tables = await self.source.get_table_list()
            logger.info(f"[Migrator] 发现 {len(source_tables)} 个表需要迁移")

            for table_name in source_tables:
                if table_name in skip_tables:
                    logger.info(f"[Migrator] 跳过表: {table_name}")
                    continue

                try:
                    # 迁移单个表
                    result = await self.migrate_table(table_name)
                    report['details'].append(result)

                    if result['success']:
                        report['tables_migrated'] += 1
                        report['total_rows'] += result['rows_migrated']
                    else:
                        report['tables_failed'] += 1
                        report['errors'].append({
                            'table': table_name,
                            'error': result.get('error', 'Unknown error')
                        })

                except Exception as e:
                    logger.error(f"[Migrator] 迁移表失败 {table_name}: {e}", exc_info=True)
                    report['tables_failed'] += 1
                    report['errors'].append({
                        'table': table_name,
                        'error': str(e)
                    })

            report['success'] = report['tables_failed'] == 0
            report['duration'] = time.time() - start_time

            logger.info(
                f"[Migrator] 迁移完成: "
                f"{report['tables_migrated']} 成功, "
                f"{report['tables_failed']} 失败, "
                f"{report['total_rows']} 行数据, "
                f"耗时 {report['duration']:.2f}秒"
            )

            return report

        except Exception as e:
            logger.error(f"[Migrator] 迁移失败: {e}", exc_info=True)
            report['success'] = False
            report['errors'].append({'global': str(e)})
            report['duration'] = time.time() - start_time
            return report

    async def migrate_table(self, table_name: str) -> Dict[str, Any]:
        """
        迁移单个表

        Args:
            table_name: 表名

        Returns:
            迁移结果
        """
        result = {
            'table': table_name,
            'success': False,
            'rows_migrated': 0,
            'error': None
        }

        try:
            logger.info(f"[Migrator] 开始迁移表: {table_name}")

            # 1. 检查目标表是否存在
            target_exists = await self.target.table_exists(table_name)

            if not target_exists:
                # 2. 获取源表结构并创建目标表
                logger.info(f"[Migrator] 目标表不存在，开始创建: {table_name}")
                schema_created = await self._create_target_table(table_name)

                if not schema_created:
                    result['error'] = "Failed to create target table"
                    return result

            # 3. 导出源表数据
            logger.info(f"[Migrator] 导出源表数据: {table_name}")
            data = await self.source.export_table_data(table_name)
            logger.info(f"[Migrator] 导出 {len(data)} 行数据")

            if not data:
                logger.info(f"[Migrator] 表 {table_name} 无数据，跳过")
                result['success'] = True
                result['rows_migrated'] = 0
                return result

            # 4. 导入数据到目标表
            logger.info(f"[Migrator] 导入数据到目标表: {table_name}")

            # 如果目标是 MySQL 且启用了 REPLACE，使用 REPLACE INTO
            use_replace_for_this_table = (
                self.use_replace and
                self.target.db_type == DatabaseType.MYSQL
            )

            rows_imported = await self.target.import_table_data(
                table_name,
                data,
                replace=use_replace_for_this_table
            )

            result['success'] = True
            result['rows_migrated'] = rows_imported
            logger.info(f"[Migrator] 表 {table_name} 迁移成功: {rows_imported} 行")

            # 调用进度回调
            if self.progress_callback:
                self.progress_callback(table_name, rows_imported, len(data))

            return result

        except Exception as e:
            logger.error(f"[Migrator] 迁移表失败 {table_name}: {e}", exc_info=True)
            result['error'] = str(e)
            return result

    async def _create_target_table(self, table_name: str) -> bool:
        """
        创建目标表（从源表结构）

        Args:
            table_name: 表名

        Returns:
            是否创建成功
        """
        try:
            # 获取源表的DDL（仅适用于SQLite）
            if self.source.db_type == DatabaseType.SQLITE:
                sql = f"SELECT sql FROM sqlite_master WHERE type='table' AND name=?"
                result = await self.source.fetch_one(sql, (table_name,))

                if not result or not result[0]:
                    logger.error(f"[Migrator] 无法获取表结构: {table_name}")
                    return False

                source_ddl = result[0]

                # 如果目标是MySQL，转换DDL
                if self.target.db_type == DatabaseType.MYSQL:
                    target_ddl = self.target.convert_ddl(source_ddl)
                else:
                    target_ddl = source_ddl

                # 创建表
                return await self.target.create_table(table_name, target_ddl)
            else:
                logger.error(f"[Migrator] 暂不支持从 {self.source.db_type} 导出表结构")
                return False

        except Exception as e:
            logger.error(f"[Migrator] 创建目标表失败 {table_name}: {e}", exc_info=True)
            return False

    async def verify_migration(self, table_name: str) -> Dict[str, Any]:
        """
        验证表迁移结果

        Args:
            table_name: 表名

        Returns:
            验证结果
        """
        result = {
            'table': table_name,
            'valid': False,
            'source_rows': 0,
            'target_rows': 0,
            'row_count_match': False
        }

        try:
            # 统计源表行数
            source_count_sql = f"SELECT COUNT(*) FROM {table_name}"
            source_result = await self.source.fetch_one(source_count_sql)
            result['source_rows'] = source_result[0] if source_result else 0

            # 统计目标表行数
            target_count_sql = f"SELECT COUNT(*) FROM {table_name}"
            target_result = await self.target.fetch_one(target_count_sql)
            result['target_rows'] = target_result[0] if target_result else 0

            # 比较行数
            result['row_count_match'] = (result['source_rows'] == result['target_rows'])
            result['valid'] = result['row_count_match']

            logger.info(
                f"[Migrator] 验证表 {table_name}: "
                f"源={result['source_rows']}, "
                f"目标={result['target_rows']}, "
                f"匹配={'是' if result['row_count_match'] else '否'}"
            )

            return result

        except Exception as e:
            logger.error(f"[Migrator] 验证失败 {table_name}: {e}", exc_info=True)
            result['error'] = str(e)
            return result

    async def verify_all(self, tables: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        验证所有表的迁移结果

        Args:
            tables: 要验证的表列表（None则验证所有表）

        Returns:
            验证报告
        """
        report = {
            'all_valid': False,
            'tables_verified': 0,
            'tables_invalid': 0,
            'details': []
        }

        try:
            if tables is None:
                tables = await self.target.get_table_list()

            for table_name in tables:
                result = await self.verify_migration(table_name)
                report['details'].append(result)

                if result.get('valid'):
                    report['tables_verified'] += 1
                else:
                    report['tables_invalid'] += 1

            report['all_valid'] = (report['tables_invalid'] == 0)

            logger.info(
                f"[Migrator] 验证完成: "
                f"{report['tables_verified']} 有效, "
                f"{report['tables_invalid']} 无效"
            )

            return report

        except Exception as e:
            logger.error(f"[Migrator] 验证失败: {e}", exc_info=True)
            report['error'] = str(e)
            return report
