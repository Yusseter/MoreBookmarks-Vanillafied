# MPE Levi History Donor Audit

- active MPE county rows checked: `60`
- counties needing user Levi donor mapping: `6`
- counties with Levi donor but current history still MPE-sourced: `10`

## Status Counts
- `has_levi_donor_but_current_history_still_mpe_sourced`: `10`
- `needs_user_levi_donor_mapping`: `6`
- `ok_or_already_levi_sourced`: `44`

## Missing User Donor Mapping
- `c_anket` capital `b_mozdok` province `13318` current source `mpe_source:21446`
- `c_avaria` capital `b_kubachi` province `13342` current source `current_capital_history`
- `c_darginia` capital `b_zirichgeran` province `13343` current source `mpe_source:21475`
- `c_lezgin` capital `b_lezgin` province `13347` current source `mpe_source:21478`
- `c_maskut` capital `b_kuba` province `13350` current source `mpe_source:21482`
- `c_ubykh` capital `b_ubykh` province `13313` current source `mpe_source:21441`

## Needs Reapply From Levi
- `c_cabardinia` should use Levi `c_cabardinia` capital `b_cabarda` province `603`; current source `mpe_source:21424`
- `c_digoria` should use Levi `c_cabardinia` capital `b_cabarda` province `603`; current source `donor_county:c_cabardinia:mpe_source:21424`
- `c_durdzukia` should use Levi `c_philan` capital `b_kumukh` province `675`; current source `donor_county:c_philan:mpe_source:21450`
- `c_iron` should use Levi `c_cabardinia` capital `b_cabarda` province `603`; current source `donor_county:c_cabardinia:mpe_source:21424`
- `c_kuban` should use Levi `c_kuban` capital `b_kuban` province `5335`; current source `mpe_source:21394`
- `c_malkhia` should use Levi `c_philan` capital `b_kumukh` province `675`; current source `donor_county:c_philan:mpe_source:21450`
- `c_ossetia` should use Levi `c_cabardinia` capital `b_cabarda` province `603`; current source `donor_county:c_cabardinia:mpe_source:21424`
- `c_peshe` should use Levi `c_kuban` capital `b_kuban` province `5335`; current source `donor_county:c_kuban:mpe_source:21394`
- `c_philan` should use Levi `c_philan` capital `b_kumukh` province `675`; current source `mpe_source:21450`
- `c_simsir` should use Levi `c_philan` capital `b_kumukh` province `675`; current source `donor_county:c_philan:mpe_source:21450`
