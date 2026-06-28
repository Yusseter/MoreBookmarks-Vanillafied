# title_relation_master_manuel_new scope summary

- source file: `title_relation_master_manuel_new.csv`
- active scope: `h_`, `e_`, `k_`, `d_`, `c_`
- note: `b_` baronies are intentionally out of scope in this report
- note: because `title_relation_master_manuel_new.csv` has a 4th metadata column (`mask_scope_change`), validator was run against a derived 3-column input:
  - `works/analysis/generated/title_relation_manual_validation_new_scope_clean/title_relation_master_manuel_new_validation_input.csv`

## Row Counts

- total rows: `1350`
- `h_`: `2`
- `e_`: `64`
- `k_`: `75`
- `d_`: `318`
- `c_`: `891`

## Mapping Fill Status

- rows with non-blank `mod_title_id`: `1350`
- rows with blank `mod_title_id`: `0`
- rows containing `*there_is_no*`: `0`

## mask_scope_change Distribution

- `blank`: `1074`
- `added_by_mask`: `251`
- `was_added_by_mask`: `1`
- `was_removed_by_mask`: `24`

## Validator Result For This Scope

- output dir: `works/analysis/generated/title_relation_manual_validation_new_scope_clean/`
- summary: `title_relation_manual_validation_summary.md`
- errors: `2695`
- warnings: `673`

## Important Interpretation

- `error:source_title_missing_from_manual_vs_master = 2695`
  - this is expected subset noise
  - reason: `title_relation_master_manuel_new.csv` is a scoped working subset, not a full `3776` row manual table
- `warning:source_title_extra_in_manual_vs_master = 269`
  - tier split: `h=1; e=40; k=19; d=118; c=91`
  - mask split: `blank=2; added_by_mask=251; was_added_by_mask=1; was_removed_by_mask=15`
- `warning:parent_mapping_mismatch = 395`
  - warning only; not automatic mechanical error

## Small Active Error Pool

- `error:duplicate_mod_title_without_second = 0`
- worklist file:
  - `title_relation_master_manuel_new_duplicate_mod_worklist.csv`

## Landed Titles Duplicate Warnings

- `warning:source_title_duplicate_in_landed_titles = 5`
  - `k_goguryeo`
  - `k_dali`
  - `e_blue_horde`
  - `d_nf_tang_wang`
  - `d_nf_tang_ma`
- `warning:mod_title_duplicate_in_landed_titles = 4`
  - `e_blue_horde`
  - `d_ogrash`
  - `d_nf_tang_wang`
  - `d_nf_tang_ma`

## Practical Next Step

- continue only on `title_relation_master_manuel_new.csv`
- keep `h_/e_/k_/d_/c_` in scope
- keep `b_` and old `title_relation_master_manuel.csv` legacy cleanup out of scope for now
- duplicate-mod mechanical blocker in this scope is now `0`; next real review pool is `source_title_extra_in_manual_vs_master + parent_mapping_mismatch`
