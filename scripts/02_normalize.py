import json
import re
from pathlib import Path

OUT_DIR = Path(__file__).parent.parent / "outputs"

def load_parsed():
    with open(OUT_DIR / "parsed_sources.json") as f:
        return json.load(f)

def build_catalogue_parts(raw_catalogue):
    """Reshape the PDF's BOM table + per-part detail pages into one record per OEM part."""
    parts = {}

    # BOM table on page 4: [item, part_no, description, sub_asm, qty, material]
    for entry in raw_catalogue:
        row = entry.get("row")
        if row and len(row) == 6 and re.match(r"^\d+$|^—$", str(row[0])):
            _, pn, desc, sub_asm, qty, material = row
            parts[pn] = {
                "oem_pn": pn,
                "description": desc,
                "sub_asm": sub_asm,
                "qty_per_assy_catalogue": qty,
                "material": material,
                "envelope_mm": None,
                "category": None,
            }

    # Detail pages: alternating key-value rows, 2 rows per part
    # Row A: [Part number, PN, Category, cat]  Row B: [Qty / assy, q, Sub-asm, s]  Row C: [Material, m, Envelope, e]
    current_pn = None
    for entry in raw_catalogue:
        row = entry.get("row")
        if not row:
            continue
        if row[0] == "Part number":
            current_pn = row[1]
            if current_pn not in parts:
                parts[current_pn] = {"oem_pn": current_pn}
            parts[current_pn]["category"] = row[3] if len(row) > 3 else None
        elif row[0] == "Material" and current_pn:
            material = row[1]
            envelope_raw = row[3] if len(row) > 3 else None
            envelope_mm = normalize_envelope(envelope_raw)
            parts[current_pn]["material"] = material
            parts[current_pn]["envelope_mm"] = envelope_mm

    return parts

def normalize_envelope(envelope_raw):
    """Convert 'X × Y × Z cm *' to mm; leave mm values as-is."""
    if not envelope_raw:
        return None
    is_cm = "cm" in envelope_raw and "*" in envelope_raw
    nums = re.findall(r"[\d.]+", envelope_raw)
    nums = [float(n) for n in nums]
    if is_cm:
        nums = [n * 10 for n in nums]
    return {"dims_mm": nums, "was_cm_corrected": is_cm}

if __name__ == "__main__":
    data = load_parsed()
    catalogue_parts = build_catalogue_parts(data["parts_catalogue"])

    print(f"Parsed {len(catalogue_parts)} unique OEM parts from catalogue")
    print(json.dumps(catalogue_parts.get("GBX-OSH-115"), indent=2))
    print(json.dumps(catalogue_parts.get("GBX-HXB-122"), indent=2))

    with open(OUT_DIR / "catalogue_parts.json", "w") as f:
        json.dump(catalogue_parts, f, indent=2)