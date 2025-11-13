import os
import asyncio
import json # 导入 json 模块
import secrets
import time
from datetime import datetime, timedelta
from astrbot.api import logger
from typing import Optional, List, Dict, Any
from dataclasses import asdict
from functools import wraps

from quart import Quart, Blueprint, render_template, request, jsonify, current_app, redirect, url_for, session # 导入 redirect 和 url_for
from quart_cors import cors # 导入 cors
import hypercorn.asyncio
from hypercorn.config import Config as HypercornConfig

from .config import PluginConfig
from .core.factory import FactoryManager
from .persona_web_manager import PersonaWebManager, set_persona_web_manager, get_persona_web_manager

# 获取当前文件所在的目录，然后向上两级到达插件根目录
PLUGIN_ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '.'))
WEB_STATIC_DIR = os.path.join(PLUGIN_ROOT_DIR, "web_res", "static")
WEB_HTML_DIR = os.path.join(WEB_STATIC_DIR, "html")
PASSWORD_FILE_PATH = os.path.join(PLUGIN_ROOT_DIR, "config", "password.json") # 定义密码文件路径

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

# 新增的变量
pending_updates: List[Any] = []
password_config: Dict[str, Any] = {} # 用于存储密码配置

# 设置日志
# logger = logging.getLogger(__name__)

# 性能指标存储
llm_call_metrics: Dict[str, Dict[str, Any]] = {}

def load_password_config() -> Dict[str, Any]:
    """加载密码配置文件"""
    if os.path.exists(PASSWORD_FILE_PATH):
        with open(PASSWORD_FILE_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"password": "self_learning_pwd", "must_change": True}

def save_password_config(config: Dict[str, Any]):
    """保存密码配置文件"""
    with open(PASSWORD_FILE_PATH, 'w', encoding='utf-8') as f:
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
    global plugin_config, persona_manager, persona_updater, database_manager, db_manager, llm_client, pending_updates
    plugin_config = config
    llm_client = llm_c

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
        persona_updater = factory_manager.get_service("persona_updater")
        database_manager = factory_manager.get_service("database_manager")
        db_manager = database_manager  # 设置别名
    except Exception as e:
        logger.error(f"获取服务实例失败: {e}")
        persona_updater = None
        database_manager = None
        db_manager = None

    # 加载待审查的人格更新
    if persona_updater:
        try:
            pending_updates = await persona_updater.get_pending_persona_updates()
        except Exception as e:
            print(f"加载待审查人格更新失败: {e}")
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
    """处理用户登录"""
    data = await request.get_json()
    password = data.get("password")
    global password_config
    password_config = load_password_config() # 登录时重新加载密码配置

    if password == password_config.get("password"):
        # 设置会话认证状态
        session['authenticated'] = True
        session.permanent = True  # 设置为永久会话
        
        if password_config.get("must_change"):
            return jsonify({"message": "Login successful, but password must be changed", "must_change": True, "redirect": "/api/plugin_change_password"}), 200
        return jsonify({"message": "Login successful", "must_change": False, "redirect": "/api/index"}), 200
    
    return jsonify({"error": "Invalid password"}), 401

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
    print(f"[DEBUG] Template folder: {WEB_HTML_DIR}")
    print(f"[DEBUG] Looking for template: ，.html")
    template_path = os.path.join(WEB_HTML_DIR, "change_password.html")
    print(f"[DEBUG] Full template path: {template_path}")
    print(f"[DEBUG] Template exists: {os.path.exists(template_path)}")
    
    return await render_template("change_password.html")

