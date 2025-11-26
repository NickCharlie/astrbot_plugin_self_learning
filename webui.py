import os
import asyncio
import json # 导入 json 模块
import secrets
import time
import base64
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from astrbot.api import logger
from typing import Optional, List, Dict, Any
from dataclasses import asdict
from functools import wraps

from quart import Quart, Blueprint, render_template, request, jsonify, current_app, redirect, url_for, session # 导入 redirect 和 url_for
from quart_cors import cors # 导入 cors
import hypercorn.asyncio
from hypercorn.config import Config as HypercornConfig
import aiohttp
from werkzeug.utils import secure_filename

from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from .config import PluginConfig
from .core.factory import FactoryManager
from .persona_web_manager import PersonaWebManager, set_persona_web_manager, get_persona_web_manager
from .services.intelligence_metrics import IntelligenceMetricsService
from .utils.security_utils import (
    PasswordHasher,
    login_attempt_tracker,
    migrate_password_to_hashed,
    verify_password_with_migration,
    SecurityValidator
)
from .constants import (
    UPDATE_TYPE_PROGRESSIVE_PERSONA_LEARNING,
    UPDATE_TYPE_STYLE_LEARNING,
    UPDATE_TYPE_EXPRESSION_LEARNING,
    UPDATE_TYPE_TRADITIONAL,
    normalize_update_type,
    get_review_source_from_update_type
)

# 获取当前文件所在的目录，然后向上两级到达插件根目录
PLUGIN_ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '.'))
WEB_STATIC_DIR = os.path.join(PLUGIN_ROOT_DIR, "web_res", "static")
WEB_HTML_DIR = os.path.join(WEB_STATIC_DIR, "html")

def get_password_file_path() -> str:
    """动态获取密码文件路径，优先使用config.data_dir"""
    if plugin_config and hasattr(plugin_config, 'data_dir'):
        # 使用配置的data_dir路径
        return os.path.join(plugin_config.data_dir, "password.json")
    else:
        # 后备路径：使用插件根目录下的config文件夹
        return os.path.join(PLUGIN_ROOT_DIR, "config", "password.json")

# 初始化 Quart 应用
app = Quart(__name__, static_folder=WEB_STATIC_DIR, static_url_path="/static", template_folder=WEB_HTML_DIR)
app.secret_key = secrets.token_hex(16)  # 生成随机密钥用于会话管理
cors(app) # 启用 CORS

# 全局变量，用于存储插件实例和服务
plugin_config: Optional[PluginConfig] = None
persona_manager: Optional[Any] = None
persona_updater: Optional[Any] = None
database_manager: Optional[Any] = None
db_manager: Optional[Any] = None  # 添加db_manager别名
llm_client = None
llm_adapter_instance = None  # LLM适配器实例，用于社交关系分析等服务
progressive_learning: Optional[Any] = None  # 添加progressive_learning全局变量
intelligence_metrics_service: Optional[IntelligenceMetricsService] = None  # 智能指标计算服务

# 新增的变量
pending_updates: List[Any] = []
password_config: Dict[str, Any] = {} # 用于存储密码配置

BUG_REPORT_ENABLED = True
# 暂时禁用附件上传功能
BUG_REPORT_ATTACHMENT_ENABLED = False  # TODO: 附件功能待修复后启用
BUG_CLOUD_FUNCTION_URL = os.getenv(
    "ASTRBOT_BUG_CLOUD_URL",
    "http://zentao-g-submit-rwpsiodjrb.cn-hangzhou.fcapp.run/zentao-bug-submit/submit-bug"
)  # 保持完整URL，不要rstrip
BUG_CLOUD_VERIFY_CODE = os.getenv("ASTRBOT_BUG_CLOUD_VERIFY_CODE", "zentao123")
BUG_REPORT_TIMEOUT_SECONDS = int(os.getenv("ASTRBOT_BUG_REPORT_TIMEOUT", "30"))
BUG_REPORT_DEFAULT_BUILDS = [build.strip() for build in os.getenv("ASTRBOT_BUG_DEFAULT_BUILDS", "v2.0").split(",") if build.strip()]
BUG_REPORT_DEFAULT_SEVERITY = 3
BUG_REPORT_DEFAULT_PRIORITY = 3
BUG_REPORT_DEFAULT_TYPE = "codeerror"
BUG_REPORT_MAX_IMAGES = 1  # 云函数只支持单个附件，如需多个文件请打包为压缩包
BUG_REPORT_MAX_IMAGE_BYTES = 8 * 1024 * 1024  # 8MB per image
BUG_REPORT_MAX_LOG_BYTES = 20_000
# 安全白名单：允许所有图片、压缩包和文档文件
BUG_REPORT_ALLOWED_EXTENSIONS = {
    # 所有常见图片格式
    '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.svg', '.ico', '.tiff', '.tif',
    # 日志和文本
    '.txt', '.log', '.md', '.json', '.xml', '.yaml', '.yml', '.csv',
    # 文档格式
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.odt', '.ods', '.odp',
    # 压缩包（用于多文件场景）
    '.zip', '.7z', '.rar', '.tar', '.gz', '.tar.gz', '.tgz', '.bz2', '.xz'
}
BUG_REPORT_ALLOWED_MIMETYPES = {
    # 所有图片MIME类型
    'image/png', 'image/jpeg', 'image/gif', 'image/bmp', 'image/webp', 'image/svg+xml',
    'image/x-icon', 'image/vnd.microsoft.icon', 'image/tiff',
    # 文本
    'text/plain', 'text/markdown', 'text/csv',
    'application/json', 'application/xml', 'text/xml',
    'application/x-yaml', 'text/yaml',
    # 文档
    'application/pdf',
    'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.ms-powerpoint', 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'application/vnd.oasis.opendocument.text',
    'application/vnd.oasis.opendocument.spreadsheet',
    'application/vnd.oasis.opendocument.presentation',
    # 压缩包
    'application/zip', 'application/x-zip-compressed',
    'application/x-7z-compressed', 'application/x-rar-compressed', 'application/vnd.rar',
    'application/x-tar', 'application/gzip', 'application/x-gzip',
    'application/x-bzip2', 'application/x-xz'
}
BUG_REPORT_SEVERITY_OPTIONS = [
    {"value": 1, "label": "S1 - 阻断故障"},
    {"value": 2, "label": "S2 - 重大问题"},
    {"value": 3, "label": "S3 - 普通问题"},
    {"value": 4, "label": "S4 - 建议优化"}
]
BUG_REPORT_PRIORITY_OPTIONS = [
    {"value": 1, "label": "P1 - 紧急"},
    {"value": 2, "label": "P2 - 高"},
    {"value": 3, "label": "P3 - 中"},
    {"value": 4, "label": "P4 - 低"}
]
BUG_REPORT_TYPE_OPTIONS = [
    {"value": "codeerror", "label": "代码缺陷"},
    {"value": "config", "label": "配置问题"},
    {"value": "performance", "label": "性能问题"},
    {"value": "security", "label": "安全问题"},
    {"value": "others", "label": "其他"}
]
BUG_REPORT_LOG_CANDIDATES = [
    "astrbot.log",
    "astrbot_debug.log",
    "astrbot_plugin.log",
    "self_learning.log"
]


def _bug_report_available() -> bool:
    return BUG_REPORT_ENABLED and bool(BUG_CLOUD_FUNCTION_URL and BUG_CLOUD_VERIFY_CODE)


def _is_safe_attachment(filename: str, mimetype: str) -> tuple[bool, str]:
    """
    检查附件是否安全（文件类型白名单验证）

    Args:
        filename: 文件名
        mimetype: MIME类型

    Returns:
        (is_safe, error_message): 是否安全及错误信息
    """
    if not filename:
        return False, "文件名为空"

    filename_lower = filename.lower()

    # 处理双扩展名（如 .tar.gz）
    ext = None
    if filename_lower.endswith('.tar.gz'):
        ext = '.tar.gz'
    else:
        _, ext = os.path.splitext(filename_lower)

    # 检查扩展名
    if ext not in BUG_REPORT_ALLOWED_EXTENSIONS:
        allowed_exts = ', '.join(sorted(BUG_REPORT_ALLOWED_EXTENSIONS))
        return False, f"不允许的文件类型 '{ext}'。允许的类型：{allowed_exts}"

    # 检查MIME类型（如果提供）
    if mimetype and mimetype not in BUG_REPORT_ALLOWED_MIMETYPES:
        # 某些MIME类型可能会有变体，只要扩展名在白名单中也可以接受
        logger.warning(f"MIME类型 '{mimetype}' 不在白名单中，但扩展名 '{ext}' 有效")

    # 检查文件名中是否包含路径遍历字符
    if '..' in filename or '/' in filename or '\\' in filename:
        return False, "文件名包含非法字符（路径遍历）"

    return True, ""


def _load_dashboard_http_config() -> Dict[str, Any]:
    try:
        data_path = get_astrbot_data_path()
        if not data_path:
            return {}
        config_path = os.path.join(data_path, "cmd_config.json")
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)
            return config_data.get("dashboard", {})
    except Exception as exc:
        logger.debug(f"读取dashboard配置失败: {exc}")
    return {}


def _fetch_dashboard_log_snapshot() -> Optional[str]:
    try:
        dashboard_cfg = _load_dashboard_http_config()
        if dashboard_cfg and not dashboard_cfg.get("enable", True):
            return None

        host = dashboard_cfg.get("host", "127.0.0.1")
        port = dashboard_cfg.get("port", 6185)
        base_url = f"http://{host}:{port}"
        url = f"{base_url}/api/log-history"

        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            logs = payload.get("data", {}).get("logs") or payload.get("logs")
            if not logs:
                return None

        target_dir = None
        if plugin_config and getattr(plugin_config, "data_dir", None):
            target_dir = os.path.join(plugin_config.data_dir, "bug_log_snapshots")
        if not target_dir:
            target_dir = os.path.join(PLUGIN_ROOT_DIR, "bug_log_snapshots")
        os.makedirs(target_dir, exist_ok=True)
        snapshot_path = os.path.join(target_dir, "dashboard_log_history.txt")

        with open(snapshot_path, "w", encoding="utf-8") as f:
            for entry in logs[-200:]:
                timestamp = entry.get("time", "")
                level = entry.get("level", "")
                message = entry.get("data", "")
                f.write(f"[{timestamp}] {level}: {message}\n")

        return snapshot_path
    except urllib.error.URLError as exc:
        logger.debug(f"访问dashboard日志接口失败: {exc}")
    except Exception as exc:
        logger.debug(f"生成dashboard日志快照失败: {exc}")
    return None


def _find_log_files() -> List[str]:
    log_paths: List[str] = []

    dashboard_snapshot = _fetch_dashboard_log_snapshot()
    if dashboard_snapshot:
        log_paths.append(dashboard_snapshot)

    candidate_dirs = []
    if plugin_config and getattr(plugin_config, "data_dir", None):
        candidate_dirs.append(plugin_config.data_dir)
        candidate_dirs.append(os.path.join(plugin_config.data_dir, "logs"))

    astrbot_path = get_astrbot_data_path()
    if astrbot_path:
        candidate_dirs.append(os.path.join(astrbot_path, "logs"))
        candidate_dirs.append(astrbot_path)

    candidate_dirs.append(os.path.join(PLUGIN_ROOT_DIR, "logs"))
    candidate_dirs.append(PLUGIN_ROOT_DIR)

    seen = set()
    for base in candidate_dirs:
        if not base or not os.path.exists(base):
            continue
        for log_name in BUG_REPORT_LOG_CANDIDATES:
            path = os.path.abspath(os.path.join(base, log_name))
            if os.path.exists(path) and path not in seen:
                seen.add(path)
                log_paths.append(path)
    return log_paths


def _read_log_snippet(path: str, max_bytes: int = BUG_REPORT_MAX_LOG_BYTES) -> Dict[str, Any]:
    try:
        size = os.path.getsize(path)
        read_bytes = min(size, max_bytes)
        with open(path, "rb") as f:
            if size > max_bytes:
                f.seek(size - max_bytes)
            data = f.read(read_bytes)
        text = data.decode("utf-8", errors="ignore")
        preview_len = min(len(text), 800)
        return {
            "path": path,
            "size": size,
            "preview": text[-preview_len:],
            "content": text
        }
    except Exception as exc:
        logger.debug(f"读取日志失败 {path}: {exc}")
        return {"path": path, "size": 0, "preview": "", "content": ""}


def _collect_log_previews(limit: int = 3, include_content: bool = False) -> List[Dict[str, Any]]:
    previews = []
    for path in _find_log_files():
        info = _read_log_snippet(path)
        if not info["preview"]:
            continue
        if not include_content and "content" in info:
            info.pop("content", None)
        previews.append(info)
        if len(previews) >= limit:
            break
    return previews


def _collect_recent_logs_text() -> Optional[str]:
    cutoff = time.time() - 86400  # 24 hours
    log_entries = []
    for path in _find_log_files():
        try:
            if os.path.getmtime(path) < cutoff:
                continue
            snippet = _read_log_snippet(path, BUG_REPORT_MAX_LOG_BYTES)
            preview = snippet.get("content") or snippet.get("preview")
            if not preview:
                continue
            log_entries.append(
                f"===== {path} (last {len(preview)} chars) =====\n{preview}\n"
            )
        except Exception as exc:
            logger.debug(f"收集日志文本失败 {path}: {exc}")
            continue

    if not log_entries:
        return None
    return "\n".join(log_entries)


def _encode_attachment_from_bytes(filename: str, file_bytes: bytes, content_type: str) -> Dict[str, Any]:
    """
    从字节数据编码附件（参考测试脚本的 _encode_attachment）

    Args:
        filename: 文件名
        file_bytes: 文件字节数据
        content_type: MIME类型

    Returns:
        编码后的附件字典
    """
    # 如果无法确定MIME类型，根据扩展名手动设置（参考测试脚本）
    mime_type = content_type
    if not mime_type:
        filename_lower = filename.lower()
        # 处理 .tar.gz 双扩展名
        if filename_lower.endswith('.tar.gz'):
            mime_type = 'application/gzip'
        else:
            ext = os.path.splitext(filename_lower)[1]
            mime_type_map = {
                # 图片
                '.png': 'image/png',
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.gif': 'image/gif',
                '.bmp': 'image/bmp',
                '.webp': 'image/webp',
                '.svg': 'image/svg+xml',
                '.ico': 'image/x-icon',
                '.tiff': 'image/tiff',
                '.tif': 'image/tiff',
                # 文本
                '.txt': 'text/plain',
                '.log': 'text/plain',
                '.md': 'text/markdown',
                '.json': 'application/json',
                '.xml': 'application/xml',
                '.yaml': 'application/x-yaml',
                '.yml': 'application/x-yaml',
                '.csv': 'text/csv',
                # 文档
                '.pdf': 'application/pdf',
                '.doc': 'application/msword',
                '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                '.xls': 'application/vnd.ms-excel',
                '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                '.ppt': 'application/vnd.ms-powerpoint',
                '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
                # 压缩包
                '.zip': 'application/zip',
                '.rar': 'application/x-rar-compressed',
                '.7z': 'application/x-7z-compressed',
                '.tar': 'application/x-tar',
                '.gz': 'application/gzip',
                '.tgz': 'application/gzip',
                '.bz2': 'application/x-bzip2',
                '.xz': 'application/x-xz',
            }
            mime_type = mime_type_map.get(ext, "application/octet-stream")

    # Base64 编码
    encoded = base64.b64encode(file_bytes).decode("ascii")

    # 返回格式：与测试脚本完全一致
    return {
        "name": filename,
        "type": mime_type,
        "data": f"data:{mime_type};base64,{encoded}",
    }


