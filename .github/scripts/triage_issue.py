"""
Issue Triage Script — Powered by OpenAI
Automatically classifies, checks completeness, and suggests solutions for new issues.
Includes source code analysis for more accurate triage.
"""

import json
import os
import re
import subprocess
import sys
import urllib.request

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
REPO = os.environ["GITHUB_REPOSITORY"]
ISSUE_NUMBER = os.environ["ISSUE_NUMBER"]
ISSUE_TITLE = os.environ["ISSUE_TITLE"]
ISSUE_BODY = os.environ.get("ISSUE_BODY", "")

# Labels that the LLM can assign (must exist on the repo)
VALID_LABELS = [
    "bug",
    "enhancement",
    "question",
    "documentation",
    "duplicate",
    "invalid",
    "help wanted",
    "good first issue",
]

# Common words to skip during keyword extraction
STOP_WORDS = {
    "the", "and", "for", "that", "this", "with", "from", "have", "has",
    "not", "but", "are", "was", "were", "been", "will", "would", "could",
    "should", "can", "may", "might", "need", "use", "used", "using",
    "also", "than", "then", "when", "where", "which", "while", "after",
    "before", "into", "through", "during", "each", "some", "all", "any",
    "both", "few", "more", "most", "other", "such", "only", "same",
    "very", "just", "about", "above", "below", "between", "under",
    "over", "again", "here", "there", "why", "how", "what", "who",
    "its", "they", "them", "their", "our", "your", "his", "her",
    "does", "did", "doing", "done", "get", "got", "set", "put",
    "let", "make", "like", "new", "old", "one", "two", "way",
    "out", "see", "now", "look", "come", "take", "want", "say",
    "try", "ask", "work", "run", "add", "still", "too", "off",
    "version", "steps", "expected", "actual", "behavior", "describe",
    "bug", "feature", "issue", "error", "problem", "please", "none",
    "true", "false", "null", "undefined", "info", "log", "logs",
}

SYSTEM_PROMPT = """\
You are a professional open-source project maintainer triaging a GitHub issue for "AstrBot Self-Learning Plugin" — \
an AI chatbot plugin that learns conversation styles, understands slang, manages social relationships, and evolves its persona.

Core modules: message capture, expression pattern learning, jargon mining, affection/mood system, \
persona management, social relationship analysis, goal-driven conversation, WebUI (port 7833), \
SQLite/MySQL database support.

You will be given:
1. The issue title and body
2. The project file tree (all Python source files)
3. Recent git commits
4. Relevant source code snippets matching keywords from the issue

Use ALL of the above context — especially the source code — to provide an accurate, code-aware analysis.

Analyze the issue and respond in **valid JSON** with these fields:

{
  "labels": ["<label1>", ...],
  "completeness": {
    "is_complete": true/false,
    "missing_fields": ["<field1>", ...]
  },
  "analysis": {
    "summary": "<1-2 sentence summary of the issue>",
    "possible_cause": "<likely root cause based on the source code, or null>",
    "suggested_solution": "<actionable suggestion referencing specific files/functions, or null>",
    "related_modules": ["<module1>", ...],
    "related_files": ["<file_path1>", ...]
  },
  "priority": "low" | "medium" | "high" | "critical",
  "language": "zh" | "en"
}

Rules:
- labels: pick from """ + json.dumps(VALID_LABELS) + """
- completeness: for bug reports, check for: version, reproduction steps, expected behavior, actual behavior, logs. \
For feature requests, check for: problem statement, proposed solution.
- analysis.possible_cause: reference actual code (file name, function name, line) when possible
- analysis.suggested_solution: be specific — point to exact files/functions to modify
- analysis.related_files: list the source files most likely related to this issue
- language: detect whether the issue is written in Chinese ("zh") or English ("en")
- priority: critical = data loss / crash on startup; high = core feature broken; medium = minor bug or important feature; low = cosmetic / question
- Return ONLY the JSON object, no markdown fences, no extra text.
"""


def call_openai(system: str, user: str) -> dict:
    """Call OpenAI Chat Completions API."""
    payload = json.dumps({
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.1,
        "max_tokens": 2048,
    }).encode()

    req = urllib.request.Request(
        f"{OPENAI_BASE_URL}/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
    )

    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())

    content = data["choices"][0]["message"]["content"].strip()
    # Strip markdown fences if present
    if content.startswith("```"):
        content = content.split("\n", 1)[1]
    if content.endswith("```"):
        content = content.rsplit("```", 1)[0]
    content = content.strip()
    return json.loads(content)


def add_labels(labels: list[str]):
    """Add labels to the issue via GitHub API."""
    filtered = [l for l in labels if l in VALID_LABELS]
    if not filtered:
        return
    payload = json.dumps({"labels": filtered}).encode()
    req = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/issues/{ISSUE_NUMBER}/labels",
        data=payload,
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    urllib.request.urlopen(req, timeout=10)


