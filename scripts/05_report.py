import json
from pathlib import Path
from datetime import datetime

OUT_DIR = Path(__file__).parent.parent / "outputs"

def load(name):
    with open(OUT_DIR / name) as f:
        return json.load(f)

def build_report():
    entities = load("entities_final.json")

    mapping = {}
    low_confidence = {}

    for eid, ent in entities.items():
        record = {
            "entity_id": eid,
            "canonical_description": ent.get("canonical_description"),
            "aliases": sorted(ent.get("aliases", [])),
            "sources_found_in": sorted(set(ent.get("sources_found_in", []))),
            "qty_per_assembly": ent.get("qty_catalogue"),
            "qty_original_before_bulletin": ent.get("qty_catalogue_original"),
            "referenced_in_steps": sorted(set(ent.get("referenced_in_steps", []))),
            "inspection_findings": ent.get("referenced_in_inspection", []),
            "work_order_activity": ent.get("referenced_in_work_order", []),
            "confidence": ent.get("confidence"),
            "notes": ent.get("notes", []),
        }
        if ent.get("confidence", 0) >= 0.7:
            mapping[eid] = record
        else:
            low_confidence[eid] = record

    manual_note = {
        "topic": "Step 20-30 mid-ring bolt count",
        "issue": "WM-GBX-450E rev.C says 'remove both mid-ring retaining bolts' (implies 2). "
                 "SB-2019-04 corrects this to 3 - a third boss was added at casting rev.E, "
                 "after the manual text was written (1998).",
        "resolution": "Bulletin is authoritative per its own header. Step 20-30 should be "
                       "treated as removing 3 bolts, not 2, for -E variant units.",
        "affects_entity_mapping": False,
        "affects_step_interpretation": True,
    }

    summary = {
        "generated": datetime.now().isoformat(),
        "total_entities_resolved": len(mapping),
        "total_low_confidence": len(low_confidence),
        "bulletin_overrides_applied": [
            "GBX-HXB-122 qty corrected 16 -> 18 (casting rev.E)",
            "GBX-OS-124-B merged into GBX-OS-124 as supersession alias",
        ],
        "known_step_level_correction_not_captured_in_entity_mapping": manual_note,
        "junk_rows_excluded": ["GBX-ZZ-999 (UNKNOWN PN)", "GBX-XX-000 (VOID ROW)"],
    }

    with open(OUT_DIR / "mapping.json", "w") as f:
        json.dump(mapping, f, indent=2)

    with open(OUT_DIR / "low_confidence.json", "w") as f:
        json.dump(low_confidence, f, indent=2)

    with open(OUT_DIR / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    return summary

if __name__ == "__main__":
    summary = build_report()
    print(json.dumps(summary, indent=2))
    print(f"\nFinal deliverable: {OUT_DIR / 'mapping.json'}")