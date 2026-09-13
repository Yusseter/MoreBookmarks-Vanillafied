from __future__ import annotations

import argparse
import csv
import hashlib
import re
import subprocess
import sys
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from audit_landed_title_source_identity import (
    TitleBlock,
    finalize_blocks,
    parse_landed_title_file,
)


MEMBER_FIELDS = ("regions", "kingdoms", "duchies", "counties", "provinces")
TITLE_FIELD_PREFIX = {
    "kingdoms": "k_",
    "duchies": "d_",
    "counties": "c_",
}
TOKEN_RE = re.compile(r'"(?:\\.|[^"\\])*"|[{}=]|[^\s{}=]+')
TITLE_RE = re.compile(r"^[hekdcb]_[A-Za-z0-9_'\-]+$")
SILK_SITUATION_REGION = "tgp_silk_road_region"
SILK_ROUTE_REGION = "dlc_tgp_silk_road_route_region"
SILK_SUFFIXES = (
    "china",
    "tibet",
    "india",
    "central_asia",
    "transcaspia",
    "occident",
    "mideast",
    "sea",
)
SILK_CURRENT_SCOPE_EXCLUSIONS = {
    "sea": "vanilla_east_policy_excludes_asil_mod_sea_extension",
}
ACTIVE_SILK_SUFFIXES = tuple(
    suffix for suffix in SILK_SUFFIXES if suffix not in SILK_CURRENT_SCOPE_EXCLUSIONS
)
SILK_COLORS = (
    (41, 182, 246, 150),
    (245, 166, 35, 150),
    (89, 201, 112, 150),
    (202, 92, 214, 150),
    (234, 91, 91, 150),
    (238, 210, 72, 150),
    (61, 205, 190, 150),
    (151, 119, 230, 150),
)


@dataclass(frozen=True)
class Token:
    value: str
    line: int


@dataclass
class Entry:
    key: str | None
    value: str | "Block"
    line: int


@dataclass
class Block:
    entries: list[Entry] = field(default_factory=list)


@dataclass(frozen=True)
class SourceText:
    relative_path: str
    source_layer: str
    text: str


@dataclass(frozen=True)
class MemberRef:
    field_name: str
    token: str
    line: int


@dataclass
class RegionDefinition:
    name: str
    relative_path: str
    source_layer: str
    line: int
    members: dict[str, list[MemberRef]]
    options: dict[str, str]
    signature: str = ""
    provenance: str = ""

    def direct_refs(self) -> Iterator[MemberRef]:
        for field_name in MEMBER_FIELDS:
            yield from self.members.get(field_name, [])


@dataclass
class MapGeometry:
    width: int
    height: int
    pixel_count: list[int]
    sum_x: list[int]
    sum_y: list[int]
    min_x: list[int]
    min_y: list[int]
    max_x: list[int]
    max_y: list[int]
    adjacency: list[set[int]]
    edge_ids: set[int]
    unknown_pixel_count: int
    palette_pixel_count: int

    def center(self, province_id: int) -> tuple[float, float]:
        count = self.pixel_count[province_id]
        if not count:
            return 0.0, 0.0
        return self.sum_x[province_id] / count, self.sum_y[province_id] / count


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[3]
    ck3_projects = repo_root.parent
    parser = argparse.ArgumentParser(
        description=(
            "Audit effective CK3 geographical regions, landed membership, raster "
            "topology, source provenance, and Silk Road region closure without "
            "editing live mod content."
        )
    )
    parser.add_argument("--repo-root", type=Path, default=repo_root)
    parser.add_argument(
        "--asil-mod-root",
        type=Path,
        default=ck3_projects / "Leviathonlx MoreBookmarks-Plus",
    )
    parser.add_argument(
        "--vanilla-root",
        type=Path,
        default=Path(
            r"C:\Program Files (x86)\Steam\steamapps\common\Crusader Kings III\game"
        ),
    )
    parser.add_argument(
        "--vanilla-east-tracking",
        type=Path,
        default=(
            repo_root
            / ".codex/works/analysis/generated/province_definition"
            / "final_orijinal_tracking_preserve_old_ids.csv"
        ),
        help="Vanilla-east source province to current province projection table.",
    )
    parser.add_argument("--premerge-revision", default="09588cbb5")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Output directory. Defaults to .codex/works/analysis/generated/"
            "repo_integration_closure/geographical_region_closure under --repo-root."
        ),
    )
    parser.add_argument(
        "--skip-geometry",
        action="store_true",
        help="Run reference/provenance checks without scanning provinces.png.",
    )
    parser.add_argument(
        "--max-gap-provinces",
        type=int,
        default=20,
        help="Largest enclosed landed complement component retained as a gap candidate.",
    )
    return parser.parse_args()


def strip_comments(text: str) -> str:
    output: list[str] = []
    quoted = False
    escaped = False
    index = 0
    while index < len(text):
        char = text[index]
        if char == "\\" and quoted:
            escaped = not escaped
            output.append(char)
            index += 1
            continue
        if char == '"' and not escaped:
            quoted = not quoted
        escaped = False
        if char == "#" and not quoted:
            while index < len(text) and text[index] not in "\r\n":
                index += 1
            continue
        output.append(char)
        index += 1
    return "".join(output)


def tokenize(text: str) -> list[Token]:
    clean = strip_comments(text).lstrip("\ufeff")
    tokens: list[Token] = []
    line = 1
    cursor = 0
    for match in TOKEN_RE.finditer(clean):
        line += clean.count("\n", cursor, match.start())
        tokens.append(Token(match.group(0), line))
        cursor = match.end()
    return tokens


def parse_block(tokens: list[Token], index: int) -> tuple[Block, int]:
    block = Block()
    while index < len(tokens):
        token = tokens[index]
        if token.value == "}":
            return block, index + 1
        if token.value in {"{", "="}:
            index += 1
            continue
        if index + 1 < len(tokens) and tokens[index + 1].value == "=":
            key = token.value
            if index + 2 >= len(tokens):
                block.entries.append(Entry(key, "", token.line))
                return block, len(tokens)
            value_token = tokens[index + 2]
            if value_token.value == "{":
                value, index = parse_block(tokens, index + 3)
            else:
                value = value_token.value.strip('"')
                index += 3
            block.entries.append(Entry(key, value, token.line))
            continue
        block.entries.append(Entry(None, token.value.strip('"'), token.line))
        index += 1
    return block, index


def parse_top_level(text: str) -> tuple[list[Entry], list[str]]:
    tokens = tokenize(text)
    entries: list[Entry] = []
    diagnostics: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if (
            index + 2 < len(tokens)
            and tokens[index + 1].value == "="
            and tokens[index + 2].value == "{"
        ):
            value, index = parse_block(tokens, index + 3)
            entries.append(Entry(token.value, value, token.line))
            continue
        diagnostics.append(f"line={token.line}:unexpected_top_level_token={token.value}")
        index += 1
    return entries, diagnostics


def bare_tokens(block: Block) -> list[tuple[str, int]]:
    return [
        (str(entry.value), entry.line)
        for entry in block.entries
        if entry.key is None and isinstance(entry.value, str)
    ]


def region_signature(region: RegionDefinition) -> str:
    chunks: list[str] = []
    for field_name in MEMBER_FIELDS:
        refs = region.members.get(field_name, [])
        if refs:
            chunks.append(field_name + "=" + ",".join(ref.token for ref in refs))
    for key in sorted(region.options):
        chunks.append(f"{key}={region.options[key]}")
    return "|".join(chunks)


def regions_from_source(source: SourceText) -> tuple[list[RegionDefinition], list[str]]:
    definitions: list[RegionDefinition] = []
    entries, diagnostics = parse_top_level(source.text)
    for entry in entries:
        if entry.key is None or not isinstance(entry.value, Block):
            continue
        members: dict[str, list[MemberRef]] = defaultdict(list)
        options: dict[str, str] = {}
        for child in entry.value.entries:
            if child.key in MEMBER_FIELDS and isinstance(child.value, Block):
                for token, line in bare_tokens(child.value):
                    members[child.key].append(MemberRef(child.key, token, line))
            elif child.key and isinstance(child.value, str):
                options[child.key] = child.value
        definition = RegionDefinition(
            name=entry.key,
            relative_path=source.relative_path,
            source_layer=source.source_layer,
            line=entry.line,
            members=dict(members),
            options=options,
        )
        definition.signature = region_signature(definition)
        definitions.append(definition)
    return definitions, diagnostics


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_effective_sources(
    mod_directory: Path,
    vanilla_directory: Path | None,
) -> list[SourceText]:
    mod_files = {
        path.relative_to(mod_directory).as_posix(): path
        for path in mod_directory.rglob("*.txt")
    }
    effective: dict[str, tuple[str, Path]] = {}
    if vanilla_directory and vanilla_directory.exists():
        for path in vanilla_directory.rglob("*.txt"):
            relative = path.relative_to(vanilla_directory).as_posix()
            if relative not in mod_files:
                effective[relative] = ("vanilla_fallback", path)
    for relative, path in mod_files.items():
        effective[relative] = ("current_mod", path)
    return [
        SourceText(relative, layer, read_text(path))
        for relative, (layer, path) in sorted(effective.items())
    ]


def collect_plain_sources(directory: Path, layer: str) -> list[SourceText]:
    if not directory.exists():
        return []
    return [
        SourceText(path.relative_to(directory).as_posix(), layer, read_text(path))
        for path in sorted(directory.rglob("*.txt"))
    ]


