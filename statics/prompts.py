"""
LLM Prompt 静态文件
"""

# 通用JSON响应系统提示 - 确保LLM只返回JSON而不包含任何注释
JSON_ONLY_SYSTEM_PROMPT = """重要：请只返回有效的JSON数据，不要包含任何解释、注释、说明文字或代码块标记。直接返回纯JSON格式的数据。"""

# ml_analyzer.py 中的 prompt
ML_ANALYZER_REPLAY_MEMORY_SYSTEM_PROMPT = """
你是一个人格提炼专家。你的任务是分析以下消息记录，并结合当前人格描述，提炼出新的、更丰富的人格特征和对话风格。
重点关注消息中体现的：
- 语言习惯、用词偏好
- 情感表达方式
- 互动模式
- 知识领域和兴趣点
- 与当前人格的契合点和差异点

当前人格描述：
{current_persona_description}

请以结构化的JSON格式返回提炼结果，例如：
{{
    "new_style_features": {{
        "formal_level": 0.X,
        "enthusiasm_level": 0.Y,
        "question_tendency": 0.Z
    }},
    "new_topic_preferences": {{
        "话题A": 0.A,
        "话题B": 0.B
    }},
    "personality_insights": "一段关于人格演变的总结"
}}
"""

ML_ANALYZER_REPLAY_MEMORY_PROMPT = """
请分析以下消息记录，并结合当前人格，提炼出新的风格和特征：

{messages_text}
"""

ML_ANALYZER_SENTIMENT_ANALYSIS_PROMPT = """
请分析以下消息集合的整体情感倾向，并以JSON格式返回积极、消极、中性、疑问、惊讶五种情感的平均置信度分数（0-1之间）。

消息集合：
{messages_text}

请只返回一个JSON对象，例如：
{{
    "积极": 0.8,
    "消极": 0.1,
    "中性": 0.1,
    "疑问": 0.0,
    "惊讶": 0.0
}}
"""

# style_analyzer.py 中的 prompt
STYLE_ANALYZER_GENERATE_STYLE_ANALYSIS_PROMPT = """
请对以下对话文本进行详细的风格分析，以JSON格式返回结果：

对话文本：
{text}

请从以下维度进行分析并返回JSON格式结果：
{{
    "语言特色": {{
        "词汇使用": "分析词汇选择和使用特点",
        "句式结构": "分析句子结构和复杂度",
        "修辞手法": "识别使用的修辞技巧"
    }},
    "情感表达": {{
        "情感倾向": "整体情感倾向(积极/消极/中性)",
        "情感强度": "情感表达的强烈程度(0-1)",
        "情感变化": "情感在对话中的变化模式"
    }},
    "交流风格": {{
        "互动方式": "与他人交流的方式方式特点",
        "话题偏好": "倾向于讨论的话题类型",
        "回应模式": "对他人消息的回应特征"
    }},
    "个性化特征": {{
        "独特表达": "特有的表达习惯和用词",
        "思维模式": "体现的思维特点",
        "沟通目标": "沟通时的主要目标"
    }},
    "适应建议": {{
        "风格匹配度": "与目标人格的匹配程度(0-1)",
        "改进方向": "建议的风格调整方向",
        "学习价值": "作为学习材料的价值评估(0-1)"
    }}
}}
"""

STYLE_ANALYZER_EXTRACT_STYLE_PROFILE_PROMPT = """
请对以下对话文本进行数值化的风格特征提取，返回JSON格式的评分(0-1)：

对话文本：
{text}

请返回以下格式的JSON，每个维度给出0-1的评分：
{{
    "vocabulary_richness": 0.0,  // 词汇丰富度
    "sentence_complexity": 0.0,  // 句式复杂度
    "emotional_expression": 0.0,  // 情感表达度
    "interaction_tendency": 0.0,  // 互动倾向
    "topic_diversity": 0.0,       // 话题多样性
    "formality_level": 0.0,       // 正式程度
    "creativity_score": 0.0       // 创造性得分
}}
"""

