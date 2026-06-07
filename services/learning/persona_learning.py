"""Persona learning module.

Keeps persona-specific learning logic separate from expression and jargon
learning. The progressive learning service remains the batch orchestrator.
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from astrbot.api import logger

from ...constants import UPDATE_TYPE_PROGRESSIVE_PERSONA_LEARNING
from ...utils.json_utils import clean_llm_json_response, safe_parse_llm_json
from ...utils.persona_selection import get_persona_identifier, resolve_target_persona


class PersonaLearningModule:
    """Generate persona candidates and create review records."""

    def __init__(
        self,
        *,
        config: Any,
        context: Any,
        db_manager: Any,
        persona_manager: Any,
        multidimensional_analyzer: Any,
        prompts: Any,
        resolve_umo,
        json_serializer,
    ) -> None:
        self.config = config
        self.context = context
        self.db_manager = db_manager
        self.persona_manager = persona_manager
        self.multidimensional_analyzer = multidimensional_analyzer
        self.prompts = prompts
        self._resolve_umo = resolve_umo
        self._json_serializer = json_serializer

    async def get_current_persona(self, group_id: str) -> Dict[str, Any]:
        """Get current persona settings for a group."""
        try:
            persona = await self.persona_manager.get_current_persona(group_id)
            if persona:
                return persona

            if hasattr(self.context, "persona_manager") and self.context.persona_manager:
                try:
                    default_persona = await resolve_target_persona(
                        self.context.persona_manager,
                        self.config,
                        self._resolve_umo(group_id),
                        require_existing=True,
                        log=logger,
                    )
                    if default_persona:
                        return {
                            "prompt": default_persona.get("prompt", "默认人格"),
                            "name": get_persona_identifier(default_persona),
                            "style_parameters": {},
                            "last_updated": datetime.now().isoformat(),
                        }
                except Exception as exc:
                    logger.warning(f"从框架获取默认人格失败: {exc}")

            return {
                "prompt": "默认人格",
                "name": "default",
                "style_parameters": {},
                "last_updated": datetime.now().isoformat(),
            }
        except Exception as exc:
            logger.error(f"获取当前人格失败 for group {group_id}: {exc}")
            return {"prompt": "默认人格", "name": "default", "style_parameters": {}}

    async def generate_updated_persona_with_refinement(
        self,
        group_id: str,
        current_persona: Dict[str, Any],
        style_analysis: Any,
    ) -> Dict[str, Any]:
        """Generate a persona candidate, using refine provider when available."""
        try:
            analysis_data = self.extract_analysis_data(style_analysis)

            if (
                hasattr(self.multidimensional_analyzer, "llm_adapter")
                and self.multidimensional_analyzer.llm_adapter
            ):
                llm_adapter = self.multidimensional_analyzer.llm_adapter

                if (
                    llm_adapter.has_refine_provider()
                    and llm_adapter.providers_configured >= 2
                ):
                    current_persona_json = json.dumps(
                        current_persona,
                        ensure_ascii=False,
                        indent=2,
                        default=self._json_serializer,
                    )
                    style_analysis_json = json.dumps(
                        analysis_data,
                        ensure_ascii=False,
                        indent=2,
                        default=self._json_serializer,
                    )

                    response = await llm_adapter.refine_chat_completion(
                        prompt=self.prompts.PROGRESSIVE_LEARNING_GENERATE_UPDATED_PERSONA_PROMPT.format(
                            current_persona_json=current_persona_json,
                            style_analysis_json=style_analysis_json,
                        ),
                        temperature=0.6,
                    )

                    if response:
                        clean_response = clean_llm_json_response(response)
                        try:
                            updated_persona = safe_parse_llm_json(clean_response)
                            logger.info("使用提炼模型成功生成更新后的人格")
                            return updated_persona
                        except json.JSONDecodeError as exc:
                            logger.error(
                                f"提炼模型返回的JSON格式不正确: {exc}, 响应: {clean_response}"
                            )
                            return await self.generate_updated_persona(
                                group_id, current_persona, style_analysis
                            )

                logger.warning("提炼模型Provider未配置，使用传统方法生成人格")
                return await self.generate_updated_persona(
                    group_id, current_persona, style_analysis
                )

            logger.warning("框架适配器未找到，使用传统方法生成人格")
            return await self.generate_updated_persona(
                group_id, current_persona, style_analysis
            )

        except Exception as exc:
            logger.error(f"使用提炼模型生成人格失败: {exc}")
            return await self.generate_updated_persona(
                group_id, current_persona, style_analysis
            )

    async def generate_updated_persona(
        self,
        group_id: str,
        current_persona: Dict[str, Any],
        style_analysis: Any,
    ) -> Dict[str, Any]:
        """Generate a persona candidate by appending incremental learning text."""
        try:
            if not hasattr(self.context, "persona_manager") or not self.context.persona_manager:
                logger.warning(f"无法获取PersonaManager for group {group_id}")
                return current_persona

            default_persona = await resolve_target_persona(
                self.context.persona_manager,
                self.config,
                self._resolve_umo(group_id),
                require_existing=True,
                log=logger,
            )
            if not default_persona:
                logger.warning(f"无法获取当前人格 for group {group_id}")
                return current_persona

            original_prompt = default_persona.get("prompt", "")
            learning_content = self.extract_learning_content(style_analysis)

            if learning_content:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
                new_content = (
                    f"\n\n【学习更新 - {timestamp}】\n"
                    + "\n".join(learning_content)
                )

                updated_persona = dict(default_persona)
                updated_persona["prompt"] = original_prompt + new_content
                updated_persona["last_updated"] = timestamp

                logger.info(
                    f" 成功追加 {len(learning_content)} 项学习内容到人格 for group {group_id}"
                )
                return updated_persona

            analysis_data = self.extract_analysis_data(style_analysis)
            logger.warning(
                f" style_analysis中没有可提取的学习内容 for group {group_id}, "
                f"数据结构: {list(analysis_data.keys())}"
            )
            return dict(default_persona)

        except Exception as exc:
            logger.error(f"生成更新人格失败 for group {group_id}: {exc}", exc_info=True)
            return current_persona

    async def apply_persona_learning(
        self,
        group_id: str,
        style_analysis: Any,
        messages: List[Dict[str, Any]],
        *,
        current_persona: Optional[Dict[str, Any]] = None,
        updated_persona: Optional[Dict[str, Any]] = None,
        quality_metrics: Any = None,
        relearn_mode: bool = False,
        ml_tuning_info: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Apply persona-side learning and create a review when needed."""
        try:
            current_persona = self._coerce_persona(current_persona, "current_persona")
            updated_persona = self._coerce_persona(updated_persona, "updated_persona")

            logger.info(f"应用人格更新 for group {group_id}")

            style_analysis_dict, _confidence = self.style_analysis_to_dict(
                style_analysis
            )
            if style_analysis_dict is None:
                return False

            update_success = await self.persona_manager.update_persona(
                group_id, style_analysis_dict, messages
            )
            if not update_success:
                logger.error(f"通过 PersonaManagerService 更新人格失败 for group {group_id}")

            should_create_review = self.should_create_review(
                current_persona=current_persona,
                updated_persona=updated_persona,
                relearn_mode=relearn_mode,
                group_id=group_id,
            )
            if should_create_review:
                await self.create_persona_review(
                    group_id,
                    style_analysis,
                    messages,
                    current_persona=current_persona,
                    updated_persona=updated_persona,
                    quality_metrics=quality_metrics,
                    relearn_mode=relearn_mode,
                    ml_tuning_info=ml_tuning_info,
                )
            else:
                logger.debug("人格未变化或缺少必要参数，跳过审查记录创建")

            return bool(update_success)

        except Exception as exc:
            logger.error(f"应用人格学习失败 for group {group_id}: {exc}")
            return False

    @staticmethod
    def extract_analysis_data(style_analysis: Any) -> Dict[str, Any]:
        """Normalize AnalysisResult/dict-like style analysis to a dict."""
        try:
            from ...core.interfaces import AnalysisResult

            if isinstance(style_analysis, AnalysisResult):
                analysis_data = style_analysis.data if style_analysis.data else {}
                logger.debug(
                    "从AnalysisResult提取data: "
                    f"success={style_analysis.success}, confidence={style_analysis.confidence}"
                )
                return analysis_data
        except Exception:
            pass

        if isinstance(style_analysis, dict):
            logger.debug("使用字典形式的style_analysis")
            return style_analysis
        if hasattr(style_analysis, "data"):
            analysis_data = style_analysis.data if style_analysis.data else {}
            logger.debug(f"从对象提取data属性: {type(style_analysis)}")
            return analysis_data

        logger.warning(f"style_analysis类型不正确: {type(style_analysis)}, 使用空字典")
        return {}

    def extract_learning_content(self, style_analysis: Any) -> List[str]:
        """Extract persona increment text from style analysis data."""
        analysis_data = self.extract_analysis_data(style_analysis)
        learning_content: List[str] = []

        if "enhanced_prompt" in analysis_data:
            learning_content.append(analysis_data["enhanced_prompt"])
            logger.debug("找到 enhanced_prompt 字段")

        if "learning_insights" in analysis_data:
            insights = analysis_data["learning_insights"]
            if insights:
                learning_content.append(insights)
                logger.debug("找到 learning_insights 字段")

        if not learning_content and "style_analysis" in analysis_data:
            style_report = analysis_data["style_analysis"]
            if isinstance(style_report, dict):
                extracted_parts = []

                if "text_style" in style_report:
                    extracted_parts.append(f"文本风格: {style_report['text_style']}")

                if "expression_features" in style_report:
                    features = style_report["expression_features"]
                    if isinstance(features, list):
                        extracted_parts.append(f"表达特点: {', '.join(features)}")
                    elif isinstance(features, str):
                        extracted_parts.append(f"表达特点: {features}")

                if "tone" in style_report:
                    extracted_parts.append(f"语气倾向: {style_report['tone']}")

                if "topics" in style_report:
                    topics = style_report["topics"]
                    if isinstance(topics, list):
                        extracted_parts.append(f"话题偏好: {', '.join(topics)}")
                    elif isinstance(topics, str):
                        extracted_parts.append(f"话题偏好: {topics}")

                if extracted_parts:
                    learning_content.append("【对话风格学习结果】\n" + "\n".join(extracted_parts))
                    logger.debug(
                        f"从 style_analysis 提取了 {len(extracted_parts)} 个风格特征"
                    )

        if not learning_content and "style_profile" in analysis_data:
            style_profile = analysis_data["style_profile"]
            if isinstance(style_profile, dict):
                profile_parts = []

                if "tone_intensity" in style_profile:
                    profile_parts.append(f"语气强度: {style_profile['tone_intensity']:.2f}")
                if "sentiment" in style_profile:
                    profile_parts.append(f"情感倾向: {style_profile['sentiment']:.2f}")
                if "vocabulary_richness" in style_profile:
                    profile_parts.append(
                        f"词汇丰富度: {style_profile['vocabulary_richness']:.2f}"
                    )

                if profile_parts:
                    learning_content.append("【风格量化指标】\n" + "\n".join(profile_parts))
                    logger.debug(f"从 style_profile 提取了 {len(profile_parts)} 个量化指标")

        if not learning_content:
            for field in ("summary", "description", "analysis", "insights", "findings"):
                if field in analysis_data and analysis_data[field]:
                    learning_content.append(f"【{field}】\n{analysis_data[field]}")
                    logger.debug(f"从顶层字段 {field} 提取了内容")
                    break

        return learning_content

    def style_analysis_to_dict(self, style_analysis: Any) -> tuple[Optional[Dict[str, Any]], float]:
        """Return (data, confidence) for persona manager updates."""
        if hasattr(style_analysis, "success"):
            if not style_analysis.success:
                logger.error(f"风格分析失败，跳过人格更新: {style_analysis.error}")
                return None, 0.0
            logger.debug(f"使用 AnalysisResult 对象，置信度: {style_analysis.confidence:.3f}")
            return style_analysis.data, style_analysis.confidence
        if isinstance(style_analysis, dict):
            logger.debug("使用字典形式的 style_analysis（向后兼容）")
            return style_analysis, style_analysis.get("confidence", 0.5)

        logger.error(f"style_analysis 类型不正确: {type(style_analysis)}")
        return None, 0.0

    @staticmethod
    def should_create_review(
        *,
        current_persona: Optional[Dict[str, Any]],
        updated_persona: Optional[Dict[str, Any]],
        relearn_mode: bool,
        group_id: str,
    ) -> bool:
        """Determine whether a persona review record should be created."""
        if relearn_mode:
            should_create = bool(updated_persona and current_persona)
            if should_create:
                has_changes = updated_persona.get("prompt", "") != current_persona.get(
                    "prompt", ""
                )
                if has_changes:
                    logger.info(
                        f" 重新学习模式：检测到人格变化，创建审查记录（group: {group_id}）"
                    )
                else:
                    logger.info(
                        f" 重新学习模式：未检测到人格变化，但仍创建审查记录供审核"
                        f"（group: {group_id}）"
                    )
            else:
                logger.warning(
                    " 重新学习模式：无法创建审查记录 - "
                    f"updated_persona={bool(updated_persona)}, "
                    f"current_persona={bool(current_persona)}"
                )
            return should_create

        if (
            updated_persona
            and current_persona
            and updated_persona.get("prompt") != current_persona.get("prompt")
        ):
            logger.info(f" 正常模式：检测到人格变化，创建审查记录（group: {group_id}）")
            return True

        logger.debug(
            f" 正常模式：人格未变化，跳过审查记录 - "
            f"updated={bool(updated_persona)}, current={bool(current_persona)}, "
            f"same_prompt={updated_persona.get('prompt') == current_persona.get('prompt') if updated_persona and current_persona else 'N/A'}"
        )
        return False

    async def create_persona_review(
        self,
        group_id: str,
        style_analysis: Any,
        messages: List[Dict[str, Any]],
        *,
        current_persona: Dict[str, Any],
        updated_persona: Dict[str, Any],
        quality_metrics: Any = None,
        relearn_mode: bool = False,
        ml_tuning_info: Optional[Dict[str, Any]] = None,
    ) -> Optional[int]:
        """Create a persona learning review record."""
        try:
            original_prompt = current_persona.get("prompt", "")
            new_prompt = updated_persona.get("prompt", "")

            if len(new_prompt) > len(original_prompt):
                incremental_content = new_prompt[len(original_prompt):].strip()
            else:
                incremental_content = new_prompt

            metadata = {
                "progressive_learning": True,
                "message_count": len(messages),
                "style_analysis_fields": list(
                    style_analysis.data.keys()
                    if hasattr(style_analysis, "data")
                    and isinstance(style_analysis.data, dict)
                    else style_analysis.keys()
                    if isinstance(style_analysis, dict)
                    else []
                ),
                "original_prompt_length": len(original_prompt),
                "new_prompt_length": len(new_prompt),
                "incremental_content": incremental_content,
                "incremental_start_pos": len(original_prompt),
                "relearn_mode": relearn_mode,
            }

            if ml_tuning_info:
                metadata["ml_tuning"] = ml_tuning_info

            confidence_score = (
                quality_metrics.consistency_score
                if quality_metrics and hasattr(quality_metrics, "consistency_score")
                else 0.5
            )

            raw_analysis_parts = [f"基于{len(messages)}条消息的风格分析"]
            if relearn_mode:
                raw_analysis_parts.append("（重新学习）")
            if ml_tuning_info and ml_tuning_info.get("applied"):
                if ml_tuning_info.get("used_conservative_fusion"):
                    raw_analysis_parts.append(
                        "强化学习生成的prompt过短"
                        f"({ml_tuning_info['tuned_length']} vs "
                        f"{ml_tuning_info['original_length']})，采用保守融合策略"
                    )
                else:
                    raw_analysis_parts.append(
                        "已应用强化学习优化，预期改进: "
                        f"{ml_tuning_info['expected_improvement']:.2%}"
                    )
            raw_analysis = "；".join(raw_analysis_parts)

            review_id = await self.db_manager.add_persona_learning_review(
                group_id=group_id,
                proposed_content=incremental_content,
                learning_source=UPDATE_TYPE_PROGRESSIVE_PERSONA_LEARNING,
                confidence_score=confidence_score,
                raw_analysis=raw_analysis,
                metadata=metadata,
                original_content=original_prompt,
                new_content=new_prompt,
            )

            logger.info(
                f" 已创建人格学习审查记录 (ID: {review_id})，"
                f"置信度: {confidence_score:.3f}"
            )
            return review_id

        except Exception as exc:
            logger.error(f"创建人格学习审查记录失败: {exc}", exc_info=True)
            return None

    @staticmethod
    def _coerce_persona(
        persona: Optional[Dict[str, Any]], label: str
    ) -> Optional[Dict[str, Any]]:
        if isinstance(persona, list):
            logger.warning(f"{label}为list类型(长度{len(persona)})，转换为空字典")
            return {}
        return persona
