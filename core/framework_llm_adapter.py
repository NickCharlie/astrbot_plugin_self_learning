"""
AstrBot 框架 LLM 适配器
用于替换自定义 LLMClient，直接使用 AstrBot 框架的 Provider 系统
"""
import asyncio
import time
from typing import Optional, List, Dict, Any
from astrbot.api import logger
from astrbot.core.provider.provider import Provider
from astrbot.core.provider.entities import LLMResponse

class FrameworkLLMAdapter:
    """AstrBot框架LLM适配器，用于替换自定义LLMClient"""
    
    def __init__(self, context):
        self.context = context
        self.filter_provider: Optional[Provider] = None
        self.refine_provider: Optional[Provider] = None  
        self.reinforce_provider: Optional[Provider] = None
        self.providers_configured = 0
        
        # 添加调用统计
        self.call_stats = {
            'filter': {'total_calls': 0, 'total_time': 0, 'errors': 0},
            'refine': {'total_calls': 0, 'total_time': 0, 'errors': 0},
            'reinforce': {'total_calls': 0, 'total_time': 0, 'errors': 0},
            'general': {'total_calls': 0, 'total_time': 0, 'errors': 0}
        }
        
    def initialize_providers(self, config):
        """根据配置初始化Provider"""
        from astrbot.core.provider.entities import ProviderType
        
        self.providers_configured = 0
        
        if config.filter_provider_id:
            self.filter_provider = self.context.get_provider_by_id(config.filter_provider_id)
            if not self.filter_provider:
                logger.warning(f"找不到筛选Provider: {config.filter_provider_id}")
            else:
                # 检查Provider类型
                provider_meta = self.filter_provider.meta()
                if provider_meta.provider_type != ProviderType.CHAT_COMPLETION:
                    logger.error(f"筛选Provider类型错误: {config.filter_provider_id} 是 {provider_meta.provider_type.value} 类型，需要 {ProviderType.CHAT_COMPLETION.value} 类型")
                    self.filter_provider = None
                else:
                    logger.info(f"筛选Provider已配置: {config.filter_provider_id}")
                    self.providers_configured += 1
                
        if config.refine_provider_id:
            self.refine_provider = self.context.get_provider_by_id(config.refine_provider_id)
            if not self.refine_provider:
                logger.warning(f"找不到提炼Provider: {config.refine_provider_id}")
            else:
                # 检查Provider类型
                provider_meta = self.refine_provider.meta()
                if provider_meta.provider_type != ProviderType.CHAT_COMPLETION:
                    logger.error(f"提炼Provider类型错误: {config.refine_provider_id} 是 {provider_meta.provider_type.value} 类型，需要 {ProviderType.CHAT_COMPLETION.value} 类型")
                    self.refine_provider = None
                else:
                    logger.info(f"提炼Provider已配置: {config.refine_provider_id}")
                    self.providers_configured += 1
                
        if config.reinforce_provider_id:
            self.reinforce_provider = self.context.get_provider_by_id(config.reinforce_provider_id)
            if not self.reinforce_provider:
                logger.warning(f"找不到强化Provider: {config.reinforce_provider_id}")
            else:
                # 检查Provider类型
                provider_meta = self.reinforce_provider.meta()
                if provider_meta.provider_type != ProviderType.CHAT_COMPLETION:
                    logger.error(f"强化Provider类型错误: {config.reinforce_provider_id} 是 {provider_meta.provider_type.value} 类型，需要 {ProviderType.CHAT_COMPLETION.value} 类型")
                    self.reinforce_provider = None
                else:
                    logger.info(f"强化Provider已配置: {config.reinforce_provider_id}")
                    self.providers_configured += 1
        
        # 友好的配置状态提示
        if self.providers_configured == 0:
            logger.info("💡 提示：暂未配置任何AI模型Provider。插件将使用简化算法运行，如需完整功能请在插件配置中设置模型Provider ID。")
        elif self.providers_configured < 3:
            logger.info(f"ℹ️ 已配置 {self.providers_configured}/3 个AI模型Provider。部分高级功能可能使用简化算法。")
    
    async def filter_chat_completion(
        self,
        prompt: str,
        contexts: Optional[List[Dict[str, str]]] = None,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> Optional[str]:
        """使用筛选模型进行对话补全"""
        if not self.filter_provider:
            logger.error("筛选Provider未配置")
            return None
            
        try:
            start_time = time.time()
            self.call_stats['filter']['total_calls'] += 1
            
            logger.debug(f"调用筛选Provider: {self.filter_provider.meta().id}")
            response = await self.filter_provider.text_chat(
                prompt=prompt,
                contexts=contexts,
                system_prompt=system_prompt,
                **kwargs
            )
            
            # 统计调用时间
            elapsed_time = time.time() - start_time
            self.call_stats['filter']['total_time'] += elapsed_time
            
            return response.completion_text if response else None
        except Exception as e:
            # 统计错误
            elapsed_time = time.time() - start_time
            self.call_stats['filter']['total_time'] += elapsed_time
            self.call_stats['filter']['errors'] += 1
            
            logger.error(f"筛选模型调用失败: {e}")
            return None
    
    async def refine_chat_completion(
        self,
        prompt: str,
        contexts: Optional[List[Dict[str, str]]] = None,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> Optional[str]:
        """使用提炼模型进行对话补全"""
        if not self.refine_provider:
            logger.error("提炼Provider未配置")
            return None
            
        try:
            start_time = time.time()
            self.call_stats['refine']['total_calls'] += 1
            
            logger.debug(f"调用提炼Provider: {self.refine_provider.meta().id}")
            response = await self.refine_provider.text_chat(
                prompt=prompt,
                contexts=contexts,
                system_prompt=system_prompt,
                **kwargs
            )
            
            # 统计调用时间
            elapsed_time = time.time() - start_time
            self.call_stats['refine']['total_time'] += elapsed_time
            
            return response.completion_text if response else None
        except Exception as e:
            # 统计错误
            elapsed_time = time.time() - start_time
            self.call_stats['refine']['total_time'] += elapsed_time
            self.call_stats['refine']['errors'] += 1
            
            logger.error(f"提炼模型调用失败: {e}")
            return None
    
    async def reinforce_chat_completion(
        self,
        prompt: str,
        contexts: Optional[List[Dict[str, str]]] = None,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> Optional[str]:
        """使用强化模型进行对话补全"""
        if not self.reinforce_provider:
            logger.error("强化Provider未配置")
            return None
            
        try:
            start_time = time.time()
            self.call_stats['reinforce']['total_calls'] += 1
            
            logger.debug(f"调用强化Provider: {self.reinforce_provider.meta().id}")
            response = await self.reinforce_provider.text_chat(
                prompt=prompt,
                contexts=contexts,
                system_prompt=system_prompt,
                **kwargs
            )
            
            # 统计调用时间
            elapsed_time = time.time() - start_time
            self.call_stats['reinforce']['total_time'] += elapsed_time
            
            return response.completion_text if response else None
        except Exception as e:
            # 统计错误
            elapsed_time = time.time() - start_time
            self.call_stats['reinforce']['total_time'] += elapsed_time
            self.call_stats['reinforce']['errors'] += 1
            
            logger.error(f"强化模型调用失败: {e}")
            return None
    
    async def generate_response(self, prompt: str, temperature: float = 0.7, model_type: str = "general", **kwargs) -> Optional[str]:
        """通用响应生成方法"""
        start_time = time.time()
        self.call_stats['general']['total_calls'] += 1
        
        try:
            # 根据model_type选择对应的provider
            if model_type == "filter" and self.filter_provider:
                provider = self.filter_provider
            elif model_type == "refine" and self.refine_provider:
                provider = self.refine_provider
            elif model_type == "reinforce" and self.reinforce_provider:
                provider = self.reinforce_provider
            else:
                # 使用第一个可用的provider
                provider = self.filter_provider or self.refine_provider or self.reinforce_provider
            
            if not provider:
                logger.error("没有可用的Provider")
                return None
            
            response = await provider.text_chat(prompt=prompt, **kwargs)
            
            # 统计调用时间
            elapsed_time = time.time() - start_time
            self.call_stats['general']['total_time'] += elapsed_time
            
            return response.completion_text if response else None
            
        except Exception as e:
            # 统计错误
            elapsed_time = time.time() - start_time
            self.call_stats['general']['total_time'] += elapsed_time
            self.call_stats['general']['errors'] += 1
            
            logger.error(f"通用模型调用失败: {e}")
            return None
    
    def get_call_statistics(self) -> Dict[str, Any]:
        """获取调用统计信息"""
        stats = {}
        total_calls = 0
        total_time = 0
        total_errors = 0
        
        for provider_type, data in self.call_stats.items():
            calls = data['total_calls']
            time_spent = data['total_time']
            errors = data['errors']
            
            total_calls += calls
            total_time += time_spent
            total_errors += errors
            
            avg_time = (time_spent / calls * 1000) if calls > 0 else 0
            success_rate = ((calls - errors) / calls) if calls > 0 else 1.0
            
            stats[provider_type] = {
                'total_calls': calls,
                'avg_response_time_ms': round(avg_time, 2),
                'success_rate': success_rate,
                'error_count': errors
            }
        
        # 添加总体统计
        overall_avg_time = (total_time / total_calls * 1000) if total_calls > 0 else 0
        overall_success_rate = ((total_calls - total_errors) / total_calls) if total_calls > 0 else 1.0
        
        stats['overall'] = {
            'total_calls': total_calls,
            'avg_response_time_ms': round(overall_avg_time, 2),
            'success_rate': overall_success_rate,
            'error_count': total_errors
        }
        
        return stats

    def has_filter_provider(self) -> bool:
        """检查是否有筛选Provider"""
        return self.filter_provider is not None
    
    def has_refine_provider(self) -> bool:
        """检查是否有提炼Provider"""
        return self.refine_provider is not None
    
    def has_reinforce_provider(self) -> bool:
        """检查是否有强化Provider"""
        return self.reinforce_provider is not None

    def get_provider_info(self) -> Dict[str, str]:
        """获取Provider信息"""
        info = {}
        if self.filter_provider:
            info['filter'] = f"{self.filter_provider.meta().id} ({self.filter_provider.meta().model})"
        if self.refine_provider:
            info['refine'] = f"{self.refine_provider.meta().id} ({self.refine_provider.meta().model})"
        if self.reinforce_provider:
            info['reinforce'] = f"{self.reinforce_provider.meta().id} ({self.reinforce_provider.meta().model})"
        return info

    async def generate_response(self, prompt: str, temperature: float = 0.7, model_type: str = "filter") -> Optional[str]:
        """
        通用的生成响应方法，根据model_type调用对应的Provider
        
        Args:
            prompt: 提示词
            temperature: 温度参数
            model_type: 模型类型 ("filter", "refine", "reinforce")
            
        Returns:
            LLM响应文本，如果失败返回None
        """
        try:
            if model_type == "filter":
                return await self.filter_chat_completion(prompt=prompt, temperature=temperature)
            elif model_type == "refine":
                return await self.refine_chat_completion(prompt=prompt, temperature=temperature)
            elif model_type == "reinforce":
                return await self.reinforce_chat_completion(prompt=prompt, temperature=temperature)
            else:
                logger.error(f"不支持的模型类型: {model_type}")
                return None
        except Exception as e:
            logger.error(f"generate_response调用失败: {e}")
            return None