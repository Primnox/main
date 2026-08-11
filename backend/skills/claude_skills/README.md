# Claude Skills

Drop real Anthropic Claude Skill packages here — one folder per skill, each
containing a `SKILL.md` (YAML frontmatter with `name` + `description`,
followed by markdown instructions) and optionally `scripts/`, `references/`,
`assets/` subfolders. Primnox discovers and registers them automatically on
startup (see `skills/skill_router.py`'s `_discover_claude_skills()`) — no
code changes needed. They're invoked the same way real Claude Skills are:
the model sees each one's name + description via the `list_skills` tool and
calls `use_skill` to run one.

Example layout:

```
claude_skills/
└── pdf/
    ├── SKILL.md
    ├── scripts/
    │   └── fill_form.py
    └── references/
        └── forms.md
```
