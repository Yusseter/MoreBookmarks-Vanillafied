# title_relation_master_manuel_new extra no summary

- source file: `title_relation_master_manuel_new.csv`
- focus: extra rows where `is_same_title_id = no`
- total worklist rows: `23`
- `added_by_mask`: `21`
- blank `mask_scope_change`: `2`
- with `parent_mapping_mismatch`: `13`
- without `parent_mapping_mismatch`: `10`

## Key Reading

- these 23 rows are the smallest active non-barony manual decision pool inside `title_relation_master_manuel_new.csv`
- `13` rows need parent-chain review first
- `10` rows are structurally easier because they do not currently raise `parent_mapping_mismatch`
- the two blank-mask rows are `c_shanzhou_mbp -> c_shanzhou` and `c_suzhou_mbp -> c_suzhou`

## Files

- full worklist: `title_relation_master_manuel_new_extra_no_worklist.csv`
- high-priority parent-mismatch subset: `title_relation_master_manuel_new_extra_no_parent_mismatch_yes.csv`
- lower-risk subset: `title_relation_master_manuel_new_extra_no_parent_mismatch_no.csv`
