# Project TODO

Updated: 2026-09-22. This file tracks the current work sequence; historical plans and project memory remain separate. The user and Codex can maintain the same list.

## How To Use

- Check an item when it is complete and link its supporting file or report.
- State the exact decision needed for an item awaiting user input; assumptions alone do not complete it.
- Record the return point when taking a side task. On resumption, repeat checks only when their evidence has changed or a new concern requires verification.
- Maintain this list before introducing another task tracker or separate status file.

## Current Sequence

Scope: the remaining topics from the August 2 project organization request. The user authorized continuing in this order and asking about decisions when needed. Next item: `TAB-01`.

- [x] `ORG-01`: Add project working rules in [AGENTS.md](../AGENTS.md), keep memory separate, and define how existing CK3 skills and future knowledge additions should be used.
- [x] `TODO-01`: Track completed, upcoming, and deferred work in this single list.
- [ ] `TAB-01`: Define file-type-aware tab/space settings for the Yusseter project folder. The user prefers literal tabs; preserve format requirements such as Python and localization indentation. Check effective editor settings first; avoid bulk reformatting and changes to upstream or vanilla editor settings.
- [ ] `SKILL-01`: Compare verified general CK3 lessons with the existing `ck3-modding` and `ck3-modding-wiki` content. Prepare reusable, sourced guidance for gaps; choose an existing or separate skill according to scope. Do not turn project-specific ID decisions into general engine rules.
- [ ] `CUSTOM-01`: Inventory personal changes unrelated to projection with the user. Fonts, intentional map edits, and title colors are starting examples; `# Yusseter:` comments are not a complete inventory. Do not extract, revert, or move these changes to another mod until intent and ownership are clear.

## Previously Completed Organization

- [x] Organized `.gitattributes`, `.gitignore`, and the [three-root workspace](../Yusseter-MBP-Development.code-workspace).
- [x] Separated permanent inputs, user-edited sources, archives, and generated analysis using the [works layout](works/README.md); removed the obsolete test mirror.
- [x] Documented reproducible map source refresh in the [source README](works/map_data_sources/README.md); application to the live map remains a separate operation.
- [x] Renamed project memory to [project_memory.md](memory/project_memory.md) and standardized [plan naming](plans/README.md).
- [x] Grouped accumulated changes and completed the local commit sequence. The [commit organization plan](plans/2026.09.13_12.53-commit-organization.md) is a historical record, not the current pending task list.

## Deferred Work

- Prompt templates, prompt type fields, and custom path notation: the user chose to keep the existing prompt system for now. The archive holds requests prepared when the user cannot immediately send them to Codex.
- `BookmarksGit/fonts/fonts.font`: the user's edit remains on hold.
- Mod issue review: paused while project organization resumes. The last completed pass was closure verification after `e722e9ccb`; refresh checks when relevant inputs change.
- Eleven uncertain higher-tier title relations remain under manual review. Runtime checks and outdated province tracking evidence are also incomplete; organization work does not resolve them.
- Errors also present in upstream remain deferred to a separate final cleanup phase by user decision. Evidence is retained in [maintained reports](works/analysis/reports/) and [project memory](memory/project_memory.md).

## Return Point

2026-09-22: Commit organization led into a new upstream merge, game testing, and issue review without a recorded return to the remaining organization topics. The user's reminder restored the sequence above. This documentation step requires no game source changes or audit regeneration.
