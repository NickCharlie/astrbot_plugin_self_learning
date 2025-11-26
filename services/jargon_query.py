"""
黑话查询服务 - LLM工具调用接口

提供给LLM使用的黑话查询工具,用于在生成回复时理解群组黑话
"""
import time
from typing import Optional, List, Dict, Any, Tuple
from astrbot.api import logger


class JargonQueryService:
    """黑话查询服务 - 供LLM工具调用"""

    def __init__(self, db_manager, cache_ttl: int = 60):
        """
        初始化黑话查询服务

        Args:
            db_manager: 数据库管理器实例
            cache_ttl: 缓存有效期（秒），默认60秒
        """
        self.db = db_manager

        # ⚡ 缓存机制 - 避免频繁查询数据库
        self._cache: Dict[str, Tuple[float, Any]] = {}
        self._cache_ttl = cache_ttl

    def _get_from_cache(self, key: str) -> Optional[Any]:
        """从缓存获取数据"""
        if key in self._cache:
            timestamp, data = self._cache[key]
            if time.time() - timestamp < self._cache_ttl:
                return data
            else:
                del self._cache[key]
        return None

    def _set_to_cache(self, key: str, data: Any):
        """设置缓存"""
        self._cache[key] = (time.time(), data)

    async def query_jargon(
        self,
        keyword: str,
        chat_id: Optional[str] = None,
        include_global: bool = True,
        limit: int = 3
    ) -> str:
        """
        查询黑话含义 - 主要供LLM工具调用

        Args:
            keyword: 要查询的黑话关键词
            chat_id: 当前群组ID (优先搜索该群组的黑话)
            include_global: 是否包含全局黑话
            limit: 返回结果数量限制

        Returns:
            格式化的黑话含义说明文本
        """
        try:
            results = []

            # 1. 首先搜索群组特定黑话
            if chat_id:
                group_results = await self.db.search_jargon(
                    keyword=keyword,
                    chat_id=chat_id,
                    limit=limit
                )
                results.extend(group_results)

            # 2. 如果结果不足且需要包含全局黑话
            if include_global and len(results) < limit:
                global_results = await self.db.search_jargon(
                    keyword=keyword,
                    chat_id=None,  # 搜索全局黑话
                    limit=limit - len(results)
                )
                # 去重
                existing_ids = {r['id'] for r in results}
                for gr in global_results:
                    if gr['id'] not in existing_ids:
                        results.append(gr)

            # 格式化输出
            if not results:
                return f"未找到关于'{keyword}'的黑话记录"

            if len(results) == 1:
                r = results[0]
                return f"黑话「{r['content']}」的含义: {r['meaning']}"

            output_lines = [f"找到 {len(results)} 个与「{keyword}」相关的黑话:"]
            for i, r in enumerate(results, 1):
                meaning = r['meaning'] if r['meaning'] else '含义待推断'
                output_lines.append(f"{i}. 「{r['content']}」: {meaning}")

            return "\n".join(output_lines)

        except Exception as e:
            logger.error(f"查询黑话失败: {e}")
            return f"查询黑话时发生错误: {str(e)}"

    async def get_jargon_context(
        self,
        chat_id: str,
        limit: int = 10
    ) -> str:
        """
        获取群组的黑话上下文 - 用于增强LLM对群组文化的理解（带缓存）

        Args:
            chat_id: 群组ID
            limit: 返回数量限制

        Returns:
            格式化的黑话列表文本
        """
        # ⚡ 先检查缓存
        cache_key = f"jargon_context_{chat_id}_{limit}"
        cached = self._get_from_cache(cache_key)
        if cached is not None:
            return cached

        try:
            jargon_list = await self.db.get_recent_jargon_list(
                chat_id=chat_id,
                limit=limit,
                only_confirmed=True
            )

            if not jargon_list:
                result = "该群组暂无已确认的黑话记录"
                self._set_to_cache(cache_key, result)
                return result

            lines = [f"群组常用黑话 ({len(jargon_list)}个):"]
            for j in jargon_list:
                meaning = j['meaning'] if j['meaning'] else '含义待推断'
                lines.append(f"- 「{j['content']}」: {meaning}")

            result = "\n".join(lines)

            # ⚡ 缓存结果
            self._set_to_cache(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"获取黑话上下文失败: {e}")
            return ""

    async def check_and_explain_jargon(
        self,
        text: str,
        chat_id: str
    ) -> Optional[str]:
        """
        检查文本中是否包含已知黑话并提供解释（带缓存）

        Args:
            text: 要检查的文本
            chat_id: 群组ID

        Returns:
            如果找到黑话则返回解释文本,否则返回None
        """
        try:
            # ⚡ 先从缓存获取该群组的黑话列表
            cache_key = f"jargon_list_{chat_id}"
            jargon_list = self._get_from_cache(cache_key)

            if jargon_list is None:
                # 缓存未命中，从数据库获取
                jargon_list = await self.db.get_recent_jargon_list(
                    chat_id=chat_id,
                    limit=100,
                    only_confirmed=True
                )
                # ⚡ 缓存黑话列表
                self._set_to_cache(cache_key, jargon_list)

            if not jargon_list:
                return None

            # 检查文本中是否包含黑话
            found_jargon = []
            for j in jargon_list:
                if j['content'] and j['content'] in text:
                    found_jargon.append(j)

            if not found_jargon:
                return None

            # 格式化解释
            lines = ["文本中包含的黑话:"]
            for j in found_jargon:
                meaning = j['meaning'] if j['meaning'] else '含义待推断'
                lines.append(f"- 「{j['content']}」: {meaning}")

            return "\n".join(lines)

        except Exception as e:
            logger.error(f"检查黑话失败: {e}")
            return None


# LLM工具函数定义 - 可直接注册为LLM工具
def create_jargon_tool(db_manager) -> Dict[str, Any]:
    """
    创建黑话查询工具定义

    Args:
        db_manager: 数据库管理器实例

    Returns:
        工具定义字典
    """
    query_service = JargonQueryService(db_manager)

    async def query_jargon_tool(keyword: str, chat_id: str = "") -> str:
        """
        查询黑话含义

        当你在对话中遇到不理解的词语、网络用语、群组特定术语时,
        可以使用这个工具来查询它们的含义。

        Args:
            keyword: 要查询的黑话或术语
            chat_id: 当前群组ID (可选)

        Returns:
            黑话的含义说明
        """
        return await query_service.query_jargon(
            keyword=keyword,
            chat_id=chat_id if chat_id else None,
            include_global=True
        )

    return {
        "name": "query_jargon",
        "description": "查询黑话/网络用语/群组术语的含义。当遇到不理解的词语时使用。",
        "parameters": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "要查询的黑话或术语"
                },
                "chat_id": {
                    "type": "string",
                    "description": "当前群组ID (可选,用于优先搜索群组特定黑话)"
                }
            },
            "required": ["keyword"]
        },
        "function": query_jargon_tool
    }
