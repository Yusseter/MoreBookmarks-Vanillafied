# Landed Title Capital Source Audit

- audited source-candidate rows: `657`
- audited current titles: `459`

## Source Candidate Status Counts

- `ambiguous_expected_current_capital`: `3`
- `mismatch`: `43`
- `missing_effective_capital`: `5`
- `missing_expected_current_capital_mapping`: `34`
- `ok`: `572`

## Current Title Aggregate Counts

- `ambiguous_no_source_ok`: `2`
- `mismatch_no_source_ok`: `15`
- `missing_effective_capital`: `2`
- `missing_mapping_no_source_ok`: `9`
- `ok_via_some_source`: `378`
- `source_conflict`: `53`

## High Signal

- titles with no validating source and effective-capital mismatch: `15`
- titles with conflicting source effective capitals: `53`
- main report: `landed_title_capital_source_audit.csv`
- title summary: `landed_title_capital_source_title_summary.csv`
- manual simple report: `landed_title_capital_manual_simple.csv`
- high-signal title mismatch report: `landed_title_capital_source_title_mismatches.csv`
- source-conflict title report: `landed_title_capital_source_title_source_conflicts.csv`
- source-candidate mismatch report: `landed_title_capital_source_candidate_mismatches.csv`

## Method

- audit target scope is `h_`, `e_`, `k_`, and `d_` titles
- current effective capital is direct `capital = c_*`; if absent, first descendant county is used
- source title is selected from the manual title relation and source-origin hint
- source effective capital is read with the same direct-or-first-descendant rule
- source effective capital is mapped back to current title id using `title_relation_master_manuel_new.csv`
- if multiple selected sources have different effective capitals, the title is flagged as `source_conflict` even if one source matches current
