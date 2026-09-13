# Upstream Merge Audit Summary

## Git Anchors
- branch: `manual-upstream-sync-2026-06-28`
- base_candidate: `786ef415bde03ccd702590e64ce13ac205fb4744`
- ours: `9453e2162c5c6517aea0cf20c9ac75f8046b4829`
- theirs: `4674b5e4084187cfb970015ea5f1997a14a6cd67`
- baseline_status: `git_merge_base_not_yet_semantically_certified`
- upstream_commits_in_range: 2
- net_changed_files: 100
- currently_unmerged_files: 14

## Landed Title Inventory
- title_rows: 17724
- changed_property_rows: 3332
- base_duplicate_title_ids: 8
- base_extra_title_definitions: 8
- ours_duplicate_title_ids: 7
- ours_extra_title_definitions: 7
- theirs_duplicate_title_ids: 8
- theirs_extra_title_definitions: 8
- working_duplicate_title_ids: 7
- working_extra_title_definitions: 7

### Title Status
- `manual_mapping_review`: 207
- `manual_review`: 12
- `no_action`: 13638
- `preserved_yusseter`: 1696
- `verify_current_resolution`: 9
- `yusseter_only_no_upstream_counterpart`: 2162

### Property Classification
- `both_changed_same`: 2
- `conflict_kept_yusseter`: 10
- `pending_upstream_change`: 23
- `preserved_yusseter_change`: 3275
- `resolved_take_upstream`: 22
- `unchanged`: 75479

### Mapping Status
- `ambiguous_multiple_upstream_titles`: 114
- `ambiguous_reverse_mapping`: 65
- `duplicate_definition_manual_review`: 8
- `mapped`: 15355
- `no_upstream_counterpart`: 2162
- `upstream_added_without_current_mapping`: 4
- `upstream_changed_without_current_mapping`: 16

## Net Changed File Domains
- `common_script`: 42
- `gfx`: 4
- `history`: 12
- `landed_titles`: 1
- `localization`: 15
- `map_data`: 4
- `other`: 14
- `province_history`: 1
- `title_history`: 7

## Safety
- This run is audit-only; CK3 source files and the Git index are not modified.
- `candidate_take_upstream` is not an automatic apply decision.
- Hierarchy, child order, capitals, province ids, behavioral blocks, and title references remain manual-review items.
- The next gate is review of `manual_review` and `candidate_take_upstream` rows before any source edit.
