# Landed Title Asil Mod Metadata Transfer Dry Run

- total_rows: 16368
- transfer_keys: definite_form, ruler_uses_title_name, can_be_named_after_dynasty, disable_regnal_numbers, landless, personal_relation_vassal, personal_relation_entry, can_create, can_create_on_partition, can_destroy, ai_primary_priority, cultural_names
- report: `landed_title_asil_mod_metadata_transfer_dry_run.csv`

## Status Counts
- `asil_mod_key_missing`: 13873
- `asil_mod_title_missing`: 1764
- `different`: 12
- `same`: 671
- `target_title_missing`: 48

## Key Counts
- `definite_form`: asil_mod_key_missing=1097, asil_mod_title_missing=147, same=116, target_title_missing=4
- `ruler_uses_title_name`: asil_mod_key_missing=1112, asil_mod_title_missing=147, same=101, target_title_missing=4
- `can_be_named_after_dynasty`: asil_mod_key_missing=1133, asil_mod_title_missing=147, same=80, target_title_missing=4
- `disable_regnal_numbers`: asil_mod_key_missing=1188, asil_mod_title_missing=147, same=25, target_title_missing=4
- `landless`: asil_mod_key_missing=1126, asil_mod_title_missing=147, same=87, target_title_missing=4
- `personal_relation_vassal`: asil_mod_key_missing=1211, asil_mod_title_missing=147, same=2, target_title_missing=4
- `personal_relation_entry`: asil_mod_key_missing=1209, asil_mod_title_missing=147, same=4, target_title_missing=4
- `can_create`: asil_mod_key_missing=1133, asil_mod_title_missing=147, same=80, target_title_missing=4
- `can_create_on_partition`: asil_mod_key_missing=1211, asil_mod_title_missing=147, same=2, target_title_missing=4
- `can_destroy`: asil_mod_key_missing=1212, asil_mod_title_missing=147, same=1, target_title_missing=4
- `ai_primary_priority`: asil_mod_key_missing=1122, asil_mod_title_missing=147, same=91, target_title_missing=4
- `cultural_names`: asil_mod_key_missing=1119, asil_mod_title_missing=147, different=12, same=82, target_title_missing=4

## Notes
- This is dry-run only; landed title source files are not modified.
- Existing target values are reported as `different`; they are not overwritten.
- `cultural_names` rows use `# Yusseter: REVIEW_ASIL_MOD_CULTURAL_NAMES` in the review_comment column.
- Asil mod blocks containing `title:*` references use `# Yusseter: REVIEW_ASIL_MOD_TITLE_REF` in the review_comment column.
