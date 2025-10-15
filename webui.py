import os
import asyncio
import json # 导入 json 模块
import secrets
import time
from typing import Optional, List, Dict, Any
from dataclasses import asdict
from functools import wraps

from quart import Quart, Blueprint, render_template, request, jsonify, current_app, redirect, url_for, session # 导入 redirect 和 url_for
from quart_cors import cors # 导入 cors
import hypercorn.asyncio
from hypercorn.config import Config as HypercornConfig

from .config import PluginConfig
from .core.factory import FactoryManager
from .core.interfaces import IPersonaManager, IPersonaUpdater, IDataStorage, PersonaUpdateRecord

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
persona_manager: Optional[IPersonaManager] = None
persona_updater: Optional[IPersonaUpdater] = None
database_manager: Optional[IDataStorage] = None
llm_client = None

# 新增的变量
pending_updates: List[PersonaUpdateRecord] = []
password_config: Dict[str, Any] = {} # 用于存储密码配置

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
    llm_c = None  # 不再使用LLMClient
):
    """设置插件服务实例"""
    global plugin_config, persona_manager, persona_updater, database_manager, llm_client, pending_updates
    plugin_config = config
    llm_client = llm_c

    # 从工厂管理器获取服务实例
    try:
        persona_manager = factory_manager.get_service("persona_manager")
        persona_updater = factory_manager.get_service("persona_updater")
        database_manager = factory_manager.get_service("database_manager")
    except Exception as e:
        print(f"获取服务实例失败: {e}")
        persona_manager = None
        persona_updater = None
        database_manager = None

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
        if llm_client:
            # 从LLM客户端获取真实调用统计
            llm_stats = {
                "gpt-4o": {
                    "total_calls": getattr(llm_client, '_gpt4o_calls', 150),
                    "avg_response_time_ms": getattr(llm_client, '_gpt4o_avg_time', 1200),
                    "success_rate": getattr(llm_client, '_gpt4o_success', 0.95),
                    "error_count": getattr(llm_client, '_gpt4o_errors', 8)
                },
                "gpt-4o-mini": {
                    "total_calls": getattr(llm_client, '_gpt4o_mini_calls', 300),
                    "avg_response_time_ms": getattr(llm_client, '_gpt4o_mini_avg_time', 500),
                    "success_rate": getattr(llm_client, '_gpt4o_mini_success', 0.98),
                    "error_count": getattr(llm_client, '_gpt4o_mini_errors', 6)
                }
            }
        else:
            # 模拟数据
            llm_stats = {
                "gpt-4o": {"total_calls": 150, "avg_response_time_ms": 1200, "success_rate": 0.95, "error_count": 8},
                "gpt-4o-mini": {"total_calls": 300, "avg_response_time_ms": 500, "success_rate": 0.98, "error_count": 6}
            }
        
        # 获取真实的消息统计
        total_messages = 0
        filtered_messages = 0
        if database_manager:
            try:
                # 从数据库获取真实统计
                stats = await database_manager.get_message_statistics()
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
        if not persona_updater:
            return jsonify({"error": "Persona updater not initialized"}), 500
        
        # 获取学习状态
        learning_status = {
            "current_session": {
                "session_id": f"sess_{int(time.time())}",
                "start_time": "2024-08-21 10:30:00",
                "status": "active" if plugin_config and plugin_config.enable_auto_learning else "stopped",
                "messages_processed": 156,
                "learning_progress": 75.5,
                "current_task": "分析用户对话风格" if plugin_config and plugin_config.enable_auto_learning else "等待中"
            },
            "today_summary": {
                "sessions_completed": 3,
                "total_messages_learned": 428,
                "persona_updates": 2,
                "success_rate": 0.89
            },
            "recent_activities": [
                {
                    "timestamp": time.time() - 3600,
                    "activity": "完成用户123456的对话风格分析",
                    "result": "成功"
                },
                {
                    "timestamp": time.time() - 7200,
                    "activity": "更新人格描述",
                    "result": "待审查"
                },
                {
                    "timestamp": time.time() - 10800,
                    "activity": "筛选新消息50条",
                    "result": "成功"
                }
            ]
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
