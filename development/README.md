# Development Resources

The playable mod is in `BookmarksGit/`. This directory contains its supporting tools and data; it is not loaded by the game.

## Layout

| Directory | Purpose |
| --- | --- |
| `tools/` | Reusable audits, transformations, and controlled application commands |
| `pipeline_inputs/` | Permanent mapping tables, decisions, exceptions, and scope definitions |
| `map_data_sources/` | Source maps and user-edited visual documents |
| `analysis/generated/` | Reproducible outputs, grouped by system and ignored by Git |
| `analysis/reports/` | Selected findings and validation reports |
| `archive/` | Historical evidence and reference snapshots |
| `local/` | Private working notes, plans, request archives, and local record history; ignored by the main repository |

Start with the [tool guide](tools/README.md), [map refresh workflow](map_data_sources/README.md), and [analysis guide](analysis/README.md).
Tools resolve external source folders from explicit arguments or documented defaults; see [the workspace](../Yusseter-MBP-Development.code-workspace) for the current upstream and vanilla locations.

## Data Safety

- Keep `map_data_sources/manual_sources/` and `pipeline_inputs/title_relations/curated_title_relations.csv` under manual control. Generators must not overwrite them.
- Pipeline inputs affect behavior and require review; do not treat them as disposable generated reports.
- Do not copy generated maps into `BookmarksGit/` without the corresponding definition and mapping checks.
- Some legacy commands apply changes directly. Inspect a command's documentation before running it; do not assume every command defaults to dry-run.
- Historical snapshots stay unchanged. Two relation tools explicitly read `archive/title_relations/` as reference baselines; other archive content is not an active input.
- Preserved generated reports are snapshots, not proof that the current inputs and tool revisions have been validated. Regenerate the relevant chain before relying on freshness-sensitive outputs.
- Tools write execution notes beside their generated reports, not into personal working records.

## Editor Indentation

[EditorConfig](../.editorconfig) and [VS Code folder settings](../.vscode/settings.json) control new indentation without reformatting existing files.

| File type | New indentation |
| --- | --- |
| CK3 scripts, GUI, fonts, JSON, PowerShell, other text | Tabs, displayed as 4 columns |
| Python | 4 spaces |
| YAML and Markdown | 2 spaces |
| CK3 localization (`*_l_*.yml`) | 1 space |

[Recommended extensions](../.vscode/extensions.json) provide EditorConfig and Markdownlint support. Encoding, BOMs, and line endings are preserved; sibling workspace folders retain their own settings.
