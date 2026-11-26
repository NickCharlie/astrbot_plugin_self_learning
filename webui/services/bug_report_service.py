"""Bug 反馈服务：把面板内容整理成 GitHub issue 预填链接。

历史实现把报告 POST 到禅道云函数（阿里云 FC）。该云函数所属账号欠费后固定
返回 403 AccessDenied，插件侧无法修复，因此改为走仓库自带的
``.github/ISSUE_TEMPLATE/bug_report.yml``：面板只负责整理字段并拼出预填 URL，
再由用户在 GitHub 上确认提交。

GitHub 的 issue form（YAML 模板）不支持 ``?body=`` 预填，但官方文档明确把
每个表单元素的 ``id`` 定为 URL query 预填的规范标识，因此这里逐字段按模板
id 编码。
"""

from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote, urlencode

from astrbot.api import logger

DEFAULT_REPOSITORY = "NickCharlie/astrbot_plugin_self_learning"
TEMPLATE_NAME = "bug_report.yml"

# 与 .github/ISSUE_TEMPLATE/bug_report.yml 的元素 id 一一对应；改模板必须同步这里
SEVERITY_LABELS = {1: "致命", 2: "严重", 3: "一般", 4: "轻微"}
PRIORITY_LABELS = {1: "紧急", 2: "高", 3: "中", 4: "低"}
TYPE_LABELS = {
    "codeerror": "代码错误",
    "config": "配置相关",
    "install": "安装部署",
    "performance": "性能问题",
    "others": "其他",
}
DB_TYPE_LABELS = {"sqlite": "SQLite (default)", "mysql": "MySQL", "postgresql": "PostgreSQL"}
OS_LABELS = {"linux": "Linux", "windows": "Windows", "macos": "macOS", "docker": "Docker"}


