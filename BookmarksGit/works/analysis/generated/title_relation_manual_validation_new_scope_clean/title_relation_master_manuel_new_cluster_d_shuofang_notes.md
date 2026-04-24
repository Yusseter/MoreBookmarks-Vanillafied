# d_shuofang cluster notes

- source cluster: `d_shuofang`
- row count: `5`
- distinct mod parents: `d_xia; d_longxi_china; k_xia_china`

## Rows

- `c_huaiyuan -> c_xingqing`
  source: `e_xi_xia > k_xia > d_shuofang > c_huaiyuan`
  mod: `h_china > e_xi_xia > k_xia_china > d_xia > c_xingqing`
- `c_huizhou -> c_huizhou_china`
  source: `e_xi_xia > k_xia > d_shuofang > c_huizhou`
  mod: `h_china > e_yongliang > k_longxi_china > d_longxi_china > c_huizhou_china`
- `c_lingzhou -> c_shunzhou`
  source: `e_xi_xia > k_xia > d_shuofang > c_lingzhou`
  mod: `h_china > e_xi_xia > k_xia_china > d_xia > c_shunzhou`
- `c_wulan -> c_huizhou_china (second)`
  source: `e_xi_xia > k_xia > d_shuofang > c_wulan`
  mod: `h_china > e_yongliang > k_longxi_china > d_longxi_china > c_huizhou_china`
- `d_shuofang -> d_shuofang_china`
  source: `e_xi_xia > k_xia > d_shuofang`
  mod: `h_china > e_xi_xia > k_xia_china > d_shuofang_china`

## Reading

- this is not a simple one-parent rename
- the cluster fans out into at least three mod-parent buckets:
  - `d_xia`: `2`
  - `d_longxi_china`: `2`
  - `k_xia_china`: `1`
- practical consequence: `d_shuofang` cluster should be reviewed as a split-migration problem, not as a single exact counterpart decision