def collect_git_sources(
    repo_root: Path,
    revision: str,
    relative_directory: str,
) -> tuple[list[SourceText], list[str]]:
    diagnostics: list[str] = []
    listed = subprocess.run(
        [
            "git",
            "ls-tree",
            "-r",
            "--name-only",
            revision,
            "--",
            relative_directory,
        ],
        cwd=repo_root,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    if listed.returncode:
        return [], [f"git_ls_tree_failed:{listed.stderr.strip()}"]
    sources: list[SourceText] = []
    prefix = relative_directory.rstrip("/") + "/"
    for git_path in sorted(
        path.strip()
        for path in listed.stdout.splitlines()
        if path.strip().endswith(".txt")
    ):
        shown = subprocess.run(
            ["git", "show", f"{revision}:{git_path}"],
            cwd=repo_root,
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )
        if shown.returncode:
            diagnostics.append(f"git_show_failed:{git_path}:{shown.stderr.strip()}")
            continue
        relative = git_path[len(prefix) :] if git_path.startswith(prefix) else git_path
        sources.append(SourceText(relative, "premerge_yusseter", shown.stdout))
    return sources, diagnostics


def parse_region_source_set(
    sources: Iterable[SourceText],
) -> tuple[dict[str, RegionDefinition], dict[str, list[RegionDefinition]], list[str]]:
    all_definitions: dict[str, list[RegionDefinition]] = defaultdict(list)
    diagnostics: list[str] = []
    for source in sources:
        definitions, source_diagnostics = regions_from_source(source)
        for definition in definitions:
            all_definitions[definition.name].append(definition)
        diagnostics.extend(
            f"{source.source_layer}:{source.relative_path}:{message}"
            for message in source_diagnostics
        )
    effective = {
        name: definitions[-1]
        for name, definitions in sorted(all_definitions.items())
    }
    return effective, dict(all_definitions), diagnostics


def load_effective_titles(mod_directory: Path, vanilla_directory: Path) -> dict[str, TitleBlock]:
    mod_files = {
        path.relative_to(mod_directory).as_posix(): path
        for path in mod_directory.glob("*.txt")
    }
    ordered: list[tuple[str, Path]] = []
    if vanilla_directory.exists():
        for path in sorted(vanilla_directory.glob("*.txt")):
            relative = path.relative_to(vanilla_directory).as_posix()
            if relative not in mod_files:
                ordered.append(("vanilla_fallback", path))
    ordered.extend(("current_mod", path) for _, path in sorted(mod_files.items()))
    blocks: dict[str, TitleBlock] = {}
    for layer, path in ordered:
        for title_id, block in parse_landed_title_file(path).items():
            if layer == "current_mod" or title_id not in blocks:
                blocks[title_id] = block
    return finalize_blocks(blocks)


def load_plain_titles(directory: Path) -> dict[str, TitleBlock]:
    blocks: dict[str, TitleBlock] = {}
    for path in sorted(directory.glob("*.txt")):
        blocks.update(parse_landed_title_file(path))
    return finalize_blocks(blocks)


def parse_definition(path: Path) -> tuple[dict[int, dict[str, object]], dict[tuple[int, int, int], list[int]]]:
    by_id: dict[int, dict[str, object]] = {}
    by_rgb: dict[tuple[int, int, int], list[int]] = defaultdict(list)
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        for line_number, row in enumerate(csv.reader(handle, delimiter=";"), start=1):
            if not row or not row[0].strip().isdigit():
                continue
            try:
                province_id = int(row[0].strip())
                rgb = tuple(int(value.strip()) for value in row[1:4])
            except (ValueError, IndexError):
                continue
            by_id[province_id] = {
                "id": province_id,
                "rgb": rgb,
                "name": row[4].strip() if len(row) > 4 else "",
                "line": line_number,
            }
            by_rgb[rgb].append(province_id)
    return by_id, dict(by_rgb)


def split_relation_values(value: str) -> list[str]:
    return [
        token.strip()
        for token in re.split(r"[;&]", value)
        if token.strip() and token.strip() != "*there_is_no*"
    ]


def load_inverse_title_relations(path: Path) -> dict[str, list[str]]:
    inverse: dict[str, set[str]] = defaultdict(set)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle)
        for raw_row in reader:
            row = {(key or "").strip(): (value or "").strip() for key, value in raw_row.items()}
            current_titles = split_relation_values(row.get("source_title_id", ""))
            source_titles = split_relation_values(row.get("mod_title_id", ""))
            for source_title in source_titles:
                inverse[source_title].update(current_titles)
    return {key: sorted(values) for key, values in inverse.items()}


def load_vanilla_east_projection(path: Path) -> dict[int, int]:
    projection: dict[int, int] = {}
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        for raw_row in csv.DictReader(handle):
            row = {(key or "").strip(): (value or "").strip() for key, value in raw_row.items()}
            if row.get("old_subset") != "orijinal_dogu":
                continue
            old_id = row.get("old_id", "")
            final_id = row.get("final_new_id", "")
            if old_id.isdigit() and final_id.isdigit():
                projection[int(old_id)] = int(final_id)
    return projection


def apply_provenance(
    current: dict[str, RegionDefinition],
    premerge: dict[str, RegionDefinition],
    asil: dict[str, RegionDefinition],
    vanilla: dict[str, RegionDefinition],
) -> None:
    for name, region in current.items():
        if region.source_layer == "vanilla_fallback":
            region.provenance = "vanilla_effective_fallback"
            continue
        same_premerge = name in premerge and region.signature == premerge[name].signature
        same_asil = name in asil and region.signature == asil[name].signature
        same_vanilla = name in vanilla and region.signature == vanilla[name].signature
        if same_premerge and same_asil:
            region.provenance = "shared_premerge_and_asil"
        elif same_premerge:
            region.provenance = "preexisting_yusseter"
        elif same_asil:
            region.provenance = "shared_asil_mod"
        elif same_vanilla:
            region.provenance = "shared_vanilla"
        elif name in premerge or name in asil or name in vanilla:
            region.provenance = "yusseter_adapted"
        else:
            region.provenance = "yusseter_current_only"


class RegionResolver:
    def __init__(
        self,
        regions: dict[str, RegionDefinition],
        titles: dict[str, TitleBlock],
        definition_ids: set[int],
    ) -> None:
        self.regions = regions
        self.titles = titles
        self.definition_ids = definition_ids
        self._cache: dict[str, set[int]] = {}
        self.cycles: set[tuple[str, ...]] = set()

    def resolve(self, region_name: str) -> set[int]:
        return set(self._resolve(region_name, []))

    def _resolve(self, region_name: str, stack: list[str]) -> set[int]:
        if region_name in self._cache:
            return self._cache[region_name]
        if region_name in stack:
            cycle_start = stack.index(region_name)
            cycle = tuple(stack[cycle_start:] + [region_name])
            self.cycles.add(cycle)
            return set()
        region = self.regions.get(region_name)
        if region is None:
            return set()
        stack.append(region_name)
        resolved: set[int] = set()
        for ref in region.members.get("provinces", []):
            if ref.token.isdigit():
                province_id = int(ref.token)
                if province_id in self.definition_ids:
                    resolved.add(province_id)
        for field_name in ("kingdoms", "duchies", "counties"):
            for ref in region.members.get(field_name, []):
                block = self.titles.get(ref.token)
                if block:
                    resolved.update(
                        province_id
                        for province_id in block.descendant_province_ids
                        if province_id in self.definition_ids
                    )
        for ref in region.members.get("regions", []):
            resolved.update(self._resolve(ref.token, stack))
        stack.pop()
        self._cache[region_name] = resolved
        return resolved


def finding_id(
    classification: str,
    path: str,
    line: int | str,
    region: str,
    obj: str,
) -> str:
    raw = "|".join((classification, path, str(line), region, obj))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def finding(
    classification: str,
    severity: str,
    confidence: str,
    region: RegionDefinition,
    obj: str,
    reason: str,
    recommendation: str,
    *,
    line: int | None = None,
    current_value: str = "",
    candidate_value: str = "",
    evidence: str = "",
    root_cause_key: str = "",
) -> dict[str, str]:
    source_line = line if line is not None else region.line
    row = {
        "finding_id": finding_id(
            classification,
            region.relative_path,
            source_line,
            region.name,
            obj,
        ),
        "classification": classification,
        "root_cause_key": root_cause_key or f"{classification}:{region.name}:{obj}",
        "severity": severity,
        "confidence": confidence,
        "region": region.name,
        "path": region.relative_path,
        "line": str(source_line),
        "object": obj,
        "current_value": current_value,
        "candidate_value": candidate_value,
        "reason": reason,
        "recommendation": recommendation,
        "provenance": region.provenance,
        "source_layer": region.source_layer,
        "evidence": evidence,
    }
    return row


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = []
        for row in rows:
            for key in row:
                if key not in fields:
                    fields.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def direct_member_counts(region: RegionDefinition) -> dict[str, int]:
    return {
        field_name: len(region.members.get(field_name, []))
        for field_name in MEMBER_FIELDS
    }


