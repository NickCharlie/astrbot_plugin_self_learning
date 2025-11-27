#!/usr/bin/env python3
"""
验证重构功能启用状态
"""
import json
import os

def check_refactoring_status():
    """检查重构功能启用状态"""

    print("=" * 70)
    print("🔍 检查重构功能启用状态")
    print("=" * 70)
    print()

    # 检查配置 schema
    schema_path = "_conf_schema.json"
    if os.path.exists(schema_path):
        with open(schema_path, 'r', encoding='utf-8') as f:
            schema = json.load(f)

        print("📋 配置 Schema 检查:")
        print()

        # 检查 Database_Settings
        db_settings = schema.get('Database_Settings', {}).get('items', {})
        use_sqlalchemy = db_settings.get('use_sqlalchemy', {})
        if use_sqlalchemy:
            default_value = use_sqlalchemy.get('default', False)
            print(f"  ✅ use_sqlalchemy: 已添加 (默认值: {default_value})")
            print(f"     描述: {use_sqlalchemy.get('description')}")
            print(f"     提示: {use_sqlalchemy.get('hint')}")
        else:
            print("  ❌ use_sqlalchemy: 未找到")

        print()

        # 检查 Advanced_Settings
        adv_settings = schema.get('Advanced_Settings', {}).get('items', {})

        use_enhanced = adv_settings.get('use_enhanced_managers', {})
        if use_enhanced:
            default_value = use_enhanced.get('default', False)
            print(f"  ✅ use_enhanced_managers: 已添加 (默认值: {default_value})")
            print(f"     描述: {use_enhanced.get('description')}")
        else:
            print("  ❌ use_enhanced_managers: 未找到")

        print()

        enable_cleanup = adv_settings.get('enable_memory_cleanup', {})
        if enable_cleanup:
            print(f"  ✅ enable_memory_cleanup: 已添加 (默认值: {enable_cleanup.get('default')})")
        else:
            print("  ❌ enable_memory_cleanup: 未找到")

        cleanup_days = adv_settings.get('memory_cleanup_days', {})
        if cleanup_days:
            print(f"  ✅ memory_cleanup_days: 已添加 (默认值: {cleanup_days.get('default')})")
        else:
            print("  ❌ memory_cleanup_days: 未找到")

        threshold = adv_settings.get('memory_importance_threshold', {})
        if threshold:
            print(f"  ✅ memory_importance_threshold: 已添加 (默认值: {threshold.get('default')})")
        else:
            print("  ❌ memory_importance_threshold: 未找到")
    else:
        print("❌ 配置文件不存在: _conf_schema.json")

    print()
    print("=" * 70)
    print("📊 总结")
    print("=" * 70)
    print()

    # 检查默认值
    all_enabled = all([
        use_sqlalchemy.get('default') == True,
        use_enhanced.get('default') == True,
        enable_cleanup.get('default') == True
    ])

    if all_enabled:
        print("✅ 所有重构功能默认启用！")
        print()
        print("下次启动插件时将自动使用:")
        print("  • SQLAlchemy 数据库管理器")
        print("  • 增强型好感度管理器")
        print("  • 增强型记忆图管理器")
        print("  • 增强型心理状态管理器")
        print("  • 统一缓存管理")
        print("  • APScheduler 任务调度")
        print("  • 自动数据库迁移")
        print()
        print("🎉 无需手动配置，直接重启 AstrBot 即可！")
    else:
        print("⚠️  部分功能未默认启用")
        print()
        print("当前默认值:")
        print(f"  • use_sqlalchemy: {use_sqlalchemy.get('default', False)}")
        print(f"  • use_enhanced_managers: {use_enhanced.get('default', False)}")
        print(f"  • enable_memory_cleanup: {enable_cleanup.get('default', False)}")
        print()
        print("如需启用，请在 AstrBot 配置文件中设置为 true")

    print()
    print("=" * 70)

    # 检查迁移标记
    migration_marker = "./data/self_learning_data/.migration_completed"
    if os.path.exists(migration_marker):
        print()
        print("📌 数据库迁移状态:")
        print(f"  ✅ 已完成迁移")
        print(f"  标记文件: {migration_marker}")
        try:
            with open(migration_marker, 'r', encoding='utf-8') as f:
                migration_info = json.load(f)
                print(f"  迁移时间: {migration_info.get('timestamp')}")
                print(f"  迁移表数: {migration_info.get('tables_migrated', 0)}")
                print(f"  总行数: {migration_info.get('total_rows_migrated', 0)}")
        except:
            pass
    else:
        print()
        print("📌 数据库迁移状态:")
        print("  ⏳ 尚未迁移（首次启动时会自动执行）")

    print()
    print("=" * 70)


if __name__ == "__main__":
    check_refactoring_status()
