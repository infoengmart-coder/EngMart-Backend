"""Extractor for "Siemens Components Price List1.pdf" (Eng-Mart supplier list).

Layout: 8 pages, one ruled 10-column quotation table spanning all pages:
    S No | Component | Description | Model | Rating | K Rating | Make | Unit Rate | QTY | TOTAL
Serial numbers run 1..110 contiguously; every data row carries all 10 cells on a
single page (no cross-page cell splits), so pdfplumber's extract_tables() per
page is faithful.

price_pkr = the "Unit Rate" column (per-unit PKR price). QTY/TOTAL are
quotation quantities, not product data, but TOTAL is used as an internal
cross-check: round(unit_rate * qty) must equal TOTAL, proving we read the
correct price column for every row.

Model cells are wrapped across lines at existing hyphens (e.g. "3WT8121-\n5UN30-\n0AA2");
joining the lines with "" reconstructs the printed catalogue number exactly.
"""
import json
import random
import re
import statistics
from pathlib import Path

import pdfplumber

PDF_PATH = Path(r"C:/Users/AWCD/Desktop/client/engmart (2)/product-details/Siemens Components Price List1.pdf")
OUT_PATH = Path(r"C:/Users/AWCD/Desktop/client/engmart (2)/backend/extraction/out/siemens.json")

HEADER = ["S No", "Component", "Description", "Model", "Rating", "K Rating",
          "Make", "Unit Rate", "QTY", "TOTAL"]

# Siemens MLFB catalogue numbers start with a family block like 3WT8, 3WA1,
# 3VM1, 3RT2, 3RH2, 3RV2, 7KM4 ... — digit + letters + digit. That first
# 4-char block is the product series printed in the model itself (and echoed
# in descriptions, e.g. "circuit breaker 3VM1", "7KM PAC4200").
SERIES_RE = re.compile(r"^(\d[A-Z]{2}\d)")

RATING_RE = re.compile(r"^\d+(?:\.\d+)?A$")
KA_RE = re.compile(r"^\d+(?:\.\d+)?kA$", re.I)
KW_RE = re.compile(r"^\d+(?:\.\d+)?kW$", re.I)
PRICE_RE = re.compile(r"^\d+(?:\.\d+)?$")


def p(s):
    print(str(s).encode("ascii", "replace").decode())


def clean(cell):
    """Collapse a wrapped cell into one line of text."""
    if cell is None:
        return ""
    return re.sub(r"\s+", " ", cell.replace("\n", " ")).strip()


def clean_model(cell):
    """Model codes wrap at hyphens; join fragments with nothing, drop spaces."""
    if cell is None:
        return ""
    return re.sub(r"\s+", "", cell)


def parse():
    rows, skipped = [], []
    price_total_mismatches = []
    with pdfplumber.open(PDF_PATH) as pdf:
        n_pages = len(pdf.pages)
        for pi, page in enumerate(pdf.pages, start=1):
            for table in page.extract_tables():
                for raw in table:
                    cells = [(c or "") for c in raw]
                    raw_line = " | ".join(clean(c) for c in cells)
                    first = clean(cells[0])
                    # header row (repeated on page 1 only) — structural, skip silently
                    if first == "S No":
                        continue
                    if not first.isdigit():
                        skipped.append({"page": pi, "raw": raw_line,
                                        "reason": "row without serial number"})
                        continue
                    if len(cells) < 10:
                        skipped.append({"page": pi, "raw": raw_line,
                                        "reason": "unexpected column count"})
                        continue

                    s_no = int(first)
                    section = clean(cells[1])
                    desc = clean(cells[2])
                    model = clean_model(cells[3])
                    rating = clean(cells[4])
                    k_rating = clean(cells[5])
                    make = clean(cells[6])
                    unit_rate = clean(cells[7])
                    qty = clean(cells[8])
                    total = clean(cells[9])

                    if not PRICE_RE.match(unit_rate):
                        skipped.append({"page": pi, "raw": raw_line,
                                        "reason": "no parseable Unit Rate"})
                        continue
                    price = float(unit_rate)

                    # cross-check: TOTAL column == round(unit_rate * qty)
                    if qty.isdigit() and total.replace(",", "").isdigit():
                        if abs(price * int(qty) - int(total.replace(",", ""))) > 1.0:
                            price_total_mismatches.append((s_no, price, qty, total))

                    specs = {"s_no": s_no}
                    if rating and rating != "-":
                        # Rating column: amperage as printed (e.g. "1250A")
                        specs["rating"] = rating
                        if not RATING_RE.match(rating):
                            specs["rating_note"] = "as printed in Rating column"
                    if k_rating and k_rating != "-":
                        if KA_RE.match(k_rating):
                            specs["breaking_capacity"] = k_rating
                        elif KW_RE.match(k_rating):
                            specs["power"] = k_rating
                        else:
                            # e.g. "66 / 50 A" — printed verbatim, keep raw
                            specs["k_rating"] = k_rating
                    if "rating" not in specs:
                        # 3RV motor-protection rows print "-" in the Rating
                        # column but state the adjustable release range in the
                        # row text, e.g. "A-release 0.28...0.4 A" — keep it as
                        # a faithful spec (it is a setting range, NOT a single
                        # amperage, so it does not go into specs.rating).
                        mr = re.search(r"A-\s*release\s+([\d.]+\s*\.\.\.\s*[\d.]+)\s*A", desc)
                        if mr:
                            specs["release_range"] = re.sub(r"\s+", "", mr.group(1)) + "A"
                    m = SERIES_RE.match(model)
                    specs["series"] = m.group(1) if m else (model.split("-")[0] or section)

                    if price < 10 or price > 10_000_000:
                        skipped.append({"page": pi, "raw": raw_line, "reason": "sanity"})
                        continue

                    rows.append({
                        "page": pi,
                        "brand": make if make else "Siemens",
                        "section": section,
                        "model": model,
                        "description": (section + " - " + desc) if desc else section,
                        "price_pkr": price,
                        "specs": specs,
                        "_raw": raw_line,  # stripped before writing; kept for spot-check
                    })
    return rows, skipped, n_pages, price_total_mismatches


