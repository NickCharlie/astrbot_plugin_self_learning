#!/usr/bin/env python3
"""
WebUI 自动重构工具
分析原 webui.py 并生成重构后的蓝图代码
"""
import re
import os
from typing import List, Dict, Tuple


class WebUIRefactorTool:
    """WebUI 重构工具"""

    def __init__(self, source_file: str = "webui.py"):
        self.source_file = source_file
        self.routes = []
        self.functions = []

    def analyze_routes(self) -> Dict[str, List[Tuple[str, str, List[str]]]]:
        """
        分析路由并按功能分组

        Returns:
            Dict[分组名, List[(路由路径, 函数名, HTTP方法)]]
        """
        route_groups = {
            'auth': [],      # 认证相关
            'config': [],    # 配置管理
            'personas': [],  # 人格管理
            'learning': [],  # 学习功能
            'metrics': [],   # 指标分析
            'social': [],    # 社交关系
            'jargon': [],    # 黑话管理
            'bug_report': [],  # Bug报告
            'chat': [],      # 聊天历史
            'other': []      # 其他
        }

        with open(self.source_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # 查找所有路由定义
        route_pattern = r'@app\.route\([\'"]([^\'"]+)[\'"]\s*(?:,\s*methods=\[(.*?)\])?\s*\)\s*async def (\w+)'

        for match in re.finditer(route_pattern, content):
            path = match.group(1)
            methods_str = match.group(2) or "'GET'"
            func_name = match.group(3)
            methods = [m.strip('\'" ') for m in methods_str.split(',')]

            # 根据路径和函数名分组
            if any(keyword in path.lower() or keyword in func_name.lower()
                   for keyword in ['login', 'logout', 'password', 'auth']):
                route_groups['auth'].append((path, func_name, methods))
            elif any(keyword in path.lower() or keyword in func_name.lower()
                    for keyword in ['persona', 'personality']):
                route_groups['personas'].append((path, func_name, methods))
            elif any(keyword in path.lower() or keyword in func_name.lower()
                    for keyword in ['learning', 'style']):
                route_groups['learning'].append((path, func_name, methods))
            elif any(keyword in path.lower() or keyword in func_name.lower()
                    for keyword in ['metrics', 'analytics']):
                route_groups['metrics'].append((path, func_name, methods))
            elif any(keyword in path.lower() or keyword in func_name.lower()
                    for keyword in ['social', 'relation']):
                route_groups['social'].append((path, func_name, methods))
            elif any(keyword in path.lower() or keyword in func_name.lower()
                    for keyword in ['jargon', '黑话']):
                route_groups['jargon'].append((path, func_name, methods))
            elif any(keyword in path.lower() or keyword in func_name.lower()
                    for keyword in ['bug', 'report']):
                route_groups['bug_report'].append((path, func_name, methods))
            elif any(keyword in path.lower() or keyword in func_name.lower()
                    for keyword in ['chat', 'message', 'history']):
                route_groups['chat'].append((path, func_name, methods))
            elif any(keyword in path.lower() or keyword in func_name.lower()
                    for keyword in ['config', 'setting']):
                route_groups['config'].append((path, func_name, methods))
            else:
                route_groups['other'].append((path, func_name, methods))

        return route_groups

    def print_analysis(self):
        """打印分析结果"""
        route_groups = self.analyze_routes()

        print("=" * 70)
        print("WebUI 路由分析结果")
        print("=" * 70)
        print()

        total_routes = 0
        for group_name, routes in route_groups.items():
            if routes:
                print(f"📦 {group_name.upper()} ({len(routes)} 个路由)")
                print("-" * 70)
                for path, func_name, methods in routes:
                    methods_str = ', '.join(methods)
                    print(f"  {methods_str:15} {path:40} -> {func_name}")
                print()
                total_routes += len(routes)

        print("=" * 70)
        print(f"总计: {total_routes} 个路由")
        print("=" * 70)

    def generate_blueprint_template(self, group_name: str, routes: List[Tuple[str, str, List[str]]]) -> str:
        """生成蓝图模板代码"""
        template = f'''"""
{group_name.capitalize()} 相关路由
"""
from quart import Blueprint, render_template, request, jsonify, session

from ..dependencies import get_container
from ..services.{group_name}_service import {group_name.capitalize()}Service
from ..middleware.auth import require_auth
from ..utils.response import success_response, error_response

{group_name}_bp = Blueprint('{group_name}', __name__, url_prefix='/api/{group_name}')


'''

        for path, func_name, methods in routes:
            # 提取路由参数
            params = re.findall(r'<(\w+)(?::(\w+))?>', path)
            param_str = ', '.join([p[1] if p[1] else p[0] for p in params]) if params else ''

            methods_str = ', '.join([f'"{m}"' for m in methods])

            template += f'''@{group_name}_bp.route('{path}', methods=[{methods_str}])
@require_auth
async def {func_name}({param_str}):
    """TODO: 实现 {func_name}"""
    try:
        service = {group_name.capitalize()}Service(get_container())
        # TODO: 实现业务逻辑
        return success_response("TODO")
    except Exception as e:
        return error_response(f"操作失败: {{str(e)}}", 500)


'''

        return template


def main():
    """主函数"""
    tool = WebUIRefactorTool()
    tool.print_analysis()

    print()
    print("💡 建议的重构步骤:")
    print("1. 创建上述每个分组的 blueprint 文件")
    print("2. 为每个 blueprint 创建对应的 service 文件")
    print("3. 从 webui.py 提取对应的业务逻辑到 service")
    print("4. 逐个测试每个 blueprint")
    print("5. 全部迁移完成后删除 webui.py")
    print()


if __name__ == "__main__":
    main()
