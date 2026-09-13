import csv
from collections import Counter
from pathlib import Path


ACCEPT_UPSTREAM = {
    ("b_taganrog", "cultural_names"): "restored unchanged upstream cultural_names metadata",
    ("e_mongolia", "__child_order__"): "accepted upstream k_tyva integration; all current child titles exist",
    ("k_anatolia", "cultural_names"): "upstream added a new name-list key without dropping current keys",
    ("k_dornogovi", "__child_order__"): "same child set reordered to upstream order",
    ("k_guishi", "__child_order__"): "same child set reordered to upstream order",
    ("k_xia", "__child_order__"): "same child set reordered to upstream order",
}

KEEP_CUSTOM = {
    ("b_sipura", "__parent__"): "same-ID collision: current province 12825 differs from upstream province 10718",
    ("e_dai_viet", "__child_order__"): "k_tay_bac is absent current-side; d_lam_tay is certified orijinal_dogu under k_viet",
    ("e_burma", "__child_order__"): "current Southeast Asia hierarchy is a deliberate Yusseter divergence",
    ("e_great_liao", "__child_order__"): "current k_raole hierarchy follows the earlier manual parent decision",
    ("e_xi_xia", "__child_order__"): "upstream-only k_hexi/k_dongxia have no compatible current hierarchy mapping",
    ("k_chiang_hung", "__child_order__"): "upstream children lack tier-compatible current mappings; current children are custom",
    ("k_tamilakam", "__child_order__"): "d_handumans was deliberately rewritten and moved to k_malayadvipa; k_pandya is integrated separately",
    ("k_xia_china", "__child_order__"): "current children follow the established Yusseter parent-selection table",
}


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_rows(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    script_path = Path(__file__).resolve()
    repo_root = script_path.parents[3]
    audit_dir = repo_root / ".codex/works/analysis/generated/upstream_merge_audit"
    identity_path = (
        repo_root
        / ".codex/works/analysis/generated/landed_title_source_identity_empire_closure/landed_title_source_identity_audit.csv"
    )
    comment_path = (
        repo_root
        / ".codex/works/analysis/generated/landed_title_localized_as_comment_transfer/landed_title_localized_as_comment_transfer_dry_run.csv"
    )

    source_decisions = {
        row["title_id"]: row.get("source_decision", "")
        for row in read_rows(identity_path)
    }
    comment_ready = [
        row for row in read_rows(comment_path) if row.get("status") == "ready_apply"
    ]
    if comment_ready:
        raise RuntimeError(
            f"exact-source comment transfer still has {len(comment_ready)} ready rows"
        )

    manual_rows = read_rows(audit_dir / "landed_title_manual_review.csv")
    resolved: list[dict[str, str]] = []
    user_rows: list[dict[str, str]] = []

    for row in manual_rows:
        title_id = row["current_title_id"]
        key = row["key"]
        pair = (title_id, key)
        source_decision = source_decisions.get(title_id, "")

        if key == "__opening_comment__":
            resolution = "accept_current_comment_state"
            evidence = "informational only; exact-source comment transfer has ready_apply=0"
        elif pair in ACCEPT_UPSTREAM:
            resolution = "accept_upstream_resolution"
            evidence = ACCEPT_UPSTREAM[pair]
        elif source_decision == "orijinal_dogu":
            resolution = "keep_current_original_east_source"
            evidence = "prior source-identity audit selected orijinal_dogu"
        elif pair in KEEP_CUSTOM:
            resolution = "keep_current_custom_resolution"
            evidence = KEEP_CUSTOM[pair]
        else:
            resolution = "requires_user_decision"
            evidence = "no certified rule matched"

        output = {
            **row,
            "source_decision": source_decision,
            "resolution": resolution,
            "resolution_evidence": evidence,
            "requires_user_decision": "yes" if resolution == "requires_user_decision" else "no",
        }
        resolved.append(output)
        if output["requires_user_decision"] == "yes":
            user_rows.append(output)

    fields = list(resolved[0]) if resolved else [
        "current_title_id",
        "upstream_title_id",
        "key",
        "resolution",
        "resolution_evidence",
        "requires_user_decision",
    ]
    write_rows(audit_dir / "landed_title_manual_review_resolved.csv", resolved, fields)
    write_rows(audit_dir / "landed_title_requires_user_decision.csv", user_rows, fields)

    candidate_rows = read_rows(audit_dir / "landed_title_candidate_take_upstream.csv")
    candidate_resolved = []
    for row in candidate_rows:
        is_comment = row.get("key") == "__opening_comment__"
        candidate_resolved.append(
            {
                **row,
                "resolution": (
                    "do_not_bulk_apply_use_exact_comment_transfer"
                    if is_comment
                    else "requires_user_decision"
                ),
                "resolution_evidence": (
                    "exact-source comment transfer has ready_apply=0"
                    if is_comment
                    else "non-comment candidate was not covered by a safe apply decision"
                ),
                "requires_user_decision": "no" if is_comment else "yes",
            }
        )
    candidate_fields = list(candidate_resolved[0]) if candidate_resolved else fields
    write_rows(
        audit_dir / "landed_title_candidate_take_upstream_resolved.csv",
        candidate_resolved,
        candidate_fields,
    )

    candidate_user_count = sum(
        row["requires_user_decision"] == "yes" for row in candidate_resolved
    )
    counts = Counter(row["resolution"] for row in resolved)
    summary = [
        "# Landed Title Review Resolution Summary",
        "",
        f"- raw manual-review rows: `{len(manual_rows)}`",
        f"- resolved without user decision: `{len(manual_rows) - len(user_rows)}`",
        f"- requires user decision: `{len(user_rows)}`",
        f"- raw candidate rows: `{len(candidate_rows)}`",
        f"- candidate rows requiring user decision: `{candidate_user_count}`",
        f"- exact comment ready_apply: `{len(comment_ready)}`",
        "",
        "## Resolutions",
        "",
    ]
    summary.extend(f"- `{key}`: `{value}`" for key, value in sorted(counts.items()))
    (audit_dir / "landed_title_review_resolution_summary.md").write_text(
        "\n".join(summary) + "\n", encoding="utf-8"
    )

    print(f"manual_rows={len(manual_rows)}")
    print(f"resolved_without_user={len(manual_rows) - len(user_rows)}")
    print(f"requires_user_decision={len(user_rows)}")
    print(f"candidate_rows={len(candidate_rows)}")
    print(f"candidate_requires_user_decision={candidate_user_count}")

    if user_rows or candidate_user_count:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