def dedupe(rows, skipped):
    """Same model + identical specs (ignoring s_no) twice:
    keep both only if prices differ (PDF genuinely lists them twice, e.g.
    3VM1063-2ED32-0AA0 at S.No 11 and 106 with different rates)."""
    seen = {}
    out = []
    for r in rows:
        key_specs = {k: v for k, v in r["specs"].items() if k != "s_no"}
        key = (r["model"], json.dumps(key_specs, sort_keys=True))
        if key in seen and seen[key]["price_pkr"] == r["price_pkr"]:
            skipped.append({"page": r["page"], "raw": r["_raw"],
                            "reason": "duplicate of S.No %d (same model+specs+price)"
                                      % seen[key]["specs"]["s_no"]})
            continue
        seen[key] = r
        out.append(r)
    return out


def main():
    rows, skipped, n_pages, mismatches = parse()
    rows = dedupe(rows, skipped)

    # ---- validation ----
    serials = sorted(r["specs"]["s_no"] for r in rows)
    missing = sorted(set(range(serials[0], serials[-1] + 1)) - set(serials))
    p("serial range %d..%d, missing serials: %s" % (serials[0], serials[-1], missing))
    p("unit_rate*qty vs TOTAL mismatches: %s" % (mismatches if mismatches else "none"))

    prices = [r["price_pkr"] for r in rows]
    p("price min/median/max: %.2f / %.2f / %.2f"
      % (min(prices), statistics.median(prices), max(prices)))

    # coverage: priced lines per page counted from raw text ("Siemens" appears
    # exactly once per data row in the Make column) vs parsed rows per page
    p("--- coverage check (3 pages) ---")
    with pdfplumber.open(PDF_PATH) as pdf:
        for pi in (2, 5, 8):
            raw_count = pdf.pages[pi - 1].extract_text().count("Siemens")
            parsed = sum(1 for r in rows if r["page"] == pi)
            p("page %d: raw 'Siemens' lines=%d  parsed rows=%d" % (pi, raw_count, parsed))

    p("--- spot-check: 10 random rows ---")
    random.seed(42)
    for r in random.sample(rows, 10):
        p("PARSED p%d %s | %s | %.2f | specs=%s" %
          (r["page"], r["model"], r["description"][:70], r["price_pkr"], r["specs"]))
        p("   RAW  " + r["_raw"][:160])

    for r in rows:
        del r["_raw"]

    out = {
        "source_pdf": PDF_PATH.name,
        "rows": rows,
        "skipped": skipped,
        "stats": {"pages": n_pages, "rows": len(rows),
                  "priced": sum(1 for r in rows if r["price_pkr"] is not None),
                  "skipped": len(skipped)},
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    p("stats: %s" % out["stats"])
    p("wrote %s" % OUT_PATH)


if __name__ == "__main__":
    main()
