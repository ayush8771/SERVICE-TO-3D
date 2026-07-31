import json
from pathlib import Path
from rapidfuzz import fuzz

OUT_DIR = Path(__file__).parent.parent / "outputs"

def load(name):
    with open(OUT_DIR / name) as f:
        return json.load(f)

def build_xref_lookup(parts_xref):
    """supplier_pn -> oem_pn, and oem_pn -> list of supplier_pns (aliases)"""
    supplier_to_oem = {}
    oem_to_suppliers = {}
    for row in parts_xref:
        oem = row["oem_pn"]
        sup = row["supplier_pn"]
        supplier_to_oem[sup] = oem
        oem_to_suppliers.setdefault(oem, []).append(sup)
    return supplier_to_oem, oem_to_suppliers

def match_entities():
    parsed = load("parsed_sources.json")
    catalogue_parts = load("catalogue_parts.json")
    supplier_to_oem, oem_to_suppliers = build_xref_lookup(parsed["parts_xref"])

    entities = {}

    # seed entities from the catalogue (most structured, reliable source)
    for oem_pn, part in catalogue_parts.items():
        entities[oem_pn] = {
            "entity_id": oem_pn,
            "canonical_description": part.get("description"),
            "sources_found_in": ["IPC-GBX-450E_parts_catalogue.pdf"],
            "aliases": oem_to_suppliers.get(oem_pn, []),
            "qty_catalogue": part.get("qty_per_assy_catalogue"),
            "referenced_in_steps": [],
            "referenced_in_inspection": [],
            "referenced_in_work_order": [],
            "confidence": 0.95,  # catalogue is structured ground truth
            "notes": [],
        }

    # link service_steps mentions via explicit GBX-xxx codes
    for step in parsed["service_steps"]:
        for code in step.get("referenced_codes", []):
            if code in entities:
                entities[code]["sources_found_in"].append("service_steps.json")
                entities[code]["referenced_in_steps"].append(step["step_id"])
            else:
                # code mentioned in a step but not in catalogue - low confidence orphan
                entities.setdefault(code, {
                    "entity_id": code,
                    "canonical_description": None,
                    "sources_found_in": ["service_steps.json"],
                    "aliases": [],
                    "referenced_in_steps": [step["step_id"]],
                    "referenced_in_inspection": [],
                    "referenced_in_work_order": [],
                    "confidence": 0.4,
                    "notes": ["found only via direct code mention in step text, not in catalogue"],
                })

    # link inspection log via part_no (direct OEM code match)
    for row in parsed["inspection_log"]:
        pn = row["part_no"]
        if row["is_junk"]:
            continue
        if pn in entities:
            if "inspection_log.csv" not in entities[pn]["sources_found_in"]:
                entities[pn]["sources_found_in"].append("inspection_log.csv")
            entities[pn]["referenced_in_inspection"].append({
                "feature": row["feature"], "disposition": row["disposition"]
            })
        else:
            entities.setdefault(pn, {
                "entity_id": pn,
                "canonical_description": None,
                "sources_found_in": ["inspection_log.csv"],
                "aliases": [],
                "referenced_in_steps": [],
                "referenced_in_inspection": [{"feature": row["feature"], "disposition": row["disposition"]}],
                "referenced_in_work_order": [],
                "confidence": 0.3,
                "notes": ["part_no not found in catalogue - possibly typo or unlisted part"],
            })

    # link work order via supplier_pn -> oem_pn through xref
    for row in parsed["work_order"]:
        sup_pn = row["supplier_pn"]
        oem = supplier_to_oem.get(sup_pn)
        if oem and oem in entities:
            if "work_order_WO-7741.txt" not in entities[oem]["sources_found_in"]:
                entities[oem]["sources_found_in"].append("work_order_WO-7741.txt")
            entities[oem]["referenced_in_work_order"].append({
                "qty": row["qty"], "disposition": row["disposition_text"]
            })
        else:
            entities.setdefault(sup_pn, {
                "entity_id": sup_pn,
                "canonical_description": None,
                "sources_found_in": ["work_order_WO-7741.txt"],
                "aliases": [],
                "referenced_in_steps": [],
                "referenced_in_inspection": [],
                "referenced_in_work_order": [{"qty": row["qty"], "disposition": row["disposition_text"]}],
                "confidence": 0.2,
                "notes": ["supplier_pn has no OEM mapping in parts_xref.csv"],
            })

    # fuzzy-match any remaining low-confidence orphans against catalogue descriptions
    catalogue_descs = {pn: p.get("description", "") for pn, p in catalogue_parts.items()}
    for eid, ent in entities.items():
        if ent["confidence"] < 0.5 and ent.get("canonical_description") is None:
            best_score, best_pn = 0, None
            for pn, desc in catalogue_descs.items():
                score = fuzz.token_sort_ratio(eid, pn)
                if score > best_score:
                    best_score, best_pn = score, pn
            if best_score > 70:
                ent["notes"].append(f"fuzzy candidate match: {best_pn} (score {best_score}) - NOT auto-merged, needs review")

    return entities

if __name__ == "__main__":
    entities = match_entities()
    high_conf = {k: v for k, v in entities.items() if v["confidence"] >= 0.7}
    low_conf = {k: v for k, v in entities.items() if v["confidence"] < 0.7}

    print(f"Total entities: {len(entities)}")
    print(f"High confidence: {len(high_conf)}")
    print(f"Low confidence / uncertain: {len(low_conf)}")
    print("\nLow confidence entity IDs:", list(low_conf.keys()))

    with open(OUT_DIR / "entities_raw.json", "w") as f:
        json.dump(entities, f, indent=2)