STYLE_ANALYZER_GENERATE_STYLE_RECOMMENDATIONS_PROMPT = """
基于当前的风格档案数据和目标人格，生成风格优化建议：

当前风格档案：
{current_style_data}

目标人格：{target_persona}

请返回JSON格式的优化建议：
{{
    "优化方向": {{
        "需要加强": ["具体的风格维度和建议"],
        "需要调整": ["需要调整的方面"],
        "保持现状": ["已经较好的方面"]
    }},
    "具体建议": {{
        "词汇使用": "词汇选择的具体建议",
        "句式结构": "句式调整建议", 
        "情感表达": "情感表达优化建议",
        "互动方式": "互动方式改进建议"
    }},
    "实施策略": {{
        "短期目标": "1-2周内可以改进的方面",
        "中期目标": "1-2个月的改进方向",
        "长期目标": "长期的风格发展目标"
    }},
    "风险提示": "需要注意的潜在风险和副作用"
}}
"""

# multidimensional_analyzer.py 中的 prompt
MULTIDIMENSIONAL_ANALYZER_FILTER_MESSAGE_PROMPT = """
你是一个消息筛选专家，你的任务是判断一条消息是否具有以下特征：
1. 与当前人格的对话风格和兴趣高度匹配。
2. 消息内容特征鲜明，不平淡，具有一定的独特性或深度。
3. 对学习当前人格的对话模式和知识有积极意义。

当前人格描述：
{current_persona_description}

待筛选消息：
"{message_text}"

请你根据以上标准，对这条消息进行评估，并给出一个0到1之间的置信度分数。
0表示完全不符合，1表示完全符合。
请只返回一个0-1之间的数值，不需要其他说明。
"""

MULTIDIMENSIONAL_ANALYZER_EVALUATE_MESSAGE_QUALITY_PROMPT = """
你是一个专业的对话质量评估专家，请根据以下标准对一条消息进行多维度量化评分。
评分范围为0到1，0表示非常低，1表示非常高。

当前人格描述：
{current_persona_description}

待评估消息：
"{message_text}"

请评估以下维度并以JSON格式返回结果：
{{
    "content_quality": 0.0-1.0,  // 消息的深度、信息量、原创性、表达清晰度
    "relevance": 0.0-1.0,        // 与当前对话主题或人格的相关性
    "emotional_positivity": 0.0-1.0, // 消息的情感倾向（积极程度）
    "interactivity": 0.0-1.0,    // 消息是否引发或回应了互动（如提问、回应、@他人）
    "learning_value": 0.0-1.0    // 消息对模型学习当前人格对话模式和知识的潜在贡献
}}

请确保返回有效的JSON格式，并且只包含JSON对象，不需要其他说明。
"""

MULTIDIMENSIONAL_ANALYZER_EMOTIONAL_CONTEXT_PROMPT = """
请分析以下文本的情感倾向，并以JSON格式返回积极、消极、中性、疑问、惊讶五种情感的置信度分数（0-1之间）。

文本内容："{message_text}"

请只返回一个JSON对象，例如：
{{
    "积极": 0.8,
    "消极": 0.1,
    "中性": 0.1,
    "疑问": 0.0,
    "惊讶": 0.0
}}
"""

MULTIDIMENSIONAL_ANALYZER_FORMAL_LEVEL_PROMPT = """
请分析以下文本的正式程度，从0-1评分，0表示非常随意，1表示非常正式。

分析维度：
- 称谓使用（您/你）
- 语言风格（书面语/口语）
- 礼貌用语频率
- 句式结构复杂度
- 专业术语使用

文本内容："{text}"

请只返回一个0-1之间的数值，不需要其他说明。
"""

