# MPE Add 1 Consistency Final Validation

# MPE Add 1 Consistency Audit (manual)

- landed_titles brace depth: `0`
- duplicate title rows: `6`
- duplicate province rows: `0`
- alias donor active title blockers: `0`
- locator target/comment issues: `0`
- active history issues: `0`
- localization missing in all sources: `0`
- test_files tree hash: `0E8250C8DFB20B0653AEB9899FE6C538EDC467B087155C8F97E03BADCA3E3DAD`

## Known Localization Checks

- `b_khunzakh`: `source_available_or_current_present`
- `c_majar`: `source_available_or_current_present`
- `cn_iryston`: `source_available_or_current_present`

## Extra Validation

- non-capital province history rows checked: `55`
- non-capital top-level culture/religion problems: `0`
- non-capital missing history blocks: `0`
- superseded alias donor playable/title blockers: `0`
- global duplicate title rows: `6`
- MPE/action blocker duplicate province rows: `0`
- localization missing in all sources: `0`
- active localization missing in all sources: `0`

## Notes

- `test_files` was not written by this pipeline; the tree hash stayed `0E8250C8DFB20B0653AEB9899FE6C538EDC467B087155C8F97E03BADCA3E3DAD`.
- Superseded alias donor IDs `12922 13359 13360 13361 13362` are now `impassable_mountains` and have no active landed title association.
- `b_khunzakh`, `c_majar`, and `cn_iryston` were added to current English localization from MPE source.
- The remaining 6 duplicate title rows are global pre-existing titles, not MPE alias/blocker rows.

## Placeholder Residual Cleanup

- Superseded alias donor placeholder IDs checked: `12922 13359 13360 13361 13362`
- Remaining references outside `definition.csv` and `default.map`: `0`
- Removed province terrain lines: `4`
- Removed province history blocks: `4`
- Removed map object locator donor blocks: `24`
- Cleanup report: `mpe_alias_placeholder_residual_cleanup_report.csv`

