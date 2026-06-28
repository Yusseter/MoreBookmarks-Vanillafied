# Locator Fix Candidate Report

- output: `locator_fix_candidates_landed_problem_non_building.csv`
- source compact problem file: `locator_position_problem_rows_compact_landed_barony_only.csv`
- source compact near-same file: `locator_position_near_same_province_compact_landed_barony_only.csv`
- compact source rows: `76`
- near-same source rows: `896`
- problem target rows after excluding plain building locators: `73`
- near-same far target rows after excluding plain building locators: `77`
- total target rows: `150`
- non-special near-same distance min: `8`
- special-building near-same distance min: `12`
- transform: `floor_height_minus_1_minus_z`
- live map object files modified: `0`

## By File

- `activities.txt`: `52`
- `combat_locators.txt`: `19`
- `player_stack_locators.txt`: `11`
- `siege_locators.txt`: `9`
- `special_building_locators.txt`: `59`

## By Confidence

- `high`: `128`
- `medium`: `12`
- `low`: `10`

## By Candidate Status

- `inside_exact`: `150`

## Notes

- This is a dry-run report only; no locator source file is changed.
- `building_locators.txt` is excluded from the target set and used only as an anchor when its current position is `inside_exact`.
- `# Yusseter: ... building_locators.txt` near-same marker rows are excluded from the target set.
- `special_building_locators.txt` is included but uses stricter high-confidence border checks.