def build_reference_audit(
    regions: dict[str, RegionDefinition],
    all_definitions: dict[str, list[RegionDefinition]],
    resolver: RegionResolver,
    title_relations: dict[str, list[str]],
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, str]]]:
    inventory_rows: list[dict[str, object]] = []
    reference_rows: list[dict[str, object]] = []
    findings: list[dict[str, str]] = []

    for name, definitions in sorted(all_definitions.items()):
        if len(definitions) <= 1:
            continue
        effective = regions[name]
        unique_signatures = {definition.signature for definition in definitions}
        classification = (
            "duplicate_region_definition_identical"
            if len(unique_signatures) == 1
            else "duplicate_region_definition_conflicting"
        )
        findings.append(
            finding(
                classification,
                "review",
                "high",
                effective,
                name,
                (
                    f"region has {len(definitions)} effective-layer definitions across "
                    f"{len({item.relative_path for item in definitions})} files"
                ),
                "review_region_load_order_and_keep_or_document_one_effective_definition",
                evidence=" | ".join(
                    f"{item.source_layer}:{item.relative_path}:{item.line}"
                    for item in definitions
                ),
            )
        )

    for region_name, region in sorted(regions.items()):
        resolved = resolver.resolve(region_name)
        counts = direct_member_counts(region)
        inventory_rows.append(
            {
                "region": region_name,
                "path": region.relative_path,
                "line": region.line,
                "source_layer": region.source_layer,
                "provenance": region.provenance,
                "definition_count": len(all_definitions.get(region_name, [])),
                "direct_regions": counts["regions"],
                "direct_kingdoms": counts["kingdoms"],
                "direct_duchies": counts["duchies"],
                "direct_counties": counts["counties"],
                "direct_provinces": counts["provinces"],
                "resolved_provinces": len(resolved),
                "should_remember_counties_order": region.options.get(
                    "should_remember_counties_order", ""
                ),
                "signature_sha256": hashlib.sha256(
                    region.signature.encode("utf-8")
                ).hexdigest(),
            }
        )

        if not resolved and any(counts.values()):
            findings.append(
                finding(
                    "empty_resolved_region",
                    "review",
                    "medium",
                    region,
                    region_name,
                    "region has direct members but resolves to no current definition province",
                    "review_missing_nested_regions_titles_or_provinces",
                )
            )

        for field_name in MEMBER_FIELDS:
            refs = region.members.get(field_name, [])
            frequencies = Counter(ref.token for ref in refs)
            duplicate_tokens = sorted(token for token, count in frequencies.items() if count > 1)
            for token in duplicate_tokens:
                first_ref = next(ref for ref in refs if ref.token == token)
                findings.append(
                    finding(
                        "duplicate_direct_region_member",
                        "review",
                        "high",
                        region,
                        token,
                        f"{field_name} contains the same direct token {frequencies[token]} times",
                        "remove_duplicate_token_or_document_intent",
                        line=first_ref.line,
                        current_value=field_name,
                    )
                )

            for ref in refs:
                status = "valid"
                candidates: list[str] = []
                resolved_count = 0
                if field_name == "regions":
                    target = regions.get(ref.token)
                    if target is None:
                        status = "undefined_region"
                        findings.append(
                            finding(
                                "undefined_nested_region_reference",
                                "blocker",
                                "high",
                                region,
                                ref.token,
                                "nested geographical region is absent from the effective region layer",
                                "define_remove_or_remap_nested_region",
                                line=ref.line,
                                current_value=field_name,
                                root_cause_key=f"undefined_nested_region:{ref.token}",
                            )
                        )
                    else:
                        resolved_count = len(resolver.resolve(ref.token))
                elif field_name == "provinces":
                    if not ref.token.isdigit():
                        status = "invalid_province_token"
                        findings.append(
                            finding(
                                "invalid_region_province_token",
                                "blocker",
                                "high",
                                region,
                                ref.token,
                                "provinces block contains a non-numeric token",
                                "replace_with_valid_current_province_id",
                                line=ref.line,
                                current_value=field_name,
                                root_cause_key=f"invalid_region_province_token:{ref.token}",
                            )
                        )
                    elif int(ref.token) not in resolver.definition_ids:
                        status = "undefined_province"
                        findings.append(
                            finding(
                                "undefined_region_province_reference",
                                "blocker",
                                "high",
                                region,
                                ref.token,
                                "province is absent from current definition.csv",
                                "remove_or_remap_region_province",
                                line=ref.line,
                                current_value=field_name,
                                root_cause_key=f"undefined_region_province:{ref.token}",
                            )
                        )
                    else:
                        resolved_count = 1
                else:
                    expected_prefix = TITLE_FIELD_PREFIX[field_name]
                    block = resolver.titles.get(ref.token)
                    if block is None:
                        status = "undefined_title"
                        candidates = [
                            candidate
                            for candidate in title_relations.get(ref.token, [])
                            if candidate in resolver.titles
                        ]
                        findings.append(
                            finding(
                                "undefined_region_title_reference",
                                "review",
                                "high" if len(candidates) == 1 else "medium",
                                region,
                                ref.token,
                                "title is absent from current effective landed titles",
                                (
                                    "review_unique_relation_candidate"
                                    if len(candidates) == 1
                                    else "review_external_stale_or_split_title_identity"
                                ),
                                line=ref.line,
                                current_value=field_name,
                                candidate_value=" | ".join(candidates),
                                root_cause_key=f"undefined_region_title:{ref.token}",
                            )
                        )
                    else:
                        resolved_count = len(block.descendant_province_ids)
                        if not ref.token.startswith(expected_prefix):
                            status = "wrong_tier"
                            findings.append(
                                finding(
                                    "region_member_tier_mismatch",
                                    "review",
                                    "high",
                                    region,
                                    ref.token,
                                    f"{field_name} expects {expected_prefix} titles",
                                    "move_title_to_matching_region_member_field_or_review_intent",
                                    line=ref.line,
                                    current_value=field_name,
                                )
                            )
                reference_rows.append(
                    {
                        "region": region_name,
                        "path": region.relative_path,
                        "line": ref.line,
                        "field": field_name,
                        "token": ref.token,
                        "status": status,
                        "relation_candidates": " | ".join(candidates),
                        "resolved_province_count": resolved_count,
                        "provenance": region.provenance,
                    }
                )

    for cycle in sorted(resolver.cycles):
        region = regions[cycle[0]]
        findings.append(
            finding(
                "cyclic_nested_region_reference",
                "blocker",
                "high",
                region,
                " -> ".join(cycle),
                "nested region graph contains a cycle",
                "break_region_cycle",
            )
        )

    inventory_rows.sort(key=lambda row: str(row["region"]))
    reference_rows.sort(
        key=lambda row: (
            str(row["path"]),
            int(row["line"]),
            str(row["field"]),
            str(row["token"]),
        )
    )
    findings.sort(
        key=lambda row: (
            row["severity"],
            row["classification"],
            row["path"],
            int(row["line"]),
            row["object"],
        )
    )
    return inventory_rows, reference_rows, findings


