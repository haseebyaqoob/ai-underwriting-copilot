from __future__ import annotations
import argparse
import gc
import json
import sys
import time
from pathlib import Path

import config
from utils import safe_json_default
from engines.ocr_engine import get_engine, EngineUnavailableError
from extractors import utility_bill, wallet_statement, khata_stub
from extractors.khata_stub import KhataNotImplementedError

SUPPORTED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"}

ROUTES = {
    "utility_bills": ("utility_bill", utility_bill),
    "wallet_statements": ("wallet_statement", wallet_statement),
    "khata": ("khata", khata_stub),
}


def walk_images(folder: Path):
    """Yield image files under `folder`, recursing into subfolders (e.g.
    utility_bills/k_electric/, utility_bills/sepco/ later) so adding a new
    provider doesn't require restructuring the walk."""
    if not folder.exists():
        return
    for path in sorted(folder.rglob("*")):
        if path.is_file():
            yield path


def process_folder(category: str, base_dir: Path, output_dir: Path, backend: str,
                    threshold: float, engine_cache: dict) -> dict:
    doc_type, extractor_module = ROUTES[category]
    category_dir = base_dir / category
    stats = {
        "category": category,
        "found": 0, "processed": 0, "failed": 0, "skipped_unsupported": 0,
        "flagged_field_count": 0, "per_image_seconds": [],
        "confidences": [],
    }

    if not category_dir.exists():
        print(f"[SKIP] {category}: folder not found at {category_dir} — skipping cleanly.")
        return stats

    files = list(walk_images(category_dir))
    if not files:
        print(f"[SKIP] {category}: folder exists but is empty — skipping cleanly.")
        return stats

    if doc_type == "khata":
        print(f"[SKIP] {category}: khata extraction not implemented in this pass "
              f"({len(files)} file(s) present, not processed). See extractors/khata_stub.py.")
        stats["found"] = len(files)
        stats["skipped_unsupported"] = len(files)
        return stats

    # Lazily init one engine per doc_type and reuse across all its images.
    if doc_type not in engine_cache:
        try:
            engine_cache[doc_type] = get_engine(doc_type, backend=backend)
        except EngineUnavailableError as e:
            print(f"[FATAL] Could not start OCR engine for {category}: {e}")
            stats["fatal_engine_error"] = str(e)
            return stats
    engine = engine_cache[doc_type]

    out_dir = output_dir / category
    out_dir.mkdir(parents=True, exist_ok=True)

    for path in files:
        stats["found"] += 1
        if path.suffix.lower() not in SUPPORTED_IMAGE_EXTS:
            print(f"[WARN] Skipping unsupported file type: {path}")
            stats["skipped_unsupported"] += 1
            continue

        t0 = time.time()
        try:
            result = extractor_module.extract(engine, str(path), threshold=threshold)
        except KhataNotImplementedError as e:
            print(f"[SKIP] {path}: {e}")
            stats["skipped_unsupported"] += 1
            continue
        except Exception as e:
            print(f"[FAIL] {path.name}: {type(e).__name__}: {e}")
            stats["failed"] += 1
            continue
        elapsed = time.time() - t0

        result["source_file"] = str(path)
        result.setdefault("warnings", [])

        # Roll up per-field confidence / flag stats for the summary.
        field_dict = result.get("fields", {})
        for fname, fval in field_dict.items():
            if isinstance(fval, dict) and "confidence" in fval:
                stats["confidences"].append(fval["confidence"])
                if fval.get("flagged"):
                    stats["flagged_field_count"] += 1

        out_path = out_dir / (path.stem + ".json")
        with open(out_path, "w") as f:
            json.dump(result, f, indent=2, default=safe_json_default)

        stats["processed"] += 1
        stats["per_image_seconds"].append(elapsed)
        print(f"[OK]   {path.name} -> {out_path.name}  ({elapsed:.2f}s, "
              f"{sum(1 for v in field_dict.values() if isinstance(v, dict) and v.get('flagged'))} flagged field(s))")

    return stats


