BOOTSTRAP_FILES: dict[str, str] = {
    ".ado-ai-review.yml": """version: 1

instructions:
  reviewer: .ado-ai-review/instructions/reviewer.md
  security: .ado-ai-review/instructions/security.md
  indexer: .ado-ai-review/instructions/indexer.md
  fixer: .ado-ai-review/instructions/fixer.md

guidelines:
  code_style:
    - .ado-ai-review/guidelines/code-style.md
    - AGENTS.md
    - CLAUDE.md
    - .github/copilot-instructions.md
  security:
    - .ado-ai-review/guidelines/security.md
""",
    ".ado-ai-review/instructions/reviewer.md": "# Reviewer Instructions\n\nFocus on correctness, tests, maintainability, and clear user impact.\n",
    ".ado-ai-review/instructions/security.md": "# Security Instructions\n\nFocus on secrets, injection, authentication, authorization, validation, deserialization, and sensitive data handling.\n",
    ".ado-ai-review/instructions/indexer.md": "# Indexer Instructions\n\nDescribe files by purpose, language, domain relevance, test relevance, and security relevance.\n",
    ".ado-ai-review/instructions/fixer.md": "# Fixer Instructions\n\nOnly propose mechanical, behavior-preserving changes.\n",
    ".ado-ai-review/guidelines/code-style.md": "# Code Style\n\nPrefer local project style over generic preferences.\n",
    ".ado-ai-review/guidelines/security.md": "# Security Guidelines\n\nNever expose secret values in comments or model prompts.\n",
}
