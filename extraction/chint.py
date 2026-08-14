"""
Faithful extractor for "CHINT PRICE LIST 2020.pdf" (HL PK (PVT) LTD - CHINT, 4 pages).

Layout
------
One ruled table per page with columns:
    Serial No. | Name (section label, vertically merged) | Model | Unit | Price
pdfplumber's extract_table() reconstructs the grid almost perfectly:
vertically merged Name cells yield the label text once and None on spanned rows.
Pages 3-4 additionally contain full-width "banner" rows (e.g. "Indicators
Lights", "Atutomatic Transfer Switches") whose text lands in column 0.

Section handling
----------------
Section labels are anchored mid-block inside merged cells; on several blocks the
label text is physically placed BELOW the first data rows of its block (page 2
"Earth Leakage" 4300A block, page 3 "Thermal Overload Relays" block), and one
label is split across four ruled rows. A generic carry-down rule would mislabel
those edge rows, so section blocks are pinned as explicit (page, row-range)
spans in BLOCKS below, and every span is ASSERTED against the label text
actually extracted from the PDF. If the document or the extraction ever shifts,
the script fails loudly instead of silently mislabeling a price.

Price handling
--------------
No price is ever carried, averaged or guessed. Every emitted price comes from
that row's own Price cell. The only merged cells in this PDF are in the Name
(section) column. Rows whose Price cell prints "0" (the NXMLE-*/3300A earth
leakage block, 8 rows) are routed to "skipped" with reason "sanity" - a printed
0 PKR is a placeholder, not a sellable price. The single row with an empty
Price cell (serial 95, NXC-120 380V) is emitted with price_pkr=null and an
explanatory specs.note.

Known PDF anomaly (kept faithfully): page 1 lists "NXB-63 1P C80 6kA" twice -
once at 1106 inside the 1P block and once at 2197 inside the 2P block (between
2P C63 and 2P C100; almost certainly a "2P" misprinted as "1P"). Both rows are
emitted exactly as printed, with a specs.note on the anomalous one.

Run:
    venv/Scripts/python.exe extraction/chint.py
Writes: extraction/out/chint.json
"""

import json
import os
import random
import re
import statistics

import pdfplumber

PDF_PATH = r"C:/Users/AWCD/Desktop/client/engmart (2)/product-details/CHINT PRICE LIST 2020.pdf"
OUT_PATH = r"C:/Users/AWCD/Desktop/client/engmart (2)/backend/extraction/out/chint.json"

BRAND = "CHINT"
CERTS = "KEMA, CE, UL,VDE, PCT"  # as printed inside "(Cetrificate From ...)" labels


def p(s=""):
    print(str(s).encode("ascii", "replace").decode())


def norm(s):
    return re.sub(r"\s+", " ", s or "").strip()


# ---------------------------------------------------------------------------
# Section blocks: (first_row, last_row, section_label, assert_phrase)
# Row indices are into the page's extract_table() rows (0-based, inclusive).
# assert_phrase must appear in the label text extracted from those rows.
# ---------------------------------------------------------------------------
BLOCKS = {
    1: [
        (3, 13, '1P"Single Pole"', "Single Pole"),
        (14, 24, '2P"Double Pole"', "Double Pole"),
        (25, 35, '3P"Three Pole"', "Three Pole"),
        (36, 38, '4P"Four Pole"', "Four Pole"),
        (39, 48, "Moulded Case Circuit Breakers (MCCB)(3P)", "MCCB"),
    ],
    2: [
        (0, 7, "Moulded Case Circuit Breakers (MCCB) (4P)", "MCCB"),
        (8, 15, "Earth Leakage 32A,63A,100A,125A, 160A,250A,400A, 630A", "Earth Leakage"),
        (16, 24, "Earth Leakage 32A, 63A, 100A 125A, 160A, 250A 400A, 630A", "Earth Leakage"),
        (25, 47, "Earth Leakage 1P,2P,3P", "Earth Leakage"),
        (48, 51, "Magnetic Contactors (Cetrificate From KEMA, CE, UL,VDE, PCT)", "Magnetic Contactors"),
    ],
    3: [
        (0, 15, "Magnetic Contactors (Cetrificate From KEMA, CE, UL,VDE, PCT)", "Magnetic Contactors"),
        (16, 27, "Thermal Overload Relays (Cetrificate From KEMA, CE, UL,VDE, PCT)", "Thermal Overload"),
        (28, 30, "Push Buttons (Cetrificate From KEMA, CE, UL,VDE, PCT)", "Push Buttons"),
        (31, 33, "Indicators Lights", "Indicators Lights"),
        (34, 36, "Voltmeter and Ammeters", "Voltmeter"),
    ],
    4: [
        (0, 2, "CHiNT Change Over Switches", "Change Over"),
        (3, 7, "ATS (250A,400A,500A and 630A)", "ATS"),
        (8, 11, "Frequency Convertor", "Frequency Convertor"),
        (12, 15, "Manual Motor Starter", "Manual Motor"),
    ],
}