class BugReportService:
    """Bug 反馈服务。"""

    def __init__(self, container):
        self.container = container
        self.plugin_config = container.plugin_config
        self.webui_config = container.webui_config

    # ── 配置 ────────────────────────────────────────────────────────────

    def get_bug_report_config(self) -> Dict[str, Any]:
        """返回面板所需的选项、默认值与目标仓库信息。"""
        enabled = getattr(self.webui_config, "bug_report_enabled", True)
        repository = self._repository()
        return {
            "enabled": enabled,
            "mode": "github_issue",
            "repository": repository,
            "template": TEMPLATE_NAME,
            "newIssueUrl": f"https://github.com/{repository}/issues/new",
            "severityOptions": _options(SEVERITY_LABELS),
            "priorityOptions": _options(PRIORITY_LABELS),
            "typeOptions": _options(TYPE_LABELS),
            "dbTypeOptions": _options(DB_TYPE_LABELS),
            "osOptions": _options(OS_LABELS),
            "defaultBuild": self._default_build(),
            "defaultAstrBotVersion": self._detect_astrbot_version(),
            "defaultDbType": self._detect_db_type(),
            "defaultOs": self._detect_os(),
            "logPreview": self._collect_log_previews(),
            "message": (
                "填写后跳转 GitHub，按模板确认并提交"
                if enabled
                else "Bug 自助提交已关闭，请联系管理员"
            ),
        }

    def build_issue_url(self, bug_data: Dict[str, Any]) -> str:
        """按 issue 模板字段 id 拼出预填链接。"""
        fields = {k: v for k, v in self._issue_fields(bug_data).items() if v}
        query = urlencode(
            {"template": TEMPLATE_NAME, **fields},
            quote_via=_quote_component,
        )
        return f"https://github.com/{self._repository()}/issues/new?{query}"

    # ── 提交 ────────────────────────────────────────────────────────────

    async def submit_bug_report(
        self, bug_data: Dict[str, Any]
    ) -> Tuple[bool, str, Optional[Dict]]:
        """校验最小必填项并返回预填链接；不对外发起任何网络请求。"""
        for field in ("title", "steps"):
            if not str(bug_data.get(field) or "").strip():
                return False, f"缺少必需字段: {field}", None
        try:
            url = self.build_issue_url(bug_data)
        except Exception as exc:
            logger.error(f"生成 Bug 反馈链接失败: {exc}", exc_info=True)
            return False, f"生成反馈链接失败: {exc}", None
        return (
            True,
            "已生成 GitHub 反馈链接，请在浏览器中确认并提交",
            {"url": url, "repository": self._repository()},
        )

    async def get_bug_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Bug 历史（既有行为：未实现，返回空列表）。"""
        return []

    # ── 内部实现 ────────────────────────────────────────────────────────

    def _issue_fields(self, bug_data: Dict[str, Any]) -> Dict[str, str]:
        """把面板表单映射为模板字段。模板没有的维度追加在复现步骤末尾。"""
        severity = _as_int(bug_data.get("severity"), 3)
        priority = _as_int(bug_data.get("pri"), 3)
        bug_type = str(bug_data.get("type") or "others").strip()
        db_type = str(bug_data.get("db_type") or "").strip().lower()
        os_name = str(bug_data.get("os") or "").strip()
        contact = str(bug_data.get("mailto") or "").strip()

        extras = [
            f"【严重程度】{severity} - {SEVERITY_LABELS.get(severity, '未知')}",
            f"【优先级】{priority} - {PRIORITY_LABELS.get(priority, '未知')}",
            f"【类型】{TYPE_LABELS.get(bug_type, bug_type or '其他')}",
        ]
        if contact:
            extras.append(f"【联系邮箱】{contact}")
        steps = str(bug_data.get("steps") or "").strip()

        return {
            "version": str(bug_data.get("build") or self._default_build()).strip(),
            "astrbot_version": str(
                bug_data.get("astrbot_version") or self._detect_astrbot_version()
            ).strip(),
            "db_type": DB_TYPE_LABELS.get(db_type) or self._detect_db_type(),
            "os": OS_LABELS.get(os_name.lower()) or os_name or self._detect_os(),
            "severity": f"{severity} - {SEVERITY_LABELS.get(severity, '未知')}",
            "priority": f"{priority} - {PRIORITY_LABELS.get(priority, '未知')}",
            "type": TYPE_LABELS.get(bug_type, bug_type),
            "title": str(bug_data.get("title") or "").strip(),
            "description": str(bug_data.get("description") or "").strip(),
            "steps": f"{steps}\n\n---\n" + "\n".join(extras) if steps else "\n".join(extras),
            "expected": str(bug_data.get("expected") or "").strip(),
            "logs": str(bug_data.get("logs") or "").strip(),
            "contact": contact,
        }

    def _repository(self) -> str:
        return str(
            getattr(self.webui_config, "bug_report_repository", "") or DEFAULT_REPOSITORY
        ).strip()

    def _default_build(self) -> str:
        return str(getattr(self.plugin_config, "version", "") or "").strip()

    def _detect_astrbot_version(self) -> str:
        try:
            import astrbot

            return str(getattr(astrbot, "__version__", "") or "")
        except Exception:
            return ""

    def _detect_db_type(self) -> str:
        raw = str(getattr(self.plugin_config, "db_type", "") or "").strip().lower()
        if raw in DB_TYPE_LABELS:
            return DB_TYPE_LABELS[raw]
        if "postgres" in raw:
            return DB_TYPE_LABELS["postgresql"]
        if "mysql" in raw:
            return DB_TYPE_LABELS["mysql"]
        return DB_TYPE_LABELS["sqlite"]

    def _detect_os(self) -> str:
        import platform

        system = platform.system().lower()
        if system == "windows":
            return OS_LABELS["windows"]
        if system == "darwin":
            return OS_LABELS["macos"]
        return OS_LABELS["linux"]

    def _collect_log_previews(self) -> Dict[str, str]:
        """日志预览：仅在页面展示，不随报告提交（保持既有行为）。"""
        return {"astrbot_log": "", "plugin_log": "", "dashboard_log": ""}


def _options(labels: Dict[Any, str]) -> List[Dict[str, Any]]:
    return [
        {"value": key, "label": f"{key} - {label}" if isinstance(key, int) else label}
        for key, label in labels.items()
    ]


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _quote_component(value: Any, safe: str = "", encoding: Optional[str] = None,
                     errors: Optional[str] = None) -> str:
    """编码 query 组件。

    GitHub 认 ``%0A`` 换行，中文保持百分号编码，避免被中间代理截断或二次转义。
    """
    return quote(str(value), safe="")