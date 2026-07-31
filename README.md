# Service-to-3D: Cross-Source Part Mapping (PS3)

## What this project builds
This project builds a deterministic, explainable data-pipeline that links the same physical gearbox part across multiple inconsistent service and parts sources into one canonical record per part.

The system reads and reconciles:
- a parts catalogue PDF,
- a supplier-to-OEM part cross-reference CSV,
- service step instructions,
- an inspection log,
- a work-order text file,
- and an authoritative service bulletin.

The final output is a canonical, cross-source mapping of part entities, with high-confidence records in `outputs/mapping.json`, uncertain or orphan-like cases in `outputs/low_confidence.json`, and an executive summary in `outputs/summary.json`.

## What the inputs are
The main input sources are stored in `data/`:

- `data/IPC-GBX-450E_parts_catalogue.pdf`
  - the most structured source, used to seed true OEM-level catalogue entities
- `data/parts_xref.csv`
  - supplier part number ↔ OEM part number bridge table
- `data/service_steps.json`
  - step-by-step service instructions containing OEM-style part references
- `data/inspection_log.csv`
  - shop-floor inspection log rows, some of which are junk/invalid
- `data/work_order_WO-7741.txt`
  - work-order text file with supplier part references and quantity/disposition text
- `data/service_bulletin_SB-2019-04.md`
  - authoritative bulletin that overrides older catalogue/manual information

## How to run it
Install the required dependencies:

```bash
pip install -r requirements.txt
```

Run the pipeline in order:

```bash
python scripts/01_parse_sources.py
python scripts/02_normalize.py
python scripts/03_match_entities.py
python scripts/04_apply_bulletin.py
python scripts/05_report.py
python scripts/06_print_summary.py
```

### Final generated outputs
- `outputs/parsed_sources.json` — raw extracted mentions from all sources
- `outputs/catalogue_parts.json` — normalized catalogue part dictionary
- `outputs/entities_raw.json` — pre-bulletin entity resolution state
- `outputs/entities_final.json` — post-bulletin corrected entity state
- `outputs/mapping.json` — final resolved high-confidence mapping
- `outputs/low_confidence.json` — uncertain/low-confidence records
- `outputs/summary.json` — summary of overrides, exclusions, and notable corrections

## The approach taken and why
The approach is intentionally rule-based and explainable rather than model-driven.

### Core design choices
- The catalogue PDF is treated as the most structured and reliable source and is used to seed the canonical part records.
- The OEM part code is treated as the anchor identity.
- The supplier cross-reference table is used to translate supplier-only part numbers back to OEM PNs.
- Service-step and inspection records are linked in through direct OEM code mentions or through xref resolution.
- Fuzzy string similarity is used only as a secondary indicator for uncertain orphan records and never auto-merges them by itself.
- The service bulletin is applied last as an explicit authoritative override layer because it supersedes earlier documentation.
- Obviously junk inspection rows such as `UNKNOWN PN` and `VOID ROW` are excluded rather than silently matched.

### Why this works for this dataset
This dataset has the exact shape that suits a deterministic matching strategy:
- a clean catalogue with strong OEM reference structure,
- a cross-reference table that bridges supplier IDs to OEM IDs,
- and a bulletin that explicitly corrects known mistakes.

That combination makes a deterministic reconciliation pipeline more robust than a pure fuzzy matching approach.

## What works
The pipeline currently does the following well:

- Resolves all real OEM catalogue parts into a single canonical entity map.
- Uses supplier PN ↔ OEM PN cross-reference data to connect work-order records back to OEM entities.
- Detects and excludes obvious junk inspection rows instead of silently blaming them onto a valid part.
- Handles the one genuinely ambiguous dataset case by first identifying it as uncertain and then correcting it under the bulletin override layer.
- Produces a final auditable mapping and summary with the corrections that were actually applied.

## What does not work / limitations
The current implementation is effective for this dataset, but it is not fully generic.

Known limitations:
- The bulletin handling is hand-coded for this specific bulletin, not a general markdown parser.
- One correction in the bulletin is a step-level procedural correction (`2 -> 3` bolts in a maintenance sequence), which affects interpretation but does not map cleanly into part-entity JSON fields.
- Matching quality still depends heavily on the presence of correct OEM codes and accurate supplier cross-reference data.
- Fuzzy matching is intentionally conservative and is used as a review signal, not as a first-class primary matching strategy.

## What we built in plain terms
We built a cross-source part identity reconciliation system that turns messy operational records into one clean, canonical parts dictionary.

In practical terms, the project converts:
- a catalogue PDF,
- service instructions,
- shop-floor inspection entries,
- and supplier-oriented work-order references

into a single resolved entity model that can be explained and audited.

## What we would do with more time
If the project were extended, these would be the next improvements:

- Replace the hand-coded bulletin override with a generic markdown bulletin parser.
- Upgrade fuzzy matching from a secondary warning signal into a weighted scoring component inside the main matching logic.
- Add automated regression tests for known edge cases such as the `GBX-OS-124` / `GBX-OS-124-B` supersession scenario.
- Improve tolerance for partially missing or typo-prone codes.

## AI tools, external libraries, and models used
### AI tools used
No external LLM API calls were used for the core matching logic.

The final pipeline is deterministic and uses rule-based extraction, direct code matching, cross-reference resolution, and conservative fuzzy review logic.

### External libraries used
- `pdfplumber` — PDF text/table extraction for the parts catalogue
- `rapidfuzz` — fuzzy string similarity scoring for uncertain low-confidence orphan checks

### Standard Python libraries used
- `json`
- `csv`
- `re`
- `pathlib`

### Models used
No separate AI model or LLM was used in the final production pipeline. The matching behavior is implemented directly in Python using explicit regexing, lookup tables, and deterministic validation logic.

## Verified current run result
The current run produces a final resolved entity count of `32` with `0` low-confidence entities in the final mapping file. The summary also records that:
- `GBX-HXB-122` quantity was corrected from `16` to `18` by the bulletin,
- `GBX-OS-124-B` was merged into `GBX-OS-124` as a supersession alias,
- and two obviously junk inspection rows were excluded.