async def _send_bug_report(
    bug_fields: Dict[str, Any],
    attachment_dict: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    发送Bug报告到服务器（完全参考测试脚本的 send_bug 函数）

    Args:
        bug_fields: Bug字段字典
        attachment_dict: 单个附件字典（可选）

    Returns:
        结果字典 {"success": bool, "message": str, "data": dict}
    """
    if not BUG_CLOUD_FUNCTION_URL:
        return {"success": False, "message": "服务器地址未配置"}

    # 构建payload - 与测试脚本完全一致
    payload: Dict[str, Any] = {
        "verifyCode": BUG_CLOUD_VERIFY_CODE,
        "bugData": bug_fields,
    }

    # 单个附件 - 使用 "attachment" 字段（单数）
    if attachment_dict:
        payload["attachment"] = attachment_dict
        logger.info(f"Payload包含附件: name={attachment_dict.get('name')}, type={attachment_dict.get('type')}")

    logger.info(f"发送Bug到服务器: {BUG_CLOUD_FUNCTION_URL}")
    logger.debug(f"Payload keys: {list(payload.keys())}, bugData keys: {list(bug_fields.keys())}")

    timeout = aiohttp.ClientTimeout(total=BUG_REPORT_TIMEOUT_SECONDS)

    try:
        # 参考测试脚本：显式设置 Content-Type 并手动序列化 JSON
        headers = {"Content-Type": "application/json"}
        payload_json = json.dumps(payload, ensure_ascii=False)

        logger.debug(f"发送的JSON长度: {len(payload_json)} 字节")

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(BUG_CLOUD_FUNCTION_URL, data=payload_json, headers=headers) as resp:
                text = await resp.text()
                logger.info(f"服务器响应: status={resp.status}, text_length={len(text)}")

                if resp.status in (200, 201):
                    try:
                        data = await resp.json()
                        logger.info(f"Bug提交成功: {data}")
                        return {"success": True, "data": data}
                    except Exception as e:
                        logger.warning(f"解析响应JSON失败: {e}, 使用原始文本")
                        return {"success": True, "data": {"raw": text}}
                else:
                    logger.error(f"Bug提交失败: status={resp.status}, response={text[:500]}")
                    return {
                        "success": False,
                        "status": resp.status,
                        "message": text[:2000]
                    }
    except Exception as e:
        logger.error(f"发送Bug请求异常: {e}", exc_info=True)
        return {"success": False, "message": f"请求异常: {str(e)}"}

# 学习内容缓存
_style_learning_content_cache: Optional[Dict[str, Any]] = None
_style_learning_content_cache_time: Optional[float] = None
_style_learning_content_cache_ttl: int = 300  # 缓存有效期5分钟

# 设置日志
# logger = logging.getLogger(__name__)

# 性能指标存储
llm_call_metrics: Dict[str, Dict[str, Any]] = {}

def load_password_config() -> Dict[str, Any]:
    """加载密码配置文件，并自动迁移旧格式"""
    password_file_path = get_password_file_path()
    if os.path.exists(password_file_path):
        with open(password_file_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        # 检查是否需要迁移到新的哈希格式
        if 'password_hash' not in config and 'password' in config:
            logger.info("检测到旧格式密码配置，正在迁移到哈希格式...")
            config = migrate_password_to_hashed(config)
            # 保存迁移后的配置
            save_password_config(config)
            logger.info("密码配置迁移完成")

        return config

    # 创建默认配置（使用新的哈希格式）
    default_password = "self_learning_pwd"
    password_hash, salt = PasswordHasher.hash_password(default_password)
    return {
        "password_hash": password_hash,
        "salt": salt,
        "must_change": True,
        "version": 2
    }

def save_password_config(config: Dict[str, Any]):
    """保存密码配置文件"""
    password_file_path = get_password_file_path()
    # 确保目录存在
    os.makedirs(os.path.dirname(password_file_path), exist_ok=True)
    with open(password_file_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2)

def require_auth(f):
    """登录验证装饰器"""
    @wraps(f)
    async def decorated_function(*args, **kwargs):
        if not session.get('authenticated'):
            if request.is_json:
                return jsonify({"error": "Authentication required", "redirect": "/api/login"}), 401
            return redirect(url_for('api.login_page'))
        return await f(*args, **kwargs)
    return decorated_function

# 创建别名以保持向后兼容
login_required = require_auth

def is_authenticated():
    """检查用户是否已认证"""
    return session.get('authenticated', False)

async def set_plugin_services(
    config: PluginConfig,
    factory_manager: FactoryManager,
    llm_c = None,  # 不再使用LLMClient
    astrbot_persona_manager = None  # 添加AstrBot PersonaManager参数
):
    """设置插件服务实例"""
    global plugin_config, persona_manager, persona_updater, database_manager, db_manager, llm_client, llm_adapter_instance, pending_updates, intelligence_metrics_service
    plugin_config = config

    # 将配置存储到app中,供API认证使用
    app.plugin_config = config

    # 使用工厂管理器获取LLM适配器
    try:
        # 从ServiceFactory获取LLM适配器，而不是ComponentFactory
        llm_client = factory_manager.get_service_factory().create_framework_llm_adapter()
        llm_adapter_instance = llm_client  # 设置llm_adapter_instance别名
        logger.info(f"从服务工厂获取LLM适配器: {type(llm_client)}")
    except Exception as e:
        logger.error(f"获取LLM适配器失败: {e}")
        llm_client = llm_c  # 回退到传入的客户端
        llm_adapter_instance = llm_client  # 同步设置别名

    # 总是创建PersonaWebManager，无论是否传入AstrBot PersonaManager
    try:
        if astrbot_persona_manager:
            persona_manager = astrbot_persona_manager
            logger.info(f"设置AstrBot PersonaManager: {type(astrbot_persona_manager)}")
        else:
            logger.warning("未传入AstrBot PersonaManager，将创建空的PersonaWebManager")
            # 从工厂管理器获取服务实例
            try:
                persona_manager = factory_manager.get_service("persona_manager")
            except Exception as e:
                logger.error(f"获取persona_manager服务失败: {e}")
                persona_manager = None
        
        # 总是初始化人格Web管理器（即使PersonaManager为None）
        persona_web_mgr = set_persona_web_manager(astrbot_persona_manager)
        logger.info(f"创建PersonaWebManager: {persona_web_mgr}")
        await persona_web_mgr.initialize()
        logger.info("PersonaWebManager初始化成功")
    except Exception as e:
        logger.error(f"PersonaWebManager初始化失败: {e}", exc_info=True)
        # 即使初始化失败，也要创建一个空的PersonaWebManager以避免500错误
        try:
            set_persona_web_manager(None)
            logger.info("创建了空的PersonaWebManager作为后备方案")
        except Exception as fallback_e:
            logger.error(f"创建后备PersonaWebManager失败: {fallback_e}")
    
    # 从工厂管理器获取其他服务实例
    try:
        logger.info("开始初始化WebUI服务...")

        # 使用更直接的方法获取服务
        service_factory = factory_manager.get_service_factory()
        logger.info("成功获取服务工厂")

        # 获取人格更新器
        logger.info("正在获取人格更新器...")
        try:
            persona_updater = service_factory.get_persona_updater()
            logger.info(f"✅ 成功获取persona_updater: {type(persona_updater)}")
        except Exception as e:
            logger.error(f"❌ 获取persona_updater失败: {e}", exc_info=True)
            persona_updater = None

        # 确保数据库管理器已创建
        logger.info("正在获取数据库管理器...")
        try:
            # 先尝试直接从factory_manager获取
            database_manager = factory_manager.get_service("database_manager")
            if not database_manager:
                logger.warning("从factory_manager.get_service获取database_manager为None，尝试创建")
                service_factory.create_database_manager()
                database_manager = factory_manager.get_service("database_manager")

            db_manager = database_manager  # 设置别名
            logger.info(f"✅ 成功获取database_manager: {type(database_manager)}")
        except Exception as e:
            logger.error(f"❌ 获取database_manager失败: {e}", exc_info=True)
            database_manager = None
            db_manager = None

        # 获取progressive_learning服务
        logger.info("正在获取progressive_learning服务...")
        try:
            progressive_learning = factory_manager.get_service("progressive_learning")
            logger.info(f"✅ 成功获取progressive_learning: {type(progressive_learning)}")
        except Exception as e:
            logger.error(f"❌ 获取progressive_learning失败: {e}", exc_info=True)
            progressive_learning = None

        # 关键修复：设置全局变量！
        logger.info("设置全局变量...")
        globals()['persona_updater'] = persona_updater
        globals()['database_manager'] = database_manager
        globals()['db_manager'] = database_manager
        globals()['progressive_learning'] = progressive_learning

        logger.info(f"全局变量设置完成:")
        logger.info(f"  - persona_updater: {globals().get('persona_updater') is not None}")
        logger.info(f"  - database_manager: {globals().get('database_manager') is not None}")
        logger.info(f"  - progressive_learning: {globals().get('progressive_learning') is not None}")

        if not database_manager:
            logger.error("⚠️ 警告: database_manager为None，WebUI人格审查功能将不可用！")

        # 初始化智能指标计算服务
        logger.info("正在初始化智能指标计算服务...")
        intelligence_metrics_service = IntelligenceMetricsService(
            config=config,
            db_manager=database_manager
        )
        globals()['intelligence_metrics_service'] = intelligence_metrics_service
        logger.info("智能指标计算服务初始化成功")

    except Exception as e:
        logger.error(f"获取服务实例失败: {e}", exc_info=True)
        globals()['persona_updater'] = None
        globals()['database_manager'] = None
        globals()['db_manager'] = None
        globals()['progressive_learning'] = None

    # 加载待审查的人格更新
    if persona_updater:
        try:
            pending_updates = await persona_updater.get_pending_persona_updates()
        except Exception as e:
            logger.error(f"加载待审查人格更新失败: {e}")
            pending_updates = []

    # 加载密码配置
    global password_config
    password_config = load_password_config()

# API 蓝图
api_bp = Blueprint("api", __name__, url_prefix="/api")

@api_bp.route("/")
async def read_root():
    """根目录重定向"""
    global password_config
    password_config = load_password_config() # 每次访问根目录时重新加载密码配置，确保最新状态
    
    # 如果用户已认证，检查是否需要强制更改密码
    if is_authenticated():
        if password_config.get("must_change"):
            return redirect("/api/plugin_change_password")
        return redirect(url_for("api.read_root_index"))
    
    # 未认证用户重定向到登录页
    return redirect(url_for("api.login_page"))

@api_bp.route("/login", methods=["GET"])
async def login_page():
    """显示登录页面"""
    # 如果已登录，重定向到主页
    if is_authenticated():
        return redirect("/api/")
    return await render_template("login.html")

@api_bp.route("/login", methods=["POST"])
async def login():
    """处理用户登录 - 支持MD5加密和暴力破解防护"""
    # 获取客户端IP
    client_ip = request.remote_addr or "unknown"

    # 检查IP是否被锁定
    is_locked, remaining_time = login_attempt_tracker.is_locked(client_ip)
    if is_locked:
        logger.warning(f"IP {client_ip} 被锁定，剩余 {remaining_time} 秒")
        return jsonify({
            "error": f"登录尝试次数过多，请在 {remaining_time} 秒后重试",
            "locked": True,
            "remaining_time": remaining_time
        }), 429

    data = await request.get_json()
    password = data.get("password", "")

    # 清理输入
    password = SecurityValidator.sanitize_input(password, max_length=128)

    if not password:
        return jsonify({"error": "密码不能为空"}), 400

    global password_config
    password_config = load_password_config()

    # 使用支持迁移的验证函数
    is_valid, updated_config = verify_password_with_migration(password, password_config)

    if is_valid:
        # 如果配置被更新（迁移），保存新配置
        if updated_config != password_config:
            save_password_config(updated_config)
            password_config = updated_config

        # 登录成功，清除失败记录
        login_attempt_tracker.record_attempt(client_ip, success=True)

        # 设置会话认证状态
        session['authenticated'] = True
        session.permanent = True

        if password_config.get("must_change"):
            return jsonify({
                "message": "Login successful, but password must be changed",
                "must_change": True,
                "redirect": "/api/plugin_change_password"
            }), 200
        return jsonify({
            "message": "Login successful",
            "must_change": False,
            "redirect": "/api/index"
        }), 200

    # 登录失败，记录尝试
    login_attempt_tracker.record_attempt(client_ip, success=False)
    remaining_attempts = login_attempt_tracker.get_remaining_attempts(client_ip)

    logger.warning(f"IP {client_ip} 登录失败，剩余尝试次数: {remaining_attempts}")

    error_msg = "密码错误"
    if remaining_attempts <= 2:
        error_msg = f"密码错误，还剩 {remaining_attempts} 次尝试机会"

    return jsonify({
        "error": error_msg,
        "remaining_attempts": remaining_attempts
    }), 401

@api_bp.route("/index")
@require_auth
async def read_root_index():
    """主页面"""
    return await render_template("index.html")

@api_bp.route("/plugin_change_password", methods=["GET"])
async def change_password_page():
    """显示修改密码页面"""
    # 检查是否已认证或者是强制更改密码状态
    if not is_authenticated():
        return redirect(url_for('api.login_page'))
    
    # 添加调试信息
    logger.debug(f"Template folder: {WEB_HTML_DIR}")
    logger.debug(f"Looking for template: change_password.html")
    template_path = os.path.join(WEB_HTML_DIR, "change_password.html")
    logger.debug(f"Full template path: {template_path}")
    logger.debug(f"Template exists: {os.path.exists(template_path)}")
    
    return await render_template("change_password.html")

@api_bp.route("/plugin_change_password", methods=["POST"])
async def change_password():
    """处理修改密码请求 - 支持MD5加密存储"""
    # 检查是否已认证
    if not is_authenticated():
        return jsonify({"error": "Authentication required", "redirect": "/api/login"}), 401

    data = await request.get_json()
    old_password = data.get("old_password", "")
    new_password = data.get("new_password", "")

    # 清理输入
    old_password = SecurityValidator.sanitize_input(old_password, max_length=128)
    new_password = SecurityValidator.sanitize_input(new_password, max_length=128)

    if not old_password or not new_password:
        return jsonify({"error": "旧密码和新密码不能为空"}), 400

    global password_config
    password_config = load_password_config()

    # 验证旧密码
    is_valid, _ = verify_password_with_migration(old_password, password_config)
    if not is_valid:
        return jsonify({"error": "当前密码错误"}), 401

    # 检查新密码是否与旧密码相同
    if old_password == new_password:
        return jsonify({"error": "新密码不能与当前密码相同"}), 400

    # 验证新密码强度
    strength_result = SecurityValidator.validate_password_strength(new_password)
    if not strength_result['valid']:
        issues = "、".join(strength_result['issues']) if strength_result['issues'] else "密码强度不足"
        return jsonify({"error": issues}), 400

    # 生成新的哈希密码
    password_hash, salt = PasswordHasher.hash_password(new_password)

    # 更新配置
    password_config = {
        "password_hash": password_hash,
        "salt": salt,
        "must_change": False,
        "version": 2,
        "last_changed": time.time()
    }
    save_password_config(password_config)

    logger.info("密码已更新为MD5哈希格式")
    return jsonify({"message": "密码修改成功"}), 200

@api_bp.route("/logout", methods=["POST"])
@require_auth
async def logout():
    """处理用户登出"""
    session.clear()
    return jsonify({"message": "Logged out successfully", "redirect": "/api/login"}), 200

@api_bp.route("/config")
@require_auth
async def get_plugin_config():
    """获取插件配置"""
    if plugin_config:
        return jsonify(asdict(plugin_config))
    return jsonify({"error": "Plugin config not initialized"}), 500

@api_bp.route("/config", methods=["POST"])
@require_auth
async def update_plugin_config():
    """更新插件配置"""
    if plugin_config:
        new_config = await request.get_json()
        for key, value in new_config.items():
            if hasattr(plugin_config, key):
                setattr(plugin_config, key, value)
        # TODO: 保存配置到文件
        return jsonify({"message": "Config updated successfully", "new_config": asdict(plugin_config)})
    return jsonify({"error": "Plugin config not initialized"}), 500


@api_bp.route("/bug_report/config", methods=["GET"])
@require_auth
async def get_bug_report_config():
    """获取Bug自助提交配置与日志预览"""
    enabled = _bug_report_available()
    log_preview = _collect_log_previews()
    return jsonify({
        "enabled": enabled,
        "cloudFunctionUrl": BUG_CLOUD_FUNCTION_URL,
        "severityOptions": BUG_REPORT_SEVERITY_OPTIONS,
        "priorityOptions": BUG_REPORT_PRIORITY_OPTIONS,
        "typeOptions": BUG_REPORT_TYPE_OPTIONS,
        "defaultBuild": BUG_REPORT_DEFAULT_BUILDS[0] if BUG_REPORT_DEFAULT_BUILDS else "",
        "maxImages": 0 if not BUG_REPORT_ATTACHMENT_ENABLED else BUG_REPORT_MAX_IMAGES,  # 禁用附件时为0
        "maxImageBytes": BUG_REPORT_MAX_IMAGE_BYTES,
        "allowedExtensions": sorted(list(BUG_REPORT_ALLOWED_EXTENSIONS)) if BUG_REPORT_ATTACHMENT_ENABLED else [],
        "attachmentEnabled": BUG_REPORT_ATTACHMENT_ENABLED,  # 新增：告诉前端是否启用附件
        "logPreview": log_preview,
        "message": "Bug自助提交通过云函数转发（暂不支持附件上传）" if enabled else "Bug自助提交功能暂不可用，请联系管理员"
    })


@api_bp.route("/bug_report", methods=["POST"])
@require_auth
async def submit_bug_report():
    """提交Bug到禅道接口"""
    if not _bug_report_available():
        return jsonify({"error": "Bug提交未配置或已禁用"}), 400

    try:
        form = await request.form
        files = await request.files
    except Exception as exc:
        logger.error(f"解析Bug提交数据失败: {exc}")
        return jsonify({"error": "提交内容解析失败"}), 400

    title = (form.get("title") or "").strip() or "未命名问题"
    severity = int(form.get("severity") or BUG_REPORT_DEFAULT_SEVERITY)
    priority = int(form.get("priority") or BUG_REPORT_DEFAULT_PRIORITY)
    bug_type = (form.get("bugType") or BUG_REPORT_DEFAULT_TYPE).strip()
    build = (form.get("build") or (BUG_REPORT_DEFAULT_BUILDS[0] if BUG_REPORT_DEFAULT_BUILDS else "unknown")).strip()
    steps = (form.get("steps") or "").strip()
    description = (form.get("description") or "").strip()
    environment = (form.get("environment") or "").strip()
    include_logs = (form.get("includeLogs") or "true").lower() in ("1", "true", "yes", "on")

    request_meta = f"IP: {request.remote_addr or 'unknown'}\nUser-Agent: {request.headers.get('User-Agent', 'unknown')}"
    full_description = description or "（未提供描述）"
    if environment:
        full_description += f"\n\n【运行环境】\n{environment}"
    full_description += f"\n\n【请求元信息】\n{request_meta}"

    bug_fields = {
        "title": title,
        "severity": severity,
        "pri": priority,
        "type": bug_type,
        "openedBuild": [build],
        "steps": steps or "暂无明确的复现步骤",
        "description": full_description,
        "openedBy": "astrbot_plugin_self_learning"
    }

    raw_attachments: List[Dict[str, Any]] = []

    # 处理上传的文件
    # 检查附件功能是否启用
    if files and files.getlist("attachments") and not BUG_REPORT_ATTACHMENT_ENABLED:
        return jsonify({"error": "附件上传功能暂时不可用，请稍后再试"}), 400

    upload_list = files.getlist("attachments") if files else []
    for file_storage in upload_list:
        if not file_storage:
            continue

        original_filename = file_storage.filename or f"screenshot_{int(time.time())}.png"
        filename = secure_filename(original_filename)
        mimetype = file_storage.mimetype or ""

        # 安全检查：验证文件类型
        is_safe, error_msg = _is_safe_attachment(filename, mimetype)
        if not is_safe:
            logger.warning(f"拒绝不安全的附件上传: {filename}, 原因: {error_msg}")
            return jsonify({"error": f"附件安全检查失败: {error_msg}"}), 400

        file_bytes = await file_storage.read()
        if not file_bytes:
            continue
        if len(file_bytes) > BUG_REPORT_MAX_IMAGE_BYTES:
            return jsonify({"error": f"单个附件不能超过 {BUG_REPORT_MAX_IMAGE_BYTES // (1024 * 1024)}MB"}), 400
        raw_attachments.append({
            "filename": filename or "screenshot.png",
            "content_type": file_storage.mimetype or "image/png",
            "data": file_bytes
        })
        if len(raw_attachments) >= BUG_REPORT_MAX_IMAGES:
            break

    try:
        # 自动附带日志摘要到描述中
        if include_logs:
            log_previews = _collect_log_previews(limit=2, include_content=True)
            if log_previews:
                log_text_sections = ["\n\n【自动附带日志摘要】"]
                for log in log_previews:
                    content = log.get("content", "")
                    if not content:
                        continue
                    tail = content[-BUG_REPORT_MAX_LOG_BYTES:]
                    log_text_sections.append(f"--- {log['path']} | 最近 {len(tail)} 字节 ---\n{tail}")
                if len(log_text_sections) > 1:
                    full_description += "\n".join(log_text_sections)

        bug_fields["description"] = full_description

        # 使用新的编码函数处理附件（参考测试脚本）
        attachment_dict = None
        if raw_attachments:
            # 只取第一个附件
            first_attachment = raw_attachments[0]
            logger.info(f"准备编码附件: filename={first_attachment['filename']}, size={len(first_attachment['data'])} bytes, type={first_attachment['content_type']}")

            try:
                attachment_dict = _encode_attachment_from_bytes(
                    filename=first_attachment["filename"],
                    file_bytes=first_attachment["data"],
                    content_type=first_attachment["content_type"]
                )
                logger.info(f"附件编码成功: name={attachment_dict['name']}, type={attachment_dict['type']}, data_length={len(attachment_dict['data'])}")
            except Exception as e:
                logger.error(f"附件编码失败: {e}", exc_info=True)
                return jsonify({"error": f"附件编码失败: {str(e)}"}), 500

            # 如果有多个附件，添加警告
            if len(raw_attachments) > 1:
                warning_msg = f"\n\n⚠️ 注意：检测到 {len(raw_attachments)} 个附件，但服务器支持单个附件。仅第一个附件 '{first_attachment['filename']}' 将被提交。如需提交多个文件，建议打包为压缩包后上传。"
                bug_fields["description"] += warning_msg
                logger.warning(f"Bug提交包含多个附件({len(raw_attachments)}个)，只会提交第一个: {first_attachment['filename']}")

        # 调用发送函数（完全参考测试脚本）
        logger.info(f"准备发送Bug报告: has_attachment={attachment_dict is not None}")
        result = await _send_bug_report(bug_fields, attachment_dict)
        logger.info(f"Bug提交结果: success={result.get('success')}, status={result.get('status')}, message={result.get('message', '')[:200]}")
        if result.get("success"):
            data = result.get("data", {})
            bug_id = data.get("id")
            return jsonify({
                "success": True,
                "bugId": bug_id,
                "message": f"Bug提交成功 (ID: {bug_id})" if bug_id else "Bug提交成功",
                "response": data
            })
        return jsonify({
            "error": result.get("message", "Bug提交失败"),
            "status": result.get("status")
        }), 502
    except Exception as exc:
        logger.error(f"Bug提交异常: {exc}", exc_info=True)
        return jsonify({"error": f"Bug提交异常: {exc}"}), 500

@api_bp.route("/persona_updates")
@require_auth
async def get_persona_updates():
    """获取需要人工审查的人格更新内容（包括风格学习审查和人格学习审查）"""
    logger.info("开始获取persona_updates数据...")
    all_updates = []
    
    # 1. 获取传统的人格更新审查
    if persona_updater:
        try:
            logger.info("正在获取传统人格更新...")
            traditional_updates = await persona_updater.get_pending_persona_updates()
            logger.info(f"获取到 {len(traditional_updates)} 个传统人格更新")
            
            # 将PersonaUpdateRecord对象转换为字典格式，确保数据完整
            for record in traditional_updates:
                # 使用dataclass的asdict或手动转换
                if hasattr(record, '__dict__'):
                    record_dict = record.__dict__.copy()
                else:
                    # 手动构建字典
                    record_dict = {
                        'id': getattr(record, 'id', None),
                        'timestamp': getattr(record, 'timestamp', 0),
                        'group_id': getattr(record, 'group_id', 'default'),
                        'update_type': getattr(record, 'update_type', 'unknown'),
                        'original_content': getattr(record, 'original_content', ''),
                        'new_content': getattr(record, 'new_content', ''),
                        'reason': getattr(record, 'reason', ''),
                        'status': getattr(record, 'status', 'pending'),
                        'reviewer_comment': getattr(record, 'reviewer_comment', None),
                        'review_time': getattr(record, 'review_time', None)
                    }
                
                # 添加一些前端需要的字段
                record_dict['proposed_content'] = record_dict.get('new_content', '')
                record_dict['confidence_score'] = 0.8  # 默认置信度
                record_dict['reviewed'] = record_dict.get('status', 'pending') != 'pending'
                record_dict['approved'] = record_dict.get('status', 'pending') == 'approved'
                record_dict['review_source'] = 'traditional'  # 标记来源
                
                all_updates.append(record_dict)
                
        except Exception as e:
            logger.error(f"获取传统人格更新失败: {e}")
    else:
        logger.warning("persona_updater 不可用")
    
    # 2. 获取人格学习审查（包括渐进式学习、表达学习等）
    if database_manager:
        try:
            logger.info("正在获取人格学习审查...")
            # ✅ 移除数量限制，获取所有待审查记录
            persona_learning_reviews = await database_manager.get_pending_persona_learning_reviews(limit=999999)
            logger.info(f"获取到 {len(persona_learning_reviews)} 个人格学习审查")

            for review in persona_learning_reviews:
                # ✅ 使用新的常量进行类型标准化和分类
                raw_update_type = review.get('update_type', '')
                normalized_type = normalize_update_type(raw_update_type)
                review_source = get_review_source_from_update_type(raw_update_type)

                # ✅ 修复：只跳过真正的风格学习（精确匹配）
                # 渐进式人格学习不再被误判为风格学习
                if normalized_type == UPDATE_TYPE_STYLE_LEARNING:
                    # Few-shot风格学习在步骤3单独处理，这里跳过
                    logger.debug(f"跳过风格学习记录 ID={review['id']}，在步骤3处理")
                    continue

                # ✅ 获取原人格文本（如果数据库中为空，实时获取）
                original_content = review['original_content']
                group_id = review['group_id']

                if not original_content or original_content.strip() == '':
                    # 数据库中没有原人格，实时获取
                    logger.info(f"数据库中没有原人格文本，实时获取群组 {group_id} 的原人格")
                    try:
                        if persona_manager:
                            current_persona = await persona_manager.get_default_persona_v3(group_id)
                            if current_persona and current_persona.get('prompt'):
                                original_content = current_persona.get('prompt', '')
                                logger.info(f"成功获取群组 {group_id} 的原人格文本，长度: {len(original_content)}")
                            else:
                                original_content = "[无法获取原人格文本]"
                                logger.warning(f"无法获取群组 {group_id} 的原人格文本")
                        else:
                            original_content = "[PersonaManager未初始化]"
                            logger.warning("PersonaManager未初始化，无法获取原人格")
                    except Exception as e:
                        logger.warning(f"获取群组 {group_id} 原人格失败: {e}")
                        original_content = f"[获取原人格失败: {str(e)}]"

                # 转换为统一的审查格式
                review_dict = {
                    # ✅ 根据review_source决定ID前缀
                    'id': f"persona_learning_{review['id']}" if review_source == 'persona_learning' else str(review['id']),
                    'timestamp': review['timestamp'],
                    'group_id': group_id,
                    'update_type': raw_update_type,  # 保留原始类型用于显示
                    'normalized_type': normalized_type,  # 添加标准化类型
                    'original_content': original_content,  # ✅ 使用获取到的原人格文本
                    'new_content': review['new_content'],
                    'proposed_content': review.get('proposed_content', review['new_content']),
                    'reason': review['reason'],
                    'status': review['status'],
                    'reviewer_comment': review['reviewer_comment'],
                    'review_time': review['review_time'],
                    'confidence_score': review.get('confidence_score', 0.5),
                    'reviewed': False,
                    'approved': False,
                    'review_source': review_source,
                    'persona_learning_review_id': review['id'],  # 原始ID用于审批操作
                    # 添加metadata中的关键字段到顶层，方便前端访问
                    'features_content': review.get('metadata', {}).get('features_content', ''),
                    'llm_response': review.get('metadata', {}).get('llm_response', ''),
                    'total_raw_messages': review.get('metadata', {}).get('total_raw_messages', 0),
                    'messages_analyzed': review.get('metadata', {}).get('messages_analyzed', 0),
                    'metadata': review.get('metadata', {}),  # 保留完整的metadata
                    # ✅ 新增：从metadata提取高亮位置信息
                    'incremental_content': review.get('metadata', {}).get('incremental_content', ''),
                    'incremental_start_pos': review.get('metadata', {}).get('incremental_start_pos', 0)
                }

                all_updates.append(review_dict)
                logger.debug(f"添加审查记录: ID={review_dict['id']}, type={raw_update_type}, source={review_source}")

        except Exception as e:
            logger.error(f"获取人格学习审查失败: {e}", exc_info=True)
    else:
        logger.warning("database_manager 不可用")
    
    # 3. 获取风格学习审查（Few-shot样本学习）
    if database_manager:
        try:
            logger.info("正在获取风格学习审查...")
            # ✅ 移除数量限制，获取所有待审查记录
            style_reviews = await database_manager.get_pending_style_reviews(limit=999999)
            logger.info(f"获取到 {len(style_reviews)} 个风格学习审查")

            for review in style_reviews:
                # ✅ 获取当前群组的原人格文本
                group_id = review['group_id']
                original_persona_text = ""

                try:
                    # 通过 persona_manager 获取当前人格
                    if persona_manager:
                        current_persona = await persona_manager.get_default_persona_v3(group_id)
                        if current_persona and current_persona.get('prompt'):
                            original_persona_text = current_persona.get('prompt', '')
                        else:
                            original_persona_text = "[无法获取原人格文本]"
                    else:
                        original_persona_text = "[PersonaManager未初始化]"
                except Exception as e:
                    logger.warning(f"获取群组 {group_id} 原人格失败: {e}")
                    original_persona_text = f"[获取原人格失败: {str(e)}]"

                # ✅ 构建完整的新内容（原人格 + Few-shot内容）
                few_shots_content = review['few_shots_content']
                full_new_content = original_persona_text + "\n\n" + few_shots_content if original_persona_text else few_shots_content

                # 转换为统一的审查格式
                review_dict = {
                    'id': f"style_{review['id']}",  # 添加前缀避免ID冲突
                    'timestamp': review['timestamp'],
                    'group_id': group_id,
                    'update_type': UPDATE_TYPE_STYLE_LEARNING,  # ✅ 使用常量
                    'normalized_type': UPDATE_TYPE_STYLE_LEARNING,
                    'original_content': original_persona_text,  # ✅ 使用实际的原人格文本
                    'new_content': full_new_content,  # ✅ 原人格 + Few-shot内容
                    'proposed_content': few_shots_content,  # 保持为增量部分
                    'reason': review['description'],
                    'status': review['status'],
                    'reviewer_comment': None,
                    'review_time': None,
                    'confidence_score': 0.9,  # 风格学习置信度高一些
                    'reviewed': False,
                    'approved': False,
                    'review_source': 'style_learning',  # 标记来源
                    'learned_patterns': review.get('learned_patterns', []),  # 额外信息
                    'style_review_id': review['id'],  # 原始ID用于审批操作
                    # ✅ 新增：方便前端计算高亮位置
                    'incremental_start_pos': len(original_persona_text) + 2 if original_persona_text else 0  # +2 是因为有 \n\n
                }

                all_updates.append(review_dict)

        except Exception as e:
            logger.error(f"获取风格学习审查失败: {e}")
    
    # 按时间倒序排列
    all_updates.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
    
    logger.info(f"返回 {len(all_updates)} 条人格更新记录给WebUI (传统: {len([u for u in all_updates if u['review_source'] == 'traditional'])}, 人格学习: {len([u for u in all_updates if u['review_source'] == 'persona_learning'])}, 风格学习: {len([u for u in all_updates if u['review_source'] == 'style_learning'])})")
    
    return jsonify({
        "success": True,
        "updates": all_updates,
        "total": len(all_updates)
    })

@api_bp.route("/persona_updates/<update_id>/review", methods=["POST"])
@require_auth
async def review_persona_update(update_id: str):
    """审查人格更新内容 (批准/拒绝) - 包括风格学习审查和人格学习审查"""
    try:
        # 获取全局服务实例并进行调试检查
        global persona_updater, database_manager
        
        logger.info(f"=== 开始审查人格更新 {update_id} ===")
        logger.info(f"全局persona_updater状态: {persona_updater is not None}")
        logger.info(f"全局database_manager状态: {database_manager is not None}")
        
        if persona_updater:
            logger.info(f"PersonaUpdater类型: {type(persona_updater)}")
            logger.info(f"PersonaUpdater backup_manager状态: {hasattr(persona_updater, 'backup_manager')}")
            if hasattr(persona_updater, 'backup_manager'):
                logger.info(f"backup_manager类型: {type(persona_updater.backup_manager)}")
        
        if database_manager:
            logger.info(f"DatabaseManager类型: {type(database_manager)}")
        
        data = await request.get_json()
        action = data.get("action")
        comment = data.get("comment", "")
        modified_content = data.get("modified_content")  # 用户修改后的内容
        
        logger.info(f"审查操作: {action}, 有修改内容: {modified_content is not None}")
        
        # 将action转换为合适的status
        if action == "approve":
            status = "approved"
        elif action == "reject":
            status = "rejected"
        else:
            return jsonify({"error": "Invalid action, must be 'approve' or 'reject'"}), 400
        
        # 判断审查类型
        if update_id.startswith("style_"):
            # 风格学习审查
            style_review_id = int(update_id.replace("style_", ""))
            
            if action == "approve":
                # 批准风格学习审查
                return await approve_style_learning_review(style_review_id)
            else:
                # 拒绝风格学习审查
                return await reject_style_learning_review(style_review_id)
                
        elif update_id.startswith("persona_learning_"):
            # 人格学习审查（质量不达标的学习结果）
            persona_learning_review_id = int(update_id.replace("persona_learning_", ""))
            
            if not database_manager:
                return jsonify({"error": "Database manager not initialized"}), 500
            
            # 更新审查状态，并保存修改后的内容和审查备注
            success = await database_manager.update_persona_learning_review_status(
                persona_learning_review_id, status, comment, modified_content
            )
            
            if success:
                if action == "approve":
                    # 批准后应用人格更新并备份
                    try:
                        # 获取人格学习审查详情
                        review_data = await database_manager.get_persona_learning_review_by_id(persona_learning_review_id)
                        if review_data:
                            # 使用修改后的内容（如果有）或原始proposed_content
                            content_to_apply = modified_content if modified_content else review_data.get('proposed_content')
                            
                            # 如果有persona_updater，使用它来应用人格更新
                            if persona_updater and content_to_apply:
                                try:
                                    logger.info(f"开始应用人格学习审查 {persona_learning_review_id}，群组: {review_data.get('group_id', 'default')}")
                                    logger.info(f"待应用内容长度: {len(content_to_apply)} 字符")
                                    
                                    # 使用已经写好的完整人格更新方法
                                    # 首先需要将content_to_apply转换为style_analysis格式
                                    style_analysis = {
                                        'enhanced_prompt': content_to_apply,
                                        'style_features': [],
                                        'style_attributes': {},
                                        'confidence': 0.8,
                                        'source': f'人格学习审查{persona_learning_review_id}'
                                    }
                                    logger.info(f"构建style_analysis: {style_analysis['source']}")
                                    
                                    # 使用空的filtered_messages（因为我们直接有学习内容）
                                    filtered_messages = []
                                    
                                    # 调用框架API方式的人格更新方法（包含自动备份）
                                    logger.info("调用update_persona_with_style方法...")
                                    success_apply = await persona_updater.update_persona_with_style(
                                        review_data.get('group_id', 'default'),
                                        style_analysis,
                                        filtered_messages
                                    )
                                    logger.info(f"update_persona_with_style返回结果: {success_apply}")
                                    
                                    if success_apply:
                                        logger.info(f"✅ 人格学习审查 {persona_learning_review_id} 已成功应用到人格（使用框架API方式）")
                                        message = f"人格学习审查 {persona_learning_review_id} 已批准并应用到人格"
                                    else:
                                        logger.warning(f"❌ 人格学习审查 {persona_learning_review_id} 批准成功但应用失败")
                                        message = f"人格学习审查 {persona_learning_review_id} 已批准，但人格应用失败"
                                        
                                except Exception as apply_error:
                                    logger.error(f"❌ 应用人格更新失败: {apply_error}", exc_info=True)
                                    message = f"人格学习审查 {persona_learning_review_id} 已批准，但应用过程出错: {str(apply_error)}"
                            elif not persona_updater:
                                logger.warning("PersonaUpdater未初始化，无法应用人格更新")
                                message = f"人格学习审查 {persona_learning_review_id} 已批准，但无法应用人格更新"
                            else:
                                logger.warning(f"人格学习审查 {persona_learning_review_id} 缺少人格内容")
                                message = f"人格学习审查 {persona_learning_review_id} 已批准，但缺少人格内容"
                        else:
                            logger.error(f"无法获取人格学习审查 {persona_learning_review_id} 的详情")
                            message = f"人格学习审查 {persona_learning_review_id} 已批准，但无法获取详情"
                    except Exception as e:
                        logger.error(f"应用人格学习审查失败: {e}")
                        message = f"人格学习审查 {persona_learning_review_id} 已批准，但应用过程出错: {str(e)}"
                else:
                    message = f"人格学习审查 {persona_learning_review_id} 已拒绝"
                    
                return jsonify({"success": True, "message": message})
            else:
                return jsonify({"error": "Failed to update persona learning review status"}), 500
                
        else:
            # 传统人格审查
            if persona_updater:
                result = await persona_updater.review_persona_update(int(update_id), status, comment)
                if result:
                    return jsonify({"success": True, "message": f"人格更新 {update_id} 已{action}"})
                else:
                    return jsonify({"error": "Failed to update persona review status"}), 500
            else:
                return jsonify({"error": "Persona updater not initialized"}), 500
                
    except ValueError as e:
        return jsonify({"error": f"Invalid update_id format: {str(e)}"}), 400
    except Exception as e:
        logger.error(f"审查人格更新失败: {e}")
        return jsonify({"error": str(e)}), 500

@api_bp.route("/persona_updates/reviewed", methods=["GET"])
@require_auth
async def get_reviewed_persona_updates():
    """获取已审查的人格更新列表"""
    try:
        limit = request.args.get('limit', 50)
        offset = request.args.get('offset', 0)
        status_filter = request.args.get('status')  # 'approved' 或 'rejected' 或 None
        
        # 获取已审查的人格更新记录
        reviewed_updates = []
        
        # 从传统人格更新审查获取
        if persona_updater:
            traditional_updates = await persona_updater.get_reviewed_persona_updates(limit, offset, status_filter)
            reviewed_updates.extend(traditional_updates)
        
        # 从人格学习审查获取
        if database_manager:
            persona_learning_updates = await database_manager.get_reviewed_persona_learning_updates(limit, offset, status_filter)
            reviewed_updates.extend(persona_learning_updates)
        
        # 从风格学习审查获取
        if database_manager:
            style_updates = await database_manager.get_reviewed_style_learning_updates(limit, offset, status_filter)
            # 将风格审查转换为统一格式
            for update in style_updates:
                if 'id' in update:
                    update['id'] = f"style_{update['id']}"
            reviewed_updates.extend(style_updates)
        
        # 按审查时间排序
        reviewed_updates.sort(key=lambda x: x.get('review_time', 0), reverse=True)
        
        return jsonify({
            "success": True,
            "updates": reviewed_updates,
            "total": len(reviewed_updates)
        })
        
    except Exception as e:
        logger.error(f"获取已审查人格更新失败: {e}")
        return jsonify({"error": str(e)}), 500

@api_bp.route("/persona_updates/<update_id>/revert", methods=["POST"])
@require_auth
async def revert_persona_update(update_id: str):
    """撤回人格更新审查"""
    try:
        data = await request.get_json()
        reason = data.get("reason", "撤回审查决定")
        
        # 判断撤回类型
        if update_id.startswith("style_"):
            # 风格学习审查撤回
            style_review_id = int(update_id.replace("style_", ""))
            
            if not database_manager:
                return jsonify({"error": "Database manager not initialized"}), 500
            
            # 将状态改回pending
            success = await database_manager.update_style_review_status(
                style_review_id, "pending"
            )
            
            if success:
                message = f"风格学习审查 {style_review_id} 已撤回，重新回到待审查状态"
                return jsonify({"success": True, "message": message})
            else:
                return jsonify({"error": "Failed to revert style learning review"}), 500
                
        elif update_id.startswith("persona_learning_"):
            # 人格学习审查撤回
            persona_learning_review_id = int(update_id.replace("persona_learning_", ""))
            
            if not database_manager:
                return jsonify({"error": "Database manager not initialized"}), 500
            
            # 将状态改回pending
            success = await database_manager.update_persona_learning_review_status(
                persona_learning_review_id, "pending", f"撤回操作: {reason}"
            )
            
            if success:
                message = f"人格学习审查 {persona_learning_review_id} 已撤回，重新回到待审查状态"
                return jsonify({"success": True, "message": message})
            else:
                return jsonify({"error": "Failed to revert persona learning review"}), 500
        else:
            # 传统人格审查撤回
            if persona_updater:
                result = await persona_updater.revert_persona_update_review(int(update_id), reason)
                if result:
                    message = f"人格更新 {update_id} 审查已撤回，重新回到待审查状态"
                    return jsonify({"success": True, "message": message})
                else:
                    return jsonify({"error": "Failed to revert persona update review"}), 500
            else:
                return jsonify({"error": "Persona updater not initialized"}), 500
                
    except ValueError as e:
        return jsonify({"error": f"Invalid update_id format: {str(e)}"}), 400
    except Exception as e:
        logger.error(f"撤回人格更新审查失败: {e}")
        return jsonify({"error": str(e)}), 500

# 删除人格更新审查记录
@api_bp.route("/persona_updates/<update_id>/delete", methods=["POST"])
async def delete_persona_update(update_id):
    """删除人格更新审查记录"""
    try:
        # 使用全局变量而不是 current_app.plugin_instance
        global database_manager, persona_updater
        if not database_manager:
            return jsonify({"error": "Database manager not available"}), 500

        # 解析update_id，处理前缀（persona_learning_、style_）
        if isinstance(update_id, str):
            if update_id.startswith("persona_learning_"):
                numeric_id = int(update_id.replace("persona_learning_", ""))
                # 删除人格学习审查记录
                success = await database_manager.delete_persona_learning_review_by_id(numeric_id)
                if success:
                    message = f"人格学习审查记录 {numeric_id} 已删除"
                    return jsonify({"success": True, "message": message})
                else:
                    return jsonify({"error": f"未找到人格学习审查记录: {numeric_id}"}), 404

            elif update_id.startswith("style_"):
                numeric_id = int(update_id.replace("style_", ""))
                # 删除风格学习审查记录
                success = await database_manager.delete_style_review_by_id(numeric_id)
                if success:
                    message = f"风格学习审查记录 {numeric_id} 已删除"
                    return jsonify({"success": True, "message": message})
                else:
                    return jsonify({"error": f"未找到风格学习审查记录: {numeric_id}"}), 404

            else:
                # 尝试作为纯数字ID处理
                try:
                    numeric_id = int(update_id)
                except ValueError:
                    return jsonify({"error": f"无效的ID格式: {update_id}"}), 400
        else:
            numeric_id = int(update_id)

        # 尝试删除人格学习审查记录
        success = await database_manager.delete_persona_learning_review_by_id(numeric_id)

        if success:
            message = f"人格学习审查记录 {numeric_id} 已删除"
            return jsonify({"success": True, "message": message})
        else:
            # 如果人格学习审查记录不存在，尝试删除传统人格审查记录
            if persona_updater:
                result = await persona_updater.delete_persona_update_review(numeric_id)
                if result:
                    message = f"人格更新审查记录 {numeric_id} 已删除"
                    return jsonify({"success": True, "message": message})
                else:
                    return jsonify({"error": "Record not found"}), 404
            else:
                return jsonify({"error": "Record not found"}), 404

    except Exception as e:
        logger.error(f"删除人格更新审查记录失败: {e}")
        return jsonify({"error": str(e)}), 500

# 批量删除人格更新审查记录
@api_bp.route("/persona_updates/batch_delete", methods=["POST"])
async def batch_delete_persona_updates():
    """批量删除人格更新审查记录"""
    try:
        data = await request.get_json()
        update_ids = data.get('update_ids', [])
        
        if not update_ids or not isinstance(update_ids, list):
            return jsonify({"error": "update_ids is required and must be a list"}), 400
        
        # 使用全局变量而不是 current_app.plugin_instance
        global database_manager, persona_updater
        if not database_manager:
            return jsonify({"error": "Database manager not available"}), 500
        
        success_count = 0
        failed_count = 0

        for update_id in update_ids:
            try:
                # 解析update_id，处理前缀（persona_learning_、style_）
                if isinstance(update_id, str):
                    if update_id.startswith("persona_learning_"):
                        numeric_id = int(update_id.replace("persona_learning_", ""))
                        # 删除人格学习审查记录
                        success = await database_manager.delete_persona_learning_review_by_id(numeric_id)
                        if success:
                            success_count += 1
                        else:
                            failed_count += 1
                            logger.warning(f"未找到人格学习审查记录: {numeric_id}")
                    elif update_id.startswith("style_"):
                        numeric_id = int(update_id.replace("style_", ""))
                        # 删除风格学习审查记录
                        success = await database_manager.delete_style_review_by_id(numeric_id)
                        if success:
                            success_count += 1
                        else:
                            failed_count += 1
                            logger.warning(f"未找到风格学习审查记录: {numeric_id}")
                    else:
                        # 纯数字ID,尝试删除传统人格审查记录
                        numeric_id = int(update_id)
                        if persona_updater:
                            result = await persona_updater.delete_persona_update_review(numeric_id)
                            if result:
                                success_count += 1
                            else:
                                failed_count += 1
                                logger.warning(f"未找到传统人格审查记录: {numeric_id}")
                        else:
                            failed_count += 1
                            logger.warning("persona_updater不可用")
                else:
                    # 纯数字ID
                    numeric_id = int(update_id)
                    # 先尝试删除人格学习审查记录
                    success = await database_manager.delete_persona_learning_review_by_id(numeric_id)

                    if success:
                        success_count += 1
                    else:
                        # 如果人格学习审查记录不存在，尝试删除传统人格审查记录
                        if persona_updater:
                            result = await persona_updater.delete_persona_update_review(numeric_id)
                            if result:
                                success_count += 1
                            else:
                                failed_count += 1
                        else:
                            failed_count += 1

            except Exception as e:
                logger.error(f"删除人格更新审查记录 {update_id} 失败: {e}")
                failed_count += 1
        
        return jsonify({
            "success": True,
            "message": f"批量删除完成：成功 {success_count} 条，失败 {failed_count} 条",
            "details": {
                "success_count": success_count,
                "failed_count": failed_count,
                "total_count": len(update_ids)
            }
        })
                
    except Exception as e:
        logger.error(f"批量删除人格更新审查记录失败: {e}")
        return jsonify({"error": str(e)}), 500

# 批量操作人格更新审查记录（批准、拒绝）
@api_bp.route("/persona_updates/batch_review", methods=["POST"])
async def batch_review_persona_updates():
    """批量审查人格更新记录"""
    try:
        data = await request.get_json()
        update_ids = data.get('update_ids', [])
        action = data.get('action')  # 'approve' or 'reject'
        comment = data.get('comment', '')

        if not update_ids or not isinstance(update_ids, list):
            return jsonify({"error": "update_ids is required and must be a list"}), 400

        if action not in ['approve', 'reject']:
            return jsonify({"error": "action must be 'approve' or 'reject'"}), 400

        # 使用全局变量而不是 current_app.plugin_instance
        global database_manager, persona_updater
        if not database_manager:
            return jsonify({"error": "Database manager not available"}), 500

        success_count = 0
        failed_count = 0

        for update_id in update_ids:
            try:
                # 解析update_id，处理前缀（persona_learning_、style_）
                if isinstance(update_id, str):
                    if update_id.startswith("persona_learning_"):
                        # 人格学习审查记录
                        numeric_id = int(update_id.replace("persona_learning_", ""))
                        review_data = await database_manager.get_persona_learning_review_by_id(numeric_id)

                        if review_data:
                            status = 'approved' if action == 'approve' else 'rejected'
                            success = await database_manager.update_persona_learning_review_status(
                                numeric_id, status, comment
                            )

                            if success and action == 'approve':
                                # 如果批准，还需要应用人格更新
                                content_to_apply = review_data.get('proposed_content') or review_data.get('new_content')
                                if persona_updater and content_to_apply:
                                    try:
                                        style_analysis = {
                                            'enhanced_prompt': content_to_apply,
                                            'style_features': [],
                                            'style_attributes': {},
                                            'confidence': 0.8,
                                            'source': f'批量审查{update_id}'
                                        }

                                        success_apply = await persona_updater.update_persona_with_style(
                                            review_data.get('group_id', 'default'),
                                            style_analysis,
                                            []
                                        )

                                        if success_apply:
                                            logger.info(f"批量审查 {update_id} 已成功应用到人格（使用框架API方式）")
                                        else:
                                            logger.warning(f"批量审查 {update_id} 应用失败")

                                    except Exception as apply_error:
                                        logger.error(f"批量审查 {update_id} 应用过程出错: {apply_error}")

                            if success:
                                success_count += 1
                            else:
                                failed_count += 1
                        else:
                            failed_count += 1
                            logger.warning(f"未找到人格学习审查记录: {numeric_id}")

                    elif update_id.startswith("style_"):
                        # 风格学习审查记录
                        numeric_id = int(update_id.replace("style_", ""))
                        status = 'approved' if action == 'approve' else 'rejected'
                        success = await database_manager.update_style_review_status(numeric_id, status)

                        if success:
                            success_count += 1
                            logger.info(f"风格学习审查 {update_id} 已{status}")
                        else:
                            failed_count += 1
                            logger.warning(f"未找到风格学习审查记录: {numeric_id}")
                    else:
                        # 尝试作为纯数字ID处理（传统人格审查记录）
                        numeric_id = int(update_id)
                        if persona_updater:
                            status = "approved" if action == 'approve' else "rejected"
                            result = await persona_updater.review_persona_update(numeric_id, status, comment)
                            if result:
                                success_count += 1
                            else:
                                failed_count += 1
                        else:
                            failed_count += 1
                else:
                    # 纯数字ID - 尝试人格学习审查记录
                    numeric_id = int(update_id)
                    review_data = await database_manager.get_persona_learning_review_by_id(numeric_id)

                    if review_data:
                        # 人格学习审查记录
                        status = 'approved' if action == 'approve' else 'rejected'
                        success = await database_manager.update_persona_learning_review_status(
                            numeric_id, status, comment
                        )

                        if success and action == 'approve':
                            # 如果批准，还需要应用人格更新
                            content_to_apply = review_data.get('proposed_content') or review_data.get('new_content')
                            if persona_updater and content_to_apply:
                                try:
                                    style_analysis = {
                                        'enhanced_prompt': content_to_apply,
                                        'style_features': [],
                                        'style_attributes': {},
                                        'confidence': 0.8,
                                        'source': f'批量审查{update_id}'
                                    }

                                    success_apply = await persona_updater.update_persona_with_style(
                                        review_data.get('group_id', 'default'),
                                        style_analysis,
                                        []
                                    )

                                    if success_apply:
                                        logger.info(f"批量审查 {update_id} 已成功应用到人格（使用框架API方式）")
                                    else:
                                        logger.warning(f"批量审查 {update_id} 应用失败")

                                except Exception as apply_error:
                                    logger.error(f"批量审查 {update_id} 应用过程出错: {apply_error}")

                        if success:
                            success_count += 1
                        else:
                            failed_count += 1
                    else:
                        # 传统人格审查记录
                        if persona_updater:
                            status = "approved" if action == 'approve' else "rejected"
                            result = await persona_updater.review_persona_update(numeric_id, status, comment)
                            if result:
                                success_count += 1
                            else:
                                failed_count += 1
                        else:
                            failed_count += 1

            except Exception as e:
                logger.error(f"批量审查人格更新记录 {update_id} 失败: {e}")
                failed_count += 1

        action_text = "批准" if action == 'approve' else "拒绝"
        return jsonify({
            "success": True,
            "message": f"批量{action_text}完成：成功 {success_count} 条，失败 {failed_count} 条",
            "details": {
                "success_count": success_count,
                "failed_count": failed_count,
                "total_count": len(update_ids)
            }
        })

    except Exception as e:
        logger.error(f"批量审查人格更新记录失败: {e}")
        return jsonify({"error": str(e)}), 500

# 添加一个测试接口，用于创建测试数据
@api_bp.route("/test/create_persona_update", methods=["POST"])
@require_auth
async def create_test_persona_update():
    """创建测试人格更新记录（仅用于开发调试）"""
    if persona_updater:
        try:
            import time
            from ..core.interfaces import PersonaUpdateRecord
            
            # 创建一个测试记录
            test_record = PersonaUpdateRecord(
                timestamp=time.time(),
                group_id="742376823",
                update_type="prompt_update", 
                original_content="You are a helpful assistant.",
                new_content="You are a helpful assistant with a friendly and enthusiastic personality. You enjoy helping users with their questions and respond in a warm, encouraging manner.",
                reason="强化学习生成的prompt过短，采用保守融合策略"
            )
            
            record_id = await persona_updater.record_persona_update_for_review(test_record)
            logger.info(f"创建测试人格更新记录，ID: {record_id}")
            
            return jsonify({
                "message": "Test persona update record created successfully",
                "record_id": record_id
            })
        except Exception as e:
            logger.error(f"创建测试记录失败: {e}", exc_info=True)
            return jsonify({"error": f"创建测试记录失败: {str(e)}"}), 500
    return jsonify({"error": "Persona updater not initialized"}), 500

@api_bp.route("/metrics")
@require_auth
async def get_metrics():
    """获取性能指标：API调用返回时间、LLM调用次数"""
    try:
        # 获取真实的LLM调用统计
        llm_stats = {}
        if llm_client and hasattr(llm_client, 'get_call_statistics'):
            # 从LLM适配器获取真实调用统计
            real_stats = llm_client.get_call_statistics()
            for provider_type, stats in real_stats.items():
                if provider_type != 'overall':
                    llm_stats[f"{provider_type}_provider"] = {
                        "total_calls": stats.get('total_calls', 0),
                        "avg_response_time_ms": stats.get('avg_response_time_ms', 0),
                        "success_rate": stats.get('success_rate', 1.0),
                        "error_count": stats.get('error_count', 0)
                    }
        else:
            # 后备的模拟数据
            llm_stats = {
                "filter_provider": {"total_calls": 0, "avg_response_time_ms": 0, "success_rate": 1.0, "error_count": 0},
                "refine_provider": {"total_calls": 0, "avg_response_time_ms": 0, "success_rate": 1.0, "error_count": 0}
            }
        
        # 获取真实的消息统计
        total_messages = 0
        filtered_messages = 0
        if database_manager:
            try:
                # 从数据库获取真实统计
                stats = await database_manager.get_messages_statistics()
                total_messages = stats.get('total_messages', 0)
                filtered_messages = stats.get('filtered_messages', 0)
            except Exception as e:
                logger.warning(f"获取数据库统计失败: {e}")
                # 使用配置中的统计作为后备
                total_messages = plugin_config.total_messages_collected if plugin_config else 0
                filtered_messages = getattr(plugin_config, 'filtered_messages', 0) if plugin_config else 0
        else:
            # 使用配置中的统计
            total_messages = plugin_config.total_messages_collected if plugin_config else 0
            filtered_messages = getattr(plugin_config, 'filtered_messages', 0) if plugin_config else 0
        
        # 获取系统性能指标
        import psutil
        import time

        # CPU和内存使用率（使用非阻塞方式获取CPU使用率）
        cpu_percent = psutil.cpu_percent(interval=0)  # interval=0 返回上次调用后的平均值，不阻塞
        memory = psutil.virtual_memory()

        # 网络统计
        net_io = psutil.net_io_counters()

        # 磁盘使用率
        disk_usage = psutil.disk_usage('/')
        
        metrics = {
            "llm_calls": llm_stats,
            "api_response_times": {
                "get_config": {"avg_time_ms": 10, "requests_count": 45},
                "get_persona_updates": {"avg_time_ms": 50, "requests_count": 12},
                "get_metrics": {"avg_time_ms": 25, "requests_count": 30},
                "post_config": {"avg_time_ms": 120, "requests_count": 8}
            },
            "total_messages_collected": total_messages,
            "filtered_messages": filtered_messages,
            "learning_efficiency": 0,  # 将被智能计算覆盖
            "system_metrics": {
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "memory_used_gb": round(memory.used / (1024**3), 2),
                "memory_total_gb": round(memory.total / (1024**3), 2),
                "disk_usage_percent": round(disk_usage.used / disk_usage.total * 100, 2),
                "network_bytes_sent": net_io.bytes_sent,
                "network_bytes_recv": net_io.bytes_recv
            },
            "database_metrics": {
                "total_queries": getattr(database_manager, '_total_queries', 0) if database_manager else 0,
                "avg_query_time_ms": getattr(database_manager, '_avg_query_time', 0) if database_manager else 0,
                "connection_pool_size": getattr(database_manager, '_pool_size', 5) if database_manager else 5,
                "active_connections": getattr(database_manager, '_active_connections', 2) if database_manager else 2
            }
        }
        
        # 获取真实的学习会话统计 - 移到metrics字典之外
        active_sessions_count = 0
        total_sessions_today = 0
        avg_session_duration = 0
        success_rate = 0.0
        
        # 从progressive_learning服务获取真实数据
        try:
            # 使用当前应用的插件实例
            plugin_instance = current_app.plugin_instance if hasattr(current_app, 'plugin_instance') else None
            progressive_learning = getattr(plugin_instance, 'progressive_learning', None) if plugin_instance else None
            
            if progressive_learning:
                # 计算活跃会话数量
                active_sessions_count = sum(1 for active in progressive_learning.learning_active.values() if active)
                
                # 获取今天的会话统计（如果有的话）
                if database_manager:
                    # 可以从数据库获取今天的会话记录
                    import time
                    from datetime import datetime, timedelta
                    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
                    
                    # 这里可以调用数据库方法获取今天的会话数据
                    # 暂时使用简单的估算
                    total_sessions_today = len(progressive_learning.learning_sessions) if hasattr(progressive_learning, 'learning_sessions') else 0
                    
                    # 计算成功率
                    if hasattr(progressive_learning, 'learning_sessions') and progressive_learning.learning_sessions:
                        successful_sessions = sum(1 for session in progressive_learning.learning_sessions if session.success)
                        success_rate = successful_sessions / len(progressive_learning.learning_sessions) if progressive_learning.learning_sessions else 0.0
                        
                        # 计算平均会话时长
                        completed_sessions = [s for s in progressive_learning.learning_sessions if s.end_time]
                        if completed_sessions:
                            durations = []
                            for session in completed_sessions:
                                try:
                                    start = datetime.fromisoformat(session.start_time)
                                    end = datetime.fromisoformat(session.end_time)
                                    duration_minutes = (end - start).total_seconds() / 60
                                    durations.append(duration_minutes)
                                except:
                                    continue
                            if durations:
                                avg_session_duration = sum(durations) / len(durations)
            else:
                # 后备方案：使用persona_updater状态作为基础指标
                active_sessions_count = 1 if persona_updater else 0
                
        except Exception as e:
            logger.warning(f"获取学习会话统计失败: {e}")
            # 使用默认值
            active_sessions_count = 1 if persona_updater else 0
            
        # 更新metrics字典中的learning_sessions部分
        metrics["learning_sessions"] = {
            "active_sessions": active_sessions_count,
            "total_sessions_today": total_sessions_today,
            "avg_session_duration_minutes": round(avg_session_duration, 1),
            "success_rate": round(success_rate, 2)
        }
        metrics["last_updated"] = time.time()

        # 使用智能指标计算服务计算学习效率
        if intelligence_metrics_service:
            try:
                # 统计额外的学习成果指标
                refined_content_count = 0
                style_patterns_learned = 0
                persona_updates_count = 0
                active_strategies = []

                # 从数据库获取提炼内容数量
                if database_manager:
                    try:
                        async with database_manager.get_db_connection() as conn:
                            cursor = await conn.cursor()

                            # 统计提炼内容数量
                            await cursor.execute("SELECT COUNT(*) FROM filtered_messages WHERE refined = 1")
                            result = await cursor.fetchone()
                            if result:
                                refined_content_count = result[0]

                            # 统计风格学习成果
                            await cursor.execute("SELECT COUNT(*) FROM style_learning_records")
                            result = await cursor.fetchone()
                            if result:
                                style_patterns_learned = result[0]

                            # 统计待审查的人格更新
                            await cursor.execute("SELECT COUNT(*) FROM persona_update_reviews WHERE status = 'pending'")
                            result = await cursor.fetchone()
                            if result:
                                persona_updates_count = result[0]

                            await cursor.close()
                    except Exception as db_error:
                        logger.warning(f"从数据库获取学习统计失败: {db_error}")

                # 统计激活的学习策略
                if plugin_config:
                    if plugin_config.enable_message_capture:
                        active_strategies.append("message_filtering")
                    if plugin_config.enable_auto_learning:
                        active_strategies.append("content_refinement")
                        active_strategies.append("persona_evolution")
                    if plugin_config.enable_expression_patterns:
                        active_strategies.append("style_learning")
                    if plugin_config.enable_knowledge_graph:
                        active_strategies.append("context_awareness")

                # 计算智能化学习效率
                efficiency_metrics = await intelligence_metrics_service.calculate_learning_efficiency(
                    total_messages=total_messages,
                    filtered_messages=filtered_messages,
                    refined_content_count=refined_content_count,
                    style_patterns_learned=style_patterns_learned,
                    persona_updates_count=persona_updates_count,
                    active_strategies=active_strategies
                )

                # 更新metrics中的学习效率
                metrics["learning_efficiency"] = efficiency_metrics.overall_efficiency
                metrics["learning_efficiency_details"] = {
                    "message_filter_rate": efficiency_metrics.message_filter_rate,
                    "content_refine_quality": efficiency_metrics.content_refine_quality,
                    "style_learning_progress": efficiency_metrics.style_learning_progress,
                    "persona_update_quality": efficiency_metrics.persona_update_quality,
                    "active_strategies_count": efficiency_metrics.active_strategies_count,
                    "active_strategies": active_strategies
                }

                logger.info(f"智能学习效率计算完成: {efficiency_metrics.overall_efficiency:.2f}%")

            except Exception as metrics_error:
                logger.warning(f"智能学习效率计算失败,使用简单算法: {metrics_error}")
                # 回退到简单计算
                metrics["learning_efficiency"] = (filtered_messages / total_messages * 100) if total_messages > 0 else 0
        else:
            # 如果服务未初始化,使用简单算法
            metrics["learning_efficiency"] = (filtered_messages / total_messages * 100) if total_messages > 0 else 0

        return jsonify(metrics)
        
    except Exception as e:
        logger.error(f"获取性能指标失败: {e}", exc_info=True)
        return jsonify({"error": f"获取性能指标失败: {str(e)}"}), 500

@api_bp.route("/metrics/realtime")
@require_auth
async def get_realtime_metrics():
    """获取实时性能指标"""
    try:
        import psutil
        import time
        
        # 获取实时系统指标
        cpu_percent = psutil.cpu_percent()
        memory = psutil.virtual_memory()
        
        # 获取最近的消息处理统计
        recent_stats = {
            "messages_last_hour": 45,  # 可以从数据库查询
            "llm_calls_last_hour": 12,
            "avg_response_time_ms": 850,
            "error_rate": 0.02
        }
        
        realtime_data = {
            "timestamp": time.time(),
            "cpu_percent": cpu_percent,
            "memory_percent": memory.percent,
            "recent_activity": recent_stats,
            "status": {
                "message_capture": plugin_config.enable_message_capture if plugin_config else False,
                "auto_learning": plugin_config.enable_auto_learning if plugin_config else False,
                "realtime_learning": plugin_config.enable_realtime_learning if plugin_config else False
            }
        }
        
        return jsonify(realtime_data)
        
    except Exception as e:
        return jsonify({"error": f"获取实时指标失败: {str(e)}"}), 500

@api_bp.route("/learning/status")
@require_auth
async def get_learning_status():
    """获取学习状态详情"""
    try:
        # 获取真实的学习状态
        learning_status = {
            "current_session": {"error": "无会话数据"},
            "today_summary": {"error": "无今日统计数据"},
            "recent_activities": []
        }
        
        if database_manager:
            try:
                # 获取最新的学习会话
                recent_sessions = await database_manager.get_recent_learning_sessions("default", 1)
                if recent_sessions:
                    latest_session = recent_sessions[0]
                    learning_status["current_session"] = {
                        "session_id": latest_session.get('session_id', '未知'),
                        "start_time": datetime.fromtimestamp(latest_session.get('start_time', time.time())).strftime('%Y-%m-%d %H:%M:%S'),
                        "status": "已完成" if latest_session.get('success') else "失败",
                        "messages_processed": latest_session.get('messages_processed', 0),
                        "learning_progress": round(latest_session.get('quality_score', 0) * 100, 1),
                        "current_task": f"已处理{latest_session.get('filtered_messages', 0)}条筛选消息"
                    }
                
                # 获取今日统计
                message_stats = await database_manager.get_messages_statistics()
                all_sessions = await database_manager.get_recent_learning_sessions("default", 10)
                learning_status["today_summary"] = {
                    "sessions_completed": len(all_sessions) if all_sessions else 0,
                    "total_messages_learned": message_stats.get('filtered_messages', 0),
                    "persona_updates": 0,  # TODO: 从数据库获取人格更新次数
                    "success_rate": (sum(1 for s in all_sessions if s.get('success', False)) / len(all_sessions)) if all_sessions else 0.0
                }
                
                # 获取最近活动（基于学习批次）
                recent_batches = await database_manager.get_recent_learning_batches(3)
                for batch in recent_batches:
                    learning_status["recent_activities"].append({
                        "timestamp": batch.get('start_time', time.time()),
                        "activity": f"学习批次: {batch.get('batch_name', '未命名')}，处理{batch.get('message_count', 0)}条消息",
                        "result": "成功" if batch.get('success') else "失败"
                    })
                
                if not learning_status["recent_activities"]:
                    learning_status["recent_activities"] = [{"error": "暂无最近活动数据"}]
                    
            except Exception as e:
                logger.warning(f"获取真实学习状态数据失败: {e}")
                learning_status = {
                    "current_session": {"error": f"获取会话数据失败: {str(e)}"},
                    "today_summary": {"error": f"获取统计数据失败: {str(e)}"},
                    "recent_activities": [{"error": f"获取活动数据失败: {str(e)}"}]
                }
        
        return jsonify(learning_status)
        
    except Exception as e:
        return jsonify({"error": f"获取学习状态失败: {str(e)}"}), 500

@api_bp.route("/analytics/trends")
@require_auth
async def get_analytics_trends():
    """获取分析趋势数据"""
    try:
        import random
        from datetime import datetime, timedelta
        
        # 生成过去24小时的趋势数据
        hours_data = []
        base_time = datetime.now() - timedelta(hours=23)
        
        for i in range(24):
            current_time = base_time + timedelta(hours=i)
            hours_data.append({
                "time": current_time.strftime("%H:%M"),
                "raw_messages": random.randint(10, 60),
                "filtered_messages": random.randint(5, 30),
                "llm_calls": random.randint(2, 15),
                "response_time": random.randint(400, 1500)
            })
        
        # 生成过去7天的数据
        days_data = []
        base_date = datetime.now() - timedelta(days=6)
        
        for i in range(7):
            current_date = base_date + timedelta(days=i)
            days_data.append({
                "date": current_date.strftime("%m-%d"),
                "total_messages": random.randint(200, 800),
                "learning_sessions": random.randint(5, 20),
                "persona_updates": random.randint(0, 5),
                "success_rate": round(random.uniform(0.7, 0.95), 2)
            })
        
        # 用户活跃度热力图数据
        heatmap_data = []
        days = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        for day_idx in range(7):
            for hour in range(24):
                activity_level = random.randint(0, 50)
                # 工作时间活跃度更高
                if 9 <= hour <= 18 and day_idx < 5:
                    activity_level = random.randint(20, 50)
                # 晚上和周末活跃度中等
                elif 19 <= hour <= 23 or day_idx >= 5:
                    activity_level = random.randint(10, 35)
                
                heatmap_data.append([hour, day_idx, activity_level])
        
        trends_data = {
            "hourly_trends": hours_data,
            "daily_trends": days_data,
            "activity_heatmap": {
                "data": heatmap_data,
                "days": days,
                "hours": [f"{i}:00" for i in range(24)]
            }
        }
        
        return jsonify(trends_data)
        
    except Exception as e:
        return jsonify({"error": f"获取趋势数据失败: {str(e)}"}), 500

# 人格管理相关API端点

@api_bp.route("/persona_management/list")
@require_auth
async def get_personas_list():
    """获取所有人格列表"""
    try:
        logger.info("开始获取人格列表...")
        persona_web_mgr = get_persona_web_manager()
        logger.info(f"PersonaWebManager实例: {persona_web_mgr}")
        
        if not persona_web_mgr:
            logger.warning("PersonaWebManager未初始化，返回空列表")
            return jsonify({"personas": []})
        
        logger.info("调用get_all_personas_for_web...")
        personas = await persona_web_mgr.get_all_personas_for_web()
        logger.info(f"获取到 {len(personas)} 个人格")
        
        return jsonify({"personas": personas})
        
    except Exception as e:
        logger.error(f"获取人格列表失败: {e}", exc_info=True)
        # 返回空列表而不是错误，避免前端显示错误
        return jsonify({"personas": []})

@api_bp.route("/persona_management/get/<persona_id>")
@require_auth 
async def get_persona_details(persona_id: str):
    """获取特定人格详情"""
    if not persona_manager:
        return jsonify({"error": "PersonaManager未初始化"}), 500
        
    try:
        persona = await persona_manager.get_persona(persona_id)
        if not persona:
            return jsonify({"error": "人格不存在"}), 404
            
        persona_dict = {
            "persona_id": persona.persona_id,
            "system_prompt": persona.system_prompt,
            "begin_dialogs": persona.begin_dialogs,
            "tools": persona.tools,
            "created_at": persona.created_at.isoformat() if persona.created_at else None,
            "updated_at": persona.updated_at.isoformat() if persona.updated_at else None,
        }
        
        return jsonify(persona_dict)
        
    except Exception as e:
        logger.error(f"获取人格详情失败: {e}")
        return jsonify({"error": f"获取人格详情失败: {str(e)}"}), 500

@api_bp.route("/persona_management/create", methods=["POST"])
@require_auth
async def create_persona():
    """创建新人格"""
    persona_web_mgr = get_persona_web_manager()
    if not persona_web_mgr:
        return jsonify({"error": "人格管理功能暂不可用，请检查AstrBot PersonaManager配置"}), 503
        
    try:
        data = await request.get_json()
        result = await persona_web_mgr.create_persona_via_web(data)
        
        if result["success"]:
            return jsonify({"message": "人格创建成功", "persona_id": result["persona_id"]})
        else:
            return jsonify({"error": result["error"]}), 400
            
    except Exception as e:
        logger.error(f"创建人格失败: {e}", exc_info=True)
        return jsonify({"error": f"创建人格失败: {str(e)}"}), 500

@api_bp.route("/persona_management/update/<persona_id>", methods=["POST"])
@require_auth
async def update_persona(persona_id: str):
    """更新人格"""
    persona_web_mgr = get_persona_web_manager()
    if not persona_web_mgr:
        return jsonify({"error": "人格管理功能暂不可用，请检查AstrBot PersonaManager配置"}), 503
        
    try:
        data = await request.get_json()
        result = await persona_web_mgr.update_persona_via_web(persona_id, data)
        
        if result["success"]:
            return jsonify({"message": "人格更新成功"})
        else:
            return jsonify({"error": result["error"]}), 400
            
    except Exception as e:
        logger.error(f"更新人格失败: {e}", exc_info=True)
        return jsonify({"error": f"更新人格失败: {str(e)}"}), 500

@api_bp.route("/persona_management/delete/<persona_id>", methods=["POST"])
@require_auth
async def delete_persona(persona_id: str):
    """删除人格"""
    persona_web_mgr = get_persona_web_manager()
    if not persona_web_mgr:
        return jsonify({"error": "人格管理功能暂不可用，请检查AstrBot PersonaManager配置"}), 503
        
    try:
        result = await persona_web_mgr.delete_persona_via_web(persona_id)
        
        if result["success"]:
            return jsonify({"message": "人格删除成功"})
        else:
            return jsonify({"error": result["error"]}), 400
            
    except Exception as e:
        logger.error(f"删除人格失败: {e}", exc_info=True)
        return jsonify({"error": f"删除人格失败: {str(e)}"}), 500

@api_bp.route("/persona_management/default")
@require_auth
async def get_default_persona():
    """获取默认人格"""
    persona_web_mgr = get_persona_web_manager()
    if not persona_web_mgr:
        # 返回一个基本的默认人格，而不是错误
        return jsonify({
            "persona_id": "default",
            "system_prompt": "You are a helpful assistant.",
            "begin_dialogs": [],
            "tools": []
        })
        
    try:
        default_persona = await persona_web_mgr.get_default_persona_for_web()
        return jsonify(default_persona)
        
    except Exception as e:
        logger.error(f"获取默认人格失败: {e}", exc_info=True)
        # 返回基本默认人格而不是错误
        return jsonify({
            "persona_id": "default",
            "system_prompt": "You are a helpful assistant.",
            "begin_dialogs": [],
            "tools": []
        })

@api_bp.route("/persona_management/export/<persona_id>")
@require_auth
async def export_persona(persona_id: str):
    """导出人格配置"""
    if not persona_manager:
        return jsonify({"error": "PersonaManager未初始化"}), 500
        
    try:
        persona = await persona_manager.get_persona(persona_id)
        if not persona:
            return jsonify({"error": "人格不存在"}), 404
            
        from datetime import datetime
        persona_export = {
            "persona_id": persona.persona_id,
            "system_prompt": persona.system_prompt,
            "begin_dialogs": persona.begin_dialogs,
            "tools": persona.tools,
            "export_time": datetime.now().isoformat(),
            "export_version": "1.0"
        }
        
        return jsonify(persona_export)
        
    except Exception as e:
        logger.error(f"导出人格失败: {e}")
        return jsonify({"error": f"导出人格失败: {str(e)}"}), 500

@api_bp.route("/persona_management/import", methods=["POST"])
@require_auth
async def import_persona():
    """导入人格配置"""
    if not persona_manager:
        return jsonify({"error": "PersonaManager未初始化"}), 500
        
    try:
        data = await request.get_json()
        
        # 验证导入数据格式
        required_fields = ["persona_id", "system_prompt"]
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"缺少必需字段: {field}"}), 400
                
        persona_id = data["persona_id"]
        system_prompt = data["system_prompt"]
        begin_dialogs = data.get("begin_dialogs", [])
        tools = data.get("tools", [])
        
        # 检查是否覆盖现有人格
        overwrite = data.get("overwrite", False)
        existing_persona = await persona_manager.get_persona(persona_id)
        
        if existing_persona and not overwrite:
            return jsonify({
                "error": "人格已存在，如要覆盖请设置overwrite=true"
            }), 400
            
        # 创建或更新人格
        if existing_persona:
            success = await persona_manager.update_persona(
                persona_id=persona_id,
                system_prompt=system_prompt,
                begin_dialogs=begin_dialogs,
                tools=tools
            )
            action = "更新"
        else:
            success = await persona_manager.create_persona(
                persona_id=persona_id,
                system_prompt=system_prompt,
                begin_dialogs=begin_dialogs,
                tools=tools
            )
            action = "创建"
            
        if success:
            logger.info(f"成功导入人格: {persona_id} ({action})")
            return jsonify({"message": f"人格{action}成功", "persona_id": persona_id})
        else:
            return jsonify({"error": f"人格{action}失败"}), 500
            
    except Exception as e:
        logger.error(f"导入人格失败: {e}")
        return jsonify({"error": f"导入人格失败: {str(e)}"}), 500

@api_bp.route("/style_learning/results", methods=["GET"])
@require_auth
async def get_style_learning_results():
    """获取风格学习结果"""
    try:
        # 初始化空数据结构
        results_data = {
            'statistics': {
                'unique_styles': 0,
                'avg_confidence': 0,
                'total_samples': 0,
                'latest_update': None
            },
            'style_progress': []
        }
        
        if db_manager:
            try:
                # 尝试从数据库获取真实数据
                real_stats = await db_manager.get_style_learning_statistics()
                if real_stats:
                    results_data['statistics'].update(real_stats)
                    
                real_progress = await db_manager.get_style_progress_data()
                if real_progress:
                    results_data['style_progress'] = real_progress
            except Exception as e:
                logger.warning(f"无法从数据库获取风格学习数据: {e}")
        
        return jsonify(results_data)
    
    except Exception as e:
        logger.error(f"获取风格学习结果失败: {e}")
        return jsonify({'error': str(e)}), 500

@api_bp.route("/style_learning/reviews", methods=["GET"])
@require_auth
async def get_style_learning_reviews():
    """获取对话风格学习审查列表"""
    try:
        if not database_manager:
            return jsonify({'error': '数据库管理器未初始化'}), 500
        
        pending_reviews = await database_manager.get_pending_style_reviews(limit=50)
        
        # 格式化审查数据
        formatted_reviews = []
        for review in pending_reviews:
            formatted_review = {
                'id': review['id'],
                'type': '对话风格学习',
                'group_id': review['group_id'],
                'description': review['description'],
                'timestamp': review['timestamp'],
                'created_at': review['created_at'],
                'status': review['status'],
                'learned_patterns': review['learned_patterns'],
                'few_shots_content': review['few_shots_content']
            }
            formatted_reviews.append(formatted_review)
        
        return jsonify({
            'reviews': formatted_reviews,
            'total': len(formatted_reviews)
        })
        
    except Exception as e:
        logger.error(f"获取风格学习审查列表失败: {e}")
        return jsonify({'error': str(e)}), 500

@api_bp.route("/style_learning/reviews/<int:review_id>/approve", methods=["POST"])
@require_auth
async def approve_style_learning_review(review_id: int):
    """批准对话风格学习审查 - 使用与人格学习审查相同的备份逻辑"""
    try:
        if not database_manager:
            return jsonify({'error': '数据库管理器未初始化'}), 500

        # 获取审查详情
        pending_reviews = await database_manager.get_pending_style_reviews()
        target_review = None
        for review in pending_reviews:
            if review['id'] == review_id:
                target_review = review
                break

        if not target_review:
            return jsonify({'error': '审查记录不存在'}), 404

        # 更新状态为approved
        success = await database_manager.update_style_review_status(review_id, 'approved', target_review['group_id'])

        if success:
            # 应用到人格（使用与人格学习审查相同的逻辑：备份+应用）
            if target_review['few_shots_content']:
                # 通过persona_updater应用到人格
                persona_update_content = target_review['few_shots_content']

                if persona_updater:
                    try:
                        logger.info(f"开始应用风格学习审查 {review_id}，群组: {target_review.get('group_id', 'default')}")
                        logger.info(f"待应用内容长度: {len(persona_update_content)} 字符")

                        # 使用与人格学习审查相同的方法（包含自动备份）
                        # 首先需要将few_shots_content转换为style_analysis格式
                        style_analysis = {
                            'enhanced_prompt': persona_update_content,
                            'style_features': [],
                            'style_attributes': {},
                            'confidence': 0.8,
                            'source': f'风格学习审查{review_id}'
                        }
                        logger.info(f"构建style_analysis: {style_analysis['source']}")

                        # 使用空的filtered_messages（因为我们直接有学习内容）
                        filtered_messages = []

                        # 调用框架API方式的人格更新方法（包含自动备份）
                        logger.info("调用update_persona_with_style方法...")
                        success_apply = await persona_updater.update_persona_with_style(
                            target_review.get('group_id', 'default'),
                            style_analysis,
                            filtered_messages
                        )
                        logger.info(f"update_persona_with_style返回结果: {success_apply}")

                        if success_apply:
                            logger.info(f"✅ 风格学习审查 {review_id} 已成功应用到人格（使用框架API方式，包含备份）")
                            message = f'风格学习审查 {review_id} 已批准并应用到人格'
                        else:
                            logger.warning(f"❌ 风格学习审查 {review_id} 批准成功但应用失败")
                            message = f'风格学习审查 {review_id} 已批准，但人格应用失败'

                    except Exception as e:
                        logger.error(f"应用风格学习到人格失败: {e}", exc_info=True)
                        return jsonify({'error': f'批准成功，但应用到人格失败: {str(e)}'}), 500
                else:
                    logger.warning("PersonaUpdater未初始化，无法应用风格学习")
                    message = f'风格学习审查 {review_id} 已批准，但无法应用人格更新'
            else:
                message = f'风格学习审查 {review_id} 已批准（无内容需要应用）'

            return jsonify({
                'success': True,
                'message': message
            })
        else:
            return jsonify({'error': '批准失败，请检查审查记录状态'}), 500

    except Exception as e:
        logger.error(f"批准风格学习审查失败: {e}")
        return jsonify({'error': str(e)}), 500

@api_bp.route("/style_learning/reviews/<int:review_id>/reject", methods=["POST"])
@require_auth
async def reject_style_learning_review(review_id: int):
    """拒绝对话风格学习审查"""
    try:
        if not database_manager:
            return jsonify({'error': '数据库管理器未初始化'}), 500
        
        # 更新状态为rejected
        success = await database_manager.update_style_review_status(review_id, 'rejected')
        
        if success:
            logger.info(f"风格学习审查 {review_id} 已拒绝")
            return jsonify({
                'success': True,
                'message': f'风格学习审查 {review_id} 已拒绝'
            })
        else:
            return jsonify({'error': '拒绝失败，请检查审查记录状态'}), 500
            
    except Exception as e:
        logger.error(f"拒绝风格学习审查失败: {e}")
        return jsonify({'error': str(e)}), 500

@api_bp.route("/style_learning/patterns", methods=["GET"])
@require_auth
async def get_style_learning_patterns():
    """获取风格学习模式"""
    try:
        # 初始化空模式数据
        patterns_data = {
            'emotion_patterns': [],
            'language_patterns': [],
            'topic_preferences': []
        }
        
        if db_manager:
            try:
                # 尝试从数据库获取真实模式数据
                real_patterns = await db_manager.get_learning_patterns_data()
                if real_patterns:
                    patterns_data.update(real_patterns)
            except Exception as e:
                logger.warning(f"无法从数据库获取学习模式数据: {e}")
        
        return jsonify(patterns_data)
    
    except Exception as e:
        logger.error(f"获取风格学习模式失败: {e}")
        return jsonify({'error': str(e)}), 500

@api_bp.route("/metrics/detailed", methods=["GET"])
@require_auth
async def get_detailed_metrics():
    """获取详细性能监控数据"""
    try:
        # 初始化空详细数据
        detailed_data = {
            'api_metrics': {
                'hours': [],
                'response_times': []
            },
            'database_metrics': {
                'table_stats': {}
            },
            'system_metrics': {
                'memory_percent': 0,
                'cpu_percent': 0,
                'disk_percent': 0
            }
        }
        
        if db_manager:
            try:
                # 尝试从数据库获取真实详细数据
                real_detailed = await db_manager.get_detailed_metrics()
                if real_detailed:
                    detailed_data.update(real_detailed)
            except Exception as e:
                logger.warning(f"无法从数据库获取详细监控数据: {e}")
        
        return jsonify(detailed_data)
    
    except Exception as e:
        logger.error(f"获取详细监控数据失败: {e}")
        return jsonify({'error': str(e)}), 500

@api_bp.route("/metrics/trends", methods=["GET"])
@require_auth
async def get_metrics_trends():
    """获取指标趋势数据"""
    try:
        # 初始化空趋势数据
        trends_data = {
            'message_growth': 0,
            'filtered_growth': 0,
            'llm_growth': 0,
            'sessions_growth': 0
        }
        
        if db_manager:
            try:
                # 尝试从数据库获取真实趋势数据
                real_trends = await db_manager.get_trends_data()
                if real_trends:
                    trends_data.update(real_trends)
            except Exception as e:
                logger.warning(f"无法从数据库获取趋势数据: {e}")
        
        return jsonify(trends_data)
    
    except Exception as e:
        logger.error(f"获取趋势数据失败: {e}")
        return jsonify({'error': str(e)}), 500

@api_bp.route("/style_learning/content_text", methods=["GET"])
@require_auth
async def get_style_learning_content_text():
    """获取对话风格学习的所有内容文本（带缓存）"""
    global _style_learning_content_cache, _style_learning_content_cache_time

    # 检查是否强制刷新
    force_refresh = request.args.get('force_refresh', 'false').lower() == 'true'

    # 检查缓存是否有效
    current_time = time.time()
    if not force_refresh and _style_learning_content_cache is not None and _style_learning_content_cache_time is not None:
        cache_age = current_time - _style_learning_content_cache_time
        if cache_age < _style_learning_content_cache_ttl:
            logger.info(f"使用缓存的学习内容数据（缓存年龄: {cache_age:.1f}秒）")
            return jsonify(_style_learning_content_cache)

    logger.info(f"开始执行get_style_learning_content_text API请求（强制刷新: {force_refresh}）")
    try:
        # 从数据库获取学习相关的文本内容
        content_data = {
            'dialogues': [],
            'analysis': [],
            'features': [],
            'history': []
        }
        logger.debug("初始化content_data数据结构")
        
        if db_manager:
            logger.info("数据库管理器可用，开始获取学习内容数据")
            try:
                # 获取对话示例文本 - 使用现有的方法
                logger.debug("开始获取对话示例文本...")
                recent_messages = await db_manager.get_filtered_messages_for_learning(20)
                logger.info(f"获取到 {len(recent_messages) if recent_messages else 0} 条筛选消息用于对话示例")
                
                if recent_messages:
                    for i, msg in enumerate(recent_messages):
                        content_data['dialogues'].append({
                            'timestamp': datetime.fromtimestamp(msg.get('timestamp', time.time())).strftime('%Y-%m-%d %H:%M:%S'),
                            'text': f"用户: {msg.get('message', '暂无内容')}",
                            'metadata': f"置信度: {msg.get('confidence', 0):.1%}, 群组: {msg.get('group_id', '未知')}"
                        })
                        if i == 0:  # 记录第一条消息的详细信息用于调试
                            logger.debug(f"第一条对话示例: 群组={msg.get('group_id')}, 时间={msg.get('timestamp')}, 内容长度={len(msg.get('message', ''))}")
                    logger.info(f"成功添加 {len(recent_messages)} 条对话示例")
                else:
                    # 没有数据时提供友好提示
                    logger.warning("未找到筛选消息，显示默认提示")
                    content_data['dialogues'].append({
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'text': '暂无对话数据，请先进行一些群聊对话，系统会自动学习和筛选有价值的内容',
                        'metadata': '系统提示'
                    })
            except Exception as e:
                logger.error(f"获取对话示例文本失败: {e}", exc_info=True)
                content_data['dialogues'].append({
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'text': f'获取对话数据时出错: {str(e)}',
                    'metadata': '错误信息'
                })
        else:
            logger.error("数据库管理器不可用，无法获取学习内容数据")

        if db_manager:
            try:
                # 获取风格分析结果 - 使用学习批次数据
                logger.info("开始获取风格学习分析结果...")
                recent_batches = await db_manager.get_recent_learning_batches(limit=5)
                logger.info(f"从数据库获取到 {len(recent_batches) if recent_batches else 0} 个学习批次记录")
                
                if recent_batches:
                    for i, batch in enumerate(recent_batches):
                        batch_name = batch.get('batch_name', '未命名')
                        start_time = batch.get('start_time', time.time())
                        message_count = batch.get('message_count', 0)
                        quality_score = batch.get('quality_score', 0)
                        success = batch.get('success', False)
                        
                        logger.debug(f"处理学习批次 {i+1}/{len(recent_batches)}: {batch_name}, "
                                   f"消息数: {message_count}, 质量得分: {quality_score:.2f}, 成功: {success}")
                        
                        content_data['analysis'].append({
                            'timestamp': datetime.fromtimestamp(start_time).strftime('%Y-%m-%d %H:%M:%S'),
                            'text': f"学习批次: {batch_name}\n处理消息: {message_count}条\n质量得分: {quality_score:.2f}",
                            'metadata': f"成功: {'是' if success else '否'}"
                        })
                    logger.info(f"成功添加 {len(recent_batches)} 个学习批次到分析内容")
                else:
                    logger.warning("未找到任何学习批次记录，可能系统尚未进行自动学习")
                    content_data['analysis'].append({
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'text': '暂无学习分析数据，系统还未开始自动学习过程',
                        'metadata': '系统提示'
                    })
            except Exception as e:
                logger.error(f"获取风格分析结果失败: {e}", exc_info=True)
                content_data['analysis'].append({
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'text': f'获取分析数据时出错: {str(e)}',
                    'metadata': '错误信息'
                })

        if db_manager:
            try:
                # 获取提炼的风格特征 - 使用工厂模式的方法
                logger.info("开始获取风格特征数据...")
                
                # 1. 从表达模式数据获取 - 使用工厂模式
                try:
                    logger.debug("尝试获取表达模式学习器...")
                    from .core.factory import FactoryManager
                    
                    factory_manager = FactoryManager()
                    component_factory = factory_manager.get_component_factory()
                    expression_learner = component_factory.create_expression_pattern_learner()
                    
                    # 获取所有群组的表达模式
                    logger.debug("获取表达模式数据...")
                    if hasattr(expression_learner, 'get_all_group_patterns'):
                        group_patterns = await expression_learner.get_all_group_patterns()
                        logger.info(f"从表达模式学习器获取到 {len(group_patterns)} 个群组的模式")
                        
                        pattern_count = 0
                        for group_id, patterns in group_patterns.items():
                            logger.debug(f"处理群组 {group_id} 的 {len(patterns)} 个表达模式")
                            for pattern in patterns[:5]:  # 每个群组取前5个
                                if hasattr(pattern, 'situation') and hasattr(pattern, 'expression'):
                                    content_data['features'].append({
                                        'timestamp': datetime.fromtimestamp(getattr(pattern, 'last_active_time', time.time())).strftime('%Y-%m-%d %H:%M:%S'),
                                        'text': f"场景: {pattern.situation}\n表达: {pattern.expression}",
                                        'metadata': f"权重: {getattr(pattern, 'weight', 0.5):.2f}, 群组: {group_id}"
                                    })
                                    pattern_count += 1
                        logger.info(f"成功添加 {pattern_count} 个表达模式特征")
                    else:
                        # 回退到传统方法
                        logger.debug("表达模式学习器不支持get_all_group_patterns方法，使用传统SQL查询")
                        async with db_manager.get_db_connection() as conn:
                            cursor = await conn.cursor()
                            
                            await cursor.execute('SELECT * FROM expression_patterns ORDER BY last_active_time DESC LIMIT 10')
                            expression_patterns = await cursor.fetchall()
                            
                            if expression_patterns:
                                logger.info(f"从数据库直接查询到 {len(expression_patterns)} 个表达模式")
                                for pattern in expression_patterns:
                                    content_data['features'].append({
                                        'timestamp': datetime.fromtimestamp(pattern[4]).strftime('%Y-%m-%d %H:%M:%S'), # last_active_time
                                        'text': f"场景: {pattern[1]}\n表达: {pattern[2]}", # situation, expression
                                        'metadata': f"权重: {pattern[3]:.2f}, 群组: {pattern[6]}" # weight, group_id
                                    })
                            else:
                                logger.warning("数据库中未找到表达模式记录")
                        
                except Exception as e:
                    logger.warning(f"获取表达模式失败，将尝试其他数据源: {e}")
                
                # 2. 从风格学习审查中获取特征 - 使用工厂方法
                try:
                    logger.debug("获取风格学习审查数据...")
                    # 获取待审查的风格学习内容
                    pending_style_reviews = await db_manager.get_pending_style_reviews()
                    logger.info(f"获取到 {len(pending_style_reviews) if pending_style_reviews else 0} 个待审查的风格学习记录")
                    
                    for review in pending_style_reviews:
                        if review.get('few_shots_content'):
                            content_data['features'].append({
                                'timestamp': datetime.fromtimestamp(review['timestamp']).strftime('%Y-%m-%d %H:%M:%S'),
                                'text': f"风格学习内容:\n{review['few_shots_content'][:300]}{'...' if len(review['few_shots_content']) > 300 else ''}",
                                'metadata': f"状态: 待审查, 描述: {review.get('description', '无')}"
                            })
                    
                    # 获取已批准的风格学习内容
                    approved_style_reviews = await db_manager.get_reviewed_style_learning_updates(limit=10, status_filter='approved')
                    logger.info(f"获取到 {len(approved_style_reviews) if approved_style_reviews else 0} 个已批准的风格学习记录")
                    
                    for review in approved_style_reviews:
                        if review.get('few_shots_content'):
                            content_data['features'].append({
                                'timestamp': datetime.fromtimestamp(review.get('review_time', review['timestamp'])).strftime('%Y-%m-%d %H:%M:%S'),
                                'text': f"已应用风格特征:\n{review['few_shots_content'][:300]}{'...' if len(review['few_shots_content']) > 300 else ''}",
                                'metadata': f"状态: 已批准应用, 描述: {review.get('description', '无')}"
                            })
                    
                except Exception as e:
                    logger.warning(f"从风格学习审查获取特征失败: {e}")
                
                # 如果所有数据源都没有数据，显示提示
                if not content_data['features']:
                    logger.warning("未从任何数据源获取到风格特征，显示默认提示")
                    content_data['features'].append({
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'text': '暂无学习到的表达模式，请耐心等待系统学习',
                        'metadata': '系统提示'
                    })
                else:
                    logger.info(f"成功获取到 {len(content_data['features'])} 个风格特征")
                    
            except Exception as e:
                logger.error(f"获取风格特征失败: {e}", exc_info=True)
                content_data['features'].append({
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'text': f'获取特征数据时出错: {str(e)}',
                    'metadata': '错误信息'
                })

        if db_manager:
            try:
                # 获取学习历程记录 - 使用现有的方法
                logger.info("开始获取学习历程记录...")
                message_stats = await db_manager.get_messages_statistics()
                logger.debug(f"获取到消息统计: {message_stats}")
                
                content_data['history'].append({
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'text': f"系统统计:\n总消息数: {message_stats.get('total_messages', 0)}条\n已筛选: {message_stats.get('filtered_messages', 0)}条\n待学习: {message_stats.get('unused_filtered_messages', 0)}条",
                    'metadata': '实时统计'
                })
                logger.info(f"成功添加学习历程记录")
            except Exception as e:
                logger.warning(f"获取学习历程记录失败: {e}")
                content_data['history'].append({
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'text': f'获取历程数据时出错: {str(e)}',
                    'metadata': '错误信息'
                })

        # 汇总所有获取的数据并记录最终状态
        logger.info("完成所有学习内容数据获取，开始汇总统计...")
        total_dialogues = len(content_data['dialogues'])
        total_analysis = len(content_data['analysis'])
        total_features = len(content_data['features'])
        total_history = len(content_data['history'])
        
        logger.info(f"内容数据汇总: 对话示例={total_dialogues}条, 分析结果={total_analysis}条, "
                   f"特征数据={total_features}条, 历程记录={total_history}条")
        
        # 检查数据完整性
        if total_dialogues == 0 and total_analysis == 0 and total_features == 0:
            logger.warning("所有主要数据源都为空，可能系统尚未进行学习或数据库存在问题")
        else:
            logger.info("成功获取学习内容数据，数据完整性良好")

        # 更新缓存
        _style_learning_content_cache = content_data
        _style_learning_content_cache_time = current_time
        logger.info(f"已更新学习内容缓存（TTL: {_style_learning_content_cache_ttl}秒）")

        logger.info("get_style_learning_content_text API请求处理完成")
        return jsonify(content_data)
    
    except Exception as e:
        logger.error(f"get_style_learning_content_text API处理失败: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@api_bp.route("/style_learning/clear_cache", methods=["POST"])
@require_auth
async def clear_style_learning_cache():
    """清除学习内容缓存"""
    global _style_learning_content_cache, _style_learning_content_cache_time
    try:
        _style_learning_content_cache = None
        _style_learning_content_cache_time = None
        logger.info("已清除学习内容缓存")
        return jsonify({'success': True, 'message': '缓存已清除'})
    except Exception as e:
        logger.error(f"清除缓存失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# 新增的高级功能API端点

@api_bp.route("/advanced/data_analytics")
@require_auth
async def get_data_analytics():
    """获取数据分析与可视化"""
    try:
        from .core.factory import FactoryManager
        
        # 获取工厂管理器
        factory_manager = FactoryManager()
        component_factory = factory_manager.get_component_factory()
        
        # 创建数据分析服务
        data_analytics_service = component_factory.create_data_analytics_service()
        
        group_id = request.args.get('group_id', 'default')
        days = int(request.args.get('days', '30'))
        
        # 获取真实的分析数据
        learning_trajectory = await data_analytics_service.generate_learning_trajectory_chart(group_id, days)
        user_activity_heatmap = await data_analytics_service.generate_user_activity_heatmap(group_id, days)
        social_network = await data_analytics_service.generate_social_network_graph(group_id)
        
        analytics_data = {
            "learning_trajectory": learning_trajectory,
            "user_activity_heatmap": user_activity_heatmap,
            "social_network": social_network
        }
        
        return jsonify(analytics_data)
        
    except Exception as e:
        return jsonify({"error": f"获取数据分析失败: {str(e)}"}), 500

@api_bp.route("/advanced/learning_status")
@require_auth
async def get_advanced_learning_status():
    """获取高级学习状态"""
    try:
        from .core.factory import FactoryManager
        
        factory_manager = FactoryManager()
        component_factory = factory_manager.get_component_factory()
        
        # 创建高级学习服务
        advanced_learning_service = component_factory.create_advanced_learning_service()
        
        group_id = request.args.get('group_id', 'default')
        
        # 获取真实的高级学习状态
        status = await advanced_learning_service.get_learning_status(group_id)
        
        return jsonify(status)
        
    except Exception as e:
        return jsonify({"error": f"获取高级学习状态失败: {str(e)}"}), 500

@api_bp.route("/advanced/interaction_status")
@require_auth
async def get_interaction_status():
    """获取交互增强状态"""
    try:
        from .core.factory import FactoryManager
        
        factory_manager = FactoryManager()
        component_factory = factory_manager.get_component_factory()
        
        # 创建增强交互服务
        interaction_service = component_factory.create_enhanced_interaction_service()
        
        group_id = request.args.get('group_id', 'default')
        
        # 获取真实的交互状态
        status = await interaction_service.get_interaction_status(group_id)
        
        return jsonify(status)
        
    except Exception as e:
        return jsonify({"error": f"获取交互状态失败: {str(e)}"}), 500

@api_bp.route("/advanced/intelligence_status")
@require_auth
async def get_intelligence_status():
    """获取智能化状态"""
    try:
        from .core.factory import FactoryManager
        
        factory_manager = FactoryManager()
        component_factory = factory_manager.get_component_factory()
        
        # 创建智能化服务
        intelligence_service = component_factory.create_intelligence_enhancement_service()
        
        group_id = request.args.get('group_id', 'default')
        
        # 获取真实的智能化状态
        status = await intelligence_service.get_intelligence_status(group_id)
        
        return jsonify(status)
        
    except Exception as e:
        return jsonify({"error": f"获取智能化状态失败: {str(e)}"}), 500

@api_bp.route("/advanced/trigger_context_switch", methods=["POST"])
@require_auth
async def trigger_context_switch():
    """手动触发情境切换"""
    try:
        from .core.factory import FactoryManager
        
        factory_manager = FactoryManager()
        component_factory = factory_manager.get_component_factory()
        
        # 创建高级学习服务
        advanced_learning_service = component_factory.create_advanced_learning_service()
        
        data = await request.get_json()
        group_id = data.get('group_id', 'default')
        target_context = data.get('target_context', 'casual')
        
        # 调用实际的情境切换功能
        result = await advanced_learning_service.trigger_context_switch(group_id, target_context)
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({"error": f"情境切换失败: {str(e)}"}), 500

@api_bp.route("/advanced/generate_recommendations", methods=["POST"])
@require_auth  
async def generate_recommendations():
    """生成个性化推荐"""
    try:
        from .core.factory import FactoryManager
        
        factory_manager = FactoryManager()
        component_factory = factory_manager.get_component_factory()
        
        # 创建智能化服务
        intelligence_service = component_factory.create_intelligence_enhancement_service()
        
        data = await request.get_json()
        group_id = data.get('group_id', 'default')
        user_id = data.get('user_id', 'user_1')
        
        # 调用实际的个性化推荐功能
        recommendations = await intelligence_service.generate_personalized_recommendations(
            group_id, user_id, data
        )
        
        # 转换为字典格式
        recommendations_dict = [
            {
                "type": rec.recommendation_type,
                "content": rec.content,
                "confidence": rec.confidence,
                "reasoning": rec.reasoning
            }
            for rec in recommendations
        ]
        
        return jsonify({"recommendations": recommendations_dict})
        
    except Exception as e:
        return jsonify({"error": f"生成推荐失败: {str(e)}"}), 500

@api_bp.route("/style_learning/stats", methods=["GET"])
@require_auth
async def get_style_learning_stats():
    """获取对话风格学习统计数据"""
    try:
        from .core.factory import FactoryManager
        
        factory_manager = FactoryManager()
        service_factory = factory_manager.get_service_factory()
        
        # 获取表达模式学习器
        component_factory = factory_manager.get_component_factory()
        expression_learner = component_factory.create_expression_pattern_learner()
        
        # 获取数据库管理器
        db_manager = service_factory.create_database_manager()
        
        # 获取基本统计信息
        stats = {
            'style_types_count': 0,
            'avg_confidence': 0,
            'total_samples': 0,  # 改为统计原始消息总数
            'latest_update': '--',
            'learning_groups': [],
            'style_features': []
        }

        try:
            # 先统计数据库中的原始消息总数(用于前端显示)
            async with db_manager.get_db_connection() as conn:
                cursor = await conn.cursor()
                await cursor.execute('SELECT COUNT(*) FROM raw_messages WHERE sender_id != "bot"')
                row = await cursor.fetchone()
                if row:
                    stats['total_samples'] = row[0]  # 使用原始消息总数
                await cursor.close()

            # 获取所有群组的表达模式(用于其他统计)
            group_patterns = {}
            if hasattr(expression_learner, 'get_all_group_patterns'):
                group_patterns = await expression_learner.get_all_group_patterns()
            
            if group_patterns:
                total_confidence = 0
                pattern_count = 0
                style_types = set()
                
                for group_id, patterns in group_patterns.items():
                    for pattern in patterns:
                        style_types.add(getattr(pattern, 'style_type', 'general'))
                        total_confidence += getattr(pattern, 'weight', 0.5)
                        pattern_count += 1

                stats['style_types_count'] = len(style_types)
                stats['avg_confidence'] = round((total_confidence / pattern_count * 100) if pattern_count > 0 else 0, 1)
                # 不再覆盖total_samples，保持使用原始消息总数

                # 获取最新更新时间
                latest_time = 0
                for group_id, patterns in group_patterns.items():
                    for pattern in patterns:
                        if hasattr(pattern, 'created_time'):
                            latest_time = max(latest_time, pattern.created_time)
                
                if latest_time > 0:
                    import time
                    from datetime import datetime
                    stats['latest_update'] = datetime.fromtimestamp(latest_time).strftime('%Y-%m-%d %H:%M')
            
            # 获取学习群组列表
            stats['learning_groups'] = list(group_patterns.keys()) if group_patterns else []
            
            # 提取风格特征
            if group_patterns:
                style_features = []
                for group_id, patterns in group_patterns.items():
                    for pattern in patterns[:5]:  # 只取前5个作为展示
                        if hasattr(pattern, 'situation') and hasattr(pattern, 'expression'):
                            style_features.append({
                                'situation': pattern.situation,
                                'expression': pattern.expression,
                                'weight': getattr(pattern, 'weight', 0.5),
                                'group_id': group_id
                            })
                
                stats['style_features'] = style_features[:10]  # 最多返回10个特征
            
        except Exception as e:
            logger.warning(f"获取表达模式统计失败: {e}")
        
        return jsonify(stats)
        
    except Exception as e:
        logger.error(f"获取风格学习统计失败: {e}")
        return jsonify({"error": f"获取统计数据失败: {str(e)}"}), 500

@api_bp.route("/style_learning/content", methods=["GET"])
@require_auth
async def get_style_learning_content():
    """获取对话风格学习内容文本"""
    try:
        from .core.factory import FactoryManager
        import os
        
        factory_manager = FactoryManager()
        
        # 获取数据库管理器
        service_factory = factory_manager.get_service_factory()
        db_manager = service_factory.create_database_manager()
        
        # 获取消息关系分析器
        relationship_analyzer = service_factory.create_message_relationship_analyzer()
        
        content = {
            'dialogue_content': '',
            'analysis_content': '',
            'features_content': '',
            'history_content': ''
        }
        
        group_id = request.args.get('group_id', 'default')
        
        try:
            # 1. 获取对话示例文本
            recent_messages = await db_manager.get_recent_filtered_messages(group_id, limit=20)
            if recent_messages:
                relationships = await relationship_analyzer.analyze_message_relationships(recent_messages, group_id)
                conversation_pairs = await relationship_analyzer.get_conversation_pairs(relationships)
                
                if conversation_pairs:
                    dialogue_lines = ["*Here are few shots of dialogs, you need to imitate the tone of 'B' in the following dialogs to respond:"]
                    for sender_content, reply_content in conversation_pairs[:5]:
                        dialogue_lines.append(f"A:{sender_content}")
                        dialogue_lines.append(f"B:{reply_content}")
                    content['dialogue_content'] = "\n".join(dialogue_lines)
                else:
                    content['dialogue_content'] = "暂无对话示例数据"
            else:
                content['dialogue_content'] = "暂无消息数据"
            
            # 2. 获取风格分析结果
            component_factory = factory_manager.get_component_factory()
            expression_learner = component_factory.create_expression_pattern_learner()
            
            try:
                patterns = await expression_learner.get_expression_patterns(group_id, limit=10)
                if patterns:
                    analysis_lines = ["*Communication patterns learned from all user interactions:"]
                    for i, pattern in enumerate(patterns[:4], 1):
                        situation = getattr(pattern, 'situation', '未知情境')
                        expression = getattr(pattern, 'expression', '未知表达')
                        analysis_lines.append(f"{i}. 在{situation}时，群组用户倾向于使用\"{expression}\"这样的表达")
                    content['analysis_content'] = "\n".join(analysis_lines)
                else:
                    content['analysis_content'] = "*Communication patterns learned from all user interactions:\n1. 保持自然流畅的对话风格\n2. 根据语境调整回复的正式程度"
            except Exception as e:
                logger.warning(f"获取表达模式失败: {e}")
                content['analysis_content'] = "*Here are few shots of dialogs, you need to imitate the tone of 'B' in the following dialogs to respond:\n1. 保持自然流畅的对话风格\n2. 根据语境调整回复的正式程度"
            
            # 3. 获取提炼的风格特征
            try:
                patterns = await expression_learner.get_expression_patterns(group_id, limit=15)
                if patterns:
                    features_lines = ["群组表达风格特征:"]
                    for i, pattern in enumerate(patterns[:8], 1):
                        situation = getattr(pattern, 'situation', '通用情境')
                        expression = getattr(pattern, 'expression', '未知表达')
                        weight = getattr(pattern, 'weight', 0.5)
                        features_lines.append(f"{i}. {situation}: \"{expression}\" (置信度: {weight:.2f})")
                    content['features_content'] = "\n".join(features_lines)
                else:
                    content['features_content'] = "暂无提炼的风格特征"
            except Exception as e:
                logger.warning(f"获取风格特征失败: {e}")
                content['features_content'] = "暂无提炼的风格特征"
            
            # 4. 获取学习历程记录
            try:
                # 从数据库获取学习历史记录
                learning_sessions = await db_manager.get_learning_sessions(group_id, limit=5)
                if learning_sessions:
                    history_lines = ["学习历程记录:"]
                    for session in learning_sessions:
                        timestamp = session.get('end_time', session.get('start_time', 0))
                        if timestamp:
                            import time
                            from datetime import datetime
                            time_str = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M')
                            style_updates = session.get('style_updates', 0)
                            total_messages = session.get('total_messages', 0)
                            history_lines.append(f"• {time_str}: 处理{total_messages}条消息，更新{style_updates}个风格")
                    content['history_content'] = "\n".join(history_lines)
                else:
                    content['history_content'] = "暂无学习历程记录"
            except Exception as e:
                logger.warning(f"获取学习历史失败: {e}")
                content['history_content'] = "暂无学习历程记录"
        
        except Exception as e:
            logger.error(f"获取学习内容失败: {e}")
            content = {
                'dialogue_content': f"获取对话内容失败: {str(e)}",
                'analysis_content': f"获取分析内容失败: {str(e)}",
                'features_content': f"获取特征内容失败: {str(e)}",
                'history_content': f"获取历程记录失败: {str(e)}"
            }
        
        return jsonify(content)
        
    except Exception as e:
        logger.error(f"获取风格学习内容失败: {e}")
        return jsonify({"error": f"获取学习内容失败: {str(e)}"}), 500

@api_bp.route("/style_learning/trigger", methods=["POST"])
@require_auth
async def trigger_style_learning():
    """手动触发对话风格学习"""
    try:
        data = await request.get_json()
        group_id = data.get('group_id', 'default')
        
        from .core.factory import FactoryManager
        
        factory_manager = FactoryManager()
        component_factory = factory_manager.get_component_factory()
        service_factory = factory_manager.get_service_factory()
        
        # 获取表达模式学习器
        expression_learner = component_factory.create_expression_pattern_learner()
        db_manager = service_factory.create_database_manager()
        
        # 获取最近的原始消息
        recent_messages = await db_manager.get_recent_raw_messages(group_id, limit=30)
        
        if not recent_messages or len(recent_messages) < 3:
            return jsonify({
                "success": False,
                "message": f"群组 {group_id} 消息数量不足（{len(recent_messages) if recent_messages else 0}条），无法进行学习",
                "patterns_count": 0
            })
        
        # 转换为 MessageData 格式
        from .core.interfaces import MessageData
        import time
        
        message_data_list = []
        for msg in recent_messages:
            if msg.get('sender_id') != "bot":  # 不学习机器人的消息
                message_data = MessageData(
                    sender_id=msg.get('sender_id', ''),
                    sender_name=msg.get('sender_name', ''),
                    message=msg.get('message', ''),
                    group_id=group_id,
                    timestamp=msg.get('timestamp', time.time()),
                    platform=msg.get('platform', 'default'),
                    message_id=msg.get('message_id'),
                    reply_to=msg.get('reply_to')
                )
                message_data_list.append(message_data)
        
        if len(message_data_list) < 3:
            return jsonify({
                "success": False,
                "message": f"有效用户消息数量不足（{len(message_data_list)}条），无法进行学习",
                "patterns_count": 0
            })
        
        # 启动表达模式学习器
        if hasattr(expression_learner, '_status') and expression_learner._status.value != 'running':
            await expression_learner.start()
        
        # 强制触发学习
        if hasattr(expression_learner, 'last_learning_times'):
            expression_learner.last_learning_times[group_id] = 0  # 重置时间以强制学习
        
        learning_success = await expression_learner.trigger_learning_for_group(group_id, message_data_list)
        
        if learning_success:
            # 获取学习到的模式数量
            patterns = await expression_learner.get_expression_patterns(group_id, limit=20)
            patterns_count = len(patterns) if patterns else 0
            
            return jsonify({
                "success": True,
                "message": f"群组 {group_id} 风格学习成功",
                "patterns_count": patterns_count,
                "processed_messages": len(message_data_list)
            })
        else:
            return jsonify({
                "success": False,
                "message": "风格学习未产生有效结果",
                "patterns_count": 0
            })
        
    except Exception as e:
        logger.error(f"触发风格学习失败: {e}")
        return jsonify({
            "success": False,
            "error": f"触发学习失败: {str(e)}",
            "patterns_count": 0
        }), 500

@api_bp.route("/groups/info", methods=["GET"])
@require_auth
async def get_groups_info():
    """获取所有群组的详细信息"""
    logger.info("开始获取所有群组信息...")
    try:
        groups_info = {
            'total_groups': 0,
            'groups': [],
            'database_status': {},
            'recommendations': []
        }
        
        if not database_manager:
            return jsonify({'error': '数据库管理器不可用'}), 500
        
        # 获取数据库连接
        async with database_manager.get_db_connection() as conn:
            cursor = await conn.cursor()
            
            try:
                # 1. 检查数据库总体状态
                logger.debug("检查数据库总体状态...")
                await cursor.execute('SELECT COUNT(*) FROM raw_messages')
                total_raw_messages = (await cursor.fetchone())[0]
                
                await cursor.execute('SELECT COUNT(*) FROM filtered_messages')
                total_filtered_messages = (await cursor.fetchone())[0]
                
                groups_info['database_status'] = {
                    'total_raw_messages': total_raw_messages,
                    'total_filtered_messages': total_filtered_messages,
                    'tables_exist': True
                }
                
                logger.info(f"数据库状态: 原始消息 {total_raw_messages} 条, 筛选消息 {total_filtered_messages} 条")
                
                # 2. 获取所有群组的详细信息
                if total_raw_messages > 0:
                    logger.debug("获取所有群组的详细统计...")
                    await cursor.execute('''
                    SELECT 
                        group_id,
                        COUNT(*) as message_count,
                        MIN(timestamp) as earliest_message,
                        MAX(timestamp) as latest_message,
                        COUNT(DISTINCT sender_id) as unique_senders
                    FROM raw_messages 
                    WHERE group_id IS NOT NULL AND group_id != ''
                    GROUP BY group_id 
                    ORDER BY message_count DESC
                ''')
                
                for row in await cursor.fetchall():
                    group_id, message_count, earliest_ts, latest_ts, unique_senders = row
                    
                    # 获取该群组的筛选消息统计
                    await cursor.execute('SELECT COUNT(*) FROM filtered_messages WHERE group_id = ?', (group_id,))
                    filtered_count = (await cursor.fetchone())[0]
                    
                    # 计算时间范围
                    import datetime
                    earliest_date = datetime.datetime.fromtimestamp(earliest_ts).strftime('%Y-%m-%d %H:%M:%S') if earliest_ts else 'N/A'
                    latest_date = datetime.datetime.fromtimestamp(latest_ts).strftime('%Y-%m-%d %H:%M:%S') if latest_ts else 'N/A'
                    
                    # 计算活跃度
                    days_span = (latest_ts - earliest_ts) / 86400 if earliest_ts and latest_ts else 0
                    avg_messages_per_day = message_count / max(1, days_span) if days_span > 0 else 0
                    
                    group_info = {
                        'group_id': group_id,
                        'message_count': message_count,
                        'filtered_count': filtered_count,
                        'unique_senders': unique_senders,
                        'earliest_message': earliest_date,
                        'latest_message': latest_date,
                        'days_span': round(days_span, 1),
                        'avg_messages_per_day': round(avg_messages_per_day, 1),
                        'learning_potential': 'high' if message_count > 100 and filtered_count > 10 else 'medium' if message_count > 20 else 'low'
                    }
                    
                    groups_info['groups'].append(group_info)
                    logger.debug(f"群组 {group_id}: {message_count} 条消息, {filtered_count} 条筛选, {unique_senders} 个用户")
                
                groups_info['total_groups'] = len(groups_info['groups'])
                logger.info(f"找到 {groups_info['total_groups']} 个有消息记录的群组")
            except Exception as e:
                logger.error(e)

            else:
                try:
                    logger.warning("数据库中没有任何原始消息记录")
                    groups_info['recommendations'] = [
                        "数据库中没有消息记录，这可能是因为:",
                        "1. 插件刚刚安装，还没有收集到消息",
                        "2. 消息收集功能未启用或配置错误",
                        "3. 群聊中没有足够的消息活动",
                        "建议: 在群聊中发送一些消息，然后重新检查"
                    ]
                
                    # 3. 添加学习建议 - 修改为推荐所有群组都进行分析
                    if groups_info['total_groups'] > 0:
                        groups_info['recommendations'] = [
                            f"发现 {groups_info['total_groups']} 个群组，建议对所有群组进行完整的关系分析和风格学习:",
                            "• 使用 /groups/analyze_all 对所有群组进行关系分析",
                            "• 使用 /groups/style_learning_all 对所有群组进行表达模式和风格分析",
                            f"• 总计可分析原始消息: {total_raw_messages} 条"
                        ]
                    
                    # 为每个群组添加分析状态
                    for group in groups_info['groups']:
                        if group['message_count'] > 50:
                            group['analysis_ready'] = True
                            group['analysis_recommendation'] = "可进行完整分析"
                        elif group['message_count'] > 10:
                            group['analysis_ready'] = True
                            group['analysis_recommendation'] = "可进行基础分析"
                        else:
                            group['analysis_ready'] = False
                            group['analysis_recommendation'] = "消息数量较少，建议积累更多消息"
                
                finally:
                    await cursor.close()
        
        logger.info("群组信息获取完成")
        return jsonify(groups_info)
        
    except Exception as e:
        logger.error(f"获取群组信息失败: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@api_bp.route("/groups/analyze_all", methods=["POST"])
@require_auth
async def analyze_all_groups():
    """对所有群组进行关系分析和表达模式分析"""
    logger.info("开始对所有群组进行关系分析...")
    try:
        from .core.factory import FactoryManager
        
        factory_manager = FactoryManager()
        service_factory = factory_manager.get_service_factory()
        component_factory = factory_manager.get_component_factory()
        
        # 获取关系分析器和表达模式学习器
        relationship_analyzer = service_factory.create_message_relationship_analyzer()
        expression_learner = component_factory.create_expression_pattern_learner()
        db_manager = service_factory.create_database_manager()
        
        # 获取所有群组
        async with db_manager.get_db_connection() as conn:
            cursor = await conn.cursor()
        
        await cursor.execute('''
            SELECT DISTINCT group_id, COUNT(*) as message_count 
            FROM raw_messages 
            WHERE group_id IS NOT NULL AND group_id != ''
            GROUP BY group_id 
            HAVING message_count >= 10
            ORDER BY message_count DESC
        ''')
        all_groups = await cursor.fetchall()
        await cursor.close()
        await conn.close()
        
        if not all_groups:
            return jsonify({
                'success': False,
                'message': '没有找到足够消息的群组进行分析',
                'analyzed_groups': []
            })
        
        analysis_results = []
        
        for group_id, message_count in all_groups:
            logger.info(f"开始分析群组 {group_id} (消息数: {message_count})")
            
            try:
                # 1. 获取原始消息
                recent_messages = await db_manager.get_recent_raw_messages(group_id, limit=200)
                
                if not recent_messages or len(recent_messages) < 5:
                    logger.warning(f"群组 {group_id} 消息数量不足，跳过分析")
                    continue
                
                # 2. 过滤和格式化消息
                formatted_messages = []
                for msg in recent_messages:
                    message_content = msg.get('message', '')
                    sender_id = msg.get('sender_id', '')
                    
                    # 基础过滤
                    if len(message_content.strip()) < 5 or len(message_content) > 500:
                        continue
                    if sender_id == "bot":
                        continue
                    if message_content.strip() in ['', '???', '。。。', '...', '嗯', '哦', '额']:
                        continue
                    
                    # @符号处理
                    import re
                    processed_message = message_content
                    if '@' in message_content:
                        at_pattern = r'@[^\s]+\s+'
                        processed_message = re.sub(at_pattern, '', message_content).strip()
                        if len(processed_message.strip()) < 5:
                            continue
                    
                    formatted_msg = {
                        'id': msg.get('id'),
                        'sender_id': sender_id,
                        'sender_name': msg.get('sender_name', ''),
                        'message': processed_message,
                        'group_id': msg.get('group_id'),
                        'timestamp': msg.get('timestamp'),
                        'platform': msg.get('platform', 'default')
                    }
                    formatted_messages.append(formatted_msg)
                
                logger.info(f"群组 {group_id} 过滤后可用消息数: {len(formatted_messages)}")
                
                if len(formatted_messages) < 3:
                    logger.warning(f"群组 {group_id} 过滤后消息数量不足，跳过分析")
                    continue
                
                # 3. 进行关系分析
                logger.info(f"开始分析群组 {group_id} 的消息关系...")
                relationships = await relationship_analyzer.analyze_message_relationships(formatted_messages, group_id)
                
                # 4. 提取对话对
                conversation_pairs = await relationship_analyzer.get_conversation_pairs(relationships)
                
                # 5. 转换为MessageData格式进行表达模式学习
                from .core.interfaces import MessageData
                message_data_list = []
                for msg in formatted_messages:
                    message_data = MessageData(
                        sender_id=msg['sender_id'],
                        sender_name=msg['sender_name'],
                        message=msg['message'],
                        group_id=msg['group_id'],
                        timestamp=msg['timestamp'],
                        platform=msg['platform'],
                        message_id=msg['id'],
                        reply_to=None
                    )
                    message_data_list.append(message_data)
                
                # 6. 启动表达模式学习器并触发学习
                if hasattr(expression_learner, '_status') and expression_learner._status.value != 'running':
                    await expression_learner.start()
                
                # 强制学习（重置时间限制）
                if hasattr(expression_learner, 'last_learning_times'):
                    expression_learner.last_learning_times[group_id] = 0
                
                learning_success = await expression_learner.trigger_learning_for_group(group_id, message_data_list)
                
                # 7. 获取学习结果
                patterns = await expression_learner.get_expression_patterns(group_id, limit=10)
                patterns_count = len(patterns) if patterns else 0
                
                analysis_result = {
                    'group_id': group_id,
                    'message_count': message_count,
                    'processed_messages': len(formatted_messages),
                    'conversation_pairs': len(conversation_pairs) if conversation_pairs else 0,
                    'expression_patterns': patterns_count,
                    'learning_success': learning_success,
                    'analysis_completed': True
                }
                
                analysis_results.append(analysis_result)
                logger.info(f"群组 {group_id} 分析完成: 对话对 {analysis_result['conversation_pairs']}, 表达模式 {patterns_count}")
                
            except Exception as e:
                logger.error(f"分析群组 {group_id} 失败: {e}")
                analysis_results.append({
                    'group_id': group_id,
                    'message_count': message_count,
                    'processed_messages': 0,
                    'conversation_pairs': 0,
                    'expression_patterns': 0,
                    'learning_success': False,
                    'analysis_completed': False,
                    'error': str(e)
                })
        
        # 统计总结果
        successful_groups = [r for r in analysis_results if r.get('analysis_completed', False)]
        total_conversation_pairs = sum(r.get('conversation_pairs', 0) for r in analysis_results)
        total_expression_patterns = sum(r.get('expression_patterns', 0) for r in analysis_results)
        
        return jsonify({
            'success': True,
            'message': f'所有群组分析完成',
            'summary': {
                'total_groups': len(all_groups),
                'successful_groups': len(successful_groups),
                'total_conversation_pairs': total_conversation_pairs,
                'total_expression_patterns': total_expression_patterns
            },
            'analyzed_groups': analysis_results
        })
        
    except Exception as e:
        logger.error(f"分析所有群组失败: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'分析失败: {str(e)}',
            'analyzed_groups': []
        }), 500

@api_bp.route("/groups/style_learning_all", methods=["POST"])
@require_auth
async def style_learning_all_groups():
    """对所有群组进行风格学习并提交审查"""
    logger.info("开始对所有群组进行风格学习...")
    try:
        from .core.factory import FactoryManager
        import time
        
        factory_manager = FactoryManager()
        service_factory = factory_manager.get_service_factory()
        component_factory = factory_manager.get_component_factory()
        
        # 获取必要服务
        relationship_analyzer = service_factory.create_message_relationship_analyzer()
        expression_learner = component_factory.create_expression_pattern_learner()
        db_manager = service_factory.create_database_manager()
        
        # 获取所有群组
        async with db_manager.get_db_connection() as conn:
            cursor = await conn.cursor()
        
        await cursor.execute('''
            SELECT DISTINCT group_id, COUNT(*) as message_count 
            FROM raw_messages 
            WHERE group_id IS NOT NULL AND group_id != ''
            GROUP BY group_id 
            HAVING message_count >= 10
            ORDER BY message_count DESC
        ''')
        all_groups = await cursor.fetchall()
        await cursor.close()
        await conn.close()
        
        if not all_groups:
            return jsonify({
                'success': False,
                'message': '没有找到足够消息的群组进行风格学习',
                'style_learning_results': []
            })
        
        style_learning_results = []
        
        for group_id, message_count in all_groups:
            logger.info(f"开始为群组 {group_id} 进行风格学习 (消息数: {message_count})")
            
            try:
                # 1. 获取并处理消息（与analyze_all相同的逻辑）
                recent_raw_messages = await db_manager.get_recent_raw_messages(group_id, limit=100)
                
                if not recent_raw_messages:
                    logger.warning(f"群组 {group_id} 没有原始消息，跳过风格学习")
                    continue
                
                # 2. 过滤消息
                formatted_messages = []
                for msg in recent_raw_messages:
                    message_content = msg.get('message', '')
                    sender_id = msg.get('sender_id', '')
                    
                    # 使用相同的过滤逻辑
                    if len(message_content.strip()) < 5 or len(message_content) > 500:
                        continue
                    if sender_id == "bot":
                        continue
                    if message_content.strip() in ['', '???', '。。。', '...', '嗯', '哦', '额']:
                        continue
                    
                    # @符号处理
                    import re
                    processed_message = message_content
                    if '@' in message_content:
                        at_pattern = r'@[^\s]+\s+'
                        processed_message = re.sub(at_pattern, '', message_content).strip()
                        if len(processed_message.strip()) < 5:
                            continue
                    
                    formatted_msg = {
                        'id': msg.get('id'),
                        'sender_id': sender_id,
                        'sender_name': msg.get('sender_name', ''),
                        'message': processed_message,
                        'group_id': msg.get('group_id'),
                        'timestamp': msg.get('timestamp'),
                        'platform': msg.get('platform', 'default')
                    }
                    formatted_messages.append(formatted_msg)
                
                if len(formatted_messages) < 3:
                    logger.warning(f"群组 {group_id} 过滤后消息数量不足，跳过风格学习")
                    continue
                
                # 3. 进行关系分析获取对话对
                relationships = await relationship_analyzer.analyze_message_relationships(formatted_messages, group_id)
                conversation_pairs = await relationship_analyzer.get_conversation_pairs(relationships)
                
                if not conversation_pairs:
                    logger.warning(f"群组 {group_id} 未找到有效对话关系，跳过风格学习")
                    continue
                
                # 4. 生成对话内容（few shots格式）
                dialogue_lines = [f"*Here are examples of real conversations between users in group {group_id}:"]
                for sender_content, reply_content in conversation_pairs[:6]:  # 取前6个对话对
                    dialogue_lines.append(f"A:{sender_content}")
                    dialogue_lines.append(f"B:{reply_content}")
                
                dialogue_content = "\n".join(dialogue_lines)
                
                # 5. 进行表达模式学习
                patterns_learned = 0
                analysis_content = "*Communication style patterns observed in group conversations:\n1. 保持自然流畅的对话风格\n2. 根据语境调整回复的正式程度"
                features_content = "提炼的风格特征:\n1. 自然对话风格\n2. 适度的情感表达"
                
                try:
                    # 转换为MessageData格式
                    from .core.interfaces import MessageData
                    message_data_list = []
                    for msg in formatted_messages:
                        message_data = MessageData(
                            sender_id=msg['sender_id'],
                            sender_name=msg['sender_name'],
                            message=msg['message'],
                            group_id=msg['group_id'],
                            timestamp=msg['timestamp'],
                            platform=msg['platform'],
                            message_id=msg['id'],
                            reply_to=None
                        )
                        message_data_list.append(message_data)
                    
                    # 启动并触发学习
                    if hasattr(expression_learner, '_status') and expression_learner._status.value != 'running':
                        await expression_learner.start()
                    
                    if hasattr(expression_learner, 'last_learning_times'):
                        expression_learner.last_learning_times[group_id] = 0
                    
                    learning_success = await expression_learner.trigger_learning_for_group(group_id, message_data_list)
                    
                    if learning_success:
                        patterns = await expression_learner.get_expression_patterns(group_id, limit=10)
                        if patterns:
                            patterns_learned = len(patterns)
                            
                            # 生成更详细的分析内容
                            analysis_lines = [f"*Communication style patterns observed from all user interactions in {group_id}:"]
                            for i, pattern in enumerate(patterns[:4], 1):
                                situation = getattr(pattern, 'situation', '未知情境')
                                expression = getattr(pattern, 'expression', '未知表达')
                                analysis_lines.append(f"{i}. 当{situation}时，群组用户使用\"{expression}\"这样的表达")
                            analysis_content = "\n".join(analysis_lines)
                            
                            # 生成特征内容
                            features_lines = [f"群组 {group_id} 对话风格特征:"]
                            for i, pattern in enumerate(patterns[:6], 1):
                                situation = getattr(pattern, 'situation', '未知情境')
                                expression = getattr(pattern, 'expression', '未知表达')
                                features_lines.append(f"{i}. {situation}: {expression}")
                            features_content = "\n".join(features_lines)
                
                except Exception as e:
                    logger.warning(f"群组 {group_id} 表达模式学习失败: {e}")
                
                # 6. 生成完整的风格学习内容
                full_style_content = f"""## 真实对话示例 - 群组 {group_id}
{dialogue_content}

## 群组风格分析
{analysis_content}

## {features_content}

## 学习来源
全群组风格学习 - 基于{len(conversation_pairs)}个真实用户对话对的深度分析

## 数据说明
- 分析了群组 {group_id} 中任意用户之间的真实对话
- 提取了用户间的对话关系和表达模式 ({patterns_learned} 个表达模式)
- 学习内容反映群组整体的对话风格特征
- 处理原始消息: {len(recent_raw_messages)} 条，过滤后: {len(formatted_messages)} 条"""
                
                # 7. 提交到人格审查系统
                review_submitted = False
                try:
                    # 使用智能置信度计算
                    confidence_score = 0.85  # 默认值
                    if intelligence_metrics_service:
                        try:
                            # 获取当前人格内容
                            current_persona_content = ""
                            try:
                                persona_web_mgr = get_persona_web_manager()
                                if persona_web_mgr:
                                    current_persona = await persona_web_mgr.get_default_persona()
                                    current_persona_content = current_persona.get('prompt', '')
                            except:
                                pass

                            # 计算智能置信度
                            confidence_metrics = await intelligence_metrics_service.calculate_persona_confidence(
                                proposed_content=full_style_content,
                                original_content=current_persona_content,
                                learning_source=f"全群组风格学习-{group_id}",
                                message_count=len(formatted_messages),
                                llm_adapter=llm_client if llm_client else None
                            )
                            confidence_score = confidence_metrics.overall_confidence
                            logger.info(f"智能置信度计算: {confidence_score:.3f} (详情: {confidence_metrics.evaluation_basis.get('method', 'unknown')})")
                        except Exception as conf_error:
                            logger.warning(f"智能置信度计算失败,使用默认值: {conf_error}")

                    # 检查是否有人格学习审查方法
                    if hasattr(db_manager, 'add_persona_learning_review'):
                        await db_manager.add_persona_learning_review(
                            group_id=group_id,
                            proposed_content=full_style_content,
                            learning_source=f"全群组风格学习-{group_id}",
                            confidence_score=confidence_score,
                            raw_analysis=f"基于{len(conversation_pairs)}个对话对和{patterns_learned}个表达模式",
                            metadata={
                                "all_groups_learning": True,
                                "conversation_pairs": len(conversation_pairs),
                                "patterns_count": patterns_learned,
                                "messages_analyzed": len(formatted_messages),
                                "original_messages": len(recent_raw_messages)
                            }
                        )
                        review_submitted = True
                        logger.info(f"群组 {group_id} 风格学习审查已提交")
                    else:
                        # 回退方法：保存到通用审查记录
                        await db_manager.save_persona_update_record({
                            'timestamp': time.time(),
                            'group_id': group_id,
                            'update_type': 'all_groups_style_learning',
                            'original_content': '群组风格特征',
                            'new_content': full_style_content,
                            'reason': f'全群组风格学习-基于{len(conversation_pairs)}个对话对的关系分析',
                            'status': 'pending'
                        })
                        review_submitted = True
                        logger.info(f"群组 {group_id} 风格学习审查已保存")
                
                except Exception as e:
                    logger.error(f"群组 {group_id} 提交风格学习审查失败: {e}")
                
                learning_result = {
                    'group_id': group_id,
                    'message_count': message_count,
                    'processed_messages': len(formatted_messages),
                    'conversation_pairs': len(conversation_pairs),
                    'expression_patterns': patterns_learned,
                    'review_submitted': review_submitted,
                    'learning_completed': True
                }
                
                style_learning_results.append(learning_result)
                logger.info(f"群组 {group_id} 风格学习完成: 对话对 {len(conversation_pairs)}, 模式 {patterns_learned}")
                
            except Exception as e:
                logger.error(f"群组 {group_id} 风格学习失败: {e}")
                style_learning_results.append({
                    'group_id': group_id,
                    'message_count': message_count,
                    'processed_messages': 0,
                    'conversation_pairs': 0,
                    'expression_patterns': 0,
                    'review_submitted': False,
                    'learning_completed': False,
                    'error': str(e)
                })
        
        # 统计总结果
        successful_learning = [r for r in style_learning_results if r.get('learning_completed', False)]
        total_reviews_submitted = sum(1 for r in style_learning_results if r.get('review_submitted', False))
        total_conversation_pairs = sum(r.get('conversation_pairs', 0) for r in style_learning_results)
        total_expression_patterns = sum(r.get('expression_patterns', 0) for r in style_learning_results)
        
        return jsonify({
            'success': True,
            'message': f'所有群组风格学习完成',
            'summary': {
                'total_groups': len(all_groups),
                'successful_learning': len(successful_learning),
                'reviews_submitted': total_reviews_submitted,
                'total_conversation_pairs': total_conversation_pairs,
                'total_expression_patterns': total_expression_patterns
            },
            'style_learning_results': style_learning_results
        })
        
    except Exception as e:
        logger.error(f"所有群组风格学习失败: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'风格学习失败: {str(e)}',
            'style_learning_results': []
        }), 500

@api_bp.route("/relearn", methods=["POST"])
@require_auth
async def relearn_all():
    """重新学习按钮 - 包括风格重新学习"""
    try:
        # 处理空请求体的情况
        data = {}
        try:
            if request.is_json and await request.get_data():
                data = await request.get_json()
        except Exception:
            # 如果JSON解析失败，使用默认空字典
            data = {}
        
        # 获取实际的群组ID，如果没有指定则尝试从数据库中获取第一个有消息的群组
        group_id = data.get('group_id')
        include_style_learning = data.get('include_style_learning', True)
        
        from .core.factory import FactoryManager
        
        factory_manager = FactoryManager()
        service_factory = factory_manager.get_service_factory()
        component_factory = factory_manager.get_component_factory()
        db_manager = service_factory.create_database_manager()
        
        # 如果没有指定群组ID，自动检测有消息记录的群组
        if not group_id or group_id == 'default':
            # 获取所有有消息记录的群组，包括所有群组
            async with db_manager.get_db_connection() as conn:
                cursor = await conn.cursor()
                
                # 检查数据库中是否有任何消息记录
                logger.info("正在检查数据库中的所有消息记录...")
                await cursor.execute('SELECT COUNT(*) FROM raw_messages')
                total_count = (await cursor.fetchone())[0]
                logger.info(f"raw_messages表中总共有 {total_count} 条记录")
                
                if total_count > 0:
                    # 首先检查所有群组的消息统计
                    await cursor.execute('''
                        SELECT DISTINCT group_id, COUNT(*) as message_count 
                        FROM raw_messages 
                        WHERE group_id IS NOT NULL AND group_id != ''
                        GROUP BY group_id 
                        ORDER BY message_count DESC
                    ''')
                    all_results = await cursor.fetchall()
                    
                    logger.info(f"数据库中发现的所有群组: {[(r[0], r[1]) for r in all_results] if all_results else '无'}")
                    
                    # 选择消息数最多的群组
                    if all_results:
                        group_id = all_results[0][0]
                        message_count = all_results[0][1] 
                        logger.info(f"自动选择群组ID: {group_id} (共有{message_count}条原始消息)")
                    else:
                        logger.warning("虽然有消息记录，但没有有效的群组ID")
                        group_id = 'default'  # 兜底使用default
                else:
                    # 没有任何消息，检查系统状态
                    logger.warning("数据库中没有任何原始消息记录")
                    
                    # 检查是否有其他相关表的数据
                    await cursor.execute('SELECT name FROM sqlite_master WHERE type="table" AND name LIKE "%message%"')
                    tables = await cursor.fetchall()
                    logger.info(f"数据库中的消息相关表: {[t[0] for t in tables] if tables else '无'}")
                    
                    # 检查filtered_messages表
                    try:
                        await cursor.execute('SELECT COUNT(*) FROM filtered_messages')
                        filtered_count = (await cursor.fetchone())[0]
                        logger.info(f"filtered_messages表中有 {filtered_count} 条记录")
                    except:
                        logger.info("filtered_messages表不存在或无法访问")
                    
                    # 提供解决建议
                    logger.warning("建议解决方案:")
                    logger.warning("1. 检查消息收集功能是否正常工作")
                    logger.warning("2. 确认群聊中有足够的消息")
                    logger.warning("3. 检查插件的消息捕获配置")
                    
                    group_id = 'default'  # 兜底使用default
                
                await cursor.close()
        
        results = {
            'success': True,
            'message': '',
            'group_id': group_id,  # 返回实际使用的群组ID
            'progressive_learning': False,
            'style_learning': False,
            'processed_messages': 0,
            'new_patterns': 0,
            'persona_update_submitted': False,
            'errors': [],
            'total_messages': 0
        }
        
        try:
            # 1. 重新执行渐进式学习
            progressive_learning = service_factory.create_progressive_learning()
            db_manager = service_factory.create_database_manager()
            
            logger.info(f"开始重新学习群组 {group_id}...")
            
            # 检查消息数量（但不强制要求） - 添加连接重试逻辑
            logger.debug(f"开始获取群组 {group_id} 的消息统计...")
            try:
                stats = await db_manager.get_message_statistics(group_id)
                total_messages = stats.get('total_messages', 0)
                results['total_messages'] = total_messages
                logger.info(f"群组 {group_id} 消息统计: {total_messages} 条总消息")
            except Exception as stats_error:
                logger.warning(f"获取群组 {group_id} 消息统计失败: {stats_error}")
                # 如果是连接问题，尝试重新创建数据库连接
                if "no active connection" in str(stats_error).lower():
                    logger.info("检测到数据库连接问题，尝试重新初始化连接...")
                    try:
                        # 使用新的重置方法
                        await db_manager.reset_messages_db_connection()
                        
                        # 重新获取统计数据
                        stats = await db_manager.get_message_statistics(group_id)
                        total_messages = stats.get('total_messages', 0)
                        results['total_messages'] = total_messages
                        logger.info(f"重新连接成功，群组 {group_id} 消息统计: {total_messages} 条总消息")
                    except Exception as retry_error:
                        logger.error(f"重试获取消息统计也失败: {retry_error}")
                        total_messages = 0
                        results['total_messages'] = 0
                        results['errors'].append(f"无法获取消息统计: {str(retry_error)}")
                else:
                    total_messages = 0
                    results['total_messages'] = 0
                    results['errors'].append(f"获取消息统计失败: {str(stats_error)}")
            
            # 执行渐进式学习批次
            try:
                # ✅ 重新学习模式：传递 relearn_mode=True 以忽略"已处理"标记
                await progressive_learning._execute_learning_batch(group_id, relearn_mode=True)
                results['progressive_learning'] = True
                results['processed_messages'] = total_messages
                logger.info(f"群组 {group_id} 渐进式学习重新执行完成（重新学习模式）")
            except Exception as e:
                error_msg = f"渐进式学习失败: {str(e)}"
                results['errors'].append(error_msg)
                logger.error(error_msg)
            
            # 2. 风格重新学习（遵循原有逻辑：关系分析->A,B对话提取->按格式加入人格审查）
            if include_style_learning:
                try:
                    import time
                    logger.info(f"开始为群组 {group_id} 进行风格重新学习...")
                    
                    # 获取消息关系分析器
                    relationship_analyzer = service_factory.create_message_relationship_analyzer()
                    
                    # 获取最近的原始消息用于风格分析（不需要筛选）
                    logger.info(f"正在为群组 {group_id} 获取原始消息进行风格分析...")
                    recent_raw_messages = await db_manager.get_recent_raw_messages(group_id, limit=100)
                    logger.info(f"群组 {group_id} 获取到 {len(recent_raw_messages) if recent_raw_messages else 0} 条原始消息")

                    if recent_raw_messages:
                        # 直接使用原始消息,不进行筛选过滤
                        # 将原始消息转换为统一格式用于风格学习
                        formatted_messages = []
                        for msg in recent_raw_messages:
                            message_content = msg.get('message', '')
                            sender_id = msg.get('sender_id', '')

                            # 只进行最基本的过滤: 跳过机器人消息和完全空白的消息
                            if sender_id == "bot":
                                continue
                            if not message_content.strip():
                                continue

                            # 保持消息原样,不进行任何内容处理和筛选
                            formatted_msg = {
                                'id': msg.get('id'),
                                'sender_id': sender_id,
                                'sender_name': msg.get('sender_name', ''),
                                'message': message_content,  # 保持原始消息内容
                                'group_id': msg.get('group_id'),
                                'timestamp': msg.get('timestamp'),
                                'platform': msg.get('platform', 'default')
                            }
                            formatted_messages.append(formatted_msg)

                        logger.info(f"群组 {group_id} 使用未筛选的原始消息数: {len(formatted_messages)}")

                        # ========== 功能1: 表达模式学习(风格学习) - 使用所有原始消息 ==========
                        # 这部分独立运行,不依赖关系分析
                        component_factory = factory_manager.get_component_factory()
                        expression_learner = component_factory.create_expression_pattern_learner()

                        # 将原始消息转换为MessageData格式进行风格学习
                        from .core.interfaces import MessageData
                        import time

                        message_data_list = []
                        for msg in formatted_messages:
                            message_data = MessageData(
                                sender_id=msg['sender_id'],
                                sender_name=msg['sender_name'],
                                message=msg['message'],  # 原始消息内容
                                group_id=msg['group_id'],
                                timestamp=msg['timestamp'],
                                platform=msg['platform'],
                                message_id=msg['id'],
                                reply_to=None
                            )
                            message_data_list.append(message_data)

                        logger.info(f"开始为群组 {group_id} 进行表达模式学习(使用未筛选消息)，消息数: {len(message_data_list)}")

                        # 触发表达模式学习
                        learning_success = False
                        if message_data_list and len(message_data_list) >= 5:  # 至少5条消息
                            try:
                                # 启动表达模式学习器
                                if hasattr(expression_learner, '_status') and expression_learner._status.value != 'running':
                                    await expression_learner.start()

                                # 强制重新学习（无时间限制）
                                if hasattr(expression_learner, 'last_learning_times'):
                                    expression_learner.last_learning_times[group_id] = 0  # 重置时间

                                # 触发学习
                                learning_success = await expression_learner.trigger_learning_for_group(group_id, message_data_list)
                                logger.info(f"群组 {group_id} 表达模式学习结果: {learning_success}")
                                results['style_learning'] = True
                                results['messages_analyzed'] = len(message_data_list)

                            except Exception as learning_error:
                                logger.error(f"表达模式学习失败: {learning_error}", exc_info=True)
                                learning_success = False
                                results['errors'].append(f"表达模式学习失败: {str(learning_error)}")
                        else:
                            logger.warning(f"群组 {group_id} 消息数不足({len(message_data_list)}条),需要至少5条消息")


                        # ========== 功能2: 消息关系分析 - 用于生成人格审查数据 ==========
                        # 这部分用于分析A→B对话对,生成人格更新审查申请
                        logger.info(f"开始分析群组 {group_id} 的消息关系(用于人格审查)...")
                        relationships = await relationship_analyzer.analyze_message_relationships(formatted_messages, group_id)

                        # 提取A,B对话对
                        conversation_pairs = await relationship_analyzer.get_conversation_pairs(relationships)
                        logger.info(f"群组 {group_id} 提取到 {len(conversation_pairs) if conversation_pairs else 0} 个对话对")

                        # 只有当有对话对时,才生成人格审查数据
                        if conversation_pairs and len(conversation_pairs) > 0:
                            # 步骤3: 按照严格格式生成对话内容
                            # 说明：这里的A、B代表群组中任意两个用户之间的对话，用于学习真实的对话风格
                            dialogue_lines = ["*Here are examples of real conversations between users in this group:"]
                            for sender_content, reply_content in conversation_pairs[:8]:  # 取更多对话对用于重新学习
                                dialogue_lines.append(f"A:{sender_content}")
                                dialogue_lines.append(f"B:{reply_content}")
                            
                            dialogue_content = "\n".join(dialogue_lines)

                            # 步骤4: 获取已经学习的表达模式(使用之前独立运行的风格学习结果)
                            analysis_content = "*Communication style patterns observed in group conversations:\n1. 保持自然流畅的对话风格\n2. 根据语境调整回复的正式程度"
                            features_content = "提炼的风格特征:\n1. 自然对话风格\n2. 适度的情感表达"
                            llm_raw_response = ""  # 保存LLM原始响应

                            try:
                                patterns = await expression_learner.get_expression_patterns(group_id, limit=10)
                                if patterns:
                                    # 生成分析内容 - 基于任何人与任何人之间的对话分析
                                    analysis_lines = ["*Communication style patterns observed from all user interactions:"]
                                    for i, pattern in enumerate(patterns[:4], 1):
                                        situation = getattr(pattern, 'situation', '未知情境')
                                        expression = getattr(pattern, 'expression', '未知表达')
                                        analysis_lines.append(f"{i}. 当{situation}时，群组用户使用\"{expression}\"这样的表达")
                                    analysis_content = "\n".join(analysis_lines)

                                    # 生成特征内容 - 反映群组整体的对话风格
                                    features_lines = ["群组对话风格特征:"]
                                    for i, pattern in enumerate(patterns[:6], 1):
                                        situation = getattr(pattern, 'situation', '未知情境')
                                        expression = getattr(pattern, 'expression', '未知表达')
                                        features_lines.append(f"{i}. {situation}: {expression}")
                                    features_content = "\n".join(features_lines)

                                    # 构建LLM响应格式（用于前端显示）
                                    llm_response_lines = []
                                    for pattern in patterns[:10]:
                                        situation = getattr(pattern, 'situation', '')
                                        expression = getattr(pattern, 'expression', '')
                                        if situation and expression:
                                            llm_response_lines.append(f'当"{situation}"时，使用"{expression}"')
                                    llm_raw_response = "\n".join(llm_response_lines)

                                    results['new_patterns'] = len(patterns)
                            except Exception as e:
                                logger.warning(f"获取表达模式失败: {e}")
                            
                            # 步骤5: 生成完整的风格学习内容
                            full_style_content = f"""## 真实对话示例
{dialogue_content}

## 群组风格分析
{analysis_content}

## {features_content}

## 学习来源
重新学习模式 - 基于{len(conversation_pairs)}个真实用户对话对的深度分析

## 数据说明
- 分析了群组中任意用户之间的真实对话
- 提取了用户间的对话关系和表达模式
- 学习内容反映群组整体的对话风格特征"""
                            
                            # 步骤6: 提交到人格审查系统
                            try:
                                # 获取原始消息总数（未筛选的）
                                total_raw_messages = len(recent_raw_messages)

                                # 使用智能置信度计算
                                confidence_score = 0.85  # 默认值
                                if intelligence_metrics_service:
                                    try:
                                        # 获取当前人格内容
                                        current_persona_content = ""
                                        try:
                                            persona_web_mgr = get_persona_web_manager()
                                            if persona_web_mgr:
                                                current_persona = await persona_web_mgr.get_default_persona()
                                                current_persona_content = current_persona.get('prompt', '')
                                        except:
                                            pass

                                        # 计算智能置信度
                                        confidence_metrics = await intelligence_metrics_service.calculate_persona_confidence(
                                            proposed_content=full_style_content,
                                            original_content=current_persona_content,
                                            learning_source="重新学习-关系分析",
                                            message_count=len(formatted_messages),
                                            llm_adapter=llm_client if llm_client else None
                                        )
                                        confidence_score = confidence_metrics.overall_confidence
                                        logger.info(f"重新学习智能置信度: {confidence_score:.3f}")
                                    except Exception as conf_error:
                                        logger.warning(f"智能置信度计算失败,使用默认值: {conf_error}")

                                # 检查是否有add_persona_learning_review方法
                                if hasattr(db_manager, 'add_persona_learning_review'):
                                    # ✅ 获取当前人格作为 original_content
                                    original_persona_content = ""
                                    try:
                                        persona_web_mgr = get_persona_web_manager()
                                        if persona_web_mgr:
                                            current_persona = await persona_web_mgr.get_default_persona()
                                            original_persona_content = current_persona.get('prompt', '')
                                    except Exception as e:
                                        logger.warning(f"获取原人格失败: {e}")
                                        original_persona_content = ""

                                    # ✅ 构建完整的新人格内容（原人格 + 风格学习内容）
                                    full_new_persona = original_persona_content + "\n\n" + full_style_content if original_persona_content else full_style_content

                                    await db_manager.add_persona_learning_review(
                                        group_id=group_id,
                                        proposed_content=full_style_content,  # 增量内容
                                        learning_source=UPDATE_TYPE_STYLE_LEARNING,  # ✅ 使用常量
                                        confidence_score=confidence_score,
                                        raw_analysis=llm_raw_response if llm_raw_response else f"基于{len(conversation_pairs)}个对话对和{results.get('new_patterns', 0)}个表达模式",
                                        metadata={
                                            "relearn_triggered": True,
                                            "conversation_pairs": len(conversation_pairs),
                                            "patterns_count": results.get('new_patterns', 0),
                                            "total_raw_messages": total_raw_messages,  # 原始消息总数
                                            "messages_analyzed": len(formatted_messages),  # 实际分析的消息数
                                            "llm_response": llm_raw_response,  # LLM原始响应
                                            "features_content": features_content,  # 风格特征内容
                                            "incremental_content": full_style_content,  # ✅ 增量内容
                                            "incremental_start_pos": len(original_persona_content) + 2 if original_persona_content else 0  # ✅ 高亮位置
                                        },
                                        original_content=original_persona_content,  # ✅ 传递原人格
                                        new_content=full_new_persona  # ✅ 传递完整新人格
                                    )
                                else:
                                    # 使用现有的人格更新记录方法
                                    await db_manager.save_persona_update_record({
                                        'timestamp': time.time(),
                                        'group_id': group_id,
                                        'update_type': 'style_relearning',
                                        'original_content': '原有风格特征',
                                        'new_content': full_style_content,
                                        'reason': f'重新学习-基于{len(conversation_pairs)}个对话对的关系分析',
                                        'status': 'pending'
                                    })

                                results['persona_update_submitted'] = True
                                results['style_learning'] = True
                                logger.info(f"群组 {group_id} 风格学习审查申请已提交")

                            except Exception as e:
                                logger.error(f"提交风格学习审查失败: {e}", exc_info=True)
                                results['errors'].append(f"提交审查失败: {str(e)}")

                            logger.info(f"群组 {group_id} 风格重新学习完成，分析了 {len(conversation_pairs)} 个对话对")

                        else:
                            # 没有对话对时，使用所有过滤后的消息进行基础风格学习
                            logger.warning(f"群组 {group_id} 未找到对话对，将基于所有消息进行基础风格学习（消息数: {len(formatted_messages)}）")

                            if len(formatted_messages) >= 5:  # 至少需要5条消息才能进行学习
                                # 步骤3: 进行基础风格分析学习 - 基于所有过滤后的消息
                                component_factory = factory_manager.get_component_factory()
                                expression_learner = component_factory.create_expression_pattern_learner()

                                # 将过滤后的消息转换为MessageData格式
                                from .core.interfaces import MessageData
                                import time

                                message_data_list = []
                                for msg in formatted_messages:
                                    message_data = MessageData(
                                        sender_id=msg['sender_id'],
                                        sender_name=msg['sender_name'],
                                        message=msg['message'],
                                        group_id=msg['group_id'],
                                        timestamp=msg['timestamp'],
                                        platform=msg['platform'],
                                        message_id=msg['id'],
                                        reply_to=None
                                    )
                                    message_data_list.append(message_data)

                                logger.info(f"开始为群组 {group_id} 进行基础表达模式学习，消息数: {len(message_data_list)}")

                                # 触发表达模式学习
                                if message_data_list:
                                    try:
                                        # 启动表达模式学习器
                                        if hasattr(expression_learner, '_status') and expression_learner._status.value != 'running':
                                            await expression_learner.start()

                                        # 强制重新学习
                                        if hasattr(expression_learner, 'last_learning_times'):
                                            expression_learner.last_learning_times[group_id] = 0

                                        # 触发学习
                                        learning_success = await expression_learner.trigger_learning_for_group(group_id, message_data_list)
                                        logger.info(f"群组 {group_id} 基础表达模式学习结果: {learning_success}")

                                        results['style_learning'] = True
                                        results['messages_analyzed'] = len(message_data_list)
                                        logger.info(f"群组 {group_id} 基础风格学习完成，分析了 {len(message_data_list)} 条消息")

                                    except Exception as learning_error:
                                        logger.error(f"基础表达模式学习失败: {learning_error}", exc_info=True)
                                        results['errors'].append(f"基础学习失败: {str(learning_error)}")
                            else:
                                error_msg = f"群组 {group_id} 消息数不足（{len(formatted_messages)}条），需要至少5条消息才能学习"
                                results['errors'].append(error_msg)
                                logger.warning(error_msg)
                    else:
                        # 当没有找到原始消息时，提供更详细的调试信息
                        total_stats = await db_manager.get_messages_statistics()
                        group_stats = await db_manager.get_message_statistics(group_id)
                        
                        # 检查原始消息表的情况
                        async with db_manager.get_db_connection() as conn:
                            cursor = await conn.cursor()
                        
                        # 检查所有群组的原始消息
                        await cursor.execute('''
                            SELECT DISTINCT group_id, COUNT(*) as raw_count 
                            FROM raw_messages 
                            WHERE group_id IS NOT NULL AND group_id != ''
                            GROUP BY group_id 
                            ORDER BY raw_count DESC
                        ''')
                        raw_results = await cursor.fetchall()
                        
                        await cursor.close()
                        await conn.close()
                        
                        error_msg = f"群组 {group_id} 没有找到原始消息，跳过风格学习。\n" \
                                  f"全局统计: {total_stats}\n" \
                                  f"当前群组统计: {group_stats}\n" \
                                  f"所有群组原始消息: {[(r[0], r[1]) for r in raw_results] if raw_results else '无'}"
                        results['errors'].append(error_msg)
                        logger.warning(error_msg)
                        
                except Exception as e:
                    error_msg = f"风格重新学习失败: {str(e)}"
                    results['errors'].append(error_msg)
                    logger.error(error_msg, exc_info=True)
            
            # 3. 构建结果消息
            success_parts = []
            if results['progressive_learning']:
                success_parts.append(f"渐进式学习已完成（处理{results['processed_messages']}条消息）")
            if results['style_learning']:
                success_parts.append(f"风格重新学习已完成（学到{results['new_patterns']}个新模式）")
            if results['persona_update_submitted']:
                success_parts.append("人格更新申请已提交，等待审查")
            
            if success_parts:
                results['message'] = "重新学习完成：" + "，".join(success_parts)
                
                if results['errors']:
                    results['message'] += f"。注意：{len(results['errors'])}个警告"
            else:
                results['success'] = False
                results['message'] = "重新学习失败：" + "；".join(results['errors']) if results['errors'] else "未知错误"
            
        except Exception as e:
            results['success'] = False
            results['message'] = f"重新学习过程中发生严重错误: {str(e)}"
            logger.error(f"重新学习失败: {e}", exc_info=True)
        
        return jsonify(results)
        
    except Exception as e:
        logger.error(f"重新学习API失败: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": f"重新学习请求失败: {str(e)}",
            "progressive_learning": False,
            "style_learning": False,
            "processed_messages": 0,
            "new_patterns": 0,
            "persona_update_submitted": False,
            "total_messages": 0
        }), 500

async def _generate_persona_update_from_patterns(patterns, group_id: str) -> str:
    """基于风格模式生成人格更新内容"""
    try:
        if not patterns:
            return ""
        
        # 构建风格学习文本
        style_lines = ["*Here are few shots of dialogs, you need to imitate the tone of 'B' in the following dialogs to respond:"]
        
        # 提取主要风格特征
        for i, pattern in enumerate(patterns[:4], 1):  # 取前4个最重要的模式
            situation = getattr(pattern, 'situation', '通用情境')
            expression = getattr(pattern, 'expression', '自然表达')
            weight = getattr(pattern, 'weight', 0.5)
            
            # 生成具体的风格建议
            if weight > 0.7:
                style_lines.append(f"{i}. 在{situation}时，要{expression}，保持这种高置信度的表达风格")
            elif weight > 0.5:
                style_lines.append(f"{i}. 当遇到{situation}的情况，适当使用{expression}的方式回应")
            else:
                style_lines.append(f"{i}. 参考{situation}场景下的{expression}表达方式，灵活运用")
        
        # 构建Few Shots对话示例
        few_shots_lines = [
            "",
            "*Here are few shots of dialogs, you need to imitate the tone of 'B' in the following dialogs to respond:"
        ]
        
        # 基于模式生成示例对话
        for i, pattern in enumerate(patterns[:3], 1):  # 前3个模式作为对话示例
            situation = getattr(pattern, 'situation', '询问问题')
            expression = getattr(pattern, 'expression', '好的，我来帮你')
            
            # 生成符合模式的示例对话
            few_shots_lines.append(f"A:{situation}")
            few_shots_lines.append(f"B:{expression}")
        
        # 合并所有内容
        full_content = "\n".join(style_lines + few_shots_lines)
        
        logger.info(f"为群组 {group_id} 生成了基于 {len(patterns)} 个模式的人格更新内容")
        return full_content
        
    except Exception as e:
        logger.error(f"生成人格更新内容失败: {e}")
        return ""

# ========== 社交关系分析API ==========

@api_bp.route("/social_relations/<group_id>", methods=["GET"])
@require_auth
async def get_social_relations(group_id: str):
    """获取指定群组的社交关系分析数据"""
    try:
        from .core.factory import FactoryManager

        factory_manager = FactoryManager()
        service_factory = factory_manager.get_service_factory()

        # 获取数据库管理器
        db_manager = service_factory.create_database_manager()

        # 从数据库加载已保存的社交关系
        logger.info(f"从数据库加载群组 {group_id} 的社交关系...")
        saved_relations = await db_manager.get_social_relations_by_group(group_id)
        logger.info(f"从数据库加载到 {len(saved_relations)} 条社交关系记录")

        # 构建用户列表和统计消息数 - 从数据库直接统计所有消息数量
        user_message_counts = {}
        user_names = {}

        # 从数据库统计每个用户的总消息数量
        async with db_manager.get_db_connection() as conn:
            cursor = await conn.cursor()

            # 查询每个用户在该群组的消息总数
            await cursor.execute('''
                SELECT sender_id, MAX(sender_name) as sender_name, COUNT(*) as message_count
                FROM raw_messages
                WHERE group_id = ? AND sender_id != 'bot'
                GROUP BY sender_id
            ''', (group_id,))

            for row in await cursor.fetchall():
                sender_id, sender_name, message_count = row
                if sender_id:
                    user_key = f"{group_id}:{sender_id}"
                    user_message_counts[user_key] = message_count
                    user_names[user_key] = sender_name or sender_id
                    # 同时存储纯ID格式的映射,以兼容数据库中的社交关系数据
                    user_names[sender_id] = sender_name or sender_id

            await cursor.close()

        logger.info(f"群组 {group_id} 从数据库统计到 {len(user_message_counts)} 个用户")

        # 初始化 raw_messages 变量
        raw_messages = []

        # 如果没有统计到用户,尝试从最近消息获取
        if not user_message_counts:
            raw_messages = await db_manager.get_recent_raw_messages(group_id, limit=200)
            if not raw_messages:
                return jsonify({
                    "success": False,
                    "error": f"群组 {group_id} 没有消息记录",
                    "relations": [],
                    "members": []
                })

            for msg in raw_messages:
                sender_id = msg.get('sender_id', '')
                sender_name = msg.get('sender_name', '')
                if sender_id and sender_id != 'bot':
                    user_key = f"{group_id}:{sender_id}"
                    if user_key not in user_message_counts:
                        user_message_counts[user_key] = 0
                        user_names[user_key] = sender_name
                        user_names[sender_id] = sender_name
                    user_message_counts[user_key] += 1

        # 构建成员列表
        group_nodes = []
        for user_key, message_count in user_message_counts.items():
            user_id = user_key.split(':')[-1] if ':' in user_key else user_key
            group_nodes.append({
                'user_id': user_id,
                'nickname': user_names.get(user_key, user_id),
                'message_count': message_count,
                'nicknames': [user_names.get(user_key, user_id)],
                'id': user_key
            })

        # 构建关系列表
        group_edges = []
        for relation in saved_relations:
            from_key = relation['from_user']
            to_key = relation['to_user']

            # 提取用户ID（from_key格式可能是 "group_id:user_id"）
            from_id = from_key.split(':')[-1] if ':' in from_key else from_key
            to_id = to_key.split(':')[-1] if ':' in to_key else to_key

            # 获取用户名 - 现在user_names字典同时包含两种格式的key
            from_name = user_names.get(from_key, user_names.get(from_id, from_id))
            to_name = user_names.get(to_key, user_names.get(to_id, to_id))

            logger.debug(f"社交关系映射: {from_key} ({from_id}) -> {to_key} ({to_id}), "
                        f"名称: {from_name} -> {to_name}")

            # 关系类型映射
            relation_type_map = {
                'mention': '提及(@)',
                'reply': '回复',
                'conversation': '对话',
                'frequent_interaction': '频繁互动',
                'topic_discussion': '话题讨论'
            }
            relation_type_text = relation_type_map.get(relation.get('relation_type', 'interaction'), '互动')

            group_edges.append({
                'source': from_id,
                'target': to_id,
                'source_name': from_name,
                'target_name': to_name,
                'strength': relation.get('strength', 0.5),
                'type': relation.get('relation_type', 'interaction'),
                'type_text': relation_type_text,
                'frequency': relation.get('frequency', 1),
                'last_interaction': relation.get('last_interaction', '')
            })

        logger.info(f"群组 {group_id} 构建了 {len(group_edges)} 条社交关系")

        # 计算总消息数：优先使用数据库统计，否则使用raw_messages长度
        total_message_count = sum(user_message_counts.values()) if user_message_counts else len(raw_messages)

        return jsonify({
            "success": True,
            "group_id": group_id,
            "members": group_nodes,
            "relations": group_edges,
            "message_count": total_message_count,
            "member_count": len(group_nodes),
            "relation_count": len(group_edges)
        })

    except Exception as e:
        logger.error(f"获取社交关系失败: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e),
            "relations": [],
            "members": []
        }), 500

@api_bp.route("/social_relations/groups", methods=["GET"])
@require_auth
async def get_available_groups_for_social_analysis():
    """获取可用于社交关系分析的群组列表"""
    try:
        from .core.factory import FactoryManager

        factory_manager = FactoryManager()
        service_factory = factory_manager.get_service_factory()
        db_manager = service_factory.create_database_manager()

        # 获取所有有消息的群组
        async with db_manager.get_db_connection() as conn:
            cursor = await conn.cursor()

            # 注意：social_relations 表应该在数据库初始化时已创建
            # 不在这里重复创建，避免 SQLite/MySQL 语法不兼容问题

            # 获取群组的消息数和成员数
            await cursor.execute('''
                SELECT DISTINCT group_id, COUNT(*) as message_count,
                       COUNT(DISTINCT sender_id) as member_count
                FROM raw_messages
                WHERE group_id IS NOT NULL AND group_id != ''
                GROUP BY group_id
                HAVING message_count >= 10
                ORDER BY message_count DESC
            ''')

            group_rows = await cursor.fetchall()

            groups = []
            for row in group_rows:
                group_id = row[0]
                message_count = row[1]
                member_count = row[2]

                # 获取该群组的社交关系数量
                await cursor.execute('''
                    SELECT COUNT(*) FROM social_relations WHERE group_id = ?
                ''', (group_id,))
                relation_row = await cursor.fetchone()
                relation_count = relation_row[0] if relation_row else 0

                groups.append({
                    'group_id': group_id,
                    'message_count': message_count,
                    'member_count': member_count,  # 修复：使用正确的字段名
                    'user_count': member_count,     # 保留旧字段以兼容
                    'relation_count': relation_count  # 新增：关系数
                })

            await cursor.close()

        return jsonify({
            "success": True,
            "groups": groups
        })

    except Exception as e:
        logger.error(f"获取群组列表失败: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e),
            "groups": []
        }), 500


@api_bp.route("/social_relations/<group_id>/analyze", methods=["POST"])
@require_auth
async def trigger_social_relation_analysis(group_id: str):
    """触发群组社交关系分析"""
    try:
        from .core.factory import FactoryManager
        from .services.social_relation_analyzer import SocialRelationAnalyzer

        factory_manager = FactoryManager()
        service_factory = factory_manager.get_service_factory()
        db_manager = service_factory.create_database_manager()

        # 获取LLM适配器
        global llm_adapter_instance
        if not llm_adapter_instance:
            return jsonify({
                "success": False,
                "error": "LLM适配器未初始化"
            }), 500

        # 创建社交关系分析器
        analyzer = SocialRelationAnalyzer(
            config=current_app.plugin_config,
            llm_adapter=llm_adapter_instance,
            db_manager=db_manager
        )

        # 获取参数
        data = await request.get_json() if request.is_json else {}
        message_limit = data.get('message_limit', 200)
        force_refresh = data.get('force_refresh', False)

        logger.info(f"开始分析群组 {group_id} 的社交关系 (消息数: {message_limit}, 强制刷新: {force_refresh})")

        # 执行分析
        relations = await analyzer.analyze_group_social_relations(
            group_id=group_id,
            message_limit=message_limit,
            force_refresh=force_refresh
        )

        return jsonify({
            "success": True,
            "message": f"成功分析 {len(relations)} 条社交关系",
            "relation_count": len(relations)
        })

    except Exception as e:
        logger.error(f"触发社交关系分析失败: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@api_bp.route("/social_relations/<group_id>/clear", methods=["DELETE"])
@require_auth
async def clear_group_social_relations(group_id: str):
    """清空群组社交关系数据"""
    try:
        from .core.factory import FactoryManager

        factory_manager = FactoryManager()
        service_factory = factory_manager.get_service_factory()
        db_manager = service_factory.create_database_manager()

        logger.info(f"开始清空群组 {group_id} 的社交关系数据")

        # 统计要删除的记录数
        deleted_count = 0

        async with db_manager.get_db_connection() as conn:
            cursor = await conn.cursor()

            # 先统计数量
            await cursor.execute('''
                SELECT COUNT(*) FROM social_relations WHERE group_id = ?
            ''', (group_id,))
            result = await cursor.fetchone()
            if result:
                deleted_count = result[0]

            # 执行删除
            await cursor.execute('''
                DELETE FROM social_relations WHERE group_id = ?
            ''', (group_id,))

            await conn.commit()
            await cursor.close()

        logger.info(f"成功清空群组 {group_id} 的 {deleted_count} 条社交关系数据")

        return jsonify({
            "success": True,
            "message": f"成功清空 {deleted_count} 条社交关系数据",
            "deleted_count": deleted_count
        })

    except Exception as e:
        logger.error(f"清空社交关系数据失败: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@api_bp.route("/social_relations/<group_id>/user/<user_id>", methods=["GET"])
@require_auth
async def get_user_social_relations(group_id: str, user_id: str):
    """获取指定用户的社交关系"""
    try:
        from .core.factory import FactoryManager
        from .services.social_relation_analyzer import SocialRelationAnalyzer

        factory_manager = FactoryManager()
        service_factory = factory_manager.get_service_factory()
        db_manager = service_factory.create_database_manager()

        # 获取LLM适配器
        global llm_adapter_instance
        if not llm_adapter_instance:
            return jsonify({
                "success": False,
                "error": "LLM适配器未初始化"
            }), 500

        # 创建社交关系分析器
        analyzer = SocialRelationAnalyzer(
            config=current_app.plugin_config,
            llm_adapter=llm_adapter_instance,
            db_manager=db_manager
        )

        # 获取用户关系
        user_relations = await analyzer.get_user_relations(group_id, user_id)

        return jsonify({
            "success": True,
            **user_relations
        })

    except Exception as e:
        logger.error(f"获取用户社交关系失败: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ========== 外部API接口 (供其他程序调用) ==========

def require_api_key(f):
    """API密钥认证装饰器"""
    @wraps(f)
    async def decorated_function(*args, **kwargs):
        # 获取配置
        config = getattr(current_app, 'plugin_config', None)

        # 如果未启用API认证,直接通过
        if not config or not config.enable_api_auth:
            return await f(*args, **kwargs)

        # 检查API密钥
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')

        if not api_key:
            return jsonify({
                "success": False,
                "error": "缺少API密钥。请在请求头中添加 X-API-Key 或在查询参数中添加 api_key"
            }), 401

        if api_key != config.api_key:
            return jsonify({
                "success": False,
                "error": "API密钥无效"
            }), 403

        return await f(*args, **kwargs)
    return decorated_function


@api_bp.route("/external/current_topic", methods=["GET"])
@require_api_key
async def get_current_topic_api():
    """
    获取指定群组当前的聊天话题

    查询参数:
        group_id: 群组ID (必需)
        recent_count: 分析的最近消息数量 (可选，默认20)

    返回:
        JSON格式的话题信息
    """
    try:
        group_id = request.args.get('group_id')
        if not group_id:
            return jsonify({
                "success": False,
                "error": "缺少必需参数: group_id"
            }), 400

        recent_count = request.args.get('recent_count', 20, type=int)

        if not database_manager:
            return jsonify({
                "success": False,
                "error": "数据库管理器未初始化"
            }), 500

        # 获取话题总结
        topic_data = await database_manager.get_current_topic_summary(group_id, recent_count)

        return jsonify({
            "success": True,
            **topic_data
        })

    except Exception as e:
        logger.error(f"获取当前话题失败: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@api_bp.route("/external/chat_history", methods=["GET"])
@require_api_key
async def get_chat_history_api():
    """
    获取指定群组的聊天记录（支持时间段筛选）

    查询参数:
        group_id: 群组ID (必需)
        start_time: 开始时间戳（秒） (可选)
        end_time: 结束时间戳（秒） (可选)
        limit: 返回消息数量限制 (可选，默认100)

    返回:
        JSON格式的聊天记录列表
    """
    try:
        group_id = request.args.get('group_id')
        if not group_id:
            return jsonify({
                "success": False,
                "error": "缺少必需参数: group_id"
            }), 400

        start_time = request.args.get('start_time', type=float)
        end_time = request.args.get('end_time', type=float)
        limit = request.args.get('limit', 100, type=int)

        if not database_manager:
            return jsonify({
                "success": False,
                "error": "数据库管理器未初始化"
            }), 500

        # 获取聊天记录
        messages = await database_manager.get_messages_by_group_and_timerange(
            group_id=group_id,
            start_time=start_time,
            end_time=end_time,
            limit=limit
        )

        return jsonify({
            "success": True,
            "group_id": group_id,
            "message_count": len(messages),
            "messages": messages,
            "filter": {
                "start_time": start_time,
                "end_time": end_time,
                "limit": limit
            }
        })

    except Exception as e:
        logger.error(f"获取聊天记录失败: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@api_bp.route("/external/new_messages", methods=["GET"])
@require_api_key
async def get_new_messages_api():
    """
    获取增量消息更新（只返回之前未获取过的新消息）

    查询参数:
        group_id: 群组ID (必需)
        last_message_id: 上次获取的最后一条消息ID (可选，优先使用)
        last_timestamp: 上次获取的最后一条消息时间戳 (可选)

    注意: last_message_id 和 last_timestamp 至少需要提供一个，优先使用 last_message_id

    返回:
        JSON格式的新消息列表
    """
    try:
        group_id = request.args.get('group_id')
        if not group_id:
            return jsonify({
                "success": False,
                "error": "缺少必需参数: group_id"
            }), 400

        last_message_id = request.args.get('last_message_id', type=int)
        last_timestamp = request.args.get('last_timestamp', type=float)

        if not database_manager:
            return jsonify({
                "success": False,
                "error": "数据库管理器未初始化"
            }), 500

        # 获取新消息
        new_messages = await database_manager.get_new_messages_since(
            group_id=group_id,
            last_message_id=last_message_id,
            last_timestamp=last_timestamp
        )

        # 提取新消息的最大ID和最新时间戳，供下次调用使用
        max_id = None
        latest_timestamp = None
        if new_messages:
            max_id = max(msg['id'] for msg in new_messages)
            latest_timestamp = max(msg['timestamp'] for msg in new_messages)

        return jsonify({
            "success": True,
            "group_id": group_id,
            "new_message_count": len(new_messages),
            "messages": new_messages,
            "next_query": {
                "last_message_id": max_id,
                "last_timestamp": latest_timestamp
            } if new_messages else None
        })

    except Exception as e:
        logger.error(f"获取增量消息失败: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ========== 黑话学习系统API ==========

@api_bp.route("/jargon/stats", methods=["GET"])
@login_required
async def get_jargon_stats():
    """
    获取黑话学习统计信息

    查询参数:
        group_id: 群组ID (可选，不传则返回全局统计)

    返回:
        JSON格式的统计信息
    """
    try:
        group_id = request.args.get('group_id')

        if not database_manager:
            return jsonify({
                "success": False,
                "error": "数据库管理器未初始化"
            }), 500

        stats = await database_manager.get_jargon_statistics(group_id)

        return jsonify({
            "success": True,
            "data": stats,
            "group_id": group_id
        })

    except Exception as e:
        logger.error(f"获取黑话统计失败: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@api_bp.route("/jargon/list", methods=["GET"])
@login_required
async def get_jargon_list():
    """
    获取黑话学习列表

    查询参数:
        group_id: 群组ID (可选，不传则返回所有)
        limit: 返回数量限制 (默认50)
        only_confirmed: 是否只返回已确认的黑话 (默认true)
        page: 页码 (默认1)

    返回:
        JSON格式的黑话列表
    """
    try:
        group_id = request.args.get('group_id')
        limit = request.args.get('limit', 50, type=int)
        only_confirmed_str = request.args.get('only_confirmed', 'true')
        only_confirmed = only_confirmed_str.lower() in ('true', '1', 'yes')
        page = request.args.get('page', 1, type=int)

        if not database_manager:
            return jsonify({
                "success": False,
                "error": "数据库管理器未初始化"
            }), 500

        # 获取黑话列表
        jargon_list = await database_manager.get_recent_jargon_list(
            chat_id=group_id,
            limit=limit,
            only_confirmed=only_confirmed
        )

        return jsonify({
            "success": True,
            "data": jargon_list,
            "total": len(jargon_list),
            "group_id": group_id,
            "page": page,
            "limit": limit
        })

    except Exception as e:
        logger.error(f"获取黑话列表失败: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@api_bp.route("/jargon/search", methods=["GET"])
@login_required
async def search_jargon():
    """
    搜索黑话

    查询参数:
        keyword: 搜索关键词 (必需)
        group_id: 群组ID (可选，不传则搜索全局黑话)
        limit: 返回数量限制 (默认10)

    返回:
        JSON格式的搜索结果
    """
    try:
        keyword = request.args.get('keyword')
        if not keyword:
            return jsonify({
                "success": False,
                "error": "缺少必需参数: keyword"
            }), 400

        group_id = request.args.get('group_id')
        limit = request.args.get('limit', 10, type=int)

        if not database_manager:
            return jsonify({
                "success": False,
                "error": "数据库管理器未初始化"
            }), 500

        results = await database_manager.search_jargon(
            keyword=keyword,
            chat_id=group_id,
            limit=limit
        )

        return jsonify({
            "success": True,
            "data": results,
            "keyword": keyword,
            "group_id": group_id,
            "count": len(results)
        })

    except Exception as e:
        logger.error(f"搜索黑话失败: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@api_bp.route("/jargon/<int:jargon_id>", methods=["DELETE"])
@login_required
async def delete_jargon(jargon_id: int):
    """
    删除指定黑话记录

    路径参数:
        jargon_id: 黑话记录ID

    返回:
        JSON格式的删除结果
    """
    try:
        if not database_manager:
            return jsonify({
                "success": False,
                "error": "数据库管理器未初始化"
            }), 500

        # 执行删除
        success = await database_manager.delete_jargon_by_id(jargon_id)

        if success:
            return jsonify({
                "success": True,
                "message": f"黑话记录 {jargon_id} 已删除"
            })
        else:
            return jsonify({
                "success": False,
                "error": f"未找到黑话记录 {jargon_id}"
            }), 404

    except Exception as e:
        logger.error(f"删除黑话失败: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@api_bp.route("/jargon/<int:jargon_id>/toggle_global", methods=["POST"])
@login_required
async def toggle_jargon_global(jargon_id: int):
    """
    切换黑话的全局状态

    路径参数:
        jargon_id: 黑话记录ID

    返回:
        JSON格式的操作结果
    """
    try:
        if not database_manager:
            return jsonify({
                "success": False,
                "error": "数据库管理器未初始化"
            }), 500

        # 先获取当前记录
        async with database_manager.get_db_connection() as conn:
            cursor = await conn.cursor()
            await cursor.execute('SELECT is_global FROM jargon WHERE id = ?', (jargon_id,))
            row = await cursor.fetchone()

            if not row:
                return jsonify({
                    "success": False,
                    "error": f"未找到黑话记录 {jargon_id}"
                }), 404

            # 切换状态
            new_status = not bool(row[0])
            await cursor.execute(
                'UPDATE jargon SET is_global = ?, updated_at = ? WHERE id = ?',
                (new_status, datetime.now(), jargon_id)
            )
            await conn.commit()
            await cursor.close()

        return jsonify({
            "success": True,
            "jargon_id": jargon_id,
            "is_global": new_status,
            "message": f"黑话记录 {jargon_id} 已{'设为全局' if new_status else '取消全局'}"
        })

    except Exception as e:
        logger.error(f"切换黑话全局状态失败: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@api_bp.route("/jargon/groups", methods=["GET"])
@login_required
async def get_jargon_groups():
    """
    获取所有有黑话记录的群组列表

    返回:
        JSON格式的群组列表，每个群组包含黑话统计
    """
    try:
        if not database_manager:
            return jsonify({
                "success": False,
                "error": "数据库管理器未初始化"
            }), 500

        async with database_manager.get_db_connection() as conn:
            cursor = await conn.cursor()

            # 获取所有有黑话记录的群组及其统计
            await cursor.execute('''
                SELECT
                    chat_id,
                    COUNT(*) as total_candidates,
                    COUNT(CASE WHEN is_jargon = 1 THEN 1 END) as confirmed_jargon,
                    MAX(updated_at) as last_updated
                FROM jargon
                GROUP BY chat_id
                ORDER BY last_updated DESC
            ''')

            groups = []
            for row in await cursor.fetchall():
                groups.append({
                    'group_id': row[0],
                    'total_candidates': row[1],
                    'confirmed_jargon': row[2],
                    'last_updated': row[3]
                })

            await cursor.close()

        return jsonify({
            "success": True,
            "data": groups,
            "total_groups": len(groups)
        })

    except Exception as e:
        logger.error(f"获取黑话群组列表失败: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@api_bp.route("/jargon/global", methods=["GET"])
@login_required
async def get_global_jargon_list():
    """
    获取全局共享的黑话列表

    参数:
        limit: 返回数量限制 (默认50)

    返回:
        JSON格式的全局黑话列表
    """
    try:
        if not database_manager:
            return jsonify({
                "success": False,
                "error": "数据库管理器未初始化"
            }), 500

        limit = request.args.get('limit', 50, type=int)
        jargon_list = await database_manager.get_global_jargon_list(limit=limit)

        return jsonify({
            "success": True,
            "data": jargon_list,
            "total": len(jargon_list)
        })

    except Exception as e:
        logger.error(f"获取全局黑话列表失败: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@api_bp.route("/jargon/<int:jargon_id>/set_global", methods=["POST"])
@login_required
async def set_jargon_global_status(jargon_id: int):
    """
    设置黑话的全局共享状态

    参数:
        jargon_id: 黑话记录ID
        is_global: 是否全局共享 (JSON body)

    返回:
        操作结果
    """
    try:
        if not database_manager:
            return jsonify({
                "success": False,
                "error": "数据库管理器未初始化"
            }), 500

        data = await request.get_json()
        is_global = data.get('is_global', True)

        result = await database_manager.set_jargon_global(jargon_id, is_global)

        if result:
            return jsonify({
                "success": True,
                "message": f"黑话已{'设为全局共享' if is_global else '取消全局共享'}"
            })
        else:
            return jsonify({
                "success": False,
                "error": "更新失败，黑话可能不存在"
            }), 404

    except Exception as e:
        logger.error(f"设置黑话全局状态失败: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@api_bp.route("/jargon/batch_set_global", methods=["POST"])
@login_required
async def batch_set_jargon_global():
    """
    批量设置黑话的全局共享状态

    参数 (JSON body):
        jargon_ids: 黑话ID列表
        is_global: 是否全局共享

    返回:
        操作结果统计
    """
    try:
        if not database_manager:
            return jsonify({
                "success": False,
                "error": "数据库管理器未初始化"
            }), 500

        data = await request.get_json()
        jargon_ids = data.get('jargon_ids', [])
        is_global = data.get('is_global', True)

        if not jargon_ids:
            return jsonify({
                "success": False,
                "error": "未提供黑话ID列表"
            }), 400

        result = await database_manager.batch_set_jargon_global(jargon_ids, is_global)

        return jsonify({
            "success": result.get('success', False),
            "data": result,
            "message": f"批量{'设为全局' if is_global else '取消全局'}: 成功 {result.get('success_count', 0)} 条"
        })

    except Exception as e:
        logger.error(f"批量设置黑话全局状态失败: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@api_bp.route("/jargon/sync_to_group", methods=["POST"])
@login_required
async def sync_global_jargon_to_group():
    """
    将全局黑话同步到指定群组

    参数 (JSON body):
        target_group_id: 目标群组ID

    返回:
        同步结果统计
    """
    try:
        if not database_manager:
            return jsonify({
                "success": False,
                "error": "数据库管理器未初始化"
            }), 500

        data = await request.get_json()
        target_group_id = data.get('target_group_id')

        if not target_group_id:
            return jsonify({
                "success": False,
                "error": "未提供目标群组ID"
            }), 400

        result = await database_manager.sync_global_jargon_to_group(target_group_id)

        return jsonify({
            "success": result.get('success', False),
            "data": result,
            "message": f"同步完成: 新增 {result.get('synced_count', 0)} 条, 跳过 {result.get('skipped_count', 0)} 条"
        })

    except Exception as e:
        logger.error(f"同步全局黑话失败: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


app.register_blueprint(api_bp)

# 添加根路由重定向
@app.route("/")
async def root():
    """根路由重定向到API根路径"""
    return redirect("/api/")


class Server:
    """Quart 服务器管理类"""
    def __init__(self, host: str = "0.0.0.0", port: int = 7833):
        try:
            logger.info(f"🔧 初始化Web服务器 (端口: {port})...")
            # 检查端口是否可用
            logger.debug(f"Debug: 开始检查端口可用性")
            self._check_port_availability(port)
            logger.debug(f"Debug: 端口检查完成")

            self.host = host
            self.port = port
            self.server_task: Optional[asyncio.Task] = None
            # 使用 Hypercorn 的 shutdown_trigger 进行优雅关闭
            self._shutdown_event: Optional[asyncio.Event] = None

            logger.debug(f"Debug: 创建 HypercornConfig")
            self.config = HypercornConfig()
            self.config.bind = [f"{self.host}:{self.port}"]
            self.config.accesslog = "-" # 输出访问日志到 stdout
            self.config.errorlog = "-" # 输出错误日志到 stdout
            # 添加其他必要的配置
            self.config.loglevel = "INFO"
            self.config.use_reloader = False
            self.config.workers = 1

            # 关键修复：设置socket选项以允许端口复用
            # 这对于快速重启和插件重载非常重要
            import socket
            self.config.bind_socket_options = [
                (socket.SOL_SOCKET, socket.SO_REUSEADDR, 1),  # 允许地址复用
            ]
            # 在支持SO_REUSEPORT的系统上启用端口复用
            if hasattr(socket, 'SO_REUSEPORT'):
                self.config.bind_socket_options.append((socket.SOL_SOCKET, socket.SO_REUSEPORT, 1))
                logger.debug("已启用SO_REUSEPORT选项")

            logger.info(f"✅ Web服务器初始化完成 (端口: {port}, 端口复用: 已启用)")
            logger.debug(f"Debug: 配置绑定: {self.config.bind}")

        except Exception as e:
            logger.error(f"❌ Web服务器初始化失败: {e}")
            import traceback
            logger.error(f"❌ 初始化异常堆栈: {traceback.format_exc()}")
            raise
    
    def _check_port_availability(self, port: int):
        """检查端口可用性，如果被占用则尝试清理或提供解决方案"""
        import socket
        
        # 检查端口是否被占用
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(1)
                result = sock.connect_ex(("127.0.0.1", port))
                if result == 0:
                    logger.warning(f"端口 {port} 被占用，这可能是之前的插件实例未正确关闭")
                    logger.info(f"Web服务器启动时将尝试重用该端口或自动处理冲突")
                    
                    # 尝试检查是否是本插件的残留进程
                    try:
                        import subprocess
                        import sys
                        if sys.platform == 'win32':
                            # Windows: 使用netstat查看端口占用情况
                            result = subprocess.run(['netstat', '-ano', '-p', 'TCP'], 
                                                  capture_output=True, text=True, timeout=5)
                            lines = result.stdout.split('\n')
                            for line in lines:
                                if f":{port}" in line and "LISTENING" in line:
                                    logger.info(f"端口占用详情: {line.strip()}")
                                    if "python" in line.lower() or "hypercorn" in line.lower():
                                        logger.info(f"检测到可能的Python/Hypercorn进程占用端口")
                                    break
                        else:
                            # Linux/Mac: 使用lsof或ss
                            try:
                                result = subprocess.run(['lsof', '-i', f':{port}'], 
                                                      capture_output=True, text=True, timeout=5)
                                if result.stdout:
                                    logger.info(f"端口占用详情:\n{result.stdout}")
                            except FileNotFoundError:
                                try:
                                    result = subprocess.run(['ss', '-tlnp', f'sport = :{port}'], 
                                                          capture_output=True, text=True, timeout=5)
                                    if result.stdout:
                                        logger.info(f"端口占用详情:\n{result.stdout}")
                                except FileNotFoundError:
                                    logger.info(f"无法检查端口占用详情（缺少lsof和ss工具）")
                    except Exception as check_error:
                        logger.debug(f"检查端口占用详情时出错: {check_error}")
                    
                    logger.info(f"建议解决方案:")
                    logger.info(f"   1. 等待几秒钟后重试（系统可能正在清理资源）")
                    logger.info(f"   2. 重启AstrBot完全清理所有资源")
                    logger.info(f"   3. 修改插件配置使用其他端口")
                else:
                    logger.debug(f"端口 {port} 可用")
        except Exception as e:
            logger.warning(f"检查端口 {port} 时出错: {e}")
            logger.info(f"继续初始化，启动时将处理任何端口冲突")

    async def start(self):
        """启动服务器 - 增强版本，包含端口冲突处理和重试机制"""
        logger.info(f"🚀 启动Web服务器 (端口: {self.port})...")
        logger.debug(f"Debug: self.server_task = {self.server_task}")
        logger.debug(f"Debug: host = {self.host}, port = {self.port}")

        if self.server_task and not self.server_task.done():
            logger.info("ℹ️ Web服务器已在运行中")
            return # Server already running

        # 预检查：等待端口完全释放（处理插件重载场景）
        # 增加等待时间和重试次数
        port_wait_attempts = 5
        for attempt in range(port_wait_attempts):
            port_available = await self._async_check_port_available(self.port)
            if port_available:
                logger.info(f"✅ 端口 {self.port} 可用，继续启动")
                break
            else:
                logger.warning(f"⚠️ 端口 {self.port} 仍被占用 (检查 {attempt + 1}/{port_wait_attempts})")
                if attempt < port_wait_attempts - 1:
                    # 尝试强制释放端口（仅Linux）
                    await self._try_force_release_port(self.port)
                    wait_time = 3 if attempt < 2 else 5  # 前两次等3秒，之后等5秒
                    logger.info(f"⏳ 等待 {wait_time} 秒后重新检查...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.warning(f"⚠️ 端口 {self.port} 在等待后仍被占用")
                    logger.info("💡 继续尝试启动，将使用SO_REUSEADDR强制复用")

        try:
            # 为本次启动创建独立的 shutdown_event，用于优雅停止
            self._shutdown_event = asyncio.Event()

            logger.info(f"🔧 配置服务器绑定: {self.config.bind}")
            logger.debug(f"Debug: 准备创建Hypercorn serve任务")
            logger.debug(f"Debug: app类型: {type(app)}")
            logger.debug(f"Debug: config类型: {type(self.config)}")

            # 重新配置socket选项（确保每次启动都设置）
            import socket
            self.config.bind_socket_options = [
                (socket.SOL_SOCKET, socket.SO_REUSEADDR, 1),
            ]
            if hasattr(socket, 'SO_REUSEPORT'):
                self.config.bind_socket_options.append((socket.SOL_SOCKET, socket.SO_REUSEPORT, 1))

            # 添加重试机制
            max_retries = 3
            for retry_count in range(max_retries):
                try:
                    # Hypercorn 的 serve 函数是阻塞的，需要在一个单独的协程中运行
                    logger.debug(f"Debug: 调用 asyncio.create_task (尝试 {retry_count + 1}/{max_retries})")
                    self.server_task = asyncio.create_task(
                        hypercorn.asyncio.serve(
                            app,
                            self.config,
                            shutdown_trigger=self._shutdown_event.wait,  # 使用 shutdown_trigger 优雅关闭
                        )
                    )

                    logger.info(f"✅ Web服务器任务已创建: {self.server_task}")
                    logger.info(f"🌐 访问地址: http://{self.host}:{self.port}")

                    # 等待服务器启动
                    logger.debug(f"Debug: 等待服务器启动 (尝试 {retry_count + 1})")
                    await asyncio.sleep(2)

                    # 检查服务器状态
                    logger.debug(f"Debug: 检查服务器状态, task.done() = {self.server_task.done() if self.server_task else 'None'}")
                    if self.server_task and not self.server_task.done():
                        # 验证服务器是否真的在监听端口
                        if await self._verify_server_listening():
                            logger.info(f"✅ Web服务器启动成功并正在监听端口 {self.port}")
                            return  # 成功启动，退出重试循环
                        else:
                            logger.warning(f"⚠️ Web服务器任务运行中，但端口未响应 (尝试 {retry_count + 1})")
                            if retry_count < max_retries - 1:
                                # 取消当前任务，准备重试
                                self.server_task.cancel()
                                try:
                                    await asyncio.wait_for(self.server_task, timeout=2.0)
                                except:
                                    pass
                                self.server_task = None
                                logger.info(f"🔄 准备重试启动...")
                                await asyncio.sleep(2)
                                continue
                    else:
                        logger.error(f"❌ Web服务器任务意外完成 (尝试 {retry_count + 1})")
                        if self.server_task and self.server_task.done():
                            try:
                                # 获取任务异常
                                exception = self.server_task.exception()
                                if exception:
                                    logger.error(f"❌ 服务器启动异常: {exception}")
                                    logger.error(f"❌ 异常类型: {type(exception)}")
                                    if "Address already in use" in str(exception):
                                        logger.warning(f"🔧 检测到端口冲突，尝试强制释放...")
                                        await self._try_force_release_port(self.port)
                                        if retry_count < max_retries - 1:
                                            await asyncio.sleep(3)
                                            continue
                            except Exception as ex:
                                logger.error(f"❌ 获取异常信息时出错: {ex}")

                        if retry_count < max_retries - 1:
                            logger.info(f"🔄 启动失败，等待后重试 (尝试 {retry_count + 1}/{max_retries})")
                            await asyncio.sleep(5)
                        continue

                except Exception as start_error:
                    logger.error(f"❌ 启动尝试 {retry_count + 1} 失败: {start_error}")
                    if "Address already in use" in str(start_error) or "port" in str(start_error).lower():
                        logger.warning(f"🔧 检测到端口 {self.port} 冲突")
                        await self._try_force_release_port(self.port)
                        if retry_count < max_retries - 1:
                            logger.info(f"⏳ 等待端口释放后重试...")
                            await asyncio.sleep(5)
                            continue
                    elif retry_count < max_retries - 1:
                        logger.info(f"🔄 等待后重试...")
                        await asyncio.sleep(3)
                        continue
                    else:
                        raise  # 最后一次重试也失败，抛出异常
            
            # 如果所有重试都失败了
            logger.error(f"❌ 经过 {max_retries} 次重试，Web服务器仍无法启动")
            self.server_task = None
                
        except Exception as e:
            logger.error(f"❌ 启动Web服务器失败: {e}")
            
            # 检查是否是端口冲突
            if "Address already in use" in str(e) or "port" in str(e).lower():
                logger.warning(f"🔧 确认检测到端口 {self.port} 冲突")
                logger.info(f"💡 建议解决方案:")
                logger.info(f"   1. 稍等片刻后重新加载插件")
                logger.info(f"   2. 重启AstrBot以完全清理资源")
                logger.info(f"   3. 在插件配置中修改web_interface_port为其他端口")
                
            import traceback
            logger.error(f"异常堆栈: {traceback.format_exc()}")
            self.server_task = None

    async def _async_check_port_available(self, port: int) -> bool:
        """异步检查端口是否可用 - 改进版，使用bind检查而不是connect"""
        try:
            import socket
            loop = asyncio.get_event_loop()

            def check_port():
                try:
                    # 尝试绑定端口而不是连接端口
                    # 这是更准确的检查方式
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                        sock.settimeout(1)
                        try:
                            # 尝试绑定端口
                            sock.bind(("127.0.0.1", port))
                            # 绑定成功,说明端口可用
                            logger.debug(f"端口 {port} 可用(绑定测试成功)")
                            return True
                        except OSError as e:
                            # 绑定失败,端口被占用
                            if e.errno in (48, 98):  # macOS: 48, Linux: 98 (Address already in use)
                                logger.debug(f"端口 {port} 被占用: {e}")
                                return False
                            # 其他错误,假设端口可用
                            logger.debug(f"检查端口 {port} 时遇到其他错误: {e},假设可用")
                            return True
                except Exception as ex:
                    logger.warning(f"检查端口 {port} 时发生异常: {ex},假设可用")
                    return True  # 异常时假设端口可用

            return await loop.run_in_executor(None, check_port)
        except Exception:
            return True  # 检查失败时假设端口可用

    async def _verify_server_listening(self) -> bool:
        """验证服务器是否正在监听端口"""
        try:
            import aiohttp
            timeout = aiohttp.ClientTimeout(total=2)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                try:
                    async with session.get(f"http://{self.host}:{self.port}/") as response:
                        return response.status in [200, 302, 404]  # 任何HTTP响应都表示服务器在运行
                except aiohttp.ClientConnectorError:
                    return False
        except ImportError:
            # 如果没有aiohttp，回退到socket检查
            try:
                import socket
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.settimeout(2)
                    result = sock.connect_ex(("127.0.0.1", self.port))
                    return result == 0
            except Exception:
                return False
        except Exception:
            return False

    async def _try_force_release_port(self, port: int):
        """
        尝试强制释放被占用的端口（跨平台支持）
        主要用于处理框架重启后端口未能及时释放的情况
        """
        import sys
        import subprocess

        logger.info(f"🔧 尝试释放端口 {port}...")

        try:
            if sys.platform == 'darwin':  # macOS
                # 查找占用端口的进程
                try:
                    result = subprocess.run(
                        ['lsof', '-i', f':{port}', '-t'],
                        capture_output=True, text=True, timeout=5
                    )
                    if result.stdout.strip():
                        pids = result.stdout.strip().split('\n')
                        current_pid = str(os.getpid())
                        for pid in pids:
                            pid = pid.strip()
                            if pid and pid != current_pid:
                                logger.warning(f"⚠️ 发现占用端口 {port} 的进程: PID={pid}")
                                # 不自动杀死进程，只是记录信息
                                # 因为可能是同一AstrBot实例的其他部分
                                logger.info(f"💡 如需释放，请手动执行: kill {pid}")
                except FileNotFoundError:
                    logger.debug("lsof命令不可用")
                except subprocess.TimeoutExpired:
                    logger.debug("lsof命令超时")

            elif sys.platform == 'linux':
                # Linux: 使用ss或lsof查找占用进程
                try:
                    result = subprocess.run(
                        ['ss', '-tlnp', f'sport = :{port}'],
                        capture_output=True, text=True, timeout=5
                    )
                    if result.stdout:
                        logger.info(f"端口 {port} 占用详情:\n{result.stdout}")
                except FileNotFoundError:
                    # 回退到lsof
                    try:
                        result = subprocess.run(
                            ['lsof', '-i', f':{port}', '-t'],
                            capture_output=True, text=True, timeout=5
                        )
                        if result.stdout.strip():
                            pids = result.stdout.strip().split('\n')
                            current_pid = str(os.getpid())
                            for pid in pids:
                                pid = pid.strip()
                                if pid and pid != current_pid:
                                    logger.warning(f"⚠️ 发现占用端口 {port} 的进程: PID={pid}")
                    except FileNotFoundError:
                        logger.debug("ss和lsof命令都不可用")
                except subprocess.TimeoutExpired:
                    logger.debug("ss命令超时")

            elif sys.platform == 'win32':  # Windows
                try:
                    result = subprocess.run(
                        ['netstat', '-ano'],
                        capture_output=True, text=True, timeout=5
                    )
                    if result.stdout:
                        for line in result.stdout.split('\n'):
                            if f':{port}' in line and 'LISTENING' in line:
                                logger.info(f"端口 {port} 占用详情: {line.strip()}")
                except Exception as e:
                    logger.debug(f"Windows netstat检查失败: {e}")

        except Exception as e:
            logger.debug(f"检查端口占用时出错: {e}")

        # 给系统一些时间来清理TIME_WAIT状态的连接
        logger.info(f"⏳ 等待系统清理TIME_WAIT连接...")
        await asyncio.sleep(1)

    async def stop(self):
        """停止服务器 - 使用 Hypercorn shutdown_trigger 优雅关闭并验证端口释放"""
        logger.info(f"🛑 正在停止Web服务器 (端口: {self.port})...")

        if self.server_task and not self.server_task.done():
            try:
                logger.info("📋 开始优雅停止Web服务器 (使用 shutdown_trigger)...")

                graceful_stopped = False

                # 1. 首先尝试通过 shutdown_trigger 优雅关闭 Hypercorn
                try:
                    if self._shutdown_event is not None and not self._shutdown_event.is_set():
                        self._shutdown_event.set()
                        # 给 Hypercorn 一定时间完成优雅关闭
                        await asyncio.wait_for(self.server_task, timeout=10.0)
                        logger.info("✅ Web服务器已通过 shutdown_trigger 优雅停止")
                        graceful_stopped = True
                except asyncio.TimeoutError:
                    logger.warning("⚠️ Web服务器优雅停止超时，将尝试强制取消任务")
                except asyncio.CancelledError:
                    logger.info("✅ Web服务器任务在优雅停止过程中被取消")
                    graceful_stopped = True
                except Exception as e:
                    logger.warning(f"⚠️ 使用 shutdown_trigger 停止Web服务器时出现异常: {e}")

                # 2. 如优雅关闭未成功，则强制取消 Hypercorn 任务
                if not graceful_stopped:
                    logger.info("🔧 开始强制取消 Hypercorn 任务...")
                    self.server_task.cancel()
                    try:
                        await asyncio.wait_for(self.server_task, timeout=5.0)
                        logger.info("✅ Web服务器任务已强制取消")
                    except asyncio.CancelledError:
                        logger.info("✅ Web服务器任务已取消")
                    except asyncio.TimeoutError:
                        logger.warning("⚠️ 强制取消 Hypercorn 任务超时，可能仍有残留连接")
                    except Exception as e:
                        logger.warning(f"⚠️ 强制终止Web服务器时出现异常: {e}")

                # 3. 清理任务引用与 shutdown_event
                self.server_task = None
                self._shutdown_event = None

                # 4. 等待更长时间让端口完全释放
                logger.info("⏳ 等待端口资源完全释放...")
                await asyncio.sleep(3)

                # 5. 强制关闭所有可能残留的socket连接
                try:
                    import socket
                    import gc
                    # 触发垃圾回收，清理未关闭的socket
                    gc.collect()
                    logger.debug("✅ 已触发垃圾回收")
                except Exception as e:
                    logger.debug(f"垃圾回收失败: {e}")

                # 6. 验证端口是否真的释放了 - 使用 bind 测试
                port_released = False
                for attempt in range(5):  # 检查5次
                    try:
                        import socket
                        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                            sock.settimeout(1)
                            try:
                                sock.bind(("127.0.0.1", self.port))
                                port_released = True
                                logger.info(f"✅ 端口 {self.port} 已确认释放 (绑定测试成功, 尝试 {attempt + 1}/5)")
                                break
                            except OSError as e:
                                if e.errno in (48, 98):  # Address already in use
                                    logger.debug(f"⏳ 端口 {self.port} 仍被占用 (尝试 {attempt + 1}/5): {e}")
                                    if attempt < 4:
                                        await asyncio.sleep(1)
                                    continue
                                else:
                                    port_released = True
                                    logger.debug(f"端口检查遇到其他错误,假设已释放: {e}")
                                    break
                    except Exception as e:
                        logger.debug(f"端口检查失败 (尝试 {attempt + 1}/5): {e}")
                        if attempt == 4:
                            port_released = True
                            logger.info("📝 端口检查失败，假定端口已释放")

                if port_released:
                    logger.info(f"✅ Web服务器完全停止，端口 {self.port} 已释放")
                else:
                    logger.warning(f"⚠️ Web服务器已停止，但端口 {self.port} 可能仍被占用")
                    logger.info("💡 提示: 如果遇到端口占用问题，请重启AstrBot或等待10-15秒后重试")

            except Exception as e:
                logger.error(f"❌ 停止Web服务器过程中发生错误: {e}", exc_info=True)
            finally:
                # 无论如何都要清理任务引用
                self.server_task = None
                self._shutdown_event = None
                logger.info("🧹 Web服务器任务引用已清理")
        else:
            logger.info("ℹ️ Web服务器已经停止或未启动，无需停止操作")

        logger.info(f"🔧 Web服务器停止流程完成 (端口: {self.port})")
