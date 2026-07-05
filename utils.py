"""Shared utilities: fuzzy matching, confidence flagging, redaction checks,
and the common "value wrapper" JSON shape used by every extracted field.
"""
from __future__ import annotations
import difflib
import re
import numpy as np
from PIL import Image

import config


def fuzzy_label_match(candidate_text: str, aliases: list[str],
                       threshold: float = config.FUZZY_MATCH_THRESHOLD) -> bool:
    """Case-insensitive, typo-tolerant match of an OCR'd label against a list
    of known aliases for a field. Not exact string equality — OCR text won't
    be perfectly clean.

    The substring check below is deliberately guarded by a length-ratio
    requirement. Without it, a short single word that happens to be a
    literal substring of a longer multi-word alias would count as a match
    regardless of context — e.g. the standalone word "Consumer" (from an
    unrelated "You are a STAR Consumer" marketing badge present on every
    K-Electric bill) is a substring of the alias "consumer name", but is
    obviously not actually that label. The real similarity between
    "consumer" and "consumer name" via SequenceMatcher is only 0.762 — below
    threshold, i.e. the proper fuzzy check already correctly rejects it. An
    earlier version of this function had an unconditional substring
    shortcut that overrode that correct rejection. Requiring the shorter
    string to cover a real fraction of the longer one keeps genuine partial
    OCR reads (e.g. "amount payabl" for "amount payable") working while
    filtering out short, generic, unrelated words.
    """
    candidate = candidate_text.strip().lower()
    if not candidate:
        return False
    for alias in aliases:
        alias_l = alias.lower()
        shorter, longer = (candidate, alias_l) if len(candidate) <= len(alias_l) else (alias_l, candidate)
        if shorter and shorter in longer and len(shorter) / len(longer) >= 0.7:
            return True
        ratio = difflib.SequenceMatcher(None, candidate, alias_l).ratio()
        if ratio >= threshold:
            return True
    return False


def bbox_distance(a: tuple, b: tuple) -> float:
    """Euclidean distance between the centers of two bboxes (x0,y0,x1,y1)."""
    ax = (a[0] + a[2]) / 2
    ay = (a[1] + a[3]) / 2
    bx = (b[0] + b[2]) / 2
    by = (b[1] + b[3]) / 2
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5


def find_nearest_value(label_bbox: tuple, tokens: list, pattern: str,
                        exclude_bboxes: set | None = None, max_distance: float = 400):
    """Given a label's bbox, find the closest token whose text matches `pattern`
    (a value shape: numeric, date, ID, etc.) rather than assuming fixed position."""
    exclude_bboxes = exclude_bboxes or set()
    best = None
    best_dist = float("inf")
    for tok in tokens:
        if tok.bbox in exclude_bboxes:
            continue
        if not re.search(pattern, tok.text):
            continue
        d = bbox_distance(label_bbox, tok.bbox)
        if d < best_dist and d <= max_distance:
            best_dist = d
            best = tok
    return best


def make_field(value, confidence: float, threshold: float = config.DEFAULT_CONFIDENCE_THRESHOLD,
               extra: dict | None = None) -> dict:
    """Common wrapper: every extracted field is {value, confidence, flagged, ...}
    — never a bare value, per the output-schema requirement."""
    field = {
        "value": value,
        "confidence": round(float(confidence), 4) if confidence is not None else 0.0,
        "flagged": (confidence is None) or (confidence < threshold) or (value is None),
    }
    if extra:
        field.update(extra)
    return field


# Matches the first well-formed decimal number in a string: digits, optional
# comma grouping, optional single decimal point. Deliberately anchored so it
# can't match a string with two separate number-like fragments concatenated
# together (e.g. two adjacent OCR tokens merged into one row/cell) — it just
# extracts the first clean number instead of trying to parse the whole mess.
#
# The comma-grouped branch requires AT LEAST ONE comma group (+, not *) —
# with * it would happily match just the first 1-3 digits of a bare number
# with no comma at all (e.g. "2363" matching only "236") and stop there,
# since the comma group was optional and satisfied by zero occurrences.
# Requiring + means a comma-less run of digits fails that branch entirely
# and falls through to the second, fully-greedy alternative instead.
_CLEAN_NUMBER_RE = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")


def safe_parse_amount(raw_text: str) -> float | None:
    """Extract a single numeric amount from OCR'd text, never raising.

    Replaces the old pattern of `re.sub(r"[^\\d.]", "", text)` followed by a
    bare `float(...)` call, which crashes with ValueError whenever OCR merges
    two adjacent number-shaped tokens into one string (e.g. two transaction
    amounts on the same visual row collapsing into ".49046.91" — two decimal
    points, not parseable as a single float). Returns None on failure rather
    than raising, so callers can degrade to a flagged/low-confidence field
    instead of the whole image failing.
    """
    if not raw_text:
        return None
    match = _CLEAN_NUMBER_RE.search(raw_text)
    if not match:
        return None
    numeric_str = match.group(0).replace(",", "")
    try:
        return float(numeric_str)
    except ValueError:
        return None


def region_looks_redacted(image_path: str, bbox: tuple) -> bool:
    """Heuristic redaction check: crop the region around where a value should be
    and test whether it looks like a solid block (very low pixel variance) rather
    than natural text (which has high local variance from strokes on background).
    This is intentionally conservative — it only flags clear solid-block regions,
    not just "low confidence" text, to avoid mislabeling faint/blurry text as
    redacted.
    """
    try:
        img = Image.open(image_path).convert("L")
        x0, y0, x1, y1 = [int(v) for v in bbox]
        # Sample the INTERIOR of the region, shrunk inward — padding outward
        # instead would pull in the background-to-block edge contrast and
        # falsely inflate variance right at the boundary of a real redaction
        # block. Shrinking is safe because redaction blocks are drawn a few
        # pixels larger than the text they cover, by design.
        shrink_x = max(2, int((x1 - x0) * 0.15))
        shrink_y = max(2, int((y1 - y0) * 0.15))
        ix0, iy0 = x0 + shrink_x, y0 + shrink_y
        ix1, iy1 = x1 - shrink_x, y1 - shrink_y
        if ix1 <= ix0 or iy1 <= iy0:
            ix0, iy0, ix1, iy1 = x0, y0, x1, y1  # region too small to shrink
        ix0, iy0 = max(0, ix0), max(0, iy0)
        ix1, iy1 = min(img.width, ix1), min(img.height, iy1)
        if ix1 <= ix0 or iy1 <= iy0:
            return False
        crop = np.array(img.crop((ix0, iy0, ix1, iy1)))
        if crop.size == 0:
            return False
        std = crop.std()
        # Natural text-on-background has meaningful pixel variance; a solid
        # highlighter/redaction block does not.
        return std < 6.0
    except Exception:
        return False


def safe_json_default(obj):
    """json.dumps default= handler for numpy types that sneak into results."""
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.ndarray,)):
        return obj.tolist()
    return str(obj)