# series per model prefix (regex, series) - all prefixes are printed in the PDF.
SERIES_MAP = [
    (r"^NXB-63\b", "NXB-63"),
    (r"^NXB-125\b", "NXB-125"),
    (r"^NM1-", "NM1/3300"),
    (r"^NXM-\d+S/3300\b", "NXM/3300"),
    (r"^NXM-\d+S/4300B\b", "NXM/4300B"),
    (r"^NXMLE-\d+S/3300A\b", "NXMLE/3300A"),
    (r"^NXMLE-\d+S/4300A\b", "NXMLE/4300A"),
    (r"^NXBLE-63\b", "NXBLE-63"),
    (r"^NXC-", "NXC"),
    (r"^NXR-", "NXR"),
    (r"^NP2-", "NP2"),
    (r"^ND16-", "ND16"),
    (r"^6L2-", "6L2"),
    (r"^HY2-", "HY2"),
    (r"^NZ7-", "NZ7"),
    (r"^NVF2G-", "NVF2G"),
    (r"^NS2-", "NS2-25"),
]


def series_for(model):
    for rx, s in SERIES_MAP:
        if re.match(rx, model):
            return s
    return model


def short_section(section):
    """Section without the '(Cetrificate From ...)' parenthetical, for descriptions."""
    return norm(re.sub(r"\(Cetrificate From[^)]*\)", "", section))


def build_specs(model, qualifier, section, serial):
    """Derive specs ONLY from text printed in the row / section header."""
    specs = {}
    line = model + " " + qualifier

    # poles: printed as '1P', '(3P)', '1P+N', '3P+N' in the row
    m = re.search(r"\(?\b([1-4]P(?:\+N)?)\b\)?", qualifier)
    if m:
        specs["poles"] = m.group(1)
    elif "(3P)" in section:
        specs["poles"] = "3P"      # from the printed section header "(MCCB)(3P)"
    elif "(4P)" in section:
        specs["poles"] = "4P"      # from the printed section header "(MCCB) (4P)"

    # amperage rating
    m = re.search(r"\bC(\d+)\b", qualifier)          # MCB trip-curve notation C6..C125
    if m:
        specs["rating"] = m.group(1) + "A"
        specs["trip_curve"] = "C"
    else:
        m = re.search(r"\b(\d+(?:\.\d+)?A?-\d+(?:\.\d+)?A?)\b(?!\s*V)", qualifier)
        if m and re.match(r"^(NXR|NS2)", model):     # relay/starter setting ranges
            specs["rating"] = m.group(1)
        else:
            m = re.search(r"\b(\d+)A\b", qualifier)
            if m and not model.startswith("6L2"):
                # (6L2-A's "500/5A" is a CT ratio, not a product amperage)
                specs["rating"] = m.group(1) + "A"
            elif re.match(r"^NXC-(\d+)$", model):
                # contactor size printed in the model number itself (NXC-32 = 32A)
                specs["rating"] = str(int(re.match(r"^NXC-(\d+)$", model).group(1))) + "A"

    m = re.search(r"\b(\d{3})V\b", line)
    if m:
        specs["voltage"] = m.group(1) + "V"
    m = re.search(r"\b(50/60Hz)\b", line, re.IGNORECASE)
    if m:
        specs["frequency"] = m.group(1)
    m = re.search(r"\b(\d+)kA\b", qualifier)
    if m:
        specs["breaking_capacity"] = m.group(1) + "kA"
    m = re.search(r"\b(\d+mA)\b", qualifier)
    if m:
        specs["sensitivity"] = m.group(1)            # RCBO 30mA / 300mA
    m = re.search(r"\b(RED|GRN)\b", qualifier)
    if m:
        specs["color"] = m.group(1)
    m = re.search(r"([\d/]+A\(NO-OL\))", qualifier)
    if m:
        specs["measure_range"] = m.group(1)          # ammeter 500/5A(NO-OL)
    m = re.search(r"\b([AB])\s*$", qualifier)
    if m and model.startswith("NXMLE"):
        specs["variant_code"] = m.group(1)           # trailing A/B letter as printed

    if "Cetrificate From" in section:
        specs["certificates"] = CERTS

    specs["series"] = series_for(model)
    if serial:
        specs["serial_no"] = serial
    return specs


