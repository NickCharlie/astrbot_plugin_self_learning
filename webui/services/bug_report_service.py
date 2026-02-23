"""
Bug报告服务 - 处理Bug报告相关业务逻辑
"""
import os
import aiohttp
from typing import Dict, Any, List, Tuple, Optional
from astrbot.api import logger


class BugReportService:
    """Bug报告服务"""

    def __init__(self, container):
        """
        初始化Bug报告服务

        Args:
            container: ServiceContainer 依赖注入容器
        """
        self.container = container
        self.plugin_config = container.plugin_config
        self.webui_config = container.webui_config

    def get_bug_report_config(self) -> Dict[str, Any]:
        """
        获取Bug报告配置

        Returns:
            Dict: Bug报告配置信息
        """
        # Bug报告配置常量
        BUG_REPORT_ENABLED = getattr(self.webui_config, 'bug_report_enabled', True)
        BUG_REPORT_ATTACHMENT_ENABLED = False # 暂时禁用附件
        BUG_CLOUD_FUNCTION_URL = os.getenv(
            "ASTRBOT_BUG_CLOUD_URL",
            "http://zentao-g-submit-rwpsiodjrb.cn-hangzhou.fcapp.run/zentao-bug-submit/submit-bug"
        )
        BUG_REPORT_DEFAULT_BUILDS = ["v2.0"]
        BUG_REPORT_MAX_IMAGES = 0 if not BUG_REPORT_ATTACHMENT_ENABLED else 1
        BUG_REPORT_MAX_IMAGE_BYTES = 8 * 1024 * 1024
        BUG_REPORT_ALLOWED_EXTENSIONS = {
            '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp',
            '.txt', '.log', '.md', '.json', '.xml', '.yaml', '.yml'
        }

        # 获取日志预览
        log_preview = self._collect_log_previews()

        return {
            "enabled": BUG_REPORT_ENABLED,
            "cloudFunctionUrl": BUG_CLOUD_FUNCTION_URL,
            "severityOptions": [
                {"value": 1, "label": "1 - 致命"},
                {"value": 2, "label": "2 - 严重"},
                {"value": 3, "label": "3 - 一般"},
                {"value": 4, "label": "4 - 轻微"}
            ],
            "priorityOptions": [
                {"value": 1, "label": "1 - 紧急"},
                {"value": 2, "label": "2 - 高"},
                {"value": 3, "label": "3 - 中"},
                {"value": 4, "label": "4 - 低"}
            ],
            "typeOptions": [
                {"value": "codeerror", "label": "代码错误"},
                {"value": "config", "label": "配置相关"},
                {"value": "install", "label": "安装部署"},
                {"value": "performance", "label": "性能问题"},
                {"value": "others", "label": "其他"}
            ],
            "defaultBuild": BUG_REPORT_DEFAULT_BUILDS[0] if BUG_REPORT_DEFAULT_BUILDS else "",
            "maxImages": BUG_REPORT_MAX_IMAGES,
            "maxImageBytes": BUG_REPORT_MAX_IMAGE_BYTES,
            "allowedExtensions": sorted(list(BUG_REPORT_ALLOWED_EXTENSIONS)) if BUG_REPORT_ATTACHMENT_ENABLED else [],
            "attachmentEnabled": BUG_REPORT_ATTACHMENT_ENABLED,
            "logPreview": log_preview,
            "message": "Bug自助提交通过云函数转发（暂不支持附件上传）" if BUG_REPORT_ENABLED else "Bug自助提交功能暂不可用，请联系管理员"
        }

    def _collect_log_previews(self) -> Dict[str, str]:
        """
        收集日志预览

        Returns:
            Dict: 日志预览数据
        """
        log_preview = {
            "astrbot_log": "",
            "plugin_log": "",
            "dashboard_log": ""
        }

        # 这里可以实现实际的日志收集逻辑
        # 暂时返回空预览
        try:
            # TODO: 实现日志收集
            pass
        except Exception as e:
            logger.warning(f"收集日志预览失败: {e}")

        return log_preview

    async def submit_bug_report(self, bug_data: Dict[str, Any]) -> Tuple[bool, str, Optional[Dict]]:
        """
        提交Bug报告

        Args:
            bug_data: Bug报告数据，包含以下字段：
                - title: Bug标题
                - steps: 重现步骤
                - severity: 严重程度 (1-4)
                - pri: 优先级 (1-4)
                - type: Bug类型
                - build: 影响版本（可选）
                - os: 操作系统（可选）
                - browser: 浏览器（可选）
                - mailto: 联系邮箱（可选）

        Returns:
            Tuple[bool, str, Optional[Dict]]: (是否成功, 消息, 响应数据)
        """
        # 验证必需字段
        required_fields = ["title", "steps", "severity", "pri", "type"]
        for field in required_fields:
            if field not in bug_data or not bug_data[field]:
                return False, f"缺少必需字段: {field}", None

        try:
            # 获取云函数URL
            cloud_url = os.getenv(
                "ASTRBOT_BUG_CLOUD_URL",
                "http://zentao-g-submit-rwpsiodjrb.cn-hangzhou.fcapp.run/zentao-bug-submit/submit-bug"
            )

            # 构建完整的重现步骤，包含所有信息
            severity_labels = {1: "致命", 2: "严重", 3: "一般", 4: "轻微"}
            priority_labels = {1: "紧急", 2: "高", 3: "中", 4: "低"}
            type_labels = {
                "codeerror": "代码错误",
                "config": "配置相关",
                "install": "安装部署",
                "performance": "性能问题",
                "others": "其他"
            }

            severity = bug_data.get("severity", 3)
            priority = bug_data.get("pri", 3)
            bug_type = bug_data.get("type", "others")
            mailto = bug_data.get("mailto", "")

            # 构建格式化的完整步骤说明
            formatted_steps = f"""【Bug标题】
{bug_data['title']}

【严重程度】
{severity} - {severity_labels.get(severity, '未知')}

【优先级】
{priority} - {priority_labels.get(priority, '未知')}

【Bug类型】
{type_labels.get(bug_type, bug_type)}

【影响版本】
{bug_data.get('build', '未指定')}

【操作系统】
{bug_data.get('os', '未指定')}

【浏览器】
{bug_data.get('browser', '未指定')}

【联系邮箱】
{mailto if mailto else '未提供'}

【重现步骤】
{bug_data['steps']}
"""

            # 构建请求数据，将完整信息放入steps字段
            payload = {
                "title": bug_data["title"],
                "steps": formatted_steps,
                "severity": severity,
                "pri": priority,
                "type": bug_type,
                "build": bug_data.get("build", "v2.0"),
                "os": bug_data.get("os", ""),
                "browser": bug_data.get("browser", ""),
                "mailto": mailto,
            }

            logger.info(f"准备提交Bug报告: {payload['title']}")
            logger.debug(f"Bug报告完整数据: {payload}")

            # 实际调用云函数API
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    cloud_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    status_code = response.status
                    response_text = await response.text()

                    logger.info(f"云函数响应状态: {status_code}")
                    logger.debug(f"云函数响应内容: {response_text}")

                    if status_code == 200:
                        try:
                            response_data = await response.json()
                            return True, "Bug报告提交成功", response_data
                        except Exception:
                            # 如果响应不是JSON，但状态码是200，仍然认为成功
                            return True, "Bug报告提交成功", {"status": "submitted", "message": response_text}
                    else:
                        return False, f"提交失败: HTTP {status_code} - {response_text}", None

        except aiohttp.ClientError as e:
            logger.error(f"提交Bug报告网络错误: {e}", exc_info=True)
            return False, f"网络请求失败: {str(e)}", None
        except Exception as e:
            logger.error(f"提交Bug报告失败: {e}", exc_info=True)
            return False, f"提交失败: {str(e)}", None

    async def get_bug_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        获取Bug报告历史

        Args:
            limit: 返回数量限制

        Returns:
            List[Dict]: Bug报告历史列表
        """
        # TODO: 实现Bug历史查询
        # 这里应该从数据库或文件中读取历史记录
        return []
