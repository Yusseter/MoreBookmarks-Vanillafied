# Map Object Locator Position Audit

- selected transform: `floor_height_minus_1_minus_z`
- total locator rows: `71999`
- alias locator rows: `36`
- alias target locator rows: `36`
- alias donor locator rows: `0`

## Status Counts

- `inside_exact`: `70935`
- `missing_pixels_in_png`: `10`
- `near_same_province`: `956`
- `outside_wrong_province`: `98`

## Calibration

- `round_direct`: exact `397` / total `71999`; in-bounds `71999`
- `floor_direct`: exact `394` / total `71999`; in-bounds `71999`
- `round_height_minus_z`: exact `70859` / total `71999`; in-bounds `71999`
- `floor_height_minus_z`: exact `70802` / total `71999`; in-bounds `71999`
- `round_height_minus_1_minus_z`: exact `70913` / total `71999`; in-bounds `71999`
- `floor_height_minus_1_minus_z`: exact `70935` / total `71999`; in-bounds `71999` selected

## By File

- `activities.txt`: `11682` rows; inside_exact=11526, missing_pixels_in_png=1, near_same_province=147, outside_wrong_province=8
- `building_locators.txt`: `11687` rows; inside_exact=11679, missing_pixels_in_png=1, near_same_province=2, outside_wrong_province=5
- `combat_locators.txt`: `12632` rows; inside_exact=12363, missing_pixels_in_png=2, near_same_province=233, outside_wrong_province=34
- `player_stack_locators.txt`: `12632` rows; inside_exact=12509, missing_pixels_in_png=2, near_same_province=86, outside_wrong_province=35
- `siege_locators.txt`: `11682` rows; inside_exact=11436, missing_pixels_in_png=1, near_same_province=240, outside_wrong_province=5
- `special_building_locators.txt`: `11684` rows; inside_exact=11422, missing_pixels_in_png=3, near_same_province=248, outside_wrong_province=11

## MPE Alias Status Counts

- `inside_exact`: `36`

## Notes

- This audit is read-only for live CK3 data files.
- `near_same_province` means the locator point is outside the exact province pixel, but the province color exists within the configured search radius.
- `game_object_layers.txt` and `great_wall_china.txt` are intentionally not included in this first audit pass.