MULTIDIMENSIONAL_ANALYZER_ENTHUSIASM_LEVEL_PROMPT = """
请分析以下文本的热情程度，从0-1评分，0表示非常冷淡，1表示非常热情。

分析维度：
- 感叹号使用频率
- 积极情感词汇
- 表情符号使用
- 语气强烈程度
- 互动意愿表达

文本内容："{text}"

请只返回一个0-1之间的数值，不需要其他说明。
"""

MULTIDIMENSIONAL_ANALYZER_QUESTION_TENDENCY_PROMPT = """
请分析以下文本的提问倾向，从0-1评分，0表示完全没有疑问，1表示强烈的求知欲和疑问。

分析维度：
- 疑问句数量
- 求知欲表达
- 不确定性表述
- 征求意见的语气
- 探索性语言

文本内容："{text}"

请只返回一个0-1之间的数值，不需要其他说明。
"""

MULTIDIMENSIONAL_ANALYZER_DEEP_INSIGHTS_PROMPT = """
请基于以下用户数据，生成深度的用户画像洞察。以JSON格式返回结果：

用户数据：
{user_data_summary}

请分析以下维度并返回JSON格式结果：
{{
    "personality_type": "用户性格类型(如：外向型/内向型/混合型)",
    "communication_preference": "沟通偏好描述",
    "social_role": "在群体中的角色定位",
    "activity_pattern_analysis": "活动模式分析",
    "interest_alignment": "兴趣领域归类",
    "learning_potential": "学习价值评估(0-1)",
    "interaction_style": "互动风格特征",
    "content_contribution": "内容贡献度评估"
}}

请确保返回有效的JSON格式。
"""

MULTIDIMENSIONAL_ANALYZER_PERSONALITY_TRAITS_PROMPT = """
基于用户的沟通风格数据，分析其人格特质。请返回JSON格式的五大人格特质评分(0-1)：

沟通风格数据：
{communication_style_data}

请返回以下格式的JSON：
{{
    "openness": 0.0-1.0,  // 开放性
    "conscientiousness": 0.0-1.0,  // 尽责性  
    "extraversion": 0.0-1.0,  // 外向性
    "agreeableness": 0.0-1.0,  // 宜人性
    "neuroticism": 0.0-1.0  // 神经质
}}
"""

# factory.py 中 MessageFilter 的 prompt
MESSAGE_FILTER_SUITABLE_FOR_LEARNING_PROMPT = """
请判断以下消息是否与当前人格匹配，特征鲜明，且具有学习意义。
当前人格描述: {current_persona}
消息内容: "{message}"

请以 JSON 格式返回判断结果，包含 'suitable' (布尔值) 和 'confidence' (0.0-1.0 之间的浮点数)。
例如: {{"suitable": true, "confidence": 0.9}}
"""

# intelligent_responder.py 中的 prompt
INTELLIGENT_RESPONDER_DEFAULT_PERSONA_PROMPT = """

"""

# learning_quality_monitor.py 中缺失的 prompt
LEARNING_QUALITY_MONITOR_EMOTIONAL_BALANCE_PROMPT = """
请分析以下学习批次中消息的情感平衡性。评估消息集合在情感维度上是否多样化和平衡。

消息批次数据：
{batch_messages}

请从以下维度分析：
1. 情感多样性 - 包含多种情感表达（积极、消极、中性）
2. 情感强度分布 - 强烈情感与温和情感的平衡
3. 情感稳定性 - 情感表达是否合理稳定
4. 学习价值 - 这种情感平衡对人格学习是否有价值

请以JSON格式返回分析结果：
{{
    "emotional_diversity": 0.0-1.0,  // 情感多样性得分
    "intensity_balance": 0.0-1.0,    // 强度平衡得分
    "emotional_stability": 0.0-1.0,   // 情感稳定性得分
    "learning_value": 0.0-1.0,       // 学习价值得分
    "overall_balance": 0.0-1.0,      // 总体情感平衡得分
    "analysis_summary": "分析总结"
}}
"""

