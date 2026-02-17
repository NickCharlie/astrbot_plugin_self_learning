# Contributing to AstrBot Self-Learning Plugin

Thank you for your interest in contributing! This guide will help you get started.

## Table of Contents

- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Commit Message Convention](#commit-message-convention)
- [Branch Strategy](#branch-strategy)
- [Pull Request Process](#pull-request-process)
- [Code Style](#code-style)
- [Issue Reporting](#issue-reporting)

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/<your-username>/astrbot_plugin_self_learning.git`
3. Create a feature branch from `develop`: `git checkout -b feat/your-feature develop`
4. Make your changes
5. Push and open a Pull Request to `develop`

## Development Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt

# Run tests
pytest tests/
```

**Requirements**: Python 3.11+

## Commit Message Convention

We follow [Conventional Commits](https://www.conventionalcommits.org/). **All commit messages must use this format:**

```
<type>(<scope>): <short description>
```

### Type

| Type       | Description                                    |
|------------|------------------------------------------------|
| `feat`     | A new feature                                  |
| `fix`      | A bug fix                                      |
| `docs`     | Documentation changes only                     |
| `style`    | Code style changes (formatting, no logic)      |
| `refactor` | Code refactoring (no feature or fix)           |
| `perf`     | Performance improvement                        |
| `test`     | Adding or updating tests                       |
| `chore`    | Build process, CI, or tooling changes          |
| `ci`       | CI/CD configuration changes                    |

### Scope (optional)

Identifies the module affected. Common scopes:

`webui`, `persona`, `affection`, `jargon`, `learning`, `social`, `db`, `config`, `api`, `memory`, `export`

### Examples

```
feat(webui): add responsive layout for login page
fix(db): handle SQLite migration on first load
docs: update README installation steps
refactor(persona): extract updater logic into separate service
test(auth): add unit tests for login endpoint
chore(deps): upgrade sqlalchemy to 2.0
perf(memory): optimize graph query with batch loading
ci: add commit message linting workflow
```

### Rules

- Use **English** for commit messages
- Use **imperative mood** ("add feature" not "added feature")
- Keep the first line under **72 characters**
- Do not end the description with a period
- Optionally add a body separated by a blank line for more detail:

```
feat(social): add relationship decay over time

Relationships now decay gradually if no interaction occurs within
the configured time window. Decay rate is configurable via the
`social.decay_rate` setting in config.
```

## Branch Strategy

| Branch    | Purpose                          |
|-----------|----------------------------------|
| `main`    | Stable releases                  |
| `develop` | Integration branch for features  |
| `feat/*`  | New features                     |
| `fix/*`   | Bug fixes                        |
| `docs/*`  | Documentation changes            |

- Always branch from `develop`
- Always open PRs targeting `develop`
- `main` is updated via PR from `develop` by maintainers only

## Pull Request Process

1. Ensure your branch is up to date with `develop`
2. Follow the [commit message convention](#commit-message-convention)
3. Fill out the PR template completely
4. Verify your changes:
   - [ ] No new warnings or errors
   - [ ] Tested on SQLite mode
   - [ ] Tested on MySQL mode (if applicable)
   - [ ] Self-reviewed the code changes
5. Wait for maintainer review

### PR Title

PR titles should also follow the commit convention format:

```
feat(webui): add dark mode toggle
fix(db): resolve connection pool leak
```

## Code Style

- **Indentation**: 4 spaces for Python, 2 spaces for YAML/JSON/HTML
- **Line length**: 120 characters max
- **Encoding**: UTF-8
- **Line endings**: LF (Unix-style)
- **Naming**: `snake_case` for functions/variables, `PascalCase` for classes
- See [.editorconfig](.editorconfig) for full editor configuration

## Issue Reporting

- Use the [issue templates](https://github.com/NickCharlie/astrbot_plugin_self_learning/issues/new/choose) provided
- For security vulnerabilities, see [SECURITY.md](SECURITY.md)

---

Thank you for contributing!