def infer_palette_bounds_fast(
    image: Image.Image,
    definition: dict[int, dict[str, object]],
    defined_rgbs: set[tuple[int, int, int]],
) -> tuple[int, int, int, int] | None:
    placeholder_rgbs = {
        tuple(meta["rgb"])
        for meta in definition.values()
        if str(meta["name"]).startswith("zz_placeholder_")
    }
    start_x = max(0, image.width - 128)
    start_y = max(0, image.height - 128)
    crop = image.crop((start_x, start_y, image.width, image.height))
    points: list[tuple[int, int]] = []
    for local_index, rgb in enumerate(crop.getdata()):
        if rgb not in placeholder_rgbs and rgb in defined_rgbs:
            continue
        x = start_x + (local_index % crop.width)
        y = start_y + (local_index // crop.width)
        points.append((x, y))
    if len(points) < 100:
        return None
    min_x = min(x for x, _ in points)
    max_x = max(x for x, _ in points)
    min_y = min(y for _, y in points)
    max_y = max(y for _, y in points)
    if max_x != image.width - 1 or max_y != image.height - 1:
        return None
    if image.width - min_x > 128 or image.height - min_y > 128:
        return None
    return min_x, min_y, max_x, max_y


def scan_map_geometry(
    image_path: Path,
    definition: dict[int, dict[str, object]],
    by_rgb: dict[tuple[int, int, int], list[int]],
) -> tuple[MapGeometry, tuple[int, int, int, int] | None]:
    image = Image.open(image_path).convert("RGB")
    unique_rgb_to_id = {
        rgb: ids[0]
        for rgb, ids in by_rgb.items()
        if len(set(ids)) == 1
    }
    max_id = max(definition, default=0)
    size = max_id + 1
    pixel_count = [0] * size
    sum_x = [0] * size
    sum_y = [0] * size
    min_x = [image.width] * size
    min_y = [image.height] * size
    max_x = [-1] * size
    max_y = [-1] * size
    adjacency = [set() for _ in range(size)]
    edge_ids: set[int] = set()
    palette_bounds = infer_palette_bounds_fast(image, definition, set(by_rgb))
    previous = [0] * image.width
    current = [0] * image.width
    x = 0
    y = 0
    left = 0
    unknown_pixel_count = 0
    palette_pixel_count = 0
    for rgb in image.getdata():
        in_palette = False
        if palette_bounds is not None:
            palette_min_x, palette_min_y, palette_max_x, palette_max_y = palette_bounds
            in_palette = (
                palette_min_x <= x <= palette_max_x
                and palette_min_y <= y <= palette_max_y
            )
        province_id = 0 if in_palette else unique_rgb_to_id.get(rgb, 0)
        if in_palette:
            palette_pixel_count += 1
        elif not province_id:
            unknown_pixel_count += 1
        current[x] = province_id
        if province_id:
            pixel_count[province_id] += 1
            sum_x[province_id] += x
            sum_y[province_id] += y
            if x < min_x[province_id]:
                min_x[province_id] = x
            if y < min_y[province_id]:
                min_y[province_id] = y
            if x > max_x[province_id]:
                max_x[province_id] = x
            if y > max_y[province_id]:
                max_y[province_id] = y
            if x in {0, image.width - 1} or y in {0, image.height - 1}:
                edge_ids.add(province_id)
            if left and left != province_id:
                adjacency[province_id].add(left)
                adjacency[left].add(province_id)
            above = previous[x]
            if above and above != province_id:
                adjacency[province_id].add(above)
                adjacency[above].add(province_id)
        left = province_id
        x += 1
        if x == image.width:
            x = 0
            y += 1
            left = 0
            previous, current = current, previous
    geometry = MapGeometry(
        width=image.width,
        height=image.height,
        pixel_count=pixel_count,
        sum_x=sum_x,
        sum_y=sum_y,
        min_x=min_x,
        min_y=min_y,
        max_x=max_x,
        max_y=max_y,
        adjacency=adjacency,
        edge_ids=edge_ids,
        unknown_pixel_count=unknown_pixel_count,
        palette_pixel_count=palette_pixel_count,
    )
    return geometry, palette_bounds


def current_landed_province_ids(
    titles: dict[str, TitleBlock],
    definition_ids: set[int],
) -> set[int]:
    result: set[int] = set()
    for title_id, block in titles.items():
        if not title_id.startswith("b_"):
            continue
        result.update(
            province_id
            for province_id in block.direct_province_ids
            if province_id in definition_ids
        )
    return result


def graph_components(nodes: set[int], adjacency: list[set[int]]) -> list[set[int]]:
    unvisited = set(nodes)
    components: list[set[int]] = []
    while unvisited:
        start = min(unvisited)
        unvisited.remove(start)
        component = {start}
        queue = deque([start])
        while queue:
            current = queue.popleft()
            for neighbor in adjacency[current]:
                if neighbor in unvisited:
                    unvisited.remove(neighbor)
                    component.add(neighbor)
                    queue.append(neighbor)
        components.append(component)
    components.sort(key=lambda item: (-len(item), min(item)))
    return components


def province_set_bbox(
    province_ids: set[int],
    geometry: MapGeometry,
) -> tuple[int, int, int, int] | None:
    visible = [
        province_id
        for province_id in province_ids
        if province_id < len(geometry.pixel_count) and geometry.pixel_count[province_id]
    ]
    if not visible:
        return None
    return (
        min(geometry.min_x[province_id] for province_id in visible),
        min(geometry.min_y[province_id] for province_id in visible),
        max(geometry.max_x[province_id] for province_id in visible),
        max(geometry.max_y[province_id] for province_id in visible),
    )


def component_inside_bbox(
    component: set[int],
    bbox: tuple[int, int, int, int],
    geometry: MapGeometry,
) -> bool:
    min_x, min_y, max_x, max_y = bbox
    for province_id in component:
        center_x, center_y = geometry.center(province_id)
        if not (min_x <= center_x <= max_x and min_y <= center_y <= max_y):
            return False
    return True


def find_enclosed_landed_gaps(
    region_land: set[int],
    all_landed: set[int],
    geometry: MapGeometry,
    max_gap_provinces: int,
) -> list[dict[str, object]]:
    if len(region_land) < 3:
        return []
    bbox = province_set_bbox(region_land, geometry)
    if bbox is None:
        return []
    complement = all_landed - region_land
    candidates: list[dict[str, object]] = []
    for component in graph_components(complement, geometry.adjacency):
        if len(component) > max_gap_provinces:
            continue
        boundary_edges = 0
        boundary_region: set[int] = set()
        for province_id in component:
            for neighbor in geometry.adjacency[province_id]:
                if neighbor in region_land:
                    boundary_edges += 1
                    boundary_region.add(neighbor)
        if len(boundary_region) < 2 or boundary_edges < 2:
            continue
        if not component_inside_bbox(component, bbox, geometry):
            continue
        candidates.append(
            {
                "province_ids": sorted(component),
                "province_count": len(component),
                "boundary_region_ids": sorted(boundary_region),
                "boundary_region_count": len(boundary_region),
                "boundary_edges": boundary_edges,
            }
        )
    candidates.sort(
        key=lambda row: (
            int(row["province_count"]),
            list(row["province_ids"]),
        )
    )
    return candidates


def build_spatial_audit(
    regions: dict[str, RegionDefinition],
    resolver: RegionResolver,
    titles: dict[str, TitleBlock],
    definition: dict[int, dict[str, object]],
    geometry: MapGeometry,
    max_gap_provinces: int,
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, str]],
]:
    landed = current_landed_province_ids(titles, set(definition))
    metric_rows: list[dict[str, object]] = []
    component_rows: list[dict[str, object]] = []
    gap_rows: list[dict[str, object]] = []
    overlap_rows: list[dict[str, object]] = []
    findings: list[dict[str, str]] = []
    resolved_land: dict[str, set[int]] = {}

    for region_name, region in sorted(regions.items()):
        resolved = resolver.resolve(region_name)
        region_land = resolved & landed
        resolved_land[region_name] = region_land
        components = graph_components(region_land, geometry.adjacency) if region_land else []
        component_sizes = [len(component) for component in components]
        visible_land = {
            province_id
            for province_id in region_land
            if province_id < len(geometry.pixel_count)
            and geometry.pixel_count[province_id]
        }
        bbox = province_set_bbox(visible_land, geometry)
        gaps = find_enclosed_landed_gaps(
            visible_land,
            landed,
            geometry,
            max_gap_provinces,
        )
        metric_rows.append(
            {
                "region": region_name,
                "path": region.relative_path,
                "line": region.line,
                "provenance": region.provenance,
                "resolved_provinces": len(resolved),
                "resolved_landed_provinces": len(region_land),
                "visible_landed_provinces": len(visible_land),
                "land_component_count": len(components),
                "largest_land_component": component_sizes[0] if component_sizes else 0,
                "second_land_component": component_sizes[1] if len(component_sizes) > 1 else 0,
                "enclosed_gap_candidates": len(gaps),
                "bbox": "" if bbox is None else ",".join(map(str, bbox)),
            }
        )
        for component_index, component in enumerate(components, start=1):
            component_rows.append(
                {
                    "region": region_name,
                    "component_index": component_index,
                    "province_count": len(component),
                    "province_ids": " ".join(map(str, sorted(component))),
                    "largest_component": "yes" if component_index == 1 else "no",
                    "provenance": region.provenance,
                }
            )
        if len(components) > 1 and component_sizes[1] >= 2:
            findings.append(
                finding(
                    "disconnected_landed_region_components",
                    "review",
                    "low",
                    region,
                    region_name,
                    (
                        f"region resolves to {len(components)} raster-land components; "
                        f"largest sizes are {component_sizes[:5]}"
                    ),
                    "review_islands_wasteland_gaps_and_intended_discontinuity",
                    evidence="raster_land_adjacency_4_neighbor",
                )
            )
        for gap_index, gap in enumerate(gaps, start=1):
            ids = list(gap["province_ids"])
            names = [str(definition[province_id]["name"]) for province_id in ids]
            row = {
                "region": region_name,
                "gap_index": gap_index,
                "gap_root_id": hashlib.sha1(
                    " ".join(map(str, ids)).encode("utf-8")
                ).hexdigest()[:16],
                "province_count": gap["province_count"],
                "province_ids": " ".join(map(str, ids)),
                "province_names": " | ".join(names),
                "boundary_region_count": gap["boundary_region_count"],
                "boundary_edges": gap["boundary_edges"],
                "boundary_region_ids": " ".join(
                    map(str, gap["boundary_region_ids"])
                ),
                "provenance": region.provenance,
            }
            gap_rows.append(row)
            findings.append(
                finding(
                    "enclosed_landed_region_gap_candidate",
                    "review",
                    "medium",
                    region,
                    " ".join(map(str, ids)),
                    (
                        f"{len(ids)} landed province(s) are separated from the outside "
                        f"land graph by this region and touch {gap['boundary_region_count']} "
                        "region provinces"
                    ),
                    "review_region_membership_against_intended_design",
                    current_value=" | ".join(names),
                    evidence="province_raster_adjacency_and_region_bbox",
                    root_cause_key=(
                        "enclosed_landed_region_gap:"
                        + hashlib.sha1(
                            " ".join(map(str, ids)).encode("utf-8")
                        ).hexdigest()[:16]
                    ),
                )
            )

    for parent_name, parent in sorted(regions.items()):
        child_names = [ref.token for ref in parent.members.get("regions", [])]
        for first_index, first_name in enumerate(child_names):
            if first_name not in resolved_land:
                continue
            for second_name in child_names[first_index + 1 :]:
                if second_name not in resolved_land:
                    continue
                overlap = resolved_land[first_name] & resolved_land[second_name]
                if not overlap:
                    continue
                overlap_rows.append(
                    {
                        "parent_region": parent_name,
                        "first_child": first_name,
                        "second_child": second_name,
                        "overlap_landed_count": len(overlap),
                        "overlap_province_ids": " ".join(map(str, sorted(overlap))),
                        "provenance": parent.provenance,
                    }
                )
                findings.append(
                    finding(
                        "nested_sibling_region_overlap",
                        "review",
                        "low",
                        parent,
                        f"{first_name} | {second_name}",
                        (
                            f"two direct child regions overlap on {len(overlap)} landed "
                            "province(s)"
                        ),
                        "review_intentional_overlap_or_remove_duplicate_coverage",
                        evidence=" ".join(map(str, sorted(overlap)[:20])),
                    )
                )

    metric_rows.sort(key=lambda row: str(row["region"]))
    component_rows.sort(
        key=lambda row: (str(row["region"]), int(row["component_index"]))
    )
    gap_rows.sort(key=lambda row: (str(row["region"]), int(row["gap_index"])))
    overlap_rows.sort(
        key=lambda row: (
            str(row["parent_region"]),
            str(row["first_child"]),
            str(row["second_child"]),
        )
    )
    findings.sort(
        key=lambda row: (
            row["classification"],
            row["path"],
            int(row["line"]),
            row["object"],
        )
    )
    return metric_rows, component_rows, gap_rows, overlap_rows, findings