def main():
    rows_out = []
    skipped = []
    with pdfplumber.open(PDF_PATH) as pdf:
        n_pages = len(pdf.pages)
        raw_text = {i + 1: (pg.extract_text() or "") for i, pg in enumerate(pdf.pages)}
        for pageno, page in enumerate(pdf.pages, start=1):
            tables = page.extract_tables()
            if len(tables) != 1:
                raise RuntimeError(f"page {pageno}: expected 1 table, got {len(tables)}")
            table = tables[0]
            blocks = BLOCKS[pageno]

            # --- assert every pinned block still matches the printed label ---
            for first, last, section, phrase in blocks:
                frag = []
                for r in table[first : last + 1]:
                    if r[1]:
                        frag.append(r[1])
                    if r[0] and not re.match(r"^\d+$", r[0].strip()):
                        frag.append(r[0])            # banner text lands in col 0
                joined = norm(" ".join(frag))
                if phrase.lower() not in joined.lower():
                    raise RuntimeError(
                        f"page {pageno} rows {first}-{last}: expected label containing "
                        f"{phrase!r}, extracted {joined!r} - PDF/extraction drifted, refusing to guess"
                    )

            covered = set()
            for first, last, section, phrase in blocks:
                for idx in range(first, last + 1):
                    covered.add(idx)
                    r = table[idx]
                    serial = norm(r[0] or "")
                    model_line = norm(r[2] or "")
                    price_text = norm(r[4] or "")
                    raw_line = " | ".join(norm(c or "") for c in r[:5])

                    if not model_line:
                        continue  # label / banner carrier row, no product on it
                    if not re.match(r"^\d*$", serial):
                        serial = ""  # banner text in col0, not a serial

                    model = model_line.split()[0]
                    qualifier = model_line[len(model):].strip()
                    specs = build_specs(model, qualifier, section, serial)

                    if price_text == "":
                        price = None
                        specs["note"] = "no price printed in the PDF for this line"
                    elif re.fullmatch(r"\d{1,3}(?:,\d{3})+|\d+", price_text):
                        price = int(price_text.replace(",", ""))
                    else:
                        skipped.append({"page": pageno, "raw": raw_line,
                                        "reason": f"unparseable price cell {price_text!r}"})
                        continue

                    # sanity band
                    if price is not None and (price < 10 or price > 10_000_000):
                        reason = ("sanity: price printed as 0 (placeholder, not a sellable price)"
                                  if price == 0 else f"sanity: price {price} outside 10..10,000,000")
                        skipped.append({"page": pageno, "raw": raw_line, "reason": reason})
                        continue

                    # known misprint, kept as printed but flagged
                    if (pageno == 1 and idx == 23):
                        specs["note"] = ('printed "1P C80" inside the 2P"Double Pole" block '
                                         "(between 2P C63 and 2P C100); price 2197 matches the "
                                         "2P price level - likely a misprint for 2P C80, kept as printed")

                    desc_section = short_section(section)
                    rows_out.append({
                        "page": pageno,
                        "brand": BRAND,
                        "section": section,
                        "model": model,
                        "description": norm(f"{desc_section} - {model_line}"),
                        "price_pkr": price,
                        "specs": specs,
                        "_raw": raw_line,  # stripped before writing JSON; kept for spot-check
                    })

            # anything with a model outside the pinned blocks -> skipped, never guessed
            for idx, r in enumerate(table):
                if idx in covered:
                    continue
                model_line = norm((r[2] or ""))
                raw_line = " | ".join(norm(c or "") for c in r[:5])
                if model_line == "Model" and norm(r[4] or "") == "Price":
                    continue  # the printed column-header row - non-product, silent
                if model_line:
                    skipped.append({"page": pageno, "raw": raw_line,
                                    "reason": "product row outside pinned section blocks"})
                # header/title rows (page 1 rows 0-2) are non-product -> silent

    # ------------------------------------------------------------------ dedupe
    seen = {}
    deduped = []
    for row in rows_out:
        key_specs = {k: v for k, v in row["specs"].items() if k not in ("serial_no", "note")}
        key = (row["model"], json.dumps(key_specs, sort_keys=True))
        if key in seen:
            prev = seen[key]
            if prev["price_pkr"] == row["price_pkr"]:
                skipped.append({"page": row["page"], "raw": row["_raw"],
                                "reason": f"duplicate of identical row (model {row['model']}, same specs, same price)"})
                continue
            # prices differ and both really printed -> keep both (e.g. NXB-63 1P C80)
        seen[key] = row
        deduped.append(row)
    rows_out = deduped

    prices = [r["price_pkr"] for r in rows_out if r["price_pkr"] is not None]

    # -------------------------------------------------------------- validation
    p("=== coverage: priced lines in raw text vs parsed, per page ===")
    price_line_rx = re.compile(r"(?:Pcs|pcs)\s+\d[\d,]*$|\(3P\)\s+\d[\d,]*$")
    for pg in range(1, n_pages + 1):
        raw_priced = sum(1 for ln in raw_text[pg].splitlines() if price_line_rx.search(ln.strip()))
        parsed_priced = sum(1 for r in rows_out if r["page"] == pg and r["price_pkr"] is not None)
        skipped_priced = sum(1 for s in skipped if s["page"] == pg and "price printed as 0" in s["reason"])
        p(f"  page {pg}: raw priced lines={raw_priced}  parsed priced={parsed_priced}  "
          f"zero-price->skipped={skipped_priced}  (parsed+zero={parsed_priced + skipped_priced})")

    p("=== price sanity ===")
    p(f"  min={min(prices)}  median={statistics.median(prices)}  max={max(prices)}")

    p("=== spot-check: 10 random parsed rows (parsed vs raw table row) ===")
    random.seed(20)
    for r in random.sample(rows_out, 10):
        p(f"  p{r['page']} {r['model']:<18} {str(r['price_pkr']):>8}  {r['description']}")
        p(f"      raw: {r['_raw']}")

    for r in rows_out:
        del r["_raw"]

    out = {
        "source_pdf": os.path.basename(PDF_PATH),
        "rows": rows_out,
        "skipped": skipped,
        "stats": {
            "pages": n_pages,
            "rows": len(rows_out),
            "priced": len(prices),
            "skipped": len(skipped),
        },
    }
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    p("=== stats ===")
    p(f"  {out['stats']}")
    p(f"  written: {OUT_PATH}")


if __name__ == "__main__":
    main()
