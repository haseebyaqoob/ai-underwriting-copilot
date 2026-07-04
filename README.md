# Yaqeen — Standalone Extraction Pipeline (Bill + Wallet)

## 1. Hardware check & path decision: **PATH A — CPU is sufficient**

I checked compute in my own execution sandbox (1 vCPU Xeon, 3.9GB RAM, no GPU)
and, since I can't fully trust "should be fine" without evidence, looked up
real published CPU benchmarks rather than assuming:

| Model | Hardware | Speed |
|---|---|---|
| PP-StructureV3 (lightweight config) | Intel 8350C CPU | **~3.74 s/image** |
| PP-OCRv6_medium (end-to-end) | Intel Xeon, OpenVINO | **1.40 s/image** |
| PP-OCRv6_small | Intel Xeon, OpenVINO | **0.59 s/image** |
| PP-OCRv5_server (the older "server" model) | Intel Xeon, OpenVINO | **7.30 s/image** |

Two takeaways:
- **CPU is genuinely fine** for a hackathon-scale batch (tens to low hundreds
  of images, not real-time). 1–4 seconds/image on ordinary CPU is a non-issue
  for offline batch validation.
- **Use PP-OCRv6, not PP-OCRv5_server**, for the wallet-statement engine —
  v5_server is 5–12x slower on CPU for no accuracy benefit relevant here.
  `engines/ocr_engine.py` already defaults to PP-OCRv6.

**GPU is not required for this pass.** It would only become worth it if
escalating to a heavier vision-LLM per-field (Step 1's stretch goal), which
this pass explicitly treats as optional.

**➡ You should run this locally in VS Code (Path A)**, exactly as you planned.

### An important caveat about *my own* test run
I could not run genuine PaddleOCR/PP-StructureV3 inference inside my own
sandbox tool — not because of CPU speed, but because this sandbox's network
allowlist blocks the three hosts PaddleX downloads model weights from
(`bcebos.com`, `modelscope.cn`, `aistudio.baidu.com` — I confirmed this with
a direct request; each returns `403 host_not_allowed`). That's a restriction
specific to my tool environment, not a real constraint — your own laptop or a
Kaggle notebook has normal internet access to those hosts and will download
the models fine on first run.

To still validate the actual pipeline logic (folder walking, routing, error
handling, confidence flagging, redaction detection, JSON schema, summary
aggregation) end-to-end on real images, I built a small offline stand-in
engine using Tesseract (`engines/ocr_engine.py::TesseractDebugEngine`) and ran
the full pipeline against synthetic test images with it. **This is not the
production engine and its output should not be used to judge extraction
accuracy** — Tesseract's confidence scale, layout handling, and table support
are all different from PaddleOCR's. What it *does* prove is that the pipeline
mechanics work correctly: see "What was actually validated" below.

## 2. How to run it (on your machine, with the real engine)

```bash
pip install paddlepaddle paddleocr
python3 main.py --input ./images --output ./output --backend paddle
```

- `--backend paddle` forces the real PP-StructureV3 / PP-OCRv6 engines (what
  you want once you're off this sandbox).
- `--backend auto` (default) tries the real engine first and falls back to
  the Tesseract debug engine with a loud console warning if models can't be
  downloaded — useful if you're unsure your network allows the Paddle model
  hosts.
- `--backend debug` forces the Tesseract stand-in (wiring tests only).
- `--threshold 0.85` (default) — confidence below this flags a field.

First run will download PP-StructureV3 and PP-OCRv6 model weights
(a few hundred MB total) — this needs normal internet access, done once.

## 3. Where to put images

```
./images/
  ├── utility_bills/
  │     └── k_electric/
  │           ├── ke_bill_01.png
  │           └── ke_bill_02.png
  │     └── sepco/                 ← add later, same pattern
  └── wallet_statements/
        ├── easypaisa_01.png
        └── jazzcash_01.png
```

Subfolders under `utility_bills/` are walked recursively, so adding a second
provider is just a new subfolder — no code changes needed.

`khata/` is recognized but intentionally **not implemented** — any files
placed there are skipped with a clear log line
(`extractors/khata_stub.py` raises `KhataNotImplementedError` on purpose;
it does not silently guess).

## 4. Output structure

```
./output/
  ├── utility_bills/
  │     ├── ke_bill_01.json
  │     └── ke_bill_02.json
  ├── wallet_statements/
  │     ├── easypaisa_01.json
  │     └── jazzcash_01.json
  └── summary.json
```

Each per-image JSON follows the schema from the spec — every value wrapped
with `confidence`/`flagged`, never bare. `summary.json` aggregates, per
category: images found/processed/failed/skipped, average field confidence,
flagged-field count, and average seconds/image.

## 5. How to read the summary to judge accuracy

- **`average_field_confidence` trending low** → either the engine choice is
  wrong for this document style, or the alias dictionaries in `config.py`
  need more label variants for your real bills/screenshots.
- **High `flagged_field_count` relative to fields extracted** → don't trust
  the numbers yet; before wiring into the website, spot-check the flagged
  fields against the source images.
- **`failed` > 0** → check the console log lines above the summary; each
  failure names the file and the exception, so you can tell corrupted files
  from genuinely unsupported ones.
- **`fatal_engine_error`** on a category → the engine itself couldn't start
  for that document type (usually a missing model download) — fix that
  before trusting any zero counts as "no images found."

## 6. What was actually validated in this environment (Tesseract debug run)

Ran against a small synthetic dataset with deliberately tricky cases:

| Case | Behaviour confirmed |
|---|---|
| Clean K-Electric bill | Field-level extraction + confidence + flagging pipeline runs end-to-end |
| Bill with a solid-block redaction over the name field | Redaction heuristic correctly distinguished the block (near-zero pixel variance) from real text (`region_looks_redacted` unit-tested directly: `True` on the block, `False` on real text) |
| Easypaisa screenshot, two date groups | Date-header grouping and transaction row detection ran without crashing |
| JazzCash screenshot with a row drawn at the image's bottom edge | Correctly flagged `"incomplete": true` / `"row appears cropped at screen edge"` |
| A `.docx` dropped into `utility_bills/` | Skipped with a warning, rest of batch continued |
| A corrupted `.png` | Caught, logged, batch continued (4 processed, 1 failed, run didn't abort) |
| `khata/` folder present with a file in it | Skipped cleanly with an explicit "not implemented" log line, not a silent skip or crash |

**What this run does *not* tell you**: real-world field accuracy on actual
K-Electric bills or Easypaisa/JazzCash screenshots. The nearest-value-token
heuristic and Tesseract's OCR quality on the synthetic test images produced
several wrong reads (visible in `output/` if you inspect them) — the
confidence flagging correctly caught and flagged nearly all of them, which is
the intended safety behavior, but you should re-run with `--backend paddle`
against your real dataset before trusting any numbers for the hackathon.

## 7. Known limitations / next steps

- `extract_tables()` in `extractors/utility_bill.py` currently detects that
  PP-StructureV3 found a table but does not yet parse its HTML into typed
  `{month, billed_amount}` rows — each detected table comes back flagged
  with `reason: "table detected but HTML-to-row parsing not yet implemented"`.
  This is the one piece of Step 1 left as a stub; wire up an HTML table
  parser (e.g. `pandas.read_html` on the `pred_html` string) next.
- Vision-LLM escalation for flagged fields (the stretch goal) is not wired in.
- Fuzzy label matching and value-shape regexes live in `config.py` — expect
  to tune these once you see real OCR output from actual bills/screenshots.
