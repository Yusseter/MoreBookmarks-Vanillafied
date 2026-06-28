# MPE Add 1 Current Map Data Audit

- import rows checked: `205`
- provinces.png size: `9216x4608`
- status ok: `196`
- status issue: `9`
- target RGB missing from provinces.png: `0`
- target duplicate RGB rows: `0`
- target IDs in blocking default.map categories: `9`
- old MPE IDs still in definition where old_id != target_id: `0`

## Default Map Category Hits For Target IDs

- `impassable_mountains`: `9`

## Issue Counts

- `target_id_in_blocking_default_map_category`: `9`

## Notes

- This is a current-state pixel audit: each target definition RGB must appear at least once in current provinces.png.
- `old_mpe_id_still_in_definition` is informational for same-id/current reused IDs; rows with old_id != target_id are counted separately above.
