"""
Commit Message Linter for Pull Requests.
Validates that all commits in a PR follow Conventional Commits format.
Posts a comment with feedback if any commit is non-compliant.
"""

import json
import os
import re
import sys
import urllib.request

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
REPO = os.environ["GITHUB_REPOSITORY"]
PR_NUMBER = os.environ["PR_NUMBER"]

VALID_TYPES = [
    "feat", "fix", "docs", "style", "refactor",
    "perf", "test", "chore", "ci", "build", "revert",
]

# Conventional Commits pattern: type(scope): description
COMMIT_PATTERN = re.compile(
    r"^(?P<type>" + "|".join(VALID_TYPES) + r")"
    r"(?:\([\w\-]+\))?"  # optional scope
    r"!?"                 # optional breaking change marker
    r": .{1,72}$",        # colon + space + description (≤72 chars first line)
    re.MULTILINE,
)

# Commits to skip (merge commits, version bumps, etc.)
SKIP_PATTERNS = [
    re.compile(r"^Merge "),
    re.compile(r"^Revert \""),
    re.compile(r"^v?\d+\.\d+"),
]


def github_api(endpoint: str, method: str = "GET", data: dict | None = None):
    """Call GitHub REST API."""
    url = f"https://api.github.com/repos/{REPO}/{endpoint}"
    payload = json.dumps(data).encode() if data else None
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        },
        method=method,
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def get_pr_commits() -> list[dict]:
    """Fetch all commits in the PR."""
    commits = []
    page = 1
    while True:
        batch = github_api(f"pulls/{PR_NUMBER}/commits?per_page=100&page={page}")
        if not batch:
            break
        commits.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return commits


def should_skip(message: str) -> bool:
    """Check if a commit message should be skipped."""
    first_line = message.split("\n")[0].strip()
    return any(p.match(first_line) for p in SKIP_PATTERNS)


def validate_commit(message: str) -> str | None:
    """Validate a commit message. Returns error string or None if valid."""
    first_line = message.split("\n")[0].strip()

    if should_skip(first_line):
        return None

    if not COMMIT_PATTERN.match(first_line):
        # Provide specific feedback
        if ":" not in first_line:
            return "Missing colon separator. Expected format: `type(scope): description`"
        parts = first_line.split(":", 1)
        type_part = parts[0].strip().split("(")[0]
        if type_part not in VALID_TYPES:
            return f"Invalid type `{type_part}`. Must be one of: {', '.join(f'`{t}`' for t in VALID_TYPES)}"
        if len(first_line) > 72:
            return f"First line is {len(first_line)} characters (max 72)"
        return "Does not match Conventional Commits format: `type(scope): description`"

    return None


def build_comment(failures: list[dict]) -> str:
    """Build the review comment for non-compliant commits."""
    lines = [
        "## Commit Message Lint Failed",
        "",
        "The following commits do not follow [Conventional Commits](https://www.conventionalcommits.org/) format:",
        "",
    ]

    for f in failures:
        sha_short = f["sha"][:7]
        lines.append(f"- `{sha_short}` **{f['message']}**")
        lines.append(f"  - {f['error']}")
        lines.append("")

    lines.extend([
        "### Expected Format",
        "",
        "```",
        "<type>(<scope>): <description>",
        "```",
        "",
        "| Type | Description |",
        "|------|-------------|",
        "| `feat` | A new feature |",
        "| `fix` | A bug fix |",
        "| `docs` | Documentation changes |",
        "| `refactor` | Code refactoring |",
        "| `style` | Code style changes |",
        "| `perf` | Performance improvement |",
        "| `test` | Adding or updating tests |",
        "| `chore` | Build process or tooling |",
        "| `ci` | CI/CD changes |",
        "",
        "### Examples",
        "",
        "```",
        "feat(webui): add responsive layout for login page",
        "fix(db): handle migration error on first load",
        "docs: update installation guide",
        "```",
        "",
        "Please update your commit messages and push again. ",
        "You can use `git rebase -i` to reword commits.",
        "",
        "---",
        "<sub>Checked by commit-lint CI</sub>",
    ])

    return "\n".join(lines)


def find_existing_comment() -> int | None:
    """Find an existing lint comment to update instead of creating duplicates."""
    comments = github_api(f"issues/{PR_NUMBER}/comments?per_page=100")
    for c in comments:
        if "Commit Message Lint" in c.get("body", ""):
            return c["id"]
    return None


def post_or_update_comment(body: str):
    """Post a new comment or update an existing one."""
    existing_id = find_existing_comment()
    if existing_id:
        github_api(f"issues/comments/{existing_id}", method="PATCH", data={"body": body})
    else:
        github_api(f"issues/{PR_NUMBER}/comments", method="POST", data={"body": body})


def delete_existing_comment():
    """Delete the lint comment if all commits pass now."""
    existing_id = find_existing_comment()
    if existing_id:
        github_api(f"issues/comments/{existing_id}", method="DELETE")


def main():
    print(f"Checking commits for PR #{PR_NUMBER}...")

    commits = get_pr_commits()
    print(f"Found {len(commits)} commits.")

    failures = []
    for commit in commits:
        message = commit["commit"]["message"]
        first_line = message.split("\n")[0].strip()
        sha = commit["sha"]

        error = validate_commit(message)
        if error:
            failures.append({"sha": sha, "message": first_line, "error": error})
            print(f"  FAIL {sha[:7]}: {first_line} ({error})")
        else:
            print(f"  OK   {sha[:7]}: {first_line}")

    if failures:
        comment = build_comment(failures)
        print(f"\n{len(failures)} commit(s) failed lint. Posting comment...")
        post_or_update_comment(comment)
        sys.exit(1)
    else:
        print("\nAll commits passed lint.")
        delete_existing_comment()


if __name__ == "__main__":
    main()
