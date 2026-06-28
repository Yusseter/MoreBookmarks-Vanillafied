# MPE Landed Titles Conflict Decisions Summary

- conflict rows: 40
- unique conflict baronies: 29
- duplicate-key report rows: 0
- safe_to_auto_apply yes rows: 0
- landed_titles unchanged: True
- test_files unchanged: True

## Status Counts

- county_child_existing_barony_conflict: 11
- county_child_removed_not_in_mpe_overlay: 8
- missing_source_barony: 1
- target_barony_existing_province_conflict: 20

## Suggested Action Counts

- defer_until_overlay_expands_or_manual_add_definition_province: 8
- manual_decide_keep_existing_or_retarget_or_rename_mpe_barony: 31
- manual_source_title_needed_or_history_only_keep: 1

## Priority Counts

- high: 32
- medium: 8

## Interpretation

- `target_barony_existing_province_conflict` and `county_child_existing_barony_conflict` require a manual title/province identity decision.
- `missing_source_barony` has no source landed-title block in MPE for the imported province and must not be guessed from history comments alone.
- `county_child_removed_not_in_mpe_overlay` was intentionally left out because its source province was not part of the Add 1 overlay/import ID map.
- decision table: `works/analysis/generated/mpe_import_add_1/mpe_landed_titles_conflict_decisions.csv`
