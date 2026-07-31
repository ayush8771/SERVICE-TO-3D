import json
from pathlib import Path

OUT_DIR = Path(__file__).parent.parent / "outputs"

def load(name):
    with open(OUT_DIR / name) as f:
        return json.load(f)

def print_table():
    mapping = load("mapping.json")

    print("=" * 100)
    print(f"{'OEM PART':<16} {'DESCRIPTION':<28} {'ALIASES':<32} {'CONF':<6}")
    print("=" * 100)

    for eid, rec in sorted(mapping.items()):
        desc = (rec.get("canonical_description") or "-")[:27]
        aliases = ", ".join(rec.get("aliases", [])) or "-"
        aliases = aliases[:31]
        conf = rec.get("confidence")
        print(f"{eid:<16} {desc:<28} {aliases:<32} {conf:<6}")

    print("=" * 100)
    print(f"Total resolved entities: {len(mapping)}")

    # highlight the interesting supersession case specifically
    print("\n--- Notable case: supersession correctly merged ---")
    seal = mapping.get("GBX-OS-124")
    if seal:
        print(f"Entity: {seal['entity_id']} ({seal['canonical_description']})")
        print(f"Aliases merged in: {seal['aliases']}")
        print(f"Confidence: {seal['confidence']}")
        for note in seal.get("notes", []):
            print(f"  Note: {note}")

    # highlight the qty correction
    print("\n--- Notable case: bulletin quantity correction ---")
    bolt = mapping.get("GBX-HXB-122")
    if bolt:
        print(f"Entity: {bolt['entity_id']} ({bolt['canonical_description']})")
        print(f"Qty now: {bolt['qty_per_assembly']}  (was: {bolt['qty_original_before_bulletin']})")
        for note in bolt.get("notes", []):
            print(f"  Note: {note}")

if __name__ == "__main__":
    print_table()