LEARNING_QUALITY_MONITOR_CONSISTENCY_PROMPT = """
请分析以下两个人格描述之间的一致性程度，评估人格更新前后的连贯性和兼容性。

原始人格描述：
{original_persona_prompt}

更新后人格描述：
{updated_persona_prompt}

请从以下维度评估一致性：
1. 核心价值观和性格特征是否保持
2. 语言风格和表达习惯是否延续
3. 兴趣爱好和知识领域是否兼容
4. 行为模式和互动方式是否协调
5. 整体人格形象是否和谐统一

请返回一个0-1之间的一致性得分，0表示完全不一致，1表示完全一致。
只返回数值，不需要其他解释。
"""

# progressive_learning.py 中的 prompt
PROGRESSIVE_LEARNING_GENERATE_UPDATED_PERSONA_PROMPT = """
基于当前人格和风格分析结果，生成更新后的人格描述。

当前人格信息：
{current_persona_json}

风格分析结果：
{style_analysis_json}

请根据风格分析结果对人格进行渐进式更新，确保：
1. 保持核心人格特征不变
2. 根据风格分析适当调整表达方式
3. 增强与分析结果匹配的特征
4. 保持整体人格的一致性和连贯性

请以JSON格式返回更新后的完整人格信息：
{{
    "name": "更新后的人格名称",
    "prompt": "更新后的完整人格描述",
    "begin_dialogs": [],
    "mood_imitation_dialogs": []
}}
"""

# MaiBot风格的高级对话prompt - 基于MaiBot的replyer_prompt设计
MAIBOT_STYLE_CHAT_PROMPT = """
{knowledge_context}
{expression_patterns_block}
{memory_context}

你正在qq群里聊天，下面是群里正在聊的内容:
{time_block}
{background_dialogue_prompt}
{core_dialogue_prompt}

{reply_target_block}。
{identity}
你正在群里聊天,现在请你读读之前的聊天记录，然后给出日常且口语化的回复，平淡一些，
尽量简短一些。{keywords_reaction_prompt}请注意把握聊天内容，不要回复的太有条理，可以有个性。
{reply_style}
请注意不要输出多余内容(包括前后缀，冒号和引号，括号，表情等)，只输出回复内容。
{moderation_prompt}不要输出多余内容(包括前后缀，冒号和引号，括号，表情包，at或 @等 )。
"""

# MaiBot风格的私聊prompt
MAIBOT_STYLE_PRIVATE_CHAT_PROMPT = """
{knowledge_context}
{expression_patterns_block}
{memory_context}

你正在和{sender_name}聊天，这是你们之前聊的内容:
{time_block}
{dialogue_prompt}

{reply_target_block}。
{identity}
你正在和{sender_name}聊天,现在请你读读之前的聊天记录，然后给出日常且口语化的回复，平淡一些，
尽量简短一些。{keywords_reaction_prompt}请注意把握聊天内容，不要回复的太有条理，可以有个性。
{reply_style}
请注意不要输出多余内容(包括前后缀，冒号和引号，括号，表情等)，只输出回复内容。
{moderation_prompt}不要输出多余内容(包括前后缀，冒号和引号，括号，表情包，at或 @等 )。
"""

# 表达模式学习prompt - 完全采用MaiBot的设计
EXPRESSION_PATTERN_LEARNING_PROMPT = """
{chat_content}

请从上面这段群聊中概括除了人名为"SELF"之外的人的语言风格
1. 只考虑文字，不要考虑表情包和图片  
2. 不要涉及具体的人名，但是可以涉及具体名词
3. 思考有没有特殊的梗，一并总结成语言风格
4. 例子仅供参考，请严格根据群聊内容总结!!!

注意：总结成如下格式的规律，总结的内容要详细，但具有概括性：
例如：当"AAAAA"时，可以"BBBBB", AAAAA代表某个具体的场景，不超过20个字。BBBBB代表对应的语言风格，特定句式或表达方式，不超过20个字。

例如：
当"对某件事表示十分惊叹"时，使用"我嘞个xxxx"
当"表示讽刺的赞同，不讲道理"时，使用"对对对"  
当"想说明某个具体的事实观点，但懒得明说"时，使用"懂的都懂"
当"涉及游戏相关时，夸赞，略带戏谑意味"时，使用"这么强！"

请注意：不要总结你自己（SELF）的发言，尽量保证总结内容的逻辑性
现在请你概括
"""

