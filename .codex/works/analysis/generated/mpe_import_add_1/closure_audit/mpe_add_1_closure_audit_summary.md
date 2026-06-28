# MPE Add 1 Closure Audit

Read-only audit across active MPE landed scope, map/province data, history, locators, localization, and old-id residue.

## Scope
- hierarchy report rows: `241`
- report title ids: `297`
- active report titles in landed_titles: `274`
- inactive/report-only title ids: `23`
- active MPE baronies: `196`
- active MPE counties: `59`
- active MPE duchies: `17`
- active MPE provinces: `196`

## Issue Counts
- `error`: `55`
- `warning`: `90`
- `info`: `25`

## Categories
- `landed_titles`: `1`
- `localization`: `17`
- `localization_adj`: `90`
- `province_history`: `37`
- `scope_excluded_title`: `23`
- `title_history`: `2`

## Hierarchy Report Status Counts
- `added_barony_to_existing_county`: `2`
- `added_county_under_existing_duchy`: `63`
- `added_duchy_under_existing_parent`: `24`
- `already_present`: `95`
- `county_child_already_present`: `13`
- `county_child_existing_barony_conflict`: `11`
- `county_child_removed_not_in_mpe_overlay`: `8`
- `missing_source_barony`: `1`
- `target_barony_existing_province_conflict`: `20`
- `validation`: `4`

## Target Action Counts
- `(blank)`: `8`
- `existing_manual_mpe_keep_target_id`: `2`
- `new_placeholder_assignment`: `158`
- `pass`: `4`
- `target_same_id_skip`: `69`

## Localization Source Rule Used
- Current source: BookmarksGit `localization/**/*_l_english.yml` with first meaningful header `l_english:`.
- MPE source fallback: MPE `localization/**/*_l_english.yml` with first meaningful header `l_english:`.
- Parent fallback: `Yusseter MoreBookmarksPlus/english/**/*_l_english.yml` with first meaningful header `l_english:`.
- Non-English files are not accepted.

## Output
- issues CSV: `F:\Storage\Codding\git\Crusader Kings III\Yusseter MoreBookmarksPlus\BookmarksGit\works\analysis\generated\mpe_import_add_1\closure_audit\mpe_add_1_closure_audit_issues.csv`