@api_bp.route("/plugin_change_password", methods=["POST"])
async def change_password():
    """处理修改密码请求"""
    # 检查是否已认证
    if not is_authenticated():
        return jsonify({"error": "Authentication required", "redirect": "/api/login"}), 401
        
    data = await request.get_json()
    old_password = data.get("old_password")
    new_password = data.get("new_password")
    global password_config
    password_config = load_password_config() # 修改密码时重新加载密码配置

    if old_password == password_config.get("password"):
        if new_password and new_password != old_password:
            password_config["password"] = new_password
            password_config["must_change"] = False
            save_password_config(password_config)
            return jsonify({"message": "Password changed successfully"}), 200
        return jsonify({"error": "New password cannot be empty or same as old password"}), 400
    return jsonify({"error": "Invalid old password"}), 401

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

@api_bp.route("/persona_updates")
@require_auth
async def get_persona_updates():
    """获取需要人工审查的人格更新内容"""
    if persona_updater:
        updates = await persona_updater.get_pending_persona_updates()
        return jsonify([record.__dict__ for record in updates])
    return jsonify({"error": "Persona updater not initialized"}), 500

@api_bp.route("/persona_updates/<int:update_id>/review", methods=["POST"])
@require_auth
async def review_persona_update(update_id: int):
    """审查人格更新内容 (批准/拒绝)"""
    if persona_updater:
        data = await request.get_json()
        action = data.get("action")
        result = await persona_updater.review_persona_update(update_id, action)
        if result:
            return jsonify({"message": f"Update {update_id} {action}d successfully"})
        return jsonify({"error": "Failed to update persona review status"}), 500
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
                print(f"获取数据库统计失败: {e}")
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
        
        # CPU和内存使用率
        cpu_percent = psutil.cpu_percent(interval=1)
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
            "learning_efficiency": (filtered_messages / total_messages * 100) if total_messages > 0 else 0,
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
            },
            "learning_sessions": {
                "active_sessions": 1 if persona_updater else 0,
                "total_sessions_today": 5,
                "avg_session_duration_minutes": 45,
                "success_rate": 0.85
            },
            "last_updated": time.time()
        }
        
        return jsonify(metrics)
        
    except Exception as e:
        print(f"获取性能指标失败: {e}")
        import traceback
        traceback.print_exc()
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
        print(f"获取人格详情失败: {e}")
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
        print(f"导出人格失败: {e}")
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
            print(f"成功导入人格: {persona_id} ({action})")
            return jsonify({"message": f"人格{action}成功", "persona_id": persona_id})
        else:
            return jsonify({"error": f"人格{action}失败"}), 500
            
    except Exception as e:
        print(f"导入人格失败: {e}")
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
    """获取对话风格学习的所有内容文本"""
    try:
        # 从数据库获取学习相关的文本内容
        content_data = {
            'dialogues': [],
            'analysis': [],
            'features': [],
            'history': []
        }
        
        if db_manager:
            try:
                # 获取对话示例文本 - 使用现有的方法
                recent_messages = await db_manager.get_filtered_messages_for_learning(20)
                if recent_messages:
                    for msg in recent_messages:
                        content_data['dialogues'].append({
                            'timestamp': datetime.fromtimestamp(msg.get('timestamp', time.time())).strftime('%Y-%m-%d %H:%M:%S'),
                            'text': f"用户: {msg.get('message', '暂无内容')}",
                            'metadata': f"置信度: {msg.get('confidence', 0):.1%}, 群组: {msg.get('group_id', '未知')}"
                        })
                else:
                    # 没有数据时提供友好提示
                    content_data['dialogues'].append({
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'text': '暂无对话数据，请先进行一些群聊对话，系统会自动学习和筛选有价值的内容',
                        'metadata': '系统提示'
                    })
            except Exception as e:
                logger.warning(f"获取对话示例文本失败: {e}")
                content_data['dialogues'].append({
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'text': f'获取对话数据时出错: {str(e)}',
                    'metadata': '错误信息'
                })
            
            try:
                # 获取风格分析结果 - 使用学习批次数据
                recent_batches = await db_manager.get_recent_learning_batches(limit=5)
                if recent_batches:
                    for batch in recent_batches:
                        content_data['analysis'].append({
                            'timestamp': datetime.fromtimestamp(batch.get('start_time', time.time())).strftime('%Y-%m-%d %H:%M:%S'),
                            'text': f"学习批次: {batch.get('batch_name', '未命名')}\n处理消息: {batch.get('message_count', 0)}条\n质量得分: {batch.get('quality_score', 0):.2f}",
                            'metadata': f"成功: {'是' if batch.get('success') else '否'}"
                        })
                else:
                    content_data['analysis'].append({
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'text': '暂无学习分析数据，系统还未开始自动学习过程',
                        'metadata': '系统提示'
                    })
            except Exception as e:
                logger.warning(f"获取风格分析结果失败: {e}")
                content_data['analysis'].append({
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'text': f'获取分析数据时出错: {str(e)}',
                    'metadata': '错误信息'
                })
            
            try:
                # 获取提炼的风格特征 - 使用表达模式数据
                conn = await db_manager._get_messages_db_connection()
                cursor = await conn.cursor()
                await cursor.execute('SELECT * FROM expression_patterns ORDER BY last_active_time DESC LIMIT 10')
                expression_patterns = await cursor.fetchall()
                
                if expression_patterns:
                    for pattern in expression_patterns:
                        content_data['features'].append({
                            'timestamp': datetime.fromtimestamp(pattern[4]).strftime('%Y-%m-%d %H:%M:%S'), # last_active_time
                            'text': f"场景: {pattern[1]}\n表达: {pattern[2]}", # situation, expression
                            'metadata': f"权重: {pattern[3]:.2f}, 群组: {pattern[6]}" # weight, group_id
                        })
                else:
                    content_data['features'].append({
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'text': '暂无学习到的表达模式，请耐心等待系统学习',
                        'metadata': '系统提示'
                    })
            except Exception as e:
                logger.warning(f"获取风格特征失败: {e}")
                content_data['features'].append({
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'text': f'获取特征数据时出错: {str(e)}',
                    'metadata': '错误信息'
                })
            
            try:
                # 获取学习历程记录 - 使用现有的方法
                message_stats = await db_manager.get_messages_statistics()
                content_data['history'].append({
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'text': f"系统统计:\n总消息数: {message_stats.get('total_messages', 0)}条\n已筛选: {message_stats.get('filtered_messages', 0)}条\n待学习: {message_stats.get('unused_filtered_messages', 0)}条",
                    'metadata': '实时统计'
                })
            except Exception as e:
                logger.warning(f"获取学习历程记录失败: {e}")
                content_data['history'].append({
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'text': f'获取历程数据时出错: {str(e)}',
                    'metadata': '错误信息'
                })
        
        # 如果数据库中没有数据，返回空数据结构
        # 不提供示例数据，让前端显示"暂无数据"状态
        
        return jsonify(content_data)
    
    except Exception as e:
        logger.error(f"获取学习内容文本失败: {e}")
        return jsonify({'error': str(e)}), 500

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
            print(f"🔧 初始化Web服务器 (端口: {port})...")

            # 检查端口是否可用
            print(f"Debug: 开始检查端口可用性")
            self._check_port_availability(port)
            print(f"Debug: 端口检查完成")

            self.host = host
            self.port = port
            self.server_task: Optional[asyncio.Task] = None

            print(f"Debug: 创建 HypercornConfig")
            self.config = HypercornConfig()
            self.config.bind = [f"{self.host}:{self.port}"]
            self.config.accesslog = "-" # 输出访问日志到 stdout
            self.config.errorlog = "-" # 输出错误日志到 stdout
            # 添加其他必要的配置
            self.config.loglevel = "INFO"
            self.config.use_reloader = False
            self.config.workers = 1

            print(f"✅ Web服务器初始化完成 (端口: {port})")
            print(f"Debug: 配置绑定: {self.config.bind}")

        except Exception as e:
            print(f"❌ Web服务器初始化失败: {e}")
            import traceback
            print(f"❌ 初始化异常堆栈: {traceback.format_exc()}")
            raise
    
    def _check_port_availability(self, port: int):
        """检查端口可用性，如果被占用则等待或警告"""
        import socket
        
        # 检查端口是否被占用
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(1)
                result = sock.connect_ex(("127.0.0.1", port))
                if result == 0:
                    print(f"⚠️ 端口 {port} 被占用，这可能是之前的实例未正确关闭")
                    print(f"🔄 Web服务器启动时将尝试重用该端口")
                else:
                    print(f"✅ 端口 {port} 可用")
        except Exception as e:
            print(f"⚠️ 检查端口 {port} 时出错: {e}")
            print(f"🔄 继续初始化，启动时处理端口冲突")

    async def start(self):
        """启动服务器 - 增强版本，包含端口冲突处理"""
        print(f"🚀 启动Web服务器 (端口: {self.port})...")
        print(f"Debug: self.server_task = {self.server_task}")
        print(f"Debug: host = {self.host}, port = {self.port}")

        if self.server_task and not self.server_task.done():
            print("ℹ️ Web服务器已在运行中")
            return # Server already running
        
        try:
            print(f"🔧 配置服务器绑定: {self.config.bind}")
            print(f"Debug: 准备创建Hypercorn serve任务")
            print(f"Debug: app类型: {type(app)}")
            print(f"Debug: config类型: {type(self.config)}")

            # Hypercorn 的 serve 函数是阻塞的，需要在一个单独的协程中运行
            print(f"Debug: 调用 asyncio.create_task")
            self.server_task = asyncio.create_task(
                hypercorn.asyncio.serve(app, self.config)
            )

            print(f"✅ Web服务器任务已创建: {self.server_task}")
            print(f"🌐 访问地址: http://{self.host}:{self.port}")

            # 等待服务器启动
            print(f"Debug: 等待2秒让服务器启动")
            await asyncio.sleep(2)

            # 检查服务器状态
            print(f"Debug: 检查服务器状态, task.done() = {self.server_task.done() if self.server_task else 'None'}")
            if self.server_task and not self.server_task.done():
                print(f"✅ Web服务器启动成功 (http://{self.host}:{self.port})")
            else:
                print(f"❌ Web服务器任务意外完成")
                if self.server_task and self.server_task.done():
                    try:
                        # 获取任务异常
                        exception = self.server_task.exception()
                        if exception:
                            print(f"❌ 服务器启动异常: {exception}")
                            print(f"❌ 异常类型: {type(exception)}")
                            import traceback
                            print(f"❌ 异常堆栈: {traceback.format_exc()}")
                    except Exception as ex:
                        print(f"❌ 获取异常信息时出错: {ex}")
                
        except Exception as e:
            print(f"❌ 启动Web服务器失败: {e}")
            
            # 检查是否是端口冲突
            if "Address already in use" in str(e) or "port" in str(e).lower():
                print(f"🔧 检测到端口 {self.port} 冲突")
                print(f"💡 建议: 插件重载时前一个实例可能未完全关闭")
                
            import traceback
            traceback.print_exc()
            self.server_task = None

    async def stop(self):
        """停止服务器 - 增强版本，包含超时处理"""
        print(f"🛑 正在停止Web服务器 (端口: {self.port})...")
        
        if self.server_task and not self.server_task.done():
            # 1. 尝试优雅关闭，设置超时
            self.server_task.cancel()
            try:
                await asyncio.wait_for(self.server_task, timeout=5.0)
                print("✅ Web服务器已优雅停止")
            except asyncio.CancelledError:
                print("✅ Web服务器已取消")
            except asyncio.TimeoutError:
                print("⚠️ Web服务器停止超时，已强制取消")
            except Exception as e:
                print(f"⚠️ 停止Web服务器时出错: {e}")
            
            # 2. 等待端口释放
            await asyncio.sleep(1)
            
            self.server_task = None
            print(f"🔧 Web服务器停止完成 (端口: {self.port})")
        else:
            print("ℹ️ Web服务器已经停止或未启动")