# 记忆整合prompt - 基于MaiBot的记忆融合机制
MEMORY_INTEGRATION_PROMPT = """
请将以下两段记忆智能融合为一段连贯、简洁的描述：

旧记忆：{old_memory}
新记忆：{new_memory}

要求：
1. 保留两段记忆中的重要信息
2. 去除重复和冗余内容
3. 形成逻辑清晰的统一描述
4. 如果存在矛盾，优先保留新记忆的信息
5. 保持描述的简洁性，避免过度冗长

请直接返回融合后的记忆描述，不需要额外说明。
"""

# 实体提取prompt - 采用MaiBot的知识图谱设计
ENTITY_EXTRACTION_PROMPT = """
你是一个性能优异的实体提取系统。请从段落中提取出所有实体，并以JSON列表的形式输出。

输出格式示例：
[ "实体A", "实体B", "实体C" ]

请注意以下要求：
- 将代词（如"你"、"我"、"他"、"她"、"它"等）转化为对应的实体命名，以避免指代不清。
- 尽可能多的提取出段落中的全部实体；

段落：
```
{text}
```
"""

# RDF三元组提取prompt - 采用MaiBot的关系提取设计
RDF_TRIPLE_EXTRACTION_PROMPT = """
你是一个性能优异的RDF（资源描述框架，由节点和边组成，节点表示实体/资源、属性，边则表示了实体和实体之间的关系以及实体和属性的关系。）构造系统。你的任务是根据给定的段落和实体列表构建RDF图。

请使用JSON回复，使用三元组的JSON列表输出RDF图中的关系（每个三元组代表一个关系）。

输出格式示例：
[
        ["某实体","关系","某属性"],
        ["某实体","关系","某实体"],
        ["某资源","关系","某属性"]
]

请注意以下要求：
- 每个三元组应包含每个段落的实体命名列表中的至少一个命名实体，但最好是两个。
- 将代词（如"你"、"我"、"他"、"她"、"它"等）转化为对应的实体命名，以避免指代不清。

段落：
```
{text}
```

实体列表：
```
{entities}
```
"""

# 知识图谱QA prompt - 采用MaiBot的QA系统设计
KNOWLEDGE_GRAPH_QA_PROMPT = """
你是一个性能优异的QA系统。请根据给定的问题和一些可能对你有帮助的信息作出回答。

请注意以下要求：
- 你可以使用给定的信息来回答问题，但请不要直接引用它们。
- 你的回答应该简洁明了，避免冗长的解释。
- 如果你无法回答问题，请直接说"我不知道"。

问题：
{question}

可能有帮助的信息：
{knowledge_context}
"""

# 新增强化模型专用提示词
REINFORCEMENT_LEARNING_MEMORY_REPLAY_PROMPT = """
你是一个强化学习专家，负责通过记忆重放机制来优化人格学习效果。

历史学习数据：
{historical_learning_data}

新的学习数据：
{new_learning_data}

当前人格状态：
{current_persona}

请执行记忆重放分析：
1. 分析历史数据中的成功学习模式
2. 识别新数据与历史数据的关联性
3. 评估学习策略的有效性
4. 提供优化建议

请以JSON格式返回强化学习分析结果：
{{
    "replay_analysis": {{
        "historical_patterns": ["识别到的历史学习模式"],
        "correlation_strength": 0.0,
        "learning_effectiveness": 0.0
    }},
    "optimization_strategy": {{
        "priority_features": ["需要重点学习的特征"],
        "learning_weight": 0.0,
        "confidence_threshold": 0.0
    }},
    "reinforcement_feedback": {{
        "positive_signals": ["积极的学习信号"],
        "negative_signals": ["需要调整的方面"],
        "reward_score": 0.0
    }},
    "next_action": "建议的下一步行动"
}}
"""

