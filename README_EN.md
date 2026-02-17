<div align="center">

**English** | **[中文](README.md)**

<br>

<img src="logo.png" alt="Self-Learning Logo" width="180"/>

<br>

# AstrBot Self-Learning Plugin

**Make your AI chatbot learn, think, and converse like a real person**

<br>

[![Version](https://img.shields.io/badge/version-Next--1.1.9-blue.svg)](https://github.com/NickCharlie/astrbot_plugin_self_learning) [![License](https://img.shields.io/badge/license-GPLv3-green.svg)](LICENSE) [![AstrBot](https://img.shields.io/badge/AstrBot-%3E%3D4.11.4-orange.svg)](https://github.com/Soulter/AstrBot) [![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)

[Features](#-key-features) · [Quick Start](#-quick-start) · [Architecture](#-technical-architecture) · [Documentation](#-documentation) · [Contributing](#-contributing)

</div>

<br>

> [!WARNING]
> **Please manually back up your persona files before use, in case bugs cause persona corruption.**

<details>
<summary><strong>⚖️ Disclaimer & User Agreement (click to expand)</strong></summary>

<br>

**By using this project, you acknowledge that you have read, understood, and agreed to the following terms:**

1. **Lawful Use Commitment**
   - This project is intended solely for learning, research, and lawful purposes
   - **It is strictly prohibited to use this project directly or indirectly for any purpose that violates applicable laws and regulations**
   - Including but not limited to: privacy invasion, illegal data collection, malicious information dissemination, violation of platform terms of service, etc.

2. **Privacy Protection Responsibilities**
   - Users must comply with applicable privacy and data protection laws in their jurisdiction
   - Explicit user consent must be obtained before collecting and processing message data
   - Collected data must not be used for commercial purposes or disclosed to third parties
   - It is recommended to use only in private environments or groups where all participants have given consent

3. **Risk Disclaimer**
   - This project is provided "AS IS" without any express or implied warranties
   - The developer is not responsible for any direct or indirect damages caused by using this project
   - Users assume all risks including data loss, persona corruption, and system crashes
   - **Thorough testing before production use is strongly recommended**

4. **Developer Disclaimer**
   - The developer bears no responsibility for users' illegal or non-compliant usage
   - Users bear full responsibility for any legal disputes arising from misuse
   - The developer reserves the right to modify or discontinue this project at any time

5. **Agreement Changes**
   - This agreement may be updated at any time without prior notice
   - Continued use of this project constitutes acceptance of updated terms

**📌 Important: By downloading, installing, or using any functionality of this project, you are deemed to have fully understood and agreed to comply with all of the above terms. If you do not agree, please immediately stop using and delete this project.**

</details>

---

## 🌟 Project Overview

The AstrBot Self-Learning Plugin is a full-featured AI self-learning and conversational humanization solution. Through real-time message capture, multi-dimensional data analysis, expression pattern learning, dynamic persona optimization, and goal-driven conversation, it enables chatbots to:

- 📖 **Learn specific users' conversation styles** - Automatically mimic target users' expression patterns
- 🎯 **Intelligent slang understanding system** - Automatically learn group-specific jargon to avoid misunderstandings
- ❤️ **Manage social relationships and affection** - Track user interactions and dynamically adjust response strategies
- 🎭 **Adaptive persona evolution** - Intelligently update AI persona settings based on learning outcomes
- 🎯 **Goal-driven conversation guidance** - Detect conversation goals and progressively advance dialogue
- 🌐 **Visual management interface** - Monitor learning progress and results through WebUI in real time


### Community
- QQ Group: **1021544792**
  (ChatPlus plugin users + Self-Learning plugin users)
- Bug reports and usage questions

### 🤝 Recommended Companion

**[Group Chat Plus Plugin](https://github.com/Him666233/astrbot_plugin_group_chat_plus)**

The two plugins complement each other:
- This plugin handles **AI learning and persona optimization**
- Group Chat Plus handles **intelligent reply decisions and social awareness**

Using both together gives your bot both learning ability and social intelligence!

---

## 💡 Key Features

### 🎯 Intelligent Learning System

#### 1. Expression Pattern Learning
```
Scene → Expression Pattern Mapping
"When expressing agreement" → "Use expressions like 'That's definitely true'"
```
- Automatically identify scene-expression relationships in conversations
- 15-day time decay mechanism, prioritizing high-quality patterns
- Few-Shot dialogue example generation for improved mimicry accuracy

#### 2. Memory Graph System
- Knowledge association network built on NetworkX
- Automatic entity and relationship extraction for long-term memory
- Supports memory retrieval and knowledge reasoning

#### 3. Social Relationship Analysis
- Real-time tracking of user interaction relationships
- Visual social network graph
- Affection system (per-user cap: 100 points, total cap: 250 points)
- Dynamic mood management (10 mood types)

#### 4. Slang Mining & Understanding
```python
# Automatically learn group-specific jargon
"jackpot" → "Expressing surprise or gaining benefits"
"next time for sure" → "Polite refusal expression"
"🦌" → "xxxxx"
```
- Automatic candidate slang detection
- LLM-powered meaning inference
- Real-time injection into conversation understanding

#### 5. Goal-Driven Conversation System 🎯
```python
# Automatically detect conversation goals and dynamically plan stages
User: "I've been so stressed at work lately..."
Bot: Detect goal → emotional_support
     Plan stages → ["Listen", "Identify core issue", "Express understanding", "Offer advice", "Encourage"]
     Current stage → "Listen"
```
- **38 preset goal types** - Covering emotional support, information exchange, entertainment, social scenarios, conflict handling, etc.
- **Intelligent goal detection** - LLM automatically analyzes user intent and identifies conversation goals
- **Dynamic stage planning** - LLM generates progressive conversation stages based on goal type and topic
- **Session-level management** - 24-hour session isolation with automatic progress and engagement tracking
- **Goal switching support** - Detects topic completion and automatically switches to new goals
- **Context injection** - Injects goal state into LLM prompt to guide response strategy

### 🏗️ Architecture Features

#### Factory Pattern
```python
# Unified service creation and management
factory_manager = FactoryManager()
factory_manager.initialize_factories(config, context)

# Service factory
service_factory = factory_manager.get_service_factory()
db_manager = service_factory.create_database_manager()

# Component factory
component_factory = factory_manager.get_component_factory()
expression_learner = component_factory.create_expression_pattern_learner()
```

#### Strategy Pattern
```python
# Flexible learning strategies
learning_strategy = StrategyFactory.create_strategy(
    LearningStrategyType.BATCH,  # INCREMENTAL / REINFORCEMENT
    config={'batch_size': 100}
)
```

#### Dependency Injection
```python
# Loose coupling between services
class MultidimensionalAnalyzer:
    def __init__(self, config, db_manager, llm_adapter, ...):
        self.config = config
        self.db = db_manager
        self.llm = llm_adapter
```

#### Repository Pattern
```python
# Data access layer abstraction
affection_repo = AffectionRepository(session)
user_affection = await affection_repo.get_user_affection(group_id, user_id)
```

### 🗄️ Multi-Database Support

```yaml
Database_Settings:
  db_type: "mysql"  # sqlite / mysql / postgresql (PostgreSQL not yet available)

  # MySQL Configuration
  mysql_host: "localhost"
  mysql_port: 3306
  mysql_user: "root"
  mysql_password: "your_password"
  mysql_database: "astrbot_self_learning"

  # Automatic connection pool management
  max_connections: 10
  min_connections: 2
```

Supported databases:
- **SQLite** - Works out of the box, suitable for single-machine deployment
- **MySQL** - High performance, suitable for production environments
- **PostgreSQL** - Enterprise-grade, supports advanced features

### 📊 Data Visualization

#### WebUI Management Interface (Port: 7833)

**1. Statistics Dashboard**
![Statistics Dashboard](https://github.com/NickCharlie/astrbot_plugin_self_learning/blob/develop/image/%E6%95%B0%E6%8D%AE%E7%BB%9F%E8%AE%A1%E9%A1%B5%E9%9D%A2.png?raw=true)
- Message collection statistics, learning progress tracking
- System runtime status, database usage

**2. Persona Management**
![Persona Management](https://github.com/NickCharlie/astrbot_plugin_self_learning/blob/develop/image/%E4%BA%BA%E6%A0%BC%E7%AE%A1%E7%90%86%E9%A1%B5%E9%9D%A2.png?raw=true)
- View persona list, one-click switching
- Persona editing, backup and recovery
- Automatic protection of active persona

**3. Persona Review**
![Persona Review](https://github.com/NickCharlie/astrbot_plugin_self_learning/blob/develop/image/%E4%BA%BA%E6%A0%BC%E5%AE%A1%E6%9F%A5%E9%A1%B5%E9%9D%A2.png?raw=true)
- Review AI-generated persona update suggestions
- Side-by-side comparison of original and proposed changes
- Approve or reject updates with manual quality control

**4. Style Learning**
![Style Learning](https://github.com/NickCharlie/astrbot_plugin_self_learning/blob/develop/image/%E5%AF%B9%E8%AF%9D%E9%A3%8E%E6%A0%BC%E5%AD%A6%E4%B9%A0%E9%A1%B5%E9%9D%A2.png?raw=true)
- Learning progress visualization charts
- Scene-expression pattern mapping display
- Quality scoring and time decay management

**5. Social Relationship Analysis**
![Social Relationships](https://github.com/NickCharlie/astrbot_plugin_self_learning/blob/develop/image/%E7%A4%BE%E4%BA%A4%E5%85%B3%E7%B3%BB%E9%A1%B5%E9%9D%A2.png?raw=true)
- Force-directed graph showing member interactions
- Node size represents activity level
- Edge thickness represents interaction frequency
- Color represents affection level

**6. System Settings**
![Settings](https://github.com/NickCharlie/astrbot_plugin_self_learning/blob/develop/image/%E9%85%8D%E7%BD%AE%E9%A1%B5%E9%9D%A2.png?raw=true)
- Learning parameter configuration
- Model configuration management
- Affection and mood system toggles
- Data management and debug mode

**7. Intelligent Conversation Management**
- Goal-driven conversation system management
- View users' current conversation goals and progress
- Clear session goals, reset conversation state
- Goal statistics and analysis
- Query 38 supported goal types

---

## 🚀 Quick Start

### Prerequisites

```bash
# Python version requirement
Python 3.8+

# Install dependencies
pip install -r requirements.txt
```

### Installation

1. **Add the plugin to the AstrBot plugin directory**
   ```bash
   cd /path/to/astrbot/data/plugins
   git clone https://github.com/NickCharlie/astrbot_plugin_self_learning.git
   ```

2. **Start AstrBot**
   - The plugin will automatically load and initialize

3. **Access the WebUI management interface**
   ```
   http://localhost:7833
   ```
   - Default password: `self_learning_pwd`
   - **⚠️ Change the password immediately after first login!**

4. **Configure the plugin**
   - Set configuration items in the AstrBot admin panel
   - Or configure via the WebUI settings page

### Basic Configuration Example

```yaml
# Basic switches
Self_Learning_Basic:
  enable_message_capture: true
  enable_auto_learning: true
  enable_realtime_learning: false
  enable_web_interface: true
  web_interface_port: 7833

# Target settings
Target_Settings:
  target_qq_list: []  # Empty = learn from all users
  current_persona_name: "default"

# Model configuration
Model_Configuration:
  filter_provider_id: "provider_id_1"  # Filter model
  refine_provider_id: "provider_id_2"  # Refinement model

# Learning parameters
Learning_Parameters:
  learning_interval_hours: 6
  min_messages_for_learning: 50
  max_messages_per_batch: 200

# Database configuration
Database_Settings:
  db_type: "sqlite"  # or mysql / postgresql
```

---

## 🏛️ Technical Architecture

### Project Structure

```
astrbot_plugin_self_learning/
├── core/                          # Core architecture layer
│   ├── factory.py                # Factory manager (DI container)
│   ├── interfaces.py             # Interface definitions (abstract base classes)
│   ├── patterns.py               # Design pattern implementations (strategy, observer, etc.)
│   ├── framework_llm_adapter.py  # LLM framework adapter
│   └── database/                 # Database abstraction layer
│       ├── backend_interface.py  # Database interface
│       ├── sqlite_backend.py     # SQLite implementation
│       ├── mysql_backend.py      # MySQL implementation
│       └── postgresql_backend.py # PostgreSQL implementation
│
├── services/                      # Service layer (business logic)
│   ├── message_collector.py      # Message collection service
│   ├── multidimensional_analyzer.py  # Multi-dimensional analysis
│   ├── style_analyzer.py         # Style analysis service
│   ├── progressive_learning.py   # Progressive learning service
│   ├── persona_manager.py        # Persona management service
│   ├── expression_pattern_learner.py  # Expression pattern learner
│   ├── affection_manager.py      # Affection management service
│   ├── jargon_miner.py          # Slang mining service
│   ├── jargon_query.py          # Slang query service
│   ├── social_context_injector.py  # Social context injector
│   └── response_diversity_manager.py  # Response diversity manager
│
├── models/                        # Data model layer
│   └── orm/                      # ORM models (SQLAlchemy)
│       ├── base.py               # Base model
│       ├── expression.py         # Expression pattern model
│       ├── affection.py          # Affection model
│       ├── learning.py           # Learning record model
│       └── social_relation.py    # Social relationship model
│
├── repositories/                  # Repository layer (data access)
│   ├── base_repository.py        # Base repository
│   ├── expression_repository.py  # Expression pattern repository
│   ├── affection_repository.py   # Affection repository
│   └── social_repository.py      # Social relationship repository
│
├── webui/                         # Web interface
│   ├── app.py                    # Quart application entry point
│   └── blueprints/               # Route blueprints
│       ├── auth.py               # Authentication routes
│       ├── persona.py            # Persona management routes
│       └── analytics.py          # Data analytics routes
│
├── utils/                         # Utilities
│   ├── cache_manager.py          # Cache management
│   └── security_utils.py         # Security utilities
│
├── config.py                      # Configuration management
├── main.py                        # Plugin entry point
└── README.md                      # Project documentation
```

### Core Design Patterns

#### 1. Factory Pattern

**Purpose**: Unified service creation management to reduce coupling

```python
class FactoryManager:
    """Global factory manager - Singleton pattern"""

    def initialize_factories(self, config, context):
        self._service_factory = ServiceFactory(config, context)
        self._component_factory = ComponentFactory(config, self._service_factory)

    def get_service_factory(self) -> ServiceFactory:
        # Service factory: creates business services (database, learning, analysis, etc.)
        return self._service_factory

    def get_component_factory(self) -> ComponentFactory:
        # Component factory: creates lightweight components (filters, schedulers, etc.)
        return self._component_factory
```

**Benefits**:
- Centralized service instance management, avoiding circular dependencies
- Service caching and singleton pattern for improved performance
- Supports service registration and dependency injection

#### 2. Strategy Pattern

**Purpose**: Flexible learning strategy switching

```python
class StrategyFactory:
    @staticmethod
    def create_strategy(strategy_type: LearningStrategyType, config: dict):
        strategies = {
            LearningStrategyType.BATCH: BatchLearningStrategy,
            LearningStrategyType.INCREMENTAL: IncrementalLearningStrategy,
            LearningStrategyType.REINFORCEMENT: ReinforcementLearningStrategy
        }
        return strategies[strategy_type](config)
```

**Learning Strategy Types**:
- **Batch Learning** - Periodically batch-process messages
- **Incremental Learning** - Real-time per-message learning
- **Reinforcement Learning** - Feedback-based optimization

#### 3. Repository Pattern

**Purpose**: Abstract data access layer, supporting multiple databases

```python
class BaseRepository:
    """Base repository - provides common CRUD operations"""

    async def get(self, id: int):
        async with self.session() as session:
            return await session.get(self.model, id)

    async def save(self, entity):
        async with self.session() as session:
            session.add(entity)
            await session.commit()

class ExpressionRepository(BaseRepository):
    """Expression pattern repository - handles expression pattern data"""

    async def get_patterns_by_group(self, group_id: str, limit: int = 10):
        # Specific business logic
        ...
```

#### 4. Observer Pattern

**Purpose**: Event-driven architecture for component decoupling

```python
class EventBus:
    """Event bus - Publish/Subscribe pattern"""

    def subscribe(self, event_type: str, handler: Callable):
        self._handlers[event_type].append(handler)

    async def publish(self, event_type: str, data: Any):
        for handler in self._handlers[event_type]:
            await handler(data)

# Usage example
event_bus.subscribe("learning_completed", on_learning_completed)
await event_bus.publish("learning_completed", learning_result)
```

### Data Flow Architecture

```
┌─────────────────┐
│  Message Layer   │  on_message() - Listen to all messages
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Filter Layer    │  QQFilter + MessageFilter
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Collection Layer│  MessageCollector - Store raw messages
└────────┬────────┘
         │
         ├──────────────────┐
         │                  │
         ▼                  ▼
┌─────────────────┐  ┌─────────────────┐
│  Analysis Layer  │  │  Learning Layer  │
│  - Multi-dim     │  │  - Expression    │
│  - Style         │  │  - Slang mining  │
│  - Social        │  │  - Memory graph  │
└────────┬────────┘  └────────┬────────┘
         │                    │
         └──────────┬─────────┘
                    ▼
         ┌─────────────────┐
         │  Persona Update  │
         │  - PersonaUpdater│
         │  - Review system │
         └────────┬────────┘
                  │
                  ▼
         ┌─────────────────┐
         │  LLM Injection   │  inject_diversity_to_llm_request()
         │  - Expression     │
         │  - Social context │
         │  - Slang meaning  │
         │  - Diversity      │
         └─────────────────┘
```

---

## 📖 Detailed Feature Descriptions

### Expression Pattern Learning System

**How It Works**:

1. **Message Collection** - Triggers learning every 10-25 collected messages
2. **Scene Recognition** - Uses LLM to analyze conversation scenes and context
3. **Expression Extraction** - Extracts target user's specific expression patterns
4. **Pattern Storage** - Saves "scene → expression" mappings
5. **Time Decay** - 15-day decay cycle, quality score decreases over time
6. **Prompt Injection** - Injects high-quality patterns into LLM requests

**Example**:
```
Scene: "User needs to express agreement"
Expression: "That's definitely how it is"
Quality Score: 0.85
Created: 2025-11-20
Score after decay: 0.78 (5 days later)
```

### Slang Mining System

**Workflow**:

```python
# 1. Extract candidates
candidates = await jargon_miner.extract_candidates(recent_messages)
# Output: ["jackpot", "next time for sure", "so good"]

# 2. LLM infers meanings
meanings = await jargon_miner.infer_meanings(candidates, context)
# Output: {
#   "jackpot": "Expressing surprise or gaining benefits",
#   "next time for sure": "Polite refusal expression"
# }

# 3. Save to database
await db.save_jargon_batch(chat_id, meanings)

# 4. Inject understanding during LLM requests
jargon_explanation = await jargon_query.check_and_explain_jargon(
    text="What a jackpot today!",
    chat_id=group_id
)
# Injected into LLM prompt: "Slang in text: 'jackpot': Expressing surprise or gaining benefits"
```

**Features**:
- Automatic detection of high-frequency and new terms
- Context-aware meaning inference
- 60-second TTL cache for improved performance
- Real-time LLM injection to avoid misunderstandings

### Goal-Driven Conversation System

**How It Works**:

1. **Session Initialization** - Automatically creates a 24-hour session when user sends a message
2. **Goal Detection** - Uses LLM to analyze user intent and identify conversation goal type
3. **Stage Planning** - LLM generates 3-5 conversation stages based on goal and topic
4. **Dynamic Adjustment** - Real-time conversation progress analysis, automatic stage advancement
5. **Goal Switching** - Detects topic completion, switches to new goal type
6. **Context Injection** - Injects goal state into LLM prompt to guide response strategy

**38 Preset Goal Types**:

```python
# Emotional Support (5 types)
comfort           # Comfort the user
emotional_support # Emotional support
empathy          # Deep empathy
encouragement    # Encouragement
calm_down        # Emotional soothing

# Information Exchange (5 types)
qa               # Q&A
guide_share      # Guide sharing
teach            # Teaching
discuss          # In-depth discussion
storytelling     # Storytelling

# Entertainment (6 types)
casual_chat      # Casual chat
tease            # Friendly teasing
flirt            # Playful flirting
joke             # Humor
meme             # Meme culture interaction
roleplay         # Role-playing

# Social Interaction (5 types)
greeting         # Greeting
compliment       # Compliment
celebrate        # Celebration
apologize        # Apology
gossip           # Gossip

# Advice & Guidance (4 types)
advise           # Give advice
brainstorm       # Brainstorming
plan             # Planning
analyze          # Problem analysis

# Mood Regulation (3 types)
vent             # Listen to venting
motivate         # Motivate
complaint        # Complaints

# Interest Sharing (3 types)
recommend        # Recommend & share
review           # Review & evaluate
hobby_chat       # Hobby discussion

# Special Scenarios (3 types)
debate           # Friendly debate
confess          # Confide secrets
nostalgia        # Nostalgia

# Conflict Scenarios (4 types)
argument         # Heated argument
quarrel          # Quarrel
insult_exchange  # Verbal sparring
provoke          # Provocation response
```

**Session Management**:

```python
# Session ID generation (unchanged for 24 hours)
session_id = MD5(group_id + user_id + date)

# Session data structure
{
  "session_id": "sess_a1b2c3d4e5f6",
  "final_goal": {
    "type": "emotional_support",
    "name": "Emotional Support",
    "topic": "Work stress",
    "topic_status": "active"
  },
  "current_stage": {
    "index": 2,
    "task": "Identify core issue",
    "strategy": "Sequential progression",
    "adjustment_reason": "Previous stage completed"
  },
  "planned_stages": [
    "Listen", "Identify core issue", "Express understanding",
    "Offer advice", "Encourage"
  ],
  "metrics": {
    "rounds": 5,
    "user_engagement": 0.8,
    "goal_progress": 0.4
  },
  "conversation_history": [...]
}
```

**WebUI API Endpoints**:

```bash
# 1. Chat with goal guidance
POST /api/intelligent_chat/chat
{
  "user_id": "10001",
  "message": "I've been so stressed at work lately...",
  "group_id": "123456",
  "force_normal_mode": false
}

# 2. Get user's current goal status
GET /api/intelligent_chat/goal/status?user_id=10001&group_id=123456

# 3. Clear user's current goal
DELETE /api/intelligent_chat/goal/clear
{
  "user_id": "10001",
  "group_id": "123456"
}

# 4. Get goal statistics
GET /api/intelligent_chat/goal/statistics

# 5. Get all available goal types
GET /api/intelligent_chat/goal/templates
```

**Features**:
- 38 preset goal types covering everyday conversation scenarios
- LLM-powered intelligent detection for automatic user intent recognition
- Dynamic stage planning with progressive conversation advancement
- Session-level isolation supporting multi-user concurrency
- Goal switching mechanism adapting to topic changes
- Complete REST API for easy integration

### Social Relationship Analysis

**Relationship Tracking**:
```python
# Automatically record user interactions
await social_relation_manager.record_interaction(
    group_id="123456",
    user_a="10001",
    user_b="10002",
    interaction_type="mention"  # at / reply / topic_discussion
)

# Analyze relationship strength
strength = await social_relation_manager.calculate_relationship_strength(
    group_id, user_a, user_b
)
# Output: 0.75 (based on interaction frequency, type, and time decay)
```

**Affection Management**:
```python
# Process user message interactions
result = await affection_manager.process_message_interaction(
    group_id, user_id, message_text
)

# Automatic interaction type recognition
interaction_types = {
    "praise": +10,      # Praise
    "encourage": +5,    # Encouragement
    "insult": -15,      # Insult
    "harass": -20       # Harassment
}

# Affection limits
- Per-user cap: 100 points
- Group total cap: 250 points
- Automatic decay of old affection when over limit
```

### Persona Update Mechanism

**Update Mode**:

#### PersonaManager Mode (Recommended)
```python
# Incremental update appended to original persona
await persona_manager_updater.apply_incremental_update(
    group_id=group_id,
    update_content="[Learning Outcomes]\nNew expression patterns: ..."
)

# Advantages:
# - Automatic backup persona creation
# - No manual apply command needed
# - Better version management
```

**Persona Review Workflow**:
```
1. AI generates update suggestion → Saved to style_learning_reviews table
2. Admin logs into WebUI → Persona review page
3. View comparison (original vs suggestion) → Red highlights for changes
4. Decision: Approve / Reject
5. Approved changes automatically applied to persona
```

---

## 📋 Command Reference

| Command | Permission | Description |
|---------|-----------|-------------|
| `/learning_status` | Admin | View learning status and statistics |
| `/start_learning` | Admin | Manually start a learning batch |
| `/stop_learning` | Admin | Stop the automatic learning loop |
| `/force_learning` | Admin | Force execute one learning cycle |
| `/affection_status` | Admin | View affection status and leaderboard |
| `/set_mood <type>` | Admin | Set bot mood state |

**Mood Types**: `happy` `sad` `excited` `calm` `angry` `anxious` `playful` `serious` `nostalgic` `curious`

---

## 🔧 Configuration Reference

### Complete Configuration Example

```yaml
# ========================================
# Basic Switches
# ========================================
Self_Learning_Basic:
  enable_message_capture: true      # Enable message capture
  enable_auto_learning: true        # Enable scheduled auto-learning
  enable_realtime_learning: false   # Enable real-time learning (per message)
  enable_web_interface: true        # Enable web management interface
  web_interface_port: 7833          # Web interface port

# ========================================
# Target Settings
# ========================================
Target_Settings:
  target_qq_list: []                # Target QQ ID list (empty = all)
  target_blacklist: []              # Learning blacklist
  current_persona_name: "default"   # Current persona name

# ========================================
# Model Configuration (AstrBot Provider)
# ========================================
Model_Configuration:
  filter_provider_id: "provider_gpt4o_mini"  # Filter model (weak model)
  refine_provider_id: "provider_gpt4o"       # Refinement model (strong model)
  reinforce_provider_id: "provider_gpt4o"    # Reinforcement model

# ========================================
# Learning Parameters
# ========================================
Learning_Parameters:
  learning_interval_hours: 6        # Auto-learning interval (hours)
  min_messages_for_learning: 50     # Minimum messages before learning starts
  max_messages_per_batch: 200       # Maximum messages per batch

# ========================================
# Filter Parameters
# ========================================
Filter_Parameters:
  message_min_length: 5             # Minimum message length
  message_max_length: 500           # Maximum message length
  confidence_threshold: 0.7         # Filter confidence threshold
  relevance_threshold: 0.6          # Relevance threshold

# ========================================
# Style Analysis
# ========================================
Style_Analysis:
  style_analysis_batch_size: 100    # Style analysis batch size
  style_update_threshold: 0.6       # Style update threshold

# ========================================
# Affection System
# ========================================
Affection_System_Settings:
  enable_affection_system: true     # Enable affection system
  max_total_affection: 250          # Bot total affection cap
  max_user_affection: 100           # Per-user affection cap
  affection_decay_rate: 0.95        # Affection decay rate
  daily_mood_change: true           # Enable daily mood changes
  mood_affect_affection: true       # Mood affects affection changes

# ========================================
# Mood System
# ========================================
Mood_System_Settings:
  enable_daily_mood: true           # Enable daily mood
  enable_startup_random_mood: true  # Enable random mood on startup
  mood_change_hour: 6               # Mood update hour (24h format)
  mood_persistence_hours: 24        # Mood duration (hours)

# ========================================
# Goal-Driven Chat System
# ========================================
Goal_Driven_Chat_Settings:
  enable_goal_driven_chat: false    # Enable goal-driven chat system
  goal_session_timeout_hours: 24    # Session timeout (hours)
  goal_auto_detect: true            # Auto-detect conversation goals
  goal_max_conversation_history: 40 # Max conversation history (rounds)

# ========================================
# Database Settings
# ========================================
Database_Settings:
  db_type: "sqlite"                 # Database type: sqlite / mysql / postgresql

  # MySQL config (active when db_type="mysql")
  mysql_host: "localhost"
  mysql_port: 3306
  mysql_user: "root"
  mysql_password: "your_password"
  mysql_database: "astrbot_self_learning"

  # PostgreSQL config (active when db_type="postgresql")
  postgresql_host: "localhost"
  postgresql_port: 5432
  postgresql_user: "postgres"
  postgresql_password: "your_password"
  postgresql_database: "astrbot_self_learning"
  postgresql_schema: "public"

  # Connection pool config
  max_connections: 10
  min_connections: 2

  # Refactoring features
  use_sqlalchemy: false             # Use SQLAlchemy ORM
  use_enhanced_managers: false      # Use enhanced managers

# ========================================
# Social Context Settings
# ========================================
Social_Context_Settings:
  enable_social_context_injection: true  # Enable social context injection
  include_social_relations: true         # Inject user social relationships
  include_affection_info: true           # Inject affection information
  include_mood_info: true                # Inject bot mood information
  context_injection_position: "start"    # Injection position: start / end

# ========================================
# Advanced Settings
# ========================================
Advanced_Settings:
  debug_mode: false                 # Debug mode
  save_raw_messages: true           # Save raw messages
  auto_backup_interval_days: 7      # Auto backup interval (days)
  use_enhanced_managers: false      # Use enhanced managers
  enable_memory_cleanup: true       # Enable memory auto-cleanup
  memory_cleanup_days: 30           # Memory retention days
  memory_importance_threshold: 0.3  # Memory importance threshold

# ========================================
# Storage Settings
# ========================================
Storage_Settings:
  data_dir: "./data/self_learning_data"  # Data storage directory
```

---

## 🛠️ Tech Stack

### AI/ML Stack
- **Large Language Models**: OpenAI GPT series, any OpenAI API-compatible model
- **Machine Learning**: `scikit-learn` `numpy` `pandas`
- **Affective Computing**: Emotion recognition, affective state modeling
- **Knowledge Graphs**: `networkx` - Relationship network analysis
- **NLP**: `jieba` - Chinese word segmentation

### Data Visualization
- **Chart Generation**: `plotly` `matplotlib` `seaborn`
- **Network Visualization**: `bokeh` - Social relationship graphs
- **Data Analysis**: Multi-dimensional statistical analysis

### System Architecture
- **Async Framework**: `asyncio` `aiohttp` `aiofiles`
- **Database**: `aiosqlite` `aiomysql` `asyncpg` + `SQLAlchemy[asyncio]`
- **Web Framework**: `quart` `quart-cors` - Async Flask-like framework
- **Caching**: `cachetools` - TTL cache
- **Task Scheduling**: `apscheduler` - Scheduled tasks

### Development Tools
- **Security**: `guardrails-ai` - LLM output validation
- **Testing**: `pytest` `pytest-asyncio`

---

## 📚 Documentation

### User Guides
- [Quick Start Guide](#-quick-start)
- [WebUI Tutorial](#-data-visualization)
- [Command Reference](#-command-reference)
- [Configuration Reference](#-configuration-reference)

### Developer Docs
- [Architecture Design](#-technical-architecture)
- [Design Patterns](#core-design-patterns)

### Advanced Topics
- [Expression Pattern Learning](#expression-pattern-learning-system)
- [Slang Mining Algorithm](#slang-mining-system)
- [Social Relationship Analysis](#social-relationship-analysis)
- [Persona Update Mechanism](#persona-update-mechanism)

---

## 🤝 Contributing

We welcome developers to participate in the project!

### How to Contribute
1. **Bug Reports** - [Submit an Issue](https://github.com/NickCharlie/astrbot_plugin_self_learning/issues)
2. **Feature Requests** - [Feature Request](https://github.com/NickCharlie/astrbot_plugin_self_learning/issues/new?template=feature_request.md)
3. **Code Contributions** - Fork the project and submit a Pull Request
4. **Documentation** - Improve documentation and tutorials

### Development Guidelines
- Follow existing architecture design and design patterns
- Use the factory pattern for unified service management
- Prefer dependency injection; avoid hardcoding
- Separate each feature into its own file, each module into its own directory
- Use relative imports for internal modules
- Add unit tests covering core logic

---

## 📄 License

This project is licensed under the [GPLv3 License](LICENSE).

### Special Thanks

Thanks to the following projects for inspiration and support:

- **[MaiBot](https://github.com/Mai-with-u/MaiBot)** - Core design concepts including expression pattern learning, time decay mechanism, and knowledge graph management
- **[AstrBot](https://github.com/Soulter/AstrBot)** - Excellent chatbot framework

### Contributors

Thanks to all the developers who have contributed to this project!

<a href="https://github.com/NickCharlie/astrbot_plugin_self_learning/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=NickCharlie/astrbot_plugin_self_learning" />
</a>

---

## ⚠️ Disclaimer (Detailed)

> **This section supplements the user agreement at the top of this document; both carry equal legal effect.**

### 1. Lawful and Compliant Use

- **Illegal use prohibited**: This project is strictly prohibited from being used directly or indirectly for any purpose that violates applicable laws and regulations
- **Legal compliance**: Users must comply with all applicable laws and regulations in their jurisdiction, including privacy and data protection laws
- **Platform rules**: Users must comply with the terms of service and usage policies of messaging platforms (QQ, WeChat, etc.)
- **Authorization required**: Explicit user consent must be obtained before collecting and processing any user data

### 2. Data Security & Privacy

- **Local storage**: All learning data is stored locally; the developer cannot access user data
- **Regular backups**: Please regularly back up database and persona files to prevent data loss
- **Password protection**: Strongly recommended to change the default WebUI password in production
- **Privacy protection**:
  - The plugin collects and analyzes user messages for learning purposes
  - Users must explicitly inform group members about data collection
  - Collected data must not be used for commercial purposes
  - Data must not be disclosed to any third party
  - Recommended for use only in private environments or groups where all members have consented

### 3. Usage Risks

- **Software status**: The plugin is currently in development/testing phase and may contain unknown bugs
- **Data risks**: Please back up persona files before use to prevent data corruption or loss
- **Quality dependency**: AI learning quality depends on the quality and quantity of learning samples
- **System stability**: Thorough testing before production use is strongly recommended
- **Network security**: Exposing the WebUI port in public environments is not recommended to avoid security risks

### 4. Developer Liability Limitation

- **Provided as-is**: This project is provided "AS IS" without any warranties of any kind
- **No warranty**: Including but not limited to implied warranties of merchantability or fitness for a particular purpose
- **Limitation of liability**:
  - The developer is not responsible for any direct, indirect, incidental, special, or consequential damages arising from using this project
  - Including but not limited to: data loss, business interruption, loss of profits, reputational damage, etc.
  - The developer bears no responsibility for users' illegal or non-compliant behavior
  - Users bear full legal and financial responsibility for any disputes arising from misuse

### 5. Other Terms

- **Copyright**: This project uses the GPLv3 open-source license; users must comply with its terms
- **Right to modify**: The developer reserves the right to modify, update, or discontinue this project at any time
- **Agreement updates**: This disclaimer and user agreement may be updated at any time without prior notice
- **Continued use implies consent**: Continued use of this project constitutes acceptance of all updated terms

### 6. Special Reminder

⚠️ **Important**:
- If you do not agree to any of the above terms, please immediately stop using and delete this project
- Downloading, installing, or using any functionality of this project constitutes your full understanding and agreement to comply with this disclaimer and user agreement
- The right of interpretation of this statement belongs to the project developer

---

## 🎯 Roadmap

### Coming Soon
- [ ] Knowledge graph and long-term memory system (understanding contextual relationships, building persistent memory)
- [ ] Multi-persona automatic switching (based on conversation scenarios)
- [ ] Advanced mood modeling (mood chains and mood transitions)
- [ ] Reinforcement learning optimization (feedback-based)
- [ ] Multi-modal learning support (images, voice)

### Long-term Plans
- [ ] Federated learning (cross-group knowledge sharing)
- [ ] Autonomous conversation initiation (proactive topic guidance)

---

<div align="center">

**Thank you for using the AstrBot Self-Learning Plugin!**

If you find it helpful, please give us a ⭐Star!

[Back to top](#astrbot-self-learning-plugin)

</div>
