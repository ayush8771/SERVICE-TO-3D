import json
import csv
import re
from pathlib import Path
import pdfplumber

DATA_DIR = Path(__file__).parent.parent / "data"
OUT_DIR = Path(__file__).parent.parent / "outputs"
OUT_DIR.mkdir(exist_ok=True)



def parse_parts_catalogue():
    """Extract text + tables from the parts catalogue PDF."""
    path = DATA_DIR / "IPC-GBX-450E_parts_catalogue.pdf"
    mentions = []

    with pdfplumber.open(path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            codes = re.findall(r"GBX-[A-Z0-9\-]+", text)

            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    if row and any(row):
                        mentions.append({
                            "source": "IPC-GBX-450E_parts_catalogue.pdf",
                            "page": page_num,
                            "row": row,
                        })

            if codes:
                mentions.append({
                    "source": "IPC-GBX-450E_parts_catalogue.pdf",
                    "page": page_num,
                    "referenced_codes": codes,
                    "raw_text_snippet": text[:300],
                })

    return mentions
def parse_service_steps():
    """Extract part-like mentions from service_steps.json"""
    path = DATA_DIR / "service_steps.json"
    with open(path, "r") as f:
        doc = json.load(f)

    mentions = []
    for step in doc["steps"]:
        # pull any OEM-style part codes mentioned in the instruction text
        # pattern matches things like GBX-OS-124-B, GBX-BC-108, etc.
        codes = re.findall(r"GBX-[A-Z0-9\-]+", step.get("instruction", ""))
        mentions.append({
            "source": "service_steps.json",
            "step_id": step.get("step_id"),
            "title": step.get("title"),
            "raw_text": step.get("instruction"),
            "referenced_codes": codes,
            "qty": step.get("qty") or step.get("expected_part_count"),
        })
    return mentions


def parse_parts_xref():
    """Each row is already a clean record."""
    path = DATA_DIR / "parts_xref.csv"
    mentions = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            mentions.append({
                "source": "parts_xref.csv",
                "oem_pn": row.get("oem_pn"),
                "description_family": row.get("description_family"),
                "supplier": row.get("supplier"),
                "supplier_pn": row.get("supplier_pn"),
                "din_ref": row.get("din_ref"),
                "status_note": row.get("status_note"),
            })
    return mentions


def parse_inspection_log():
    """Messy CSV - keep raw, flag obviously junk rows."""
    path = DATA_DIR / "inspection_log.csv"
    mentions = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            part_no = (row.get("part_no") or "").strip()
            disposition = (row.get("disposition") or "").strip().upper()
            is_junk = (
                not part_no
                or "UNKNOWN" in disposition
                or "VOID" in disposition
            )
            mentions.append({
                "source": "inspection_log.csv",
                "part_no": part_no,
                "feature": row.get("feature"),
                "disposition": row.get("disposition"),
                "raw_date": row.get("date"),
                "is_junk": is_junk,
            })
    return mentions


def parse_work_order():
    """Text file - lines with supplier PN, qty, disposition."""
    path = DATA_DIR / "work_order_WO-7741.txt"
    mentions = []
    with open(path, "r") as f:
        lines = f.readlines()

    for line in lines:
        # match lines like: " 1    DFT-BA-20x35x7-FKM      1    fitted, drive-end..."
        m = re.match(r"\s*(\d+)\s+([A-Za-z0-9\-\.]+)\s+(\d+)\s+(.*)", line)
        if m:
            mentions.append({
                "source": "work_order_WO-7741.txt",
                "line_no": m.group(1),
                "supplier_pn": m.group(2),
                "qty": m.group(3),
                "disposition_text": m.group(4).strip(),
            })
    return mentions


if __name__ == "__main__":
    all_mentions = {
        "service_steps": parse_service_steps(),
        "parts_xref": parse_parts_xref(),
        "inspection_log": parse_inspection_log(),
        "work_order": parse_work_order(),
        "parts_catalogue": parse_parts_catalogue(),
    }

    for key, records in all_mentions.items():
        print(f"{key}: {len(records)} records extracted")

    with open(OUT_DIR / "parsed_sources.json", "w") as f:
        json.dump(all_mentions, f, indent=2)

    print(f"\nSaved to {OUT_DIR / 'parsed_sources.json'}")