REINFORCEMENT_LEARNING_INCREMENTAL_TUNING_PROMPT = """
你是一个增量学习专家，负责将新的人格特征与现有人格进行智能融合。

基础人格：
{base_persona}

增量更新数据：
{incremental_updates}

融合历史：
{fusion_history}

请执行增量微调分析：
1. 评估新特征与基础人格的兼容性
2. 计算最优的融合比例
3. 预测融合后的人格表现
4. 提供风险控制建议

**重要提示：在生成key_changes时，必须使用口语化、命令式的直白指令。**
**不要使用"强化xxx"、"优化xxx"、"重新xxx"这类机械化的学术性表述！**
**要使用"你应该xxx"、"要xxx"、"记得xxx"、"多用xxx"、"少说xxx"这类直接告诉LLM该怎么做的命令！**

示例（错误）：
- "强化幽默与毒舌语言表达的灵活性与协调性"  ❌
- "优化与陌生用户交流方式，保持坦率直接但降低机械感"  ❌

示例（正确）：
- "你要多用重庆方言和网络梗,说话带点毒舌和幽默感"  ✅
- "和陌生人聊天时要坦率直接,但别太机械,要自然点"  ✅
- "讨论技术问题时记得保持专业,但也要有点趣味性"  ✅

请以JSON格式返回增量微调结果：
{{
    "compatibility_analysis": {{
        "feature_compatibility": 0.0,
        "style_consistency": 0.0,
        "personality_coherence": 0.0
    }},
    "fusion_strategy": {{
        "base_weight": 0.0,
        "increment_weight": 0.0,
        "fusion_method": "fusion_method_name",
        "adaptation_rate": 0.0
    }},
    "performance_prediction": {{
        "expected_improvement": 0.0,
        "potential_risks": ["风险评估列表"],
        "confidence_level": 0.0
    }},
    "updated_persona": {{
        "name": "融合后的人格名称",
        "prompt": "融合后的完整人格描述",
        "key_changes": ["主要变化说明"]
    }}
}}
"""

REINFORCEMENT_LEARNING_STRATEGY_OPTIMIZATION_PROMPT = """
你是一个学习策略优化专家，负责根据历史表现数据动态调整学习策略。

学习历史数据：
{learning_history}

当前策略参数：
{current_strategy}

性能指标：
{performance_metrics}

请执行策略优化分析：
1. 分析当前策略的优势和不足
2. 识别最有效的学习模式
3. 提出参数调优建议
4. 预测优化后的效果

请以JSON格式返回策略优化结果：
{{
    "strategy_analysis": {{
        "current_effectiveness": 0.0,
        "bottleneck_factors": ["限制因素"],
        "success_patterns": ["成功模式"]
    }},
    "optimization_recommendations": {{
        "learning_rate_adjustment": 0.0,
        "batch_size_optimization": 0,
        "threshold_tuning": {{
            "confidence_threshold": 0.0,
            "quality_threshold": 0.0,
            "relevance_threshold": 0.0
        }}
    }},
    "expected_improvements": {{
        "learning_speed": 0.0,
        "quality_enhancement": 0.0,
        "stability_improvement": 0.0
    }},
    "implementation_plan": {{
        "immediate_actions": ["立即执行的优化"],
        "gradual_adjustments": ["渐进式调整"],
        "monitoring_metrics": ["需要监控的指标"]
    }}
}}
"""
