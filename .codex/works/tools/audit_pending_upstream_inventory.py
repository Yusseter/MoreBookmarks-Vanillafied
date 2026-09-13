#!/usr/bin/env python3
"""Build a reproducible, read-only inventory of pending upstream changes."""

from __future__ import annotations

import argparse
import csv
import subprocess
from collections import defaultdict
from pathlib import Path


LIVE_PREFIX = "BookmarksGit/"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--base", required=True)
    parser.add_argument("--ours", default="HEAD")
    parser.add_argument("--theirs", default="upstream/main")
    parser.add_argument("--previous-upstream", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout


def resolve(repo: Path, revision: str) -> str:
    return git(repo, "rev-parse", revision).strip()


def changed_paths(repo: Path, revision: str) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    output = git(repo, "diff-tree", "--no-commit-id", "--name-status", "-r", "-M", revision)
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            rows.append((parts[0], parts[-1].replace("\\", "/")))
    return rows


def net_changed_paths(repo: Path, base: str, theirs: str) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for line in git(repo, "diff", "--name-status", "-M", f"{base}..{theirs}").splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            rows.append((parts[0], parts[-1].replace("\\", "/")))
    return rows


def worktree_paths(repo: Path) -> set[str]:
    paths: set[str] = set()
    records = git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all").split("\0")
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if not record:
            continue
        status = record[:2]
        path = record[3:].replace("\\", "/")
        if status[0] in {"R", "C"} and index < len(records):
            path = records[index].replace("\\", "/")
            index += 1
        paths.add(path)
    return paths


def classify(path: str) -> tuple[str, str, str]:
    relative = path.removeprefix(LIVE_PREFIX).lower()
    rules = [
        ("map_data/provinces.png", "binary_map", "high", "three_way_semantic_and_visual_audit_before_merge"),
        ("gfx/map/map_object_data/", "map_object_locators", "high", "three_way_semantic_and_visual_audit_before_merge"),
        ("history/characters/", "character_history", "high", "identity_and_lifetime_audit_before_merge"),
        ("history/titles/", "title_history", "high", "holder_liege_and_identity_audit_before_merge"),
        ("history/provinces/", "province_history", "high", "field_and_bookmark_semantics_audit_before_merge"),
        ("common/on_action/", "on_action", "high", "semantic_review_before_merge"),
        ("common/scripted_effects/", "scripted_effects", "high", "semantic_review_before_merge"),
        ("common/religion/", "religion", "high", "semantic_review_before_merge"),
        ("common/landed_titles/", "landed_titles", "high", "four_way_semantic_audit_before_merge"),
        ("common/dynasties/", "dynasties", "medium", "identity_chain_audit_before_merge"),
        ("common/coat_of_arms/", "coat_of_arms", "medium", "identity_asset_and_duplicate_audit_before_merge"),
        ("localization/", "localization", "medium", "identity_and_visibility_audit_before_merge"),
    ]
    for prefix, system, risk, recommendation in rules:
        if relative == prefix or relative.startswith(prefix):
            return system, risk, recommendation
    return "other_live_content", "medium", "semantic_review_before_merge"


def write_csv(path: Path, rows: list[dict[str, str]], default_field: str) -> None:
    fields = list(rows[0]) if rows else [default_field]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    repo = args.repo_root.resolve()
    base, ours = resolve(repo, args.base), resolve(repo, args.ours)
    theirs, previous = resolve(repo, args.theirs), resolve(repo, args.previous_upstream)
    merge_base = git(repo, "merge-base", ours, theirs).strip()
    if merge_base != base:
        raise RuntimeError(f"Expected merge base {base}, found {merge_base}")

    new_commits = set(git(repo, "rev-list", "--reverse", f"{previous}..{theirs}").splitlines())
    commit_lines = git(repo, "log", "--reverse", "--format=%H%x1f%h%x1f%aI%x1f%s", f"{base}..{theirs}").splitlines()
    touches: dict[str, list[str]] = defaultdict(list)
    new_touches: set[str] = set()
    commits: list[dict[str, str]] = []
    for line in commit_lines:
        commit, short, authored_at, subject = line.split("\x1f", 3)
        paths = changed_paths(repo, commit)
        live = sorted(path for _, path in paths if path.startswith(LIVE_PREFIX))
        for path in live:
            touches[path].append(short)
            if commit in new_commits:
                new_touches.add(path)
        commits.append({
            "commit": commit,
            "short_commit": short,
            "authored_at": authored_at,
            "subject": subject,
            "changed_path_count": str(len(paths)),
            "live_mod_path_count": str(len(live)),
            "other_reference_path_count": str(sum(path.startswith("Other/") for _, path in paths)),
            "log_only_path_count": str(sum(path.lower().endswith("error.log") for _, path in paths)),
            "newly_fetched": "yes" if commit in new_commits else "no",
            "live_mod_paths": ";".join(live),
        })

    dirty = worktree_paths(repo)
    net = net_changed_paths(repo, base, theirs)
    live_rows: list[dict[str, str]] = []
    for status, path in net:
        if not path.startswith(LIVE_PREFIX):
            continue
        system, risk, recommendation = classify(path)
        live_rows.append({
            "status": status,
            "path": path,
            "system": system,
            "risk": risk,
            "working_tree_path_overlap": "yes" if path in dirty else "no",
            "touching_commits": ";".join(touches.get(path, [])),
            "newly_fetched_commit_touches": "yes" if path in new_touches else "no",
            "recommendation": recommendation,
        })

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "pending_upstream_commits.csv", commits, "commit")
    write_csv(args.output_dir / "pending_live_mod_files.csv", live_rows, "status")

    net_paths = [path for _, path in net]
    live_paths = [path for path in net_paths if path.startswith(LIVE_PREFIX)]
    other_paths = [path for path in net_paths if path.startswith("Other/")]
    log_paths = [path for path in net_paths if path.lower().endswith("error.log")]
    overlaps = [row for row in live_rows if row["working_tree_path_overlap"] == "yes"]
    systems: dict[str, int] = defaultdict(int)
    for row in live_rows:
        systems[row["system"]] += 1
    summary = [
        "# Upstream Güncelleme Envanteri", "", "## Git Çapaları", "",
        f"- Yusseter HEAD: `{ours}`",
        f"- Son merge edilen asıl-mod kaynağı / merge-base: `{base}`",
        f"- Önceki `upstream/main`: `{previous}`",
        f"- Güncel `upstream/main`: `{theirs}`",
        f"- Bekleyen commit: `{len(commits)}`",
        f"- Yeni fetch edilen commit: `{len(new_commits)}`",
        "- Merge uygulanmadı; index ve canlı `BookmarksGit` kaynakları değiştirilmedi.",
        "", "## Kapsam", "",
        f"- Net değişen yol: `{len(net_paths)}`",
        f"- Canlı mod yolu: `{len(live_paths)}`",
        f"- `Other/` extraction/reference yolu: `{len(other_paths)}`",
        f"- `error.log` yolu: `{len(log_paths)}`",
        f"- Çalışma ağacıyla doğrudan yol çakışması: `{len(overlaps)}`",
        f"- Upstream landed-title dosya değişikliği: `{'yes' if any('/landed_titles/' in p for p in live_paths) else 'no'}`",
        "", "## Sistem Dağılımı", "",
    ]
    summary.extend(f"- `{key}`: `{systems[key]}`" for key in sorted(systems))
    summary.extend(["", "## Yeni Commit Etkisi", "", f"- Yeni commitlerin dokunduğu canlı yol: `{len(new_touches)}`"])
    summary.extend(f"- `{path}`" for path in sorted(new_touches))
    summary.extend([
        "", "## Risk Kararı", "",
        "- Dirty-path çakışması olmaması semantik olarak güvenli merge anlamına gelmez.",
        "- Karakter, history, CoA, dynasty, on_action ve localization değişiklikleri Tiger ve kimlik zinciri auditinden geçmelidir.",
        "- Harita/locator girdileri yeni committe değişmediyse mevcut üç-yönlü kanıt freshness hash ile yeniden kullanılabilir.",
        "- Sonuç: `do_not_merge_yet`; önce güncel Tiger delta ve sistem özel auditleri tamamlanmalıdır.",
        "", "## Yeniden Çalıştırma", "", "```powershell",
        f'python .codex\\works\\tools\\audit_pending_upstream_inventory.py --repo-root "{repo}" --base {base} --ours HEAD --theirs upstream/main --previous-upstream {previous} --output-dir ".codex\\works\\analysis\\generated\\upstream_update_inventory"',
        "```", "",
        "Ayrıntılı commit ve yol listeleri: `pending_upstream_commits.csv` ve `pending_live_mod_files.csv`.",
    ])
    (args.output_dir / "upstream_update_inventory_summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
