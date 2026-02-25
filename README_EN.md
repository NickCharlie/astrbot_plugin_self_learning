<div align="center">

**English** | **[中文](README.md)**

<br>

<img src="logo.png" alt="Self-Learning Logo" width="180"/>

<br>

# AstrBot Self-Learning Plugin

**Make your AI chatbot learn, think, and converse like a real person**

<br>

[![Version](https://img.shields.io/badge/version-Next--2.1.0-blue.svg)](https://github.com/NickCharlie/astrbot_plugin_self_learning) [![License](https://img.shields.io/badge/license-GPLv3-green.svg)](LICENSE) [![AstrBot](https://img.shields.io/badge/AstrBot-%3E%3D4.11.4-orange.svg)](https://github.com/Soulter/AstrBot) [![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)

[Features](#what-we-can-do) · [Quick Start](#quick-start) · [Web UI](#visual-management-interface) · [Community](#community) · [Contributing](CONTRIBUTING.md)

</div>

<br>

> [!WARNING]
> **Please manually back up your persona files before use, in case bugs cause persona corruption.**

<details>
<summary><strong>Disclaimer & User Agreement (click to expand)</strong></summary>

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

**Important: By downloading, installing, or using any functionality of this project, you are deemed to have fully understood and agreed to comply with all of the above terms. If you do not agree, please immediately stop using and delete this project.**

</details>

---

## What We Can Do

### Conversation Style Learning — Make Your Bot Talk Like a Real Person

Your bot can automatically observe and learn a specific user's speaking style — catchphrases, expression habits, tone markers, even distinctive punctuation usage. Learning is continuous: the more the bot observes, the more natural and human-like its expressions become.

It doesn't just copy individual sentences. It understands **which expressions to use in which situations** — how to speak when happy, how to comfort someone, how to complain.

### Social Relationship Insight — See Through Who's Really Close in the Group

This is one of our most interesting features. The plugin automatically analyzes social relationships between group chat members and generates a visual relationship graph.

We can identify **22 relationship types**, including but not limited to:

| Category | Identifiable Relationships |
|----------|---------------------------|
| **Daily Interaction** | Frequent interaction, Reply conversations, Topic discussions, Q&A, Agreement, Debates |
| **Social Ties** | Best friends, Colleagues, Classmates, Teacher-student |
| **Family Relations** | Parent-child, Siblings, Relatives |
| **Intimate Relations** | Couples, Spouses, **Ambiguous relationships**, **Inappropriate relationships** |
| **Special Relations** | Enemies, Rivals, Admirers, Idol-fan |

Yes, **ambiguous and inappropriate relationships can be detected too**. By analyzing nicknames, tone, interaction frequency, and intimacy levels in chat messages, the plugin can uncover those "unusual" connections. Each relationship type is color-coded on the graph, with relationship strength and interaction frequency visible at a glance.

You can filter to view all relationships for a specific member, or get an overview of the entire group's social network.

### Adaptive Persona Evolution — Your Bot's Personality Grows on Its Own

Traditional bot personas are static — whatever personality you set, it stays that way forever. We're different.

This plugin **automatically generates persona update suggestions** based on learned conversation styles, group atmosphere, and user feedback. Every update goes through a review mechanism: you can compare the "original persona" with the "proposed changes" in the management interface and decide whether to adopt them.

A persona isn't written once and forgotten — it **continuously evolves and keeps growing**.

### Group Slang Understanding — No More Embarrassing Misunderstandings

Every group has its own "dialect." "Jackpot" might mean surprise, "next time for sure" is actually a polite refusal, and a certain emoji might mean something completely different from its literal meaning.

Regular bots get confused by these and embarrass themselves. This plugin automatically detects and learns group-specific slang, understands their real meanings, and uses them correctly in conversations. **Your bot won't blow its cover by "not understanding the lingo" anymore.**

### Affection System — Different Attitudes for Different People

The bot remembers the closeness of its relationship with each user. For users who chat often and interact kindly, the bot responds with more warmth and enthusiasm. For users with poor attitudes, the bot's replies become cold or even sharp.

Affection naturally decays over time — **no contact means gradually drifting apart**, just like real-life relationships. Each user has a cap of 100 points, and the bot's total affection has an upper limit — it can't be equally devoted to everyone.

### Mood System — Your Bot Has Good Days and Bad Days Too

The bot is no longer a machine with permanently stable emotions. It experiences happiness, sadness, excitement, anxiety, playfulness, curiosity, and other emotional states that change naturally over time and through interactions.

When in a good mood, replies are more energetic and humorous. When in a bad mood, it might be slightly negative or dismissive. **This makes every conversation slightly different, making the bot feel more real.**

### Goal-Driven Conversation — Not Just Responding, But Actively Guiding

Traditional bots only react — "you say something, I answer." This plugin's bot can automatically identify the user's conversational intent — whether they need comfort, want to chat casually, are venting, or asking for help — and **actively guides the conversation direction** based on the detected intent.

It supports 38 conversation scenarios covering emotional support, information exchange, entertainment, social interaction, conflict handling, and more. The bot acts like a real conversationalist who knows when to listen, when to respond, and when to change the subject.

### Memory Graph — Remembers Everything You've Talked About

The bot no longer has "goldfish memory." It automatically extracts key information from conversations, builds a knowledge association network, and forms genuine long-term memory.

Topics discussed last week, preferences you've mentioned, funny moments between you — the bot remembers all of it and brings things up naturally at the right time. **This feeling of "being remembered" is the key to making a bot feel like a real person.**

---

## Visual Management Interface

The plugin comes with a macOS-style web management interface (port 7833). All features are visually operable — no command line needed.

**Statistics Dashboard**
![Statistics Dashboard](https://github.com/NickCharlie/astrbot_plugin_self_learning/blob/develop/image/%E6%95%B0%E6%8D%AE%E7%BB%9F%E8%AE%A1%E9%A1%B5%E9%9D%A2.png?raw=true)

**Persona Management & Review**
![Persona Management](https://github.com/NickCharlie/astrbot_plugin_self_learning/blob/develop/image/%E4%BA%BA%E6%A0%BC%E7%AE%A1%E7%90%86%E9%A1%B5%E9%9D%A2.png?raw=true)

**Conversation Style Learning Tracker**
![Style Learning](https://github.com/NickCharlie/astrbot_plugin_self_learning/blob/develop/image/%E5%AF%B9%E8%AF%9D%E9%A3%8E%E6%A0%BC%E5%AD%A6%E4%B9%A0%E9%A1%B5%E9%9D%A2.png?raw=true)

**Social Relationship Graph**
![Social Relationships](https://github.com/NickCharlie/astrbot_plugin_self_learning/blob/develop/image/%E7%A4%BE%E4%BA%A4%E5%85%B3%E7%B3%BB%E9%A1%B5%E9%9D%A2.png?raw=true)

---

## Quick Start

### Installation

```bash
cd /path/to/astrbot/data/plugins
git clone https://github.com/NickCharlie/astrbot_plugin_self_learning.git
```

Start AstrBot and the plugin loads automatically.

### Access the Management Interface

```
http://localhost:7833
```

Default password: `self_learning_pwd` (change immediately after first login)

### Basic Configuration

Set the following key items in the AstrBot admin panel:

- **Learning Target** — Specify user QQ IDs to learn from (leave empty to learn from everyone)
- **Model Configuration** — Set the Provider IDs for filter and refinement models
- **Learning Frequency** — Auto-learning interval (default: 6 hours)
- **Database** — Supports SQLite (works out of the box), MySQL, PostgreSQL

More configuration options are available in the WebUI settings page.

---

## Commands

| Command | Description |
|---------|-------------|
| `/learning_status` | View learning status and statistics |
| `/start_learning` | Manually start learning |
| `/stop_learning` | Stop automatic learning |
| `/force_learning` | Force execute one learning cycle |
| `/affection_status` | View affection leaderboard |
| `/set_mood <type>` | Set bot mood |

All commands require admin privileges.

---

## Recommended Companion

**[Group Chat Plus Plugin](https://github.com/Him666233/astrbot_plugin_group_chat_plus)**

The two plugins complement each other perfectly: this plugin handles **learning and persona optimization**, while Group Chat Plus handles **intelligent reply decisions and social awareness**. Together, your bot can both learn and navigate social situations.

---

## Community

- QQ Group: **1021544792** (ChatPlus plugin users + Self-Learning plugin users)
- [Report Bugs](https://github.com/NickCharlie/astrbot_plugin_self_learning/issues)
- [Feature Requests](https://github.com/NickCharlie/astrbot_plugin_self_learning/issues/new?template=feature_request.md)
- [Contribute Code](CONTRIBUTING.md)

---

## License

This project is licensed under the [GPLv3 License](LICENSE).

### Special Thanks

- **[MaiBot](https://github.com/Mai-with-u/MaiBot)** — Core design concepts including expression pattern learning and knowledge graph management
- **[AstrBot](https://github.com/Soulter/AstrBot)** — Excellent chatbot framework
- **[ACE (Agentic Context Engineering)](https://github.com/ace-agent/ace)** — Design patterns for automated persona prompt curation (Curator pattern), few-shot exemplar effectiveness tracking (helpful/harmful dual counters), and semantic deduplication (BulletpointAnalyzer pattern). See the paper [*Agentic Context Engineering*](https://arxiv.org/abs/2510.04618)

### Contributors

<a href="https://github.com/NickCharlie/astrbot_plugin_self_learning/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=NickCharlie/astrbot_plugin_self_learning" />
</a>

---

<div align="center">

**If you find this helpful, please give us a Star!**

[Back to top](#astrbot-self-learning-plugin)

</div>
