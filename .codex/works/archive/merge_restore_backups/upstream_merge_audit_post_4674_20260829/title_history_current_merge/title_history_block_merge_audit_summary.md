# Title History Upstream Merge Audit

- source mode: explicit_revisions
- base revision: 786ef415b
- ours revision: 9453e2162c5c6517aea0cf20c9ac75f8046b4829
- upstream revision: 4674b5e4084187cfb970015ea5f1997a14a6cd67
- current landed title IDs: 17723
- upstream landed title IDs: 19019
- mapped upstream IDs: 17547
- ambiguous reverse mappings: 30
- logical base blocks: 2342
- logical ours blocks: 2455
- logical upstream blocks: 2338
- safe candidates: 16
- manual review rows: 109
- unmapped raw blocks: 624

## Decisions

- `both_same`: 1928
- `keep_ours_addition`: 95
- `keep_ours_change`: 295
- `keep_ours_exact_only_both_same`: 12
- `manual_both_modified`: 3
- `manual_duplicate_logical_title`: 105
- `manual_ours_modified_upstream_deleted`: 1
- `take_upstream_change`: 15
- `take_upstream_deletion`: 1

## Mapping Status

- `ambiguous_multiple_upstream_titles`: 113
- `mapped`: 15446
- `no_upstream_counterpart`: 2164

## File Block Counts

- `BookmarksGit/history/titles/00_ASIA_CHINA.txt`: base=361, ours=442, upstream=360
- `BookmarksGit/history/titles/00_ASIA_JAPAN.txt`: base=88, ours=88, upstream=88
- `BookmarksGit/history/titles/00_ASIA_NORTH.txt`: base=965, ours=979, upstream=962
- `BookmarksGit/history/titles/z00_ADEVELOPMENT.txt`: base=1017, ours=1054, upstream=1015

## Safety

- This tool is read-only and does not modify title-history files.
- Safe candidates require a unique current landed-title counterpart.
- Duplicate logical titles, ambiguous reverse mappings, and both-modified blocks are not auto-resolved.
