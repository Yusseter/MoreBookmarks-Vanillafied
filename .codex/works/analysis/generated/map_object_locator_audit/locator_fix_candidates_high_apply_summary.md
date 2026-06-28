# Locator Fix Candidate High-Confidence Apply Report

- source candidates: `locator_fix_candidates_landed_problem_non_building.csv`
- output report: `locator_fix_candidates_high_apply_report.csv`
- apply mode: `apply`
- selected high-confidence rows: `128`
- changed/would_change rows: `128`
- skipped rows: `0`
- marker added to changed position lines: `# Yusseter: Auto fixed from locator candidate`
- live locator files modified: `5`

## By Status

- `changed`: `128`

## By File

- `activities.txt`: changed=45
- `combat_locators.txt`: changed=18
- `player_stack_locators.txt`: changed=10
- `siege_locators.txt`: changed=9
- `special_building_locators.txt`: changed=46

## Notes

- Only `confidence=high` and `candidate_status=inside_exact` rows are selected.
- `building_locators.txt` and `# Yusseter: ... building_locators.txt` candidates are excluded.
- Only the `position` line is changed; rotation, scale, comments on other lines, and block order are preserved.