def build_silk_road_audit(
    regions: dict[str, RegionDefinition],
    resolver: RegionResolver,
    landed: set[int],
    metric_rows: list[dict[str, object]],
    gap_rows: list[dict[str, object]],
    reference_rows: list[dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, str]]]:
    metrics = {str(row["region"]): row for row in metric_rows}
    gap_counts = Counter(str(row["region"]) for row in gap_rows)
    bad_reference_counts = Counter(
        str(row["region"])
        for row in reference_rows
        if str(row["status"]) != "valid"
    )
    findings: list[dict[str, str]] = []
    rows: list[dict[str, object]] = []
    overall_situation = resolver.resolve(SILK_SITUATION_REGION) & landed
    overall_route = resolver.resolve(SILK_ROUTE_REGION) & landed

    for suffix in SILK_SUFFIXES:
        exclusion_reason = SILK_CURRENT_SCOPE_EXCLUSIONS.get(suffix, "")
        situation_name = f"tgp_silk_road_{suffix}_region"
        route_name = f"dlc_tgp_silk_road_route_{suffix}"
        situation = resolver.resolve(situation_name) & landed
        route = resolver.resolve(route_name) & landed
        outside_paired = route - situation
        outside_overall = route - overall_situation
        situation_region = regions.get(situation_name)
        route_region = regions.get(route_name)
        rows.append(
            {
                "suffix": suffix,
                "scope_status": "excluded_by_policy" if exclusion_reason else "active",
                "scope_reason": exclusion_reason,
                "situation_region": situation_name,
                "situation_present": "yes" if situation_region else "no",
                "situation_landed_provinces": len(situation),
                "situation_components": metrics.get(situation_name, {}).get(
                    "land_component_count", 0
                ),
                "situation_gap_candidates": gap_counts[situation_name],
                "situation_reference_issues": bad_reference_counts[situation_name],
                "situation_provenance": (
                    situation_region.provenance if situation_region else "missing"
                ),
                "route_region": route_name,
                "route_present": "yes" if route_region else "no",
                "route_landed_provinces": len(route),
                "route_components": metrics.get(route_name, {}).get(
                    "land_component_count", 0
                ),
                "route_reference_issues": bad_reference_counts[route_name],
                "route_provenance": route_region.provenance if route_region else "missing",
                "route_outside_paired_region_count": len(outside_paired),
                "route_outside_paired_region_ids": " ".join(
                    map(str, sorted(outside_paired))
                ),
                "route_outside_overall_region_count": len(outside_overall),
                "route_outside_overall_region_ids": " ".join(
                    map(str, sorted(outside_overall))
                ),
            }
        )
        if exclusion_reason:
            for present_name, region in (
                (situation_name, situation_region),
                (route_name, route_region),
            ):
                if region is not None:
                    findings.append(
                        finding(
                            "intentionally_excluded_silk_road_region_present",
                            "blocker",
                            "high",
                            region,
                            present_name,
                            exclusion_reason,
                            "remove_the_excluded_region_and_all_consumers",
                        )
                    )
            continue
        for missing_name, region in (
            (situation_name, situation_region),
            (route_name, route_region),
        ):
            if region is None:
                parent = regions.get(SILK_SITUATION_REGION) or regions.get(
                    SILK_ROUTE_REGION
                )
                if parent:
                    findings.append(
                        finding(
                            "missing_silk_road_region_definition",
                            "blocker",
                            "high",
                            parent,
                            missing_name,
                            "expected Silk Road child region is absent",
                            "restore_or_remap_silk_road_child_region",
                        )
                    )
        if route_region and outside_overall:
            unresolved_route_refs = bad_reference_counts[route_name]
            findings.append(
                finding(
                    "silk_route_outside_situation_region",
                    "review",
                    "low" if unresolved_route_refs else "medium",
                    route_region,
                    route_name,
                    (
                        f"route resolves to {len(outside_overall)} landed province(s) "
                        "outside the overall Silk Road situation region"
                        + (
                            f"; {unresolved_route_refs} direct route references are unresolved, "
                            "so route coverage is incomplete"
                            if unresolved_route_refs
                            else ""
                        )
                    ),
                    "review_route_and_situation_region_membership_together",
                    current_value=" ".join(map(str, sorted(outside_overall))),
                )
            )
        elif route_region and outside_paired:
            findings.append(
                finding(
                    "silk_route_outside_paired_subregion",
                    "review",
                    "low",
                    route_region,
                    route_name,
                    (
                        f"route resolves to {len(outside_paired)} landed province(s) "
                        f"outside {situation_name} but remains inside the overall situation"
                    ),
                    "review_cross_subregion_connection_intent",
                    current_value=" ".join(map(str, sorted(outside_paired))),
                )
            )

    parent_row = {
        "suffix": "__overall__",
        "scope_status": "active",
        "scope_reason": "",
        "situation_region": SILK_SITUATION_REGION,
        "situation_present": "yes" if SILK_SITUATION_REGION in regions else "no",
        "situation_landed_provinces": len(overall_situation),
        "situation_components": metrics.get(SILK_SITUATION_REGION, {}).get(
            "land_component_count", 0
        ),
        "situation_gap_candidates": gap_counts[SILK_SITUATION_REGION],
        "situation_reference_issues": bad_reference_counts[SILK_SITUATION_REGION],
        "situation_provenance": regions.get(
            SILK_SITUATION_REGION, RegionDefinition("", "", "", 0, {}, {})
        ).provenance,
        "route_region": SILK_ROUTE_REGION,
        "route_present": "yes" if SILK_ROUTE_REGION in regions else "no",
        "route_landed_provinces": len(overall_route),
        "route_components": metrics.get(SILK_ROUTE_REGION, {}).get(
            "land_component_count", 0
        ),
        "route_reference_issues": bad_reference_counts[SILK_ROUTE_REGION],
        "route_provenance": regions.get(
            SILK_ROUTE_REGION, RegionDefinition("", "", "", 0, {}, {})
        ).provenance,
        "route_outside_paired_region_count": "",
        "route_outside_paired_region_ids": "",
        "route_outside_overall_region_count": len(overall_route - overall_situation),
        "route_outside_overall_region_ids": " ".join(
            map(str, sorted(overall_route - overall_situation))
        ),
    }
    rows.insert(0, parent_row)
    findings.sort(
        key=lambda row: (
            row["classification"],
            row["path"],
            int(row["line"]),
            row["object"],
        )
    )
    return rows, findings


def build_silk_projection_audit(
    regions: dict[str, RegionDefinition],
    current_resolver: RegionResolver,
    vanilla_resolver: RegionResolver,
    projection: dict[int, int],
    current_definition: dict[int, dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, str]]]:
    targets = [
        SILK_SITUATION_REGION,
        *[f"tgp_silk_road_{suffix}_region" for suffix in ACTIVE_SILK_SUFFIXES],
        SILK_ROUTE_REGION,
        *[f"dlc_tgp_silk_road_route_{suffix}" for suffix in ACTIVE_SILK_SUFFIXES],
    ]
    projection_targets = set(projection.values())
    overall_situation = current_resolver.resolve(SILK_SITUATION_REGION)
    overall_route = current_resolver.resolve(SILK_ROUTE_REGION)
    rows: list[dict[str, object]] = []
    findings: list[dict[str, str]] = []

    for region_name in targets:
        source = vanilla_resolver.resolve(region_name)
        tracked_source = sorted(source & set(projection))
        expected = {
            projection[province_id]
            for province_id in tracked_source
            if projection[province_id] in current_definition
        }
        current = current_resolver.resolve(region_name) & set(current_definition)
        missing = expected - current
        overall = overall_route if region_name.startswith("dlc_tgp_") else overall_situation
        covered_elsewhere = missing & overall
        missing_overall = missing - overall
        current_east = current & projection_targets
        if not missing:
            status = "clean"
        elif missing_overall:
            status = "missing_from_overall"
        else:
            status = "subregion_assignment_drift"
        rows.append(
            {
                "region": region_name,
                "status": status,
                "vanilla_source_provinces": len(source),
                "tracked_vanilla_east_provinces": len(tracked_source),
                "mapped_expected_current_provinces": len(expected),
                "current_resolved_provinces": len(current),
                "missing_expected_count": len(missing),
                "missing_expected_ids": " ".join(map(str, sorted(missing))),
                "missing_expected_names": " | ".join(
                    str(current_definition[province_id].get("name", ""))
                    for province_id in sorted(missing)
                ),
                "missing_but_covered_elsewhere_count": len(covered_elsewhere),
                "missing_but_covered_elsewhere_ids": " ".join(
                    map(str, sorted(covered_elsewhere))
                ),
                "missing_from_overall_count": len(missing_overall),
                "missing_from_overall_ids": " ".join(
                    map(str, sorted(missing_overall))
                ),
                "current_east_not_in_source_count": len(current_east - expected),
                "current_east_not_in_source_ids": " ".join(
                    map(str, sorted(current_east - expected))
                ),
            }
        )
        if region_name not in {SILK_SITUATION_REGION, SILK_ROUTE_REGION} or not missing:
            continue
        region = regions.get(region_name)
        if region is None:
            continue
        findings.append(
            finding(
                "silk_vanilla_east_projection_gap",
                "blocker",
                "high",
                region,
                region_name,
                (
                    f"{len(missing)} vanilla-east projected province(s) are absent "
                    "from the effective Silk Road region"
                ),
                "restore_projected_vanilla_east_membership_without_removing_current_extensions",
                current_value=" ".join(map(str, sorted(missing))),
                evidence=(
                    f"tracked_source={len(tracked_source)};"
                    f"expected_current={len(expected)};current={len(current)}"
                ),
            )
        )
    return rows, findings


