import asyncio
import json
from typing import Optional, List, Dict, Any
import aiohttp

from astrbot.api import logger

from ..utils.rate_limiter import get_rate_limiter

class LLMResponse:
    """
    模拟 AstrBot 内部 LLMResponse 的简化类。
    """
    def __init__(self, text: str, raw_response: Dict[str, Any]):
        self._text = text
        self._raw_response = raw_response

    def text(self) -> str:
        return self._text

    def raw(self) -> Dict[str, Any]:
        return self._raw_response

class LLMClient:
    """
    封装自定义 LLM API 调用的客户端。
    用于根据配置的 API URL 和 API Key 调用不同的 LLM。
    ！！！已弃用！！！已由 FrameworkLLMAdapter 取代，但保留此文件以防其他模块引用。
    限流逻辑已迁移至 FrameworkLLMAdapter。
    """

    def __init__(self):
        self.client = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60.0)) # 设置超时时间

    def _get_provider_info(self, api_url: str, model_name: str) -> str:
        """获取API提供商信息用于日志"""
        if not api_url:  # 防止None值导致错误
            return f"Unknown API ({model_name})"
        
        if 'deepseek.com' in api_url:
            return f"DeepSeek ({model_name})"
        elif 'openai.com' in api_url:
            return f"OpenAI ({model_name})"
        elif 'anthropic.com' in api_url:
            return f"Anthropic ({model_name})"
        else:
            return f"Custom API ({model_name})"

    def _validate_api_url(self, api_url: str, model_name: str = "") -> str:
        """验证并补全API URL为完整端点路径
        
        这个方法已经不需要了
        """
        return api_url

    async def chat_completion(
        self,
        api_url: str = None,
        api_key: str = None, 
        model_name: str = None,
        prompt: str = None,
        contexts: Optional[List[Dict[str, str]]] = None,
        system_prompt: Optional[str] = None,
        max_retries: int = 3,
        retry_delay: float = 0.0,
        **kwargs
    ) -> Optional[LLMResponse]:
        """
        执行 LLM 对话补全。
        
        Args:
            api_url: API 地址
            api_key: API 密钥
            model_name: 模型名称
            prompt: 用户提示词
            contexts: 上下文对话历史
            system_prompt: 系统提示词
            max_retries: 最大重试次数，默认3次
            retry_delay: 重试间隔时间(秒)，默认1秒
            **kwargs: 其他参数
        
        Returns:
            LLMResponse 对象或 None
        """
        # 参数验证 - 如果参数为空，返回警告并返回None
        if not api_url or not api_key or not model_name or not prompt:
            logger.warning(f"LLMClient参数不完整: api_url={bool(api_url)}, api_key={bool(api_key)}, model_name={bool(model_name)}, prompt={bool(prompt)}")
            return None
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if contexts:
            messages.extend(contexts)
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model_name,
            "messages": messages,
            **kwargs
        }
        
        # 根据模型名称进行特殊处理
        model_lower = model_name.lower()
        
        # DeepSeek模型特殊处理
        if 'deepseek' in model_lower:
            payload.setdefault("stream", False)  # 确保非流式输出
            # 对于deepseek-reasoner模型，使用更适合推理的参数
            if 'reasoner' in model_lower:
                payload.setdefault("temperature", 0.1)  # 思考模式建议较低温度
                payload.setdefault("top_p", 0.95)
                
        # OpenAI模型特殊处理
        elif any(model in model_lower for model in ['gpt-', 'text-', 'davinci']):
            payload.setdefault("temperature", 0.7)
            
        # Claude模型特殊处理
        elif 'claude' in model_lower:
            # Anthropic可能有不同的参数格式
            payload.setdefault("temperature", 0.7)
        
        # 验证API URL是完整路径
        api_url = self._validate_api_url(api_url, model_name)

        last_error = None
        
        # 实施重试机制
        for attempt in range(max_retries):
            try:
                provider_info = self._get_provider_info(api_url, model_name)
                logger.debug(f"调用 {provider_info} API: {api_url} (尝试 {attempt + 1}/{max_retries})")
                async with self.client.post(api_url, headers=headers, json=payload) as response:
                    # 检查HTTP状态码，区分可重试和不可重试的错误
                    if response.status in [401, 403, 404]:  # 认证、权限、资源不存在错误，不可重试
                        error_msg = f"不可重试的HTTP错误 {response.status}: {await response.text()}"
                        logger.error(error_msg)
                        return None
                    
                    if response.status not in [200, 429, 500, 502, 503, 504]:  # 其他未知错误
                        response.raise_for_status()

                    response_data = await response.json()
                    
                    # 假设LLM响应格式与OpenAI兼容
                    if "choices" in response_data and len(response_data["choices"]) > 0:
                        message = response_data["choices"][0].get("message", {})
                        text_content = message.get("content", "")
                        if text_content:
                            if attempt > 0:  # 如果之前有失败的尝试，记录成功
                                logger.info(f"LLM API 调用在第 {attempt + 1} 次尝试后成功")
                            return LLMResponse(text=text_content, raw_response=response_data)
                    
                    # 响应格式错误，不进行重试
                    error_msg = f"LLM API 响应格式不正确或无内容: {response_data}"
                    logger.error(error_msg)
                    return None
                        
            except aiohttp.ClientResponseError as e:
                if e.status in [429, 500, 502, 503, 504]:  # 可重试的HTTP错误
                    error_msg = f"可重试的HTTP错误 {e.status}: {e.message}"
                    logger.warning(f"{error_msg} (attempt {attempt + 1}/{max_retries})")
                    last_error = e
                else:  # 不可重试的HTTP错误
                    error_msg = f"不可重试的HTTP错误 {e.status}: {e.message}"
                    logger.error(error_msg)
                    return None
                
            except aiohttp.ClientError as e:
                error_msg = f"调用 LLM API ({api_url}) 网络请求失败: {e}"
                logger.warning(f"{error_msg} (attempt {attempt + 1}/{max_retries})")
                last_error = e
                
            except json.JSONDecodeError as e:
                error_msg = f"LLM API 响应JSON解析失败: {e}"
                logger.warning(f"{error_msg} (attempt {attempt + 1}/{max_retries})")
                last_error = e
                
            except Exception as e:
                error_msg = f"调用 LLM API ({api_url}) 发生未知错误: {e}"
                logger.warning(f"{error_msg} (attempt {attempt + 1}/{max_retries})")
                last_error = e
            
            # 如果不是最后一次尝试，等待后重试
            if attempt < max_retries - 1:
                wait_time = retry_delay * (2 ** attempt)  # 指数退避
                logger.info(f"等待 {wait_time} 秒后重试...")
                await asyncio.sleep(wait_time)
        
        # 所有重试都失败了
        logger.error(f"LLM API 调用在 {max_retries} 次尝试后全部失败，最后错误: {last_error}", exc_info=True)
        return None

    async def close(self):
        """关闭 HTTP 客户端会话"""
        if self.client:
            await self.client.close()