def build_summary(all_stats: list[dict]) -> dict:
    summary = {"categories": {}, "totals": {"found": 0, "processed": 0, "failed": 0, "skipped": 0}}
    for s in all_stats:
        cat = s["category"]
        confidences = s.get("confidences", [])
        per_image = s.get("per_image_seconds", [])
        summary["categories"][cat] = {
            "found": s["found"],
            "processed": s["processed"],
            "failed": s["failed"],
            "skipped_unsupported": s["skipped_unsupported"],
            "average_field_confidence": round(sum(confidences) / len(confidences), 4) if confidences else None,
            "flagged_field_count": s["flagged_field_count"],
            "average_seconds_per_image": round(sum(per_image) / len(per_image), 3) if per_image else None,
            "fatal_engine_error": s.get("fatal_engine_error"),
        }
        summary["totals"]["found"] += s["found"]
        summary["totals"]["processed"] += s["processed"]
        summary["totals"]["failed"] += s["failed"]
        summary["totals"]["skipped"] += s["skipped_unsupported"]
    return summary


def main():
    parser = argparse.ArgumentParser(description="Yaqeen document extraction pipeline")
    parser.add_argument("--input", default="./images", help="Input folder (default ./images)")
    parser.add_argument("--output", default="./output", help="Output folder (default ./output)")
    parser.add_argument("--threshold", type=float, default=config.DEFAULT_CONFIDENCE_THRESHOLD,
                         help="Confidence flag threshold (default 0.85)")
    parser.add_argument("--backend", choices=["auto", "paddle", "debug"], default="auto",
                         help="'paddle' = real PP-StructureV3/PP-OCRv6 (requires model download), "
                              "'debug' = offline Tesseract stand-in for wiring tests, "
                              "'auto' = try paddle, fall back to debug with a loud warning")
    args = parser.parse_args()

    base_dir = Path(args.input)
    output_dir = Path(args.output)

    if not base_dir.exists():
        print(f"[ERROR] Input folder '{base_dir}' does not exist.\n"
              f"        Create it with subfolders utility_bills/ and wallet_statements/ "
              f"and place images inside, then re-run.")
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)
    engine_cache: dict = {}
    all_stats = []

    print(f"=== Yaqeen extraction pipeline ===")
    print(f"Input:  {base_dir.resolve()}")
    print(f"Output: {output_dir.resolve()}")
    print(f"Backend: {args.backend}\n")

    for category in ROUTES:
        stats = process_folder(category, base_dir, output_dir, args.backend,
                                args.threshold, engine_cache)
        all_stats.append(stats)
        print()

        # BUG FIX: engine_cache used to live for the ENTIRE run, so every
        # engine used so far stayed resident in memory even after its
        # category finished. Concretely: by the time wallet_statements
        # started, the full utility-bill engine (PP-StructureV3 — layout
        # model, table model, OCR det/rec, orientation classifiers) was
        # STILL loaded, on top of the new wallet-statement engine
        # (PP-OCRv6) being initialized. On a CPU-only machine with no GPU
        # (this project's dev environment), that's enough to exhaust
        # available RAM partway through a run — confirmed by the actual
        # failure pattern seen: 2 utility bills processed fine, the 3rd
        # failed on a tiny 22.4 MiB allocation (a sign of being right at
        # the memory ceiling, not one big spike), and the wallet-statement
        # engine then failed to even INITIALIZE immediately after — both
        # consistent with cumulative memory pressure, not a code bug in
        # the extractors themselves.
        #
        # Each category maps to exactly one doc_type/engine and nothing
        # downstream ever reuses a prior category's engine (utility_bills
        # -> wallet_statements -> khata are processed once, in order), so
        # it's always safe to drop this category's engine before moving to
        # the next one.
        doc_type, _ = ROUTES[category]
        if doc_type in engine_cache:
            del engine_cache[doc_type]
            gc.collect()

    summary = build_summary(all_stats)
    summary_path = output_dir / "summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2, default=safe_json_default)

    print("=== RUN SUMMARY ===")
    print(json.dumps(summary["totals"], indent=2))
    print(f"\nFull summary written to: {summary_path}")
    print(f"Per-image results written under: {output_dir.resolve()}")


if __name__ == "__main__":
    main()