def render_province_overlay(
    image_path: Path,
    by_rgb: dict[tuple[int, int, int], list[int]],
    landed: set[int],
    province_colors: dict[int, tuple[int, int, int, int]],
    output_path: Path,
    title: str,
    legend: list[tuple[tuple[int, int, int, int], str]],
    *,
    max_width: int = 2304,
) -> None:
    source = Image.open(image_path).convert("RGB")
    scale = min(1.0, max_width / source.width)
    size = (max(1, round(source.width * scale)), max(1, round(source.height * scale)))
    sampled = source.resize(size, Image.Resampling.NEAREST)
    rgb_to_id = {
        rgb: ids[0]
        for rgb, ids in by_rgb.items()
        if len(set(ids)) == 1
    }
    raw_background = bytearray()
    raw_overlay = bytearray()
    transparent = (0, 0, 0, 0)
    for rgb in sampled.getdata():
        province_id = rgb_to_id.get(rgb, 0)
        if province_id in landed:
            raw_background.extend((101, 105, 104, 255))
        elif province_id:
            raw_background.extend((42, 55, 65, 255))
        else:
            raw_background.extend((27, 31, 36, 255))
        raw_overlay.extend(province_colors.get(province_id, transparent))
    background = Image.frombytes("RGBA", size, bytes(raw_background))
    overlay = Image.frombytes("RGBA", size, bytes(raw_overlay))
    canvas = Image.alpha_composite(background, overlay)
    red, green, blue = sampled.split()
    edge_mask = ImageChops.lighter(
        red.filter(ImageFilter.FIND_EDGES),
        ImageChops.lighter(
            green.filter(ImageFilter.FIND_EDGES),
            blue.filter(ImageFilter.FIND_EDGES),
        ),
    ).point(lambda value: 115 if value >= 18 else 0)
    edge_layer = Image.new("RGBA", size, (5, 8, 11, 0))
    edge_layer.putalpha(edge_mask)
    canvas = Image.alpha_composite(canvas, edge_layer)
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    box_width = min(720, size[0] - 20)
    box_height = 40 + 23 * len(legend)
    draw.rounded_rectangle(
        (10, 10, 10 + box_width, 10 + box_height),
        radius=8,
        fill=(18, 22, 28, 220),
        outline=(230, 230, 230, 190),
        width=1,
    )
    draw.text((22, 20), title, fill=(255, 255, 255, 255), font=font)
    for index, (color, label) in enumerate(legend):
        y = 44 + index * 23
        draw.rectangle((22, y, 38, y + 14), fill=color, outline=(255, 255, 255, 220))
        draw.text((46, y + 1), label, fill=(245, 245, 245, 255), font=font)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(output_path, optimize=True)


def render_control_pngs(
    image_path: Path,
    by_rgb: dict[tuple[int, int, int], list[int]],
    regions: dict[str, RegionDefinition],
    resolver: RegionResolver,
    landed: set[int],
    gap_rows: list[dict[str, object]],
    output_dir: Path,
) -> list[Path]:
    silk_colors: dict[int, tuple[int, int, int, int]] = {}
    legend: list[tuple[tuple[int, int, int, int], str]] = []
    for suffix, color in zip(ACTIVE_SILK_SUFFIXES, SILK_COLORS):
        region_name = f"tgp_silk_road_{suffix}_region"
        members = resolver.resolve(region_name) & landed
        for province_id in members:
            if province_id in silk_colors:
                silk_colors[province_id] = (255, 45, 45, 210)
            else:
                silk_colors[province_id] = color
        legend.append((color, region_name))
    route_members = resolver.resolve(SILK_ROUTE_REGION) & landed
    for province_id in route_members:
        base = silk_colors.get(province_id, (255, 255, 255, 0))
        silk_colors[province_id] = (
            min(255, base[0] + 45),
            min(255, base[1] + 45),
            min(255, base[2] + 45),
            max(base[3], 185),
        )
    silk_gap_ids: set[int] = set()
    all_gap_ids: set[int] = set()
    for row in gap_rows:
        ids = {int(value) for value in str(row["province_ids"]).split()}
        all_gap_ids.update(ids)
        if str(row["region"]).startswith("tgp_silk_road"):
            silk_gap_ids.update(ids)
    for province_id in silk_gap_ids:
        silk_colors[province_id] = (255, 0, 190, 235)
    legend.extend(
        [
            ((255, 255, 255, 185), "route-region landed coverage (brightened)"),
            ((255, 45, 45, 210), "subregion overlap"),
            ((255, 0, 190, 235), "enclosed landed gap candidate"),
        ]
    )
    silk_path = output_dir / "silk_road_region_control.png"
    render_province_overlay(
        image_path,
        by_rgb,
        landed,
        silk_colors,
        silk_path,
        "Silk Road region closure: situation subregions, route coverage, gap candidates",
        legend,
    )

    all_gap_colors = {province_id: (235, 55, 55, 220) for province_id in all_gap_ids}
    for province_id in silk_gap_ids:
        all_gap_colors[province_id] = (255, 210, 30, 235)
    all_gap_path = output_dir / "geographical_region_gap_candidates_control.png"
    render_province_overlay(
        image_path,
        by_rgb,
        landed,
        all_gap_colors,
        all_gap_path,
        "Repo-wide enclosed landed region gap candidates",
        [
            ((235, 55, 55, 220), "candidate in any effective region"),
            ((255, 210, 30, 235), "candidate in Silk Road situation region"),
        ],
    )
    return [silk_path, all_gap_path]


def bookmarks_root(path: Path) -> Path:
    if (path / "map_data").is_dir() and (path / "common").is_dir():
        return path
    return path / "BookmarksGit"


