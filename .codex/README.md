# Project Codex Files

This directory holds project support files for Codex and local working data.
The live CK3 mod is under `BookmarksGit/` and loads directly through `BookmarksGit/descriptor.mod`; there is no separate test mirror.

## Start Here

- [Project working rules](../AGENTS.md): concise guidance for Codex in this repository.
- [TODO](TODO.md): the current topic, next action, completed work, and deferred decisions. The user can maintain this list without Codex.
- [Project memory](memory/project_memory.md): detailed prior decisions and verified findings; consult the relevant sections.

## Maintained Files

- `TODO.md`: current task tracking and the return point after a topic change.
- `memory/project_memory.md`: long-term project knowledge and decisions. Tracked in Git; updated only when the user requests it.
- `plans/`: historical or active work plans.
- `works/`: tools, pipeline inputs, map sources, and analysis results.

## Local Files

- `prompts/`: the user's personal request and image archive, prepared when they cannot immediately write to Codex. Preserved locally, ignored by Git, and not automatically treated as current facts.
- `memory/local/`: machine-specific or personal temporary notes, kept locally and ignored by Git.

## Skills

Use the available `ck3-modding` and `ck3-modding-wiki` skills for relevant CK3 work. Their availability does not mean they contain every lesson discovered in this project; compiling missing knowledge with sources is a separate TODO item.

New repository skills belong in `.agents/skills/<skill-name>/SKILL.md` at the repository root. No repository skill has been created yet; existing user skills have not been copied or modified. Skills hold reusable knowledge, while project memory holds project decisions.

Discovery and location references: [OpenAI AGENTS.md documentation](https://learn.chatgpt.com/docs/agent-configuration/agents-md) and [skills documentation](https://learn.chatgpt.com/docs/build-skills).

## Editor Indentation

The repository [EditorConfig](../.editorconfig) defines indentation by filename. [VS Code folder settings](../.vscode/settings.json) disable automatic indentation detection for Yusseter MBP, so existing space-indented files cannot silently change the default tab preference. The sibling upstream and vanilla folders retain their own settings.

| File type | New indentation |
| --- | --- |
| CK3 scripts, GUI, font definitions, JSON, PowerShell, other text | Tabs, displayed as 4 columns |
| Python | 4 spaces |
| YAML and Markdown, including prompt files | 2 spaces |
| CK3 localization (`*_l_*.yml`) | 1 space |

The installed EditorConfig extension applies the filename-specific localization rule even when the file uses YAML language mode. Without it, the YAML fallback still uses spaces. Existing content, encoding/BOM, line endings, and formatter selection are unchanged; these settings do not run a bulk conversion. Reopen a file if an already-open editor retains its previous indentation setting.

[Extension recommendations](../.vscode/extensions.json) list EditorConfig for these rules and Markdownlint for the repository's existing Markdown checks. Recommendations do not install extensions automatically.

Behavior references: [VS Code indentation](https://code.visualstudio.com/docs/editing/codebasics#_indentation), [EditorConfig properties](https://editorconfig.org/#supported-properties), and [VS Code extension recommendations](https://code.visualstudio.com/docs/configure/extensions/extension-marketplace#_workspace-recommended-extensions).

## Organization Rules

- Write new maintained documentation in English. Keep user-facing conversation in Turkish and preserve historical notes and personal prompt content in their original language.
- Names and paths may change when needed; preserve content, function, and user ownership.
- Keep user-edited sources separate from generated outputs; tools must not overwrite them.
- Group reproducible outputs by system under `works/analysis/generated/`.
- Retire old paths only after updating active consumers and verifying content preservation.

Git index cleanup, staging, and commits follow the scope authorized for the current task; reorganizing files alone does not authorize deleting unrelated work.
