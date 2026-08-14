"""Extractor for 'PCE - Industrial Price List June 2020.pdf'.

Layout: ONE page, clean 4-column table rendered as text lines:
    [Product group] CatNo Description ListPrice
The Product-group column is a merged cell: it appears only on the first row of
each group and carries down for subsequent rows. Brand is PCE throughout.

Line grammar (after plain-text extraction, which is already well-ordered):
    ^(section words)? <catno starting with a digit> <description...> <price|POR>$
The cat number is the FIRST whitespace token that starts with a digit
(e.g. 113-6, 75332-6, 9755100, 1020-5S, 1050-0WS, 02958-WE); section names
contain no digits, so everything before that token is the section header.
Price is the last token: digits with optional thousands commas, or "POR"
(price on request) -> price_pkr = null with a note.
"""
import json
import re
import statistics
from pathlib import Path

import pdfplumber

PDF_PATH = Path("C:/Users/AWCD/Desktop/client/engmart (2)/product-details/PCE - Industrial Price List June 2020.pdf")
OUT_PATH = Path("C:/Users/AWCD/Desktop/client/engmart (2)/backend/extraction/out/pce.json")

BRAND = "PCE"

CATNO_RE = re.compile(r"^\d[\w-]*$")          # first token starting with a digit
PRICE_RE = re.compile(r"^\d{1,3}(?:,\d{3})*$|^\d+$")
RATING_RE = re.compile(r"(\d+)\s*Amp", re.I)
POLES_RE = re.compile(r"(\d+)\s*(Pole|Pin)s?", re.I)
IP_RE = re.compile(r"\bIP\d{2}\b")
COLOR_RE = re.compile(r",\s*(Blue|White|Black|Red|Yellow|Green|Grey|Gray)\b", re.I)

# Non-product lines on the page (header block + column header) — skipped silently.
HEADER_PREFIXES = (
    "Price List of Industrial Plugs",
    "Catalogue Ref.",
    "Product Cat No Description List Price",
)


def out(s: str) -> None:
    print(str(s).encode("ascii", "replace").decode())


def parse_line(line: str, section: str):
    """Return (row_dict, section) or (None, section). Raises ValueError on unparseable."""
    tokens = line.split()
    # find first token that starts with a digit -> cat no
    cat_idx = None
    for i, tok in enumerate(tokens):
        if tok[0].isdigit():
            cat_idx = i
            break
    if cat_idx is None:
        raise ValueError("no catalogue number found")

    if cat_idx > 0:  # new section header printed on this row (merged cell start)
        section = " ".join(tokens[:cat_idx])

    model = tokens[cat_idx]
    if not CATNO_RE.match(model):
        raise ValueError("catalogue token malformed: %s" % model)

    price_tok = tokens[-1]
    desc_tokens = tokens[cat_idx + 1:-1]
    if price_tok.upper() == "POR":
        price = None
    elif PRICE_RE.match(price_tok):
        price = int(price_tok.replace(",", ""))
    else:
        raise ValueError("last token is not a price: %s" % price_tok)

    desc = " ".join(desc_tokens)
    if not desc:
        raise ValueError("empty description")

    specs = {"series": section}
    m = RATING_RE.search(desc)
    if m:
        specs["rating"] = m.group(1) + "A"
    m = POLES_RE.search(desc)
    if m:
        specs["poles"] = m.group(1) + "P"
        specs["pin_type"] = m.group(2).title()  # Pole vs Pin as printed
    m = IP_RE.search(desc)
    if m:
        specs["ip_rating"] = m.group(0)
    m = COLOR_RE.search(desc)
    if m:
        specs["color"] = m.group(1).title()
    if price is None:
        specs["note"] = "PDF shows 'POR' (price on request) instead of a price"

    row = {
        "page": 1,
        "brand": BRAND,
        "section": section,
        "model": model,
        "description": ("%s - %s" % (section, desc)) if section else desc,
        "price_pkr": price,
        "specs": specs,
    }
    return row, section


def main():
    rows, skipped = [], []
    raw_by_row = []  # parallel raw source lines for spot-check
    with pdfplumber.open(PDF_PATH) as pdf:
        n_pages = len(pdf.pages)
        page = pdf.pages[0]
        text = page.extract_text() or ""
        section = ""
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if any(line.startswith(h) for h in HEADER_PREFIXES):
                continue  # page header / column header, not a product
            try:
                row, section = parse_line(line, section)
            except ValueError as e:
                skipped.append({"page": 1, "raw": line, "reason": str(e)})
                continue
            rows.append(row)
            raw_by_row.append(line)

    # --- validation -------------------------------------------------------
    # sanity: flag implausible prices
    kept, kept_raw = [], []
    for row, raw in zip(rows, raw_by_row):
        p = row["price_pkr"]
        if p is not None and (p < 10 or p > 10_000_000):
            skipped.append({"page": row["page"], "raw": raw, "reason": "sanity"})
        else:
            kept.append(row)
            kept_raw.append(raw)
    rows, raw_by_row = kept, kept_raw

    # duplicates: same model + identical specs
    seen = {}
    deduped, deduped_raw = [], []
    for row, raw in zip(rows, raw_by_row):
        key = (row["model"], json.dumps(row["specs"], sort_keys=True))
        if key in seen:
            prev = seen[key]
            if prev["price_pkr"] == row["price_pkr"]:
                skipped.append({"page": row["page"], "raw": raw,
                                "reason": "duplicate of identical row"})
                continue
        seen[key] = row
        deduped.append(row)
        deduped_raw.append(raw)
    rows, raw_by_row = deduped, deduped_raw

    priced = [r for r in rows if r["price_pkr"] is not None]
    result = {
        "source_pdf": PDF_PATH.name,
        "rows": rows,
        "skipped": skipped,
        "stats": {
            "pages": n_pages,
            "rows": len(rows),
            "priced": len(priced),
            "skipped": len(skipped),
        },
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")

    # --- report -----------------------------------------------------------
    out("stats: %s" % result["stats"])
    prices = [r["price_pkr"] for r in priced]
    out("price min=%d median=%d max=%d" %
        (min(prices), statistics.median(prices), max(prices)))
    out("")
    out("spot-check (parsed vs raw):")
    import random
    random.seed(7)
    for row, raw in random.sample(list(zip(rows, raw_by_row)), min(10, len(rows))):
        out("  RAW: %s" % raw)
        out("  ROW: model=%s section=%s price=%s specs=%s" %
            (row["model"], row["section"], row["price_pkr"], row["specs"]))
    if skipped:
        out("")
        out("skipped:")
        for s in skipped:
            out("  p%d [%s] %s" % (s["page"], s["reason"], s["raw"]))


if __name__ == "__main__":
    main()