def git_revision(repo_root: Path, revision: str = "HEAD") -> str:
    result = subprocess.run(
        ["git", "rev-parse", revision],
        cwd=repo_root,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout.strip() if result.returncode == 0 else "unavailable"


def merge_manual_decisions(
    path: Path,
    findings: list[dict[str, str]],
) -> list[dict[str, str]]:
    existing: dict[str, dict[str, str]] = {}
    if path.exists() and path.stat().st_size:
        with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
            for row in csv.DictReader(handle):
                finding_key = (row.get("finding_id") or "").strip()
                if finding_key:
                    existing[finding_key] = row
    rows: list[dict[str, str]] = []
    for finding_row in findings:
        prior = existing.get(finding_row["finding_id"], {})
        row = dict(finding_row)
        row["manual_decision"] = prior.get("manual_decision", "")
        row["manual_note"] = prior.get("manual_note", "")
        rows.append(row)
    return rows


def build_input_manifest(
    repo_root: Path,
    current_mod: Path,
    asil_mod: Path,
    vanilla_root: Path,
    premerge_revision: str,
    vanilla_east_tracking: Path,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    def add_file(role: str, root: Path, path: Path) -> None:
        if not path.exists() or not path.is_file():
            return
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError:
            relative = path.as_posix()
        rows.append(
            {
                "role": role,
                "root": root.as_posix(),
                "path": relative,
                "bytes": str(path.stat().st_size),
                "sha256": file_sha256(path),
            }
        )

    for path in sorted((current_mod / "map_data/geographical_regions").rglob("*.txt")):
        add_file("current_region", repo_root, path)
    for path in sorted((current_mod / "common/landed_titles").glob("*.txt")):
        add_file("current_landed_titles", repo_root, path)
    add_file("current_definition", repo_root, current_mod / "map_data/definition.csv")
    add_file("current_provinces_png", repo_root, current_mod / "map_data/provinces.png")
    add_file(
        "title_relation",
        repo_root,
        repo_root
        / ".codex/works/pipeline_inputs/title_relations/curated_title_relations.csv",
    )
    for path in sorted((asil_mod / "map_data/geographical_regions").rglob("*.txt")):
        add_file("asil_mod_region", asil_mod, path)
    for path in sorted((vanilla_root / "map_data/geographical_regions").rglob("*.txt")):
        add_file("vanilla_region", vanilla_root, path)
    for path in sorted((vanilla_root / "common/landed_titles").glob("*.txt")):
        add_file("vanilla_landed_titles", vanilla_root, path)
    add_file(
        "vanilla_definition",
        vanilla_root,
        vanilla_root / "map_data/definition.csv",
    )
    add_file("vanilla_east_projection", repo_root, vanilla_east_tracking)
    rows.append(
        {
            "role": "git_revision",
            "root": repo_root.as_posix(),
            "path": "HEAD",
            "bytes": "",
            "sha256": git_revision(repo_root),
        }
    )
    rows.append(
        {
            "role": "premerge_revision",
            "root": repo_root.as_posix(),
            "path": premerge_revision,
            "bytes": "",
            "sha256": git_revision(repo_root, premerge_revision),
        }
    )
    asil_repo = asil_mod.parent if asil_mod.name == "BookmarksGit" else asil_mod
    rows.append(
        {
            "role": "asil_mod_revision",
            "root": asil_repo.as_posix(),
            "path": "HEAD",
            "bytes": "",
            "sha256": git_revision(asil_repo),
        }
    )
    rows.sort(key=lambda row: (row["role"], row["root"], row["path"]))
    return rows


def build_coverage_rows(
    *,
    geometry_enabled: bool,
    premerge_sources: int,
    asil_sources: int,
    vanilla_sources: int,
    parser_diagnostics: int,
) -> list[dict[str, str]]:
    spatial_status = "full" if geometry_enabled else "not_run"
    return [
        {
            "area": "effective_region_file_override_layer",
            "status": "full",
            "method": "vanilla files shadowed by same relative current-mod path",
            "limitation": "CK3 load order for duplicate region keys is reported for review",
        },
        {
            "area": "ck3_region_parser",
            "status": "full" if parser_diagnostics == 0 else "partial",
            "method": "quote-aware comments and recursive brace parser",
            "limitation": f"parser_diagnostics={parser_diagnostics}",
        },
        {
            "area": "direct_reference_validation",
            "status": "full",
            "method": "all regions/kingdoms/duchies/counties/provinces tokens",
            "limitation": "undefined title relation candidates remain manual",
        },
        {
            "area": "recursive_region_membership",
            "status": "full",
            "method": "cycle-protected nested region and landed descendant expansion",
            "limitation": "none",
        },
        {
            "area": "source_provenance",
            "status": "full" if premerge_sources and asil_sources and vanilla_sources else "partial",
            "method": "semantic direct-member signatures across current/premerge/asil/vanilla",
            "limitation": (
                f"premerge_files={premerge_sources};asil_files={asil_sources};"
                f"vanilla_files={vanilla_sources}"
            ),
        },
        {
            "area": "province_raster_adjacency_and_bbox",
            "status": spatial_status,
            "method": "single-pass 4-neighbor provinces.png graph excluding inferred palette",
            "limitation": "strait/sea travel adjacency is intentionally not treated as a land border",
        },
        {
            "area": "landed_gap_component_overlap_candidates",
            "status": spatial_status,
            "method": "effective landed province graph and nested child intersections",
            "limitation": "all findings are design-review candidates, not automatic errors",
        },
        {
            "area": "silk_road_region_static_closure",
            "status": spatial_status,
            "method": "situation/route subregions, membership, components, gaps, control PNG",
            "limitation": "does not prove GUI runtime rendering",
        },
        {
            "area": "silk_road_vanilla_east_projection_closure",
            "status": "full",
            "method": "vanilla hierarchy resolved then mapped through final east province tracking",
            "limitation": "subregion assignment drift is reported separately from overall gaps",
        },
        {
            "area": "silk_road_market_building_gui_closure",
            "status": "not_audited",
            "method": "separate next subsystem pass required",
            "limitation": "center IDs, market placement, localization and GUI fallback remain separate",
        },
        {
            "area": "game_runtime_smoke_test",
            "status": "partial",
            "method": "static audit plus generated control PNG",
            "limitation": "final region map-mode and Silk Road situation display require game test",
        },
    ]


def write_summary(
    path: Path,
    *,
    repo_root: Path,
    current_revision: str,
    asil_revision: str,
    premerge_revision: str,
    regions: dict[str, RegionDefinition],
    reference_rows: list[dict[str, object]],
    findings: list[dict[str, str]],
    metric_rows: list[dict[str, object]],
    gap_rows: list[dict[str, object]],
    overlap_rows: list[dict[str, object]],
    silk_rows: list[dict[str, object]],
    projection_rows: list[dict[str, object]],
    coverage_rows: list[dict[str, str]],
    palette_bounds: tuple[int, int, int, int] | None,
    geometry: MapGeometry | None,
) -> None:
    severity_counts = Counter(row["severity"] for row in findings)
    class_counts = Counter(row["classification"] for row in findings)
    root_counts = Counter(
        (row["classification"], row["root_cause_key"])
        for row in findings
    )
    independent_class_counts = Counter(classification for classification, _ in root_counts)
    status_counts = Counter(str(row["status"]) for row in reference_rows)
    provenance_counts = Counter(region.provenance for region in regions.values())
    coverage_counts = Counter(row["status"] for row in coverage_rows)
    silk_overall = next(
        (row for row in silk_rows if row["suffix"] == "__overall__"),
        {},
    )
    projection_situation = next(
        (row for row in projection_rows if row["region"] == SILK_SITUATION_REGION),
        {},
    )
    projection_route = next(
        (row for row in projection_rows if row["region"] == SILK_ROUTE_REGION),
        {},
    )
    lines = [
        "# Geographical Region Closure Audit",
        "",
        "## Scope",
        "",
        f"- Yusseter revision: `{current_revision}`",
        f"- Asil mod revision: `{asil_revision}`",
        f"- Pre-merge comparison revision: `{premerge_revision}`",
        f"- Effective region definitions: `{len(regions)}`",
        f"- Direct membership tokens: `{len(reference_rows)}`",
        f"- Spatial regions measured: `{len(metric_rows)}`",
        f"- Coverage: `{dict(sorted(coverage_counts.items()))}`",
        "",
        "## Findings",
        "",
        f"- Total findings: `{len(findings)}`",
        f"- Independent decision roots: `{len(root_counts)}`",
        f"- Severity: `{dict(sorted(severity_counts.items()))}`",
        f"- Direct reference status: `{dict(sorted(status_counts.items()))}`",
        f"- Region provenance: `{dict(sorted(provenance_counts.items()))}`",
        f"- Enclosed landed gap candidates: `{len(gap_rows)}`",
        f"- Nested sibling overlaps: `{len(overlap_rows)}`",
        "",
        "### Classes",
        "",
        *[f"- `{key}`: `{value}`" for key, value in sorted(class_counts.items())],
        "",
        "### Independent Roots",
        "",
        *[
            f"- `{key}`: `{value}`"
            for key, value in sorted(independent_class_counts.items())
        ],
        "",
        "## Silk Road",
        "",
        "- Active subregions audited: "
        f"`{len(ACTIVE_SILK_SUFFIXES)}/{len(ACTIVE_SILK_SUFFIXES)}`",
        "- Intentional current-scope exclusions: `"
        + ", ".join(
            f"{suffix} ({reason})"
            for suffix, reason in SILK_CURRENT_SCOPE_EXCLUSIONS.items()
        )
        + "`",
        f"- Situation landed provinces: `{silk_overall.get('situation_landed_provinces', 0)}`",
        f"- Situation components: `{silk_overall.get('situation_components', 0)}`",
        f"- Situation gap candidates: `{silk_overall.get('situation_gap_candidates', 0)}`",
        f"- Route landed provinces: `{silk_overall.get('route_landed_provinces', 0)}`",
        f"- Route outside situation: `{silk_overall.get('route_outside_overall_region_count', 0)}`",
        "- Vanilla-east projected situation provinces missing: "
        f"`{projection_situation.get('missing_expected_count', 0)}`",
        "- Vanilla-east projected route provinces missing: "
        f"`{projection_route.get('missing_expected_count', 0)}`",
        "- `silk_road_region_control.png` is the static membership/topology control image.",
        "- Market centers, market building placement, `building_` GUI fallback and related localization are explicitly not closed by this pass.",
        "",
        "## Geometry",
        "",
        f"- Palette bounds excluded from playable geometry: `{palette_bounds}`",
        f"- Unknown pixels outside palette: `{geometry.unknown_pixel_count if geometry else 'not_run'}`",
        f"- Raster province adjacency edges: `{sum(len(value) for value in geometry.adjacency) // 2 if geometry else 'not_run'}`",
        "- Disconnected components and enclosed gaps are review candidates. Islands, exclaves, wasteland boundaries and deliberate overlaps can be valid.",
        "",
        "## User Workflow",
        "",
        "1. Run the command below from the project root.",
        "2. Read `geographical_region_closure_summary.md` and `geographical_region_manual_review.csv`.",
        "3. Record decisions in `manual_decision` and `manual_note`; reruns preserve them by `finding_id`.",
        "4. Use the two PNG files for visual review.",
        "5. Do not edit live region files until findings are classified.",
        "",
        "```powershell",
        ".\\.codex\\works\\tools\\run_geographical_region_closure.ps1",
        "```",
        "",
        "Fast reference-only run:",
        "",
        "```powershell",
        ".\\.codex\\works\\tools\\run_geographical_region_closure.ps1 -SkipGeometry",
        "```",
        "",
        "## Output Contract",
        "",
        "- `geographical_region_findings.csv`: all classified findings.",
        "- `geographical_region_manual_review.csv`: persistent user decision worklist.",
        "- `geographical_region_inventory.csv`: one row per effective region.",
        "- `geographical_region_references.csv`: every direct membership token.",
        "- `geographical_region_spatial_metrics.csv`: membership/component/gap counts.",
        "- `geographical_region_gap_candidates.csv`: enclosed landed complement candidates.",
        "- `geographical_region_nested_overlaps.csv`: direct child overlap candidates.",
        "- `silk_road_region_closure.csv`: paired situation/route subregion status.",
        "- `silk_road_vanilla_east_projection_coverage.csv`: source-projected east coverage.",
        "- `coverage.csv`: audited, partial and deliberately unaudited layers.",
        "- `input_manifest.csv`: reproducibility hashes and revisions.",
        "",
        f"Project root: `{repo_root}`",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    current_mod = bookmarks_root(repo_root)
    asil_mod = bookmarks_root(args.asil_mod_root.resolve())
    vanilla_root = args.vanilla_root.resolve()
    vanilla_east_tracking = args.vanilla_east_tracking.resolve()
    output_dir = (
        args.output_dir.resolve()
        if args.output_dir is not None
        else repo_root
        / ".codex/works/analysis/generated/repo_integration_closure"
        / "geographical_region_closure"
    )
    required = [
        current_mod / "map_data/geographical_regions",
        current_mod / "map_data/definition.csv",
        current_mod / "common/landed_titles",
        vanilla_root / "map_data/geographical_regions",
        vanilla_root / "map_data/definition.csv",
        vanilla_root / "common/landed_titles",
        vanilla_east_tracking,
    ]
    if not args.skip_geometry:
        required.append(current_mod / "map_data/provinces.png")
    missing = [path for path in required if not path.exists()]
    if missing:
        for path in missing:
            print(f"missing required input: {path}", file=sys.stderr)
        return 2
    output_dir.mkdir(parents=True, exist_ok=True)

    current_sources = collect_effective_sources(
        current_mod / "map_data/geographical_regions",
        vanilla_root / "map_data/geographical_regions",
    )
    current_regions, all_current_definitions, current_diagnostics = (
        parse_region_source_set(current_sources)
    )
    premerge_sources, git_diagnostics = collect_git_sources(
        repo_root,
        args.premerge_revision,
        "BookmarksGit/map_data/geographical_regions",
    )
    premerge_regions, _, premerge_diagnostics = parse_region_source_set(
        premerge_sources
    )
    asil_sources = collect_plain_sources(
        asil_mod / "map_data/geographical_regions", "asil_mod"
    )
    asil_regions, _, asil_diagnostics = parse_region_source_set(asil_sources)
    vanilla_sources = collect_plain_sources(
        vanilla_root / "map_data/geographical_regions", "vanilla"
    )
    vanilla_regions, _, vanilla_diagnostics = parse_region_source_set(vanilla_sources)
    apply_provenance(
        current_regions,
        premerge_regions,
        asil_regions,
        vanilla_regions,
    )

    titles = load_effective_titles(
        current_mod / "common/landed_titles",
        vanilla_root / "common/landed_titles",
    )
    vanilla_titles = load_plain_titles(vanilla_root / "common/landed_titles")
    definition, by_rgb = parse_definition(current_mod / "map_data/definition.csv")
    vanilla_definition, _ = parse_definition(vanilla_root / "map_data/definition.csv")
    vanilla_east_projection = load_vanilla_east_projection(vanilla_east_tracking)
    title_relations = load_inverse_title_relations(
        repo_root
        / ".codex/works/pipeline_inputs/title_relations/curated_title_relations.csv"
    )
    resolver = RegionResolver(current_regions, titles, set(definition))
    vanilla_resolver = RegionResolver(
        vanilla_regions,
        vanilla_titles,
        set(vanilla_definition),
    )
    inventory_rows, reference_rows, reference_findings = build_reference_audit(
        current_regions,
        all_current_definitions,
        resolver,
        title_relations,
    )

    geometry: MapGeometry | None = None
    palette_bounds: tuple[int, int, int, int] | None = None
    metric_rows: list[dict[str, object]] = []
    component_rows: list[dict[str, object]] = []
    gap_rows: list[dict[str, object]] = []
    overlap_rows: list[dict[str, object]] = []
    spatial_findings: list[dict[str, str]] = []
    control_pngs: list[Path] = []
    landed = current_landed_province_ids(titles, set(definition))
    if not args.skip_geometry:
        geometry, palette_bounds = scan_map_geometry(
            current_mod / "map_data/provinces.png",
            definition,
            by_rgb,
        )
        (
            metric_rows,
            component_rows,
            gap_rows,
            overlap_rows,
            spatial_findings,
        ) = build_spatial_audit(
            current_regions,
            resolver,
            titles,
            definition,
            geometry,
            args.max_gap_provinces,
        )

    silk_rows, silk_findings = build_silk_road_audit(
        current_regions,
        resolver,
        landed,
        metric_rows,
        gap_rows,
        reference_rows,
    )
    projection_rows, projection_findings = build_silk_projection_audit(
        current_regions,
        resolver,
        vanilla_resolver,
        vanilla_east_projection,
        definition,
    )
    all_findings_by_id: dict[str, dict[str, str]] = {}
    for row in (
        reference_findings
        + spatial_findings
        + silk_findings
        + projection_findings
    ):
        all_findings_by_id.setdefault(row["finding_id"], row)
    findings = sorted(
        all_findings_by_id.values(),
        key=lambda row: (
            {"blocker": 0, "review": 1, "info": 2}.get(row["severity"], 9),
            row["classification"],
            row["path"],
            int(row["line"]),
            row["object"],
        ),
    )

    diagnostics = (
        [("current", value) for value in current_diagnostics]
        + [("premerge_git", value) for value in git_diagnostics]
        + [("premerge_parser", value) for value in premerge_diagnostics]
        + [("asil_parser", value) for value in asil_diagnostics]
        + [("vanilla_parser", value) for value in vanilla_diagnostics]
    )
    diagnostics_rows = [
        {"source": source, "diagnostic": diagnostic}
        for source, diagnostic in diagnostics
    ]
    coverage_rows = build_coverage_rows(
        geometry_enabled=not args.skip_geometry,
        premerge_sources=len(premerge_sources),
        asil_sources=len(asil_sources),
        vanilla_sources=len(vanilla_sources),
        parser_diagnostics=len(diagnostics),
    )
    manifest_rows = build_input_manifest(
        repo_root,
        current_mod,
        asil_mod,
        vanilla_root,
        args.premerge_revision,
        vanilla_east_tracking,
    )

    write_csv(output_dir / "geographical_region_inventory.csv", inventory_rows)
    write_csv(output_dir / "geographical_region_references.csv", reference_rows)
    write_csv(output_dir / "geographical_region_findings.csv", findings)
    write_csv(output_dir / "geographical_region_spatial_metrics.csv", metric_rows)
    write_csv(output_dir / "geographical_region_components.csv", component_rows)
    write_csv(output_dir / "geographical_region_gap_candidates.csv", gap_rows)
    write_csv(output_dir / "geographical_region_nested_overlaps.csv", overlap_rows)
    write_csv(output_dir / "silk_road_region_closure.csv", silk_rows)
    write_csv(
        output_dir / "silk_road_vanilla_east_projection_coverage.csv",
        projection_rows,
    )
    write_csv(output_dir / "coverage.csv", coverage_rows)
    write_csv(output_dir / "input_manifest.csv", manifest_rows)
    write_csv(output_dir / "diagnostics.csv", diagnostics_rows)
    manual_path = output_dir / "geographical_region_manual_review.csv"
    write_csv(manual_path, merge_manual_decisions(manual_path, findings))

    if geometry is not None:
        control_pngs = render_control_pngs(
            current_mod / "map_data/provinces.png",
            by_rgb,
            current_regions,
            resolver,
            landed,
            gap_rows,
            output_dir,
        )

    current_revision = git_revision(repo_root)
    asil_repo = asil_mod.parent if asil_mod.name == "BookmarksGit" else asil_mod
    asil_revision = git_revision(asil_repo)
    write_summary(
        output_dir / "geographical_region_closure_summary.md",
        repo_root=repo_root,
        current_revision=current_revision,
        asil_revision=asil_revision,
        premerge_revision=git_revision(repo_root, args.premerge_revision),
        regions=current_regions,
        reference_rows=reference_rows,
        findings=findings,
        metric_rows=metric_rows,
        gap_rows=gap_rows,
        overlap_rows=overlap_rows,
        silk_rows=silk_rows,
        projection_rows=projection_rows,
        coverage_rows=coverage_rows,
        palette_bounds=palette_bounds,
        geometry=geometry,
    )

    print(f"effective regions: {len(current_regions)}")
    print(f"direct references: {len(reference_rows)}")
    print(f"findings: {len(findings)}")
    print(f"gap candidates: {len(gap_rows)}")
    print(f"nested overlaps: {len(overlap_rows)}")
    print(f"diagnostics: {len(diagnostics_rows)}")
    print(f"control pngs: {len(control_pngs)}")
    print(f"output: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
