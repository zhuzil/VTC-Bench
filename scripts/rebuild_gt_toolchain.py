#!/usr/bin/env python3
"""Rebuild the GT-toolchain TSV against the canonical published metadata.

The original GT-toolchain file was generated before the selected color and
counting samples were renumbered for release.  The toolchains themselves are
ordered correctly within each category, but the accompanying IDs, image paths,
questions, and answers are stale.  This script keeps only ``model_tools_gt``
from that file and takes every other field from ``data/VTC-Bench.tsv``.
"""

from __future__ import annotations

import argparse
import csv
import os
import tempfile
from collections import defaultdict
from pathlib import Path


METADATA_FIELDS = [
    "index",
    "id",
    "category",
    "image",
    "question",
    "answer",
    "A",
    "B",
    "C",
    "D",
]
OUTPUT_FIELDS = [*METADATA_FIELDS, "model_tools_gt"]


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise ValueError(f"Missing TSV header: {path}")
        rows = list(reader)
    return rows


def group_by_category(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["category"]].append(row)
    return grouped


def rebuild(
    canonical_rows: list[dict[str, str]],
    source_gt_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    if len(canonical_rows) != 680 or len(source_gt_rows) != 680:
        raise ValueError(
            "Expected 680 rows in both files, got "
            f"canonical={len(canonical_rows)}, GT={len(source_gt_rows)}"
        )

    source_by_category = group_by_category(source_gt_rows)
    canonical_by_category = group_by_category(canonical_rows)

    if set(source_by_category) != set(canonical_by_category):
        raise ValueError(
            "Category sets differ: "
            f"canonical={sorted(canonical_by_category)}, "
            f"GT={sorted(source_by_category)}"
        )

    chains_by_category: dict[str, list[str]] = {}
    for category, canonical_category_rows in canonical_by_category.items():
        source_category_rows = source_by_category[category]
        if len(canonical_category_rows) != len(source_category_rows):
            raise ValueError(
                f"Category {category!r} has different row counts: "
                f"canonical={len(canonical_category_rows)}, "
                f"GT={len(source_category_rows)}"
            )
        chains = [row.get("model_tools_gt", "").strip() for row in source_category_rows]
        if any(not chain for chain in chains):
            raise ValueError(f"Category {category!r} contains an empty model_tools_gt")
        chains_by_category[category] = chains

    category_offsets: dict[str, int] = defaultdict(int)
    rebuilt_rows: list[dict[str, str]] = []
    for canonical_row in canonical_rows:
        category = canonical_row["category"]
        offset = category_offsets[category]
        category_offsets[category] += 1

        rebuilt = {field: canonical_row.get(field, "") for field in METADATA_FIELDS}
        rebuilt["model_tools_gt"] = chains_by_category[category][offset]
        rebuilt_rows.append(rebuilt)

    ids = [row["id"] for row in rebuilt_rows]
    if len(set(ids)) != len(ids):
        raise ValueError("Canonical TSV contains duplicate IDs")

    mismatched_image_ids = [
        row["id"]
        for row in rebuilt_rows
        if Path(row["image"]).stem != row["id"]
    ]
    if mismatched_image_ids:
        preview = ", ".join(mismatched_image_ids[:10])
        raise ValueError(
            "Canonical TSV contains IDs that do not match their image filenames: "
            f"{preview}"
        )

    return rebuilt_rows


def write_tsv_atomic(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=OUTPUT_FIELDS,
                delimiter="\t",
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--canonical",
        type=Path,
        default=repo_root / "data" / "VTC-Bench.tsv",
        help="Canonical published metadata TSV",
    )
    parser.add_argument(
        "--source-gt",
        type=Path,
        default=repo_root / "data" / "VTC-Bench_GTToolChain.tsv",
        help="TSV providing category-ordered model_tools_gt values",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=repo_root / "data" / "VTC-Bench_GTToolChain.tsv",
        help="Corrected GT-toolchain TSV",
    )
    args = parser.parse_args()

    canonical_rows = read_tsv(args.canonical)
    source_gt_rows = read_tsv(args.source_gt)
    rebuilt_rows = rebuild(canonical_rows, source_gt_rows)
    write_tsv_atomic(args.output, rebuilt_rows)
    print(f"Wrote {len(rebuilt_rows)} rows to {args.output}")


if __name__ == "__main__":
    main()