def post_comment(body: str):
    """Post a comment on the issue."""
    payload = json.dumps({"body": body}).encode()
    req = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/issues/{ISSUE_NUMBER}/comments",
        data=payload,
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    urllib.request.urlopen(req, timeout=10)


# ---------------------------------------------------------------------------
# Source code analysis helpers
# ---------------------------------------------------------------------------

def get_file_tree() -> str:
    """Generate a compact project file tree of Python source files."""
    try:
        proc = subprocess.run(
            ["find", ".", "-name", "*.py",
             "-not", "-path", "./.git/*",
             "-not", "-path", "*/__pycache__/*",
             "-not", "-path", "./tests/*",
             "-not", "-path", "./scripts/*",
             "-not", "-path", "./export/*"],
            capture_output=True, text=True, timeout=5,
        )
        files = sorted(f for f in proc.stdout.strip().split("\n") if f)
        return "\n".join(files)
    except Exception:
        return ""


def get_recent_commits(n: int = 15) -> str:
    """Get recent git commit messages."""
    try:
        proc = subprocess.run(
            ["git", "log", "--oneline", f"-{n}"],
            capture_output=True, text=True, timeout=5,
        )
        return proc.stdout.strip()
    except Exception:
        return ""


def extract_keywords(title: str, body: str) -> list[str]:
    """Extract meaningful keywords from issue text for code search."""
    text = f"{title}\n{body}"
    keywords = set()

    # CamelCase class/error names (from original text)
    for m in re.finditer(r'\b([A-Z][a-z]+(?:[A-Z][a-z]+)+)\b', text):
        keywords.add(m.group(1))

    # Error/Exception/Warning types
    for m in re.finditer(r'\b(\w+(?:Error|Exception|Warning))\b', text):
        keywords.add(m.group(1))

    # Python filenames
    for m in re.finditer(r'\b(\w+\.py)\b', text):
        keywords.add(m.group(1))

    # Quoted identifiers (backticks, single/double quotes)
    for m in re.finditer(r'[`\'"](\w{3,})[`\'"]', text):
        word = m.group(1)
        if word.lower() not in STOP_WORDS:
            keywords.add(word)

    # snake_case identifiers (3+ chars, from lowered text)
    for m in re.finditer(r'\b([a-z][a-z0-9_]{2,})\b', text.lower()):
        word = m.group(1)
        if word not in STOP_WORDS and not word.isdigit():
            keywords.add(word)

    return list(keywords)[:20]


def search_source_code(keywords: list[str]) -> str:
    """Search source code for keywords, return matching lines with context."""
    all_matches = []
    seen = set()

    for keyword in keywords:
        if len(all_matches) >= 40:
            break
        try:
            proc = subprocess.run(
                ["grep", "-rn", "--include=*.py", "-m", "3", keyword, "."],
                capture_output=True, text=True, timeout=5,
            )
            for line in proc.stdout.strip().split("\n"):
                if line and line not in seen:
                    seen.add(line)
                    all_matches.append(line)
        except Exception:
            continue

    if not all_matches:
        return ""

    result = "\n".join(all_matches[:50])
    if len(result) > 8000:
        result = result[:8000] + "\n... (truncated)"
    return result


def gather_source_context(title: str, body: str) -> str:
    """Gather relevant source code context for LLM analysis."""
    sections = []

    # 1. Project file tree
    tree = get_file_tree()
    if tree:
        sections.append(f"## Project Source Files\n{tree}")

    # 2. Recent commits
    commits = get_recent_commits(15)
    if commits:
        sections.append(f"## Recent Commits\n{commits}")

    # 3. Keyword-based code search
    keywords = extract_keywords(title, body)
    if keywords:
        print(f"Extracted keywords: {keywords}")
        matches = search_source_code(keywords)
        if matches:
            sections.append(f"## Relevant Source Code (grep matches)\n{matches}")
        else:
            print("No source code matches found for keywords.")

    context = "\n\n".join(sections)
    # Hard limit to avoid token overflow
    if len(context) > 15000:
        context = context[:15000] + "\n\n... (source context truncated)"

    return context


# ---------------------------------------------------------------------------
# Comment builder
# ---------------------------------------------------------------------------

