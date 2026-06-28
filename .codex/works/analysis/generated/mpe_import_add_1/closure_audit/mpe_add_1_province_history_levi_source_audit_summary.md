# MPE Add 1 Province History Current-State Donor Audit

- rows: `145`
- current county capital rows: `25`
- current non-capital rows: `120`
- missing/mismatch candidates: `0`
- target repo: `F:\Storage\Codding\git\Crusader Kings III\Yusseter MoreBookmarksPlus\BookmarksGit`
- authoritative base repo for explicit `asil_mod` donor fallback: `F:\Storage\Codding\git\Crusader Kings III\Leviathonlx MoreBookmarks-Plus\BookmarksGit`

## By source_match_status

- `accepted_deviation`: `2`
- `matches_source`: `23`
- `needs_manual_review`: `2`
- `not_checked`: `109`
- `scope_excluded_or_retargeted`: `9`

## By issue

- `active_landed_province_differs`: `9`
- `explicit_donor_has_no_top_level_culture_religion`: `2`
- `non_capital_culture_religion_accepted`: `2`
- `non_capital_holding_history_ok`: `109`
- `ok`: `23`

## Rule

- County capital status is recalculated from current `common/landed_titles/00_landed_titles.txt`.
- Explicit `# Yusseter: ... donor .../ID` comments in current province history override stale import-report donors.
- Non-capital culture/religion is accepted by project decision and is not a blocker.
- Donors with no top-level culture/religion are manual-review rows, not auto-fix candidates.