def build_comment(result: dict) -> str:
    """Build the triage comment in the detected language."""
    lang = result.get("language", "zh")
    analysis = result.get("analysis", {})
    completeness = result.get("completeness", {})
    priority = result.get("priority", "medium")

    priority_emoji = {
        "critical": "\U0001f534",
        "high": "\U0001f7e0",
        "medium": "\U0001f7e1",
        "low": "\U0001f7e2",
    }
    p_emoji = priority_emoji.get(priority, "\u26aa")

    if lang == "zh":
        lines = [
            "## \U0001f916 Issue \u5ba1\u67e5\u62a5\u544a",
            "",
            f"**\u4f18\u5148\u7ea7**: {p_emoji} `{priority}`",
            "",
            f"**\u6458\u8981**: {analysis.get('summary', 'N/A')}",
            "",
        ]

        if analysis.get("related_modules"):
            lines.append(f"**\u76f8\u5173\u6a21\u5757**: {', '.join(analysis['related_modules'])}")
            lines.append("")

        if analysis.get("related_files"):
            files_str = ", ".join(f"`{f}`" for f in analysis["related_files"])
            lines.append(f"**\u76f8\u5173\u6587\u4ef6**: {files_str}")
            lines.append("")

        if analysis.get("possible_cause"):
            lines.append(f"**\u53ef\u80fd\u539f\u56e0**: {analysis['possible_cause']}")
            lines.append("")

        if analysis.get("suggested_solution"):
            lines.append(f"**\u5efa\u8bae\u65b9\u6848**: {analysis['suggested_solution']}")
            lines.append("")

        if not completeness.get("is_complete", True):
            missing = completeness.get("missing_fields", [])
            lines.append("---")
            lines.append("")
            lines.append("> [!NOTE]")
            lines.append("> **\u4fe1\u606f\u4e0d\u5b8c\u6574** \u2014 \u8bf7\u8865\u5145\u4ee5\u4e0b\u4fe1\u606f\u4ee5\u4fbf\u6211\u4eec\u66f4\u5feb\u5730\u5904\u7406\uff1a")
            for field in missing:
                lines.append(f"> - {field}")
            lines.append("")

        lines.append("---")
        lines.append("<sub>\U0001f916 \u6b64\u62a5\u544a\u7531 AI \u81ea\u52a8\u751f\u6210\uff0c\u5df2\u5206\u6790\u4ed3\u5e93\u6e90\u7801\uff0c\u4ec5\u4f9b\u53c2\u8003\u3002\u5f00\u53d1\u8005\u4f1a\u5c3d\u5feb\u5ba1\u9605\u60a8\u7684 issue\u3002</sub>")
    else:
        lines = [
            "## \U0001f916 Issue Triage Report",
            "",
            f"**Priority**: {p_emoji} `{priority}`",
            "",
            f"**Summary**: {analysis.get('summary', 'N/A')}",
            "",
        ]

        if analysis.get("related_modules"):
            lines.append(f"**Related Modules**: {', '.join(analysis['related_modules'])}")
            lines.append("")

        if analysis.get("related_files"):
            files_str = ", ".join(f"`{f}`" for f in analysis["related_files"])
            lines.append(f"**Related Files**: {files_str}")
            lines.append("")

        if analysis.get("possible_cause"):
            lines.append(f"**Possible Cause**: {analysis['possible_cause']}")
            lines.append("")

        if analysis.get("suggested_solution"):
            lines.append(f"**Suggested Solution**: {analysis['suggested_solution']}")
            lines.append("")

        if not completeness.get("is_complete", True):
            missing = completeness.get("missing_fields", [])
            lines.append("---")
            lines.append("")
            lines.append("> [!NOTE]")
            lines.append("> **Incomplete information** \u2014 Please provide the following so we can address this faster:")
            for field in missing:
                lines.append(f"> - {field}")
            lines.append("")

        lines.append("---")
        lines.append("<sub>\U0001f916 This report was auto-generated by AI with source code analysis. A maintainer will review your issue shortly.</sub>")

    return "\n".join(lines)


def main():
    print(f"Triaging issue #{ISSUE_NUMBER}: {ISSUE_TITLE}")

    # Gather source code context
    print("Analyzing repository source code...")
    source_context = gather_source_context(ISSUE_TITLE, ISSUE_BODY)

    # Build user message with issue + source context
    user_content = f"**Issue Title**: {ISSUE_TITLE}\n\n**Issue Body**:\n{ISSUE_BODY}"
    if source_context:
        user_content += f"\n\n---\n\n# Repository Source Code Context\n\n{source_context}"

    try:
        result = call_openai(SYSTEM_PROMPT, user_content)
    except Exception as e:
        print(f"OpenAI API error: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"LLM result: {json.dumps(result, ensure_ascii=False, indent=2)}")

    # Add labels
    labels = result.get("labels", [])
    if labels:
        print(f"Adding labels: {labels}")
        add_labels(labels)

    # Post comment
    comment = build_comment(result)
    print("Posting triage comment...")
    post_comment(comment)

    print("Done.")


if __name__ == "__main__":
    main()
