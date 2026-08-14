# -*- coding: utf-8 -*-
"""
Faithful extractor for "FICO LIST.pdf"  ->  extraction/out/fico.json

Supplier : FICO  (pages 3-12 head "Fico Hi-TECH (Pvt) LTD / Industrial automation
           & control"; page 13 heads "FICO ENTERPRISES").  Price list W.E.F
           01.07.2020, distributed by Cognitive Solutions.  13 pages.

Page map
--------
  p1  cover                                          -> non-product, silent
  p2  table of contents + notes                      -> non-product, silent
  p3  two columns: ELC (left) / ILC + "CT WITH SECONDARY CURRENT - 1 AMP" (right)
  p4  two columns: RLC SERIES (left) / SLC SERIES (right)
  p5  two columns: SDH + TAB/TLC (left) / SCLC + WOUND TYPE CT (right)
  p6  two columns: WAPDA(WSB) + KE(SLC) (left) / MLC RESIN CAST (right)
  p7  INDICATION LAMPS (FIL) + PUSH BUTTON (FPB/FMHB)
  p8  PANEL METERS (Analogue) (FAM + un-coded meters) + Selector SWITCHES
  p9  CHANGE OVER / PHASE SELECTOR / SERIES ROTARY SWITCHES (FS)
      + DIGITAL PANEL METER: DIGITAL AC AMMETER / DIGITAL AC Voltmeter (FDM)
  p10 DIGITAL FREQUENCY METER / DIGITAL WATT METER / DIGITAL DIN RAIL TYPE METER
  p11 DIGITAL VA METER / DIGITAL VAF METER / DIGITAL POWER ANALYSER
  p12 D FUSE Fitting + FUSE LINK (11 KV)
  p13 MAIN SWITCHES + CHANGE OVER SWITCHES (Rating|Type|Poles|Price)

How each page is read
---------------------
Pages 3-5 are two-column instrument-transformer tables.  extract_text() glues the
left and right column of a table onto one text line, and several prices are split
into digit fragments ("1 ,510" == 1510, "1 0,150" == 10150), so those pages are
rebuilt from extract_words():
  * split the page at x=300 into a left and a right half,
  * chain-cluster words into visual rows (top gap <= 4.5pt),
  * derive the column bands from each table's OWN printed header row
    (Ration/Ratio | Class | VA | P-Turn/pt | Price Rs, or the TLC variant
     Primery Current | cl. 0.5 | cl. 1 | cl. 5P10 | Price Rs),
  * every word that lands in the Price band is concatenated -> the price.

Page 6 is the hard one: both tables use VERTICALLY MERGED cells, so a row's model
(left table) or its Class/VA/pt trio (right table) is printed once and applies to
several ratio rows.  Position alone is not enough - the label is centred inside
its merged cell and can sit nearer a neighbouring row than to its own first row.
Both halves are therefore reconstructed from the table's RULED LINES
(page.edges): a horizontal rule that crosses the Model column ends a model cell,
while a rule that only crosses the Ratio/Price columns merely ends a data row.
The resulting cell map was verified against a 220-dpi render of page 6 and is
additionally pinned in PAGE6_LEFT_EXPECTED below, so any future drift in the PDF
or in pdfplumber fails loudly instead of silently mislabelling a price.

Pages 7-13 extract as clean text lines and are parsed line-wise.

Fidelity rules honoured here
----------------------------
* No price is ever guessed, averaged or carried between rows.  A price is only
  shared across several rows where the PDF physically merges the cell, which
  happens exactly twice in this document and in both cases is derived from the
  ruled lines, not from proximity:
    - page 6 left  : the Model cell (the price still comes from each row's own
                     Price cell - only the model name is shared),
    - page 6 right : the Class/VA/pt trio (again, prices are per-row).
* A colour list under one model with a single printed price stays ONE row
  (page 7: FIL-22 lists RED/GREEN/YELLOW/BLUE for one price of 60; FIL-30 lists
  RED/GREEN for 120).  The colours are recorded in specs.colours.
* Rows whose model code is not printed at all (page 8 un-coded analogue meters,
  page 12 D-fuse fittings, page 13 switches, page 5 wound-type CTs) use the
  printed description/rating as the model and carry specs.note saying so.

Known anomalies in the source, kept exactly as printed and flagged in specs.note
-------------------------------------------------------------------------------
  p5  "800/5AA"   - stray second A in an SCLC-58 ratio.
  p5  "5/5A to"   - the wound-type CT's first ratio cell is printed unfinished.
  p9  "FS26-16 32A 4-POSITION" - FS26-16 is 16A everywhere else on the page.
  p10 "FDM-60A" appears twice (890 and 540); the 540 row sits directly under
      FDM-80V in the voltmeter pair and is almost certainly a misprint for
      FDM-60V.  Both rows are emitted with their own printed price.
  p7  FPBRS-NOC is described GREEN and FPBGS-NOC is described RED (the R/G in
      the code and the colour word disagree).
  p13 "43 Amp" change-over (the rest of the ladder is 30/60/100...).

Run:
    venv/Scripts/python.exe extraction/fico.py
Writes: extraction/out/fico.json
"""

import json
import os
import random
import re
import statistics

import pdfplumber

PDF = r"C:/Users/AWCD/Desktop/client/engmart (2)/product-details/FICO LIST.pdf"
OUT = r"C:/Users/AWCD/Desktop/client/engmart (2)/backend/extraction/out/fico.json"

BRAND = "FICO"

# rows parsed per page - verified by hand against the raw text / rendered pages.
EXPECTED_PER_PAGE = {3: 84, 4: 62, 5: 93, 6: 40, 7: 18, 8: 13,
                     9: 20, 10: 8, 11: 4, 12: 19, 13: 29}


def P(*a):
    print(" ".join(str(x) for x in a).encode("ascii", "replace").decode())


# --------------------------------------------------------------------------
# shared helpers
# --------------------------------------------------------------------------

RATIO_RE = re.compile(r"^\d+/\d+A{0,2}$")      # 100/5A, 8000/5, 800/5AA
INT_RE = re.compile(r"^\d+$")

rows = []
skipped = []


def add_row(page, section, model, description, price, specs, raw):
    rows.append({
        "page": page,
        "brand": BRAND,
        "section": section,
        "model": model,
        "description": re.sub(r"\s{2,}", " ", description).strip(" |"),
        "price_pkr": price,
        "specs": specs,
        "_raw": raw,
    })


def add_skip(page, raw, reason):
    skipped.append({"page": page, "raw": raw, "reason": reason})


def note(specs, text):
    """Append to specs.note without losing an existing note."""
    if specs.get("note"):
        specs["note"] += "; " + text
    else:
        specs["note"] = text


def cluster_lines(words, gap=4.5):
    """Chain-cluster words into visual rows (a word joins the running row when
    its top is within `gap` of the previous word's top)."""
    if not words:
        return []
    ws = sorted(words, key=lambda w: (w["top"], w["x0"]))
    out = [[ws[0]]]
    prev_top = ws[0]["top"]
    for w in ws[1:]:
        if w["top"] - prev_top <= gap:
            out[-1].append(w)
        else:
            out.append([w])
        prev_top = w["top"]
    for r in out:
        r.sort(key=lambda w: (round(w["top"]), w["x0"]))
    return out


def line_text(ws):
    return " ".join(w["text"] for w in ws)


def xc(w):
    return (w["x0"] + w["x1"]) / 2.0


def yc(w):
    return (w["top"] + w["bottom"]) / 2.0


def parse_price(tokens):
    """Join price-band fragments: ['1', '0,150'] -> 10150."""
    s = "".join(tokens).replace(",", "").replace(" ", "")
    return int(s) if re.fullmatch(r"\d+", s) else None


def norm_model(s):
    """'ELC - 20S' -> 'ELC-20S'.  Only collapses typesetting space around the
    hyphen of a catalogue code; the printed form is kept in specs when it
    differs."""
    return re.sub(r"\s*-\s*", "-", s).strip()


def rating_from_ratio(ratio):
    """Primary amperage from a CT ratio, e.g. '3000/5A'->'3000A',
    '100 TO 300/5A'->'100-300A', '150/5A - 200/5A'->'150-200A'."""
    prims = re.findall(r"(\d+)\s*/\s*\d+", ratio)
    lead = re.match(r"^(\d+)\s+(?:TO|to)\b", ratio)
    if lead:
        prims = [lead.group(1)] + prims
    if not prims:
        prims = re.findall(r"\d+", ratio)
    if not prims:
        return None
    return prims[0] + "A" if len(prims) == 1 else "%s-%sA" % (prims[0], prims[-1])


def cluster_bounds(vals, tol=1.5):
    """Ruled lines are drawn as thin rectangles -> two edge tops ~0.5pt apart.
    Collapse them into single boundaries."""
    out = []
    for v in sorted(vals):
        if out and v - out[-1] <= tol:
            continue
        out.append(v)
    return out


def hbounds(page, x_lo, x_hi):
    """Tops of horizontal rules that span the x-range [x_lo, x_hi]."""
    return cluster_bounds(e["top"] for e in page.edges
                          if e["orientation"] == "h"
                          and e["x0"] <= x_lo and e["x1"] >= x_hi)


def interval_of(y, bounds):
    """Index of the bounds-interval containing y, or None."""
    for i in range(len(bounds) - 1):
        if bounds[i] <= y <= bounds[i + 1]:
            return i
    return None


# --------------------------------------------------------------------------
# pages 3-5: two-column CT tables, column bands from the printed header row
# --------------------------------------------------------------------------

STD_HDR_NAMES = ("Ration", "Ratio", "Class", "VA", "P-Turn", "pt", "Price")
SIZE_START = ("INNER WINDOW", "Window Size", "Windo Size", "Max Bar", "Max Cable")
NOISE_TOKENS = {"CT", "Picture", "PICTURE"}
FOOTER_PAT = re.compile(
    r"WARRANTY|SALES TAX|Contact:|cognitivesolutions|Fico Hi-TECH|"
    r"Industrial automation|\d{3,4}-\d{7}", re.I)   # last: bare phone numbers

# printed prose/headings that sit inside a table area but carry no product
BLURB_PAT = re.compile(
    r"^(STARTING FROM|HIGHEST LEVEL|USED FOR|RESIN ENCAPSULATION|ANTI THEFT|"
    r"Below are the measurements)", re.I)


def build_bands(ws):
    """Column bands (name, centre_x) from a printed header row, else None."""
    txts = [w["text"] for w in ws]
    if "Price" not in " ".join(txts):
        return None
    if "cl." in txts:                       # TLC: Current | cl.0.5 | cl.1 | cl.5P10
        cl_idx = [i for i, t in enumerate(txts) if t == "cl."]
        cur = next((w for w in ws if w["text"] in ("Current", "Primery")), None)
        if cur is None or len(cl_idx) != 3:
            return None
        bands = [("ratio", xc(cur))]
        for n, i in zip(["cl_0.5_va", "cl_1_va", "cl_5P10_va"], cl_idx):
            w0 = ws[i]
            w1 = ws[i + 1] if i + 1 < len(ws) else w0
            bands.append((n, (w0["x0"] + w1["x1"]) / 2.0))
        pw = [w for w in ws if w["text"] in ("Price", "Rs")]
        bands.append(("price", sum(xc(w) for w in pw) / len(pw)))
        return bands
    if len({w["text"] for w in ws if w["text"] in STD_HDR_NAMES}) < 4:
        return None
    bands = []
    for w in ws:
        t = w["text"]
        if t in ("Ration", "Ratio"):
            bands.append(("ratio", xc(w)))
        elif t == "Class":
            bands.append(("class", xc(w)))
        elif t == "VA":
            bands.append(("va", xc(w)))
        elif t in ("P-Turn", "pt"):
            bands.append(("p_turn", xc(w)))
        elif t == "Price":
            rs = next((v for v in ws if v["text"] == "Rs" and v["x0"] > w["x0"]), None)
            bands.append(("price", (xc(w) + xc(rs)) / 2.0 if rs else xc(w)))
    return bands


def parse_ct_half(page_no, lines, section):
    """One half-column of pages 3/4/5."""
    bands = None
    model = printed_model = size = None
    n_before = len(rows)

    for ws in lines:
        ws = [w for w in ws if w["text"] not in NOISE_TOKENS]
        if not ws:
            continue
        text = line_text(ws)
        if FOOTER_PAT.search(text) or BLURB_PAT.match(text):
            continue

        # NB: the leading 'CT' is dropped by NOISE_TOKENS, so match on the rest.
        if "SECONDARY CURRENT" in text:
            section = "CT WITH SECONDARY CURRENT - 1 AMP"
            model = printed_model = size = None
            continue
        if "WOUND TYPE" in text:
            section = "WOUND TYPE CT"
            model = printed_model = size = None
            continue
        if "TAB FEATURES" in text:
            section = "TAB"                       # printed header above the TLC tables
            model = printed_model = size = None
            continue

        nb = build_bands(ws)
        if nb:
            bands = nb
            continue

        if text.startswith("Type:"):
            m = text[len("Type:"):].strip()
            size = None
            for cut in (" Max Bar", " Window", " INNER"):
                if cut in m:
                    m, rest = m.split(cut, 1)
                    size = (cut.strip() + rest).strip()
                    break
            printed_model = m.strip()
            model = norm_model(printed_model)
            continue

        if any(text.startswith(s) for s in SIZE_START):
            size = text
            continue

        toks = [w["text"] for w in ws]
        if not (bands and any(RATIO_RE.match(t) for t in toks)):
            if bands and re.search(r"\d", text) and not re.match(r"^[A-Za-z]", text):
                add_skip(page_no, text, "unparsed line inside a CT table")
            continue

        # ---- assign every word of the row to its column band
        cols = {name: [] for name, _ in bands}
        ratio_c = dict(bands).get("ratio")
        for w in ws:
            if RATIO_RE.match(w["text"]) and ratio_c is not None:
                cols["ratio"].append(w)
            else:
                cols[min(bands, key=lambda b: abs(xc(w) - b[1]))[0]].append(w)
        # a '-' / 'to' printed between two ratio tokens belongs to the ratio cell
        if len(cols["ratio"]) >= 2:
            lo = min(w["x0"] for w in cols["ratio"])
            hi = max(w["x1"] for w in cols["ratio"])
            for name in list(cols):
                if name == "ratio":
                    continue
                keep = []
                for w in cols[name]:
                    if w["text"] in ("-", "TO", "to") and lo <= xc(w) <= hi:
                        cols["ratio"].append(w)
                    else:
                        keep.append(w)
                cols[name] = keep
        for name in cols:
            cols[name].sort(key=lambda w: (round(w["top"]), w["x0"]))

        ratio = " ".join(w["text"] for w in cols["ratio"]).strip()
        price = parse_price([w["text"] for w in cols["price"]])
        if not ratio or price is None:
            add_skip(page_no, text, "CT row without a parseable ratio+price pair")
            continue

        specs = {}
        if "cl_0.5_va" in cols:                                   # TLC burden table
            for k in ("cl_0.5_va", "cl_1_va", "cl_5P10_va"):
                v = " ".join(w["text"] for w in cols[k]).strip()
                if v:
                    specs[k] = v
        else:
            for k in ("class", "va", "p_turn"):
                v = " ".join(w["text"] for w in cols.get(k, [])).strip()
                if v and v != "-":
                    specs[k] = v

        specs["ratio"] = ratio
        r = rating_from_ratio(ratio)
        if r:
            specs["rating"] = r
        if size:
            specs["size"] = size

        # secondary current = the ratio's denominator (…/5A vs …/1A)
        sec_m = re.search(r"/\s*(\d+)A?\b", ratio)
        secondary = (sec_m.group(1) + "A") if sec_m else None
        if secondary:
            specs["secondary_current"] = secondary

        if model is None:                     # wound-type CT prints no model code
            this_model = ratio.split()[0]
            specs["series"] = "WOUND TYPE CT"
            note(specs, "no model code printed; row identified by its printed ratio "
                        "under the WOUND TYPE CT heading")
        else:
            this_model = model
            # ELC-30/-40/-60 are listed twice in this PDF: once with a 5A
            # secondary and again under "CT WITH SECONDARY CURRENT - 1 AMP" at a
            # different price.  Same model code, different product - so the
            # series (the storefront's grouping key) has to keep them apart.
            if secondary and secondary != "5A":
                specs["series"] = "%s (SECONDARY %s)" % (model, secondary)
            else:
                specs["series"] = model
            if printed_model != model:
                specs["model_as_printed"] = printed_model

        if ratio.endswith(" to") or ratio.endswith(" TO"):
            note(specs, "ratio cell printed unfinished in the PDF (%r)" % ratio)
        if "AA" in ratio:
            note(specs, "ratio printed with a stray extra 'A' (%r)" % ratio)

        desc = " | ".join(dict.fromkeys(
            [b for b in [section, ("Type: " + this_model) if model else None,
                         size, ratio] if b]))
        extra = ", ".join("%s %s" % (k.replace("_", "-"), specs[k])
                          for k in ("class", "va", "p_turn") if k in specs)
        if extra:
            desc += " | " + extra
        add_row(page_no, section, this_model, desc, price, specs, text)

    return len(rows) - n_before


# --------------------------------------------------------------------------
# page 6 - ruled-cell reconstruction of the merged tables
# --------------------------------------------------------------------------

# (model, ratio, price) exactly as read off a 220-dpi render of page 6 left.
PAGE6_LEFT_EXPECTED = [
    ("WAPDA APPROVED MODEL", "WSB-30", "100/5A", 4950),
    ("WAPDA APPROVED MODEL", "WSB-50", "150/5A", 4600),
    ("WAPDA APPROVED MODEL", "WSB-50", "200/5A", 4500),
    ("WAPDA APPROVED MODEL", "WSB-50", "300/5A", 4150),
    ("WAPDA APPROVED MODEL", "WSB-65", "400/5A", 3740),
    ("WAPDA APPROVED MODEL", "WSB-75", "600/5A", 3300),
    ("WAPDA APPROVED MODEL", "WSB-75", "800/5A", 3300),
    ("WAPDA APPROVED MODEL", "WSB-75", "1000/5A", 3650),
    ("KE APPROVED MODEL", "SLC-40", "100/5A", 2900),
    ("KE APPROVED MODEL", "SLC-40", "200/5A", 2600),
    ("KE APPROVED MODEL", "SLC 65", "300/5A", 2600),
    ("KE APPROVED MODEL", "SLC 65", "400/5A", 2800),
    ("KE APPROVED MODEL", "SLC 65", "600/5A", 3000),
    ("KE APPROVED MODEL", "SLC 65", "800/5A", 3300),
    ("KE APPROVED MODEL", "SLC 65", "1000/5A", 4100),
    ("KE APPROVED MODEL", "SLC 125-k", "1200/5A", 6000),
    ("KE APPROVED MODEL", "SLC 125-k", "2400/5A", 7050),
]


def parse_page6_left(page, page_no):
    """WAPDA (WSB) and KE (SLC) tables.  Columns are ruled at
    x = 55 | 103.1 | 138.7 | 178.6 (Ratio | Model | Price | CT picture).
    A rule that crosses the Model column closes a merged Model cell; a rule that
    only crosses Ratio/Price merely separates two data rows inside that cell."""
    C_RATIO, C_MODEL, C_PRICE, C_END = 55.0, 103.1, 138.7, 178.6
    row_bounds = hbounds(page, C_RATIO + 5, C_MODEL - 3)     # crosses Ratio
    model_bounds = hbounds(page, C_MODEL + 7, C_PRICE - 7)   # crosses Model
    if len(row_bounds) < 10 or len(model_bounds) < 6:
        raise RuntimeError("page 6 left: ruled grid not found (%d row / %d model "
                           "boundaries) - refusing to guess merged cells"
                           % (len(row_bounds), len(model_bounds)))

    words = [w for w in page.extract_words(x_tolerance=1.5, y_tolerance=2.0)
             if w["x1"] <= 300]

    # section titles are printed between the two tables
    ke_top = min((w["top"] for w in words if w["text"] == "KE"), default=10 ** 6)

    def section_of(y):
        return "KE APPROVED MODEL" if y > ke_top else "WAPDA APPROVED MODEL"

    # merged model cells: cell index -> printed model text.  Cluster every word
    # sitting in the Model column, then keep the clusters that actually start
    # with a model code - 'SLC 65' and 'SLC 125-k' are two words on one line, so
    # filtering word-by-word would throw the size away.
    cell_model = {}
    for ws in cluster_lines([w for w in words if C_MODEL < w["x0"] < C_PRICE]):
        if not re.match(r"^(WSB|SLC)", ws[0]["text"]):
            continue                      # column header ('Model' / 'Class')
        i = interval_of(yc(ws[0]), model_bounds)
        if i is not None:
            cell_model[i] = " ".join(w["text"] for w in ws)

    out = []
    for ws in cluster_lines(words):
        ratio_ws = [w for w in ws if RATIO_RE.match(w["text"]) and w["x0"] < C_MODEL]
        price_ws = [w for w in ws if INT_RE.match(w["text"])
                    and C_PRICE < w["x0"] < C_END]
        text = line_text(ws)
        if not ratio_ws or not price_ws:
            if (ratio_ws or price_ws) and not FOOTER_PAT.search(text):
                add_skip(page_no, text, "page-6-left fragment without a ratio+price pair")
            continue
        y = yc(ratio_ws[0])
        ri = interval_of(y, row_bounds)
        mi = interval_of(y, model_bounds)
        model = cell_model.get(mi)
        if ri is None or model is None:
            add_skip(page_no, text, "page-6-left row outside the ruled model grid")
            continue
        sec = section_of(y)
        ratio = ratio_ws[0]["text"]
        price = int(price_ws[0]["text"])
        specs = {"ratio": ratio, "series": model}
        r = rating_from_ratio(ratio)
        if r:
            specs["rating"] = r
        if sec.startswith("WAPDA"):
            specs["va"] = "5"                 # printed as the 'VA:5' column header
        out.append((sec, model, ratio, price, specs, text))

    got = [(s, m, r, p) for s, m, r, p, _, _ in out]
    if got != PAGE6_LEFT_EXPECTED:
        raise RuntimeError(
            "page 6 left: merged-cell reconstruction changed.\n  expected %s\n"
            "  got      %s\nRefusing to emit possibly mislabelled prices."
            % (PAGE6_LEFT_EXPECTED, got))

    for sec, model, ratio, price, specs, text in out:
        add_row(page_no, sec, model,
                "%s | %s | %s" % (sec, model, ratio), price, specs, text)


def parse_page6_right(page, page_no):
    """MLC (RESIN CAST).  Columns ruled at
    x = 302.6 | 350.2 | 381.2 | 412.1 | 443.1 | 474.1 (Ratio|Class|VA|pt|Price).
    The Class/VA/pt trio is printed once per merged block and applies to every
    ratio row inside that block; ratio cells may hold two text lines
    ('5000 TO' + '6000/5A')."""
    C = [302.6, 350.2, 381.2, 412.1, 443.1, 474.1]
    row_bounds = hbounds(page, C[0] + 5, C[1] - 3)    # crosses Ratio
    trio_bounds = hbounds(page, C[0] + 5, C[5] + 0.4)  # crosses Class..Price
    if len(row_bounds) < 20 or len(trio_bounds) < 8:
        raise RuntimeError("page 6 right: ruled grid not found (%d row / %d trio "
                           "boundaries)" % (len(row_bounds), len(trio_bounds)))

    words = [w for w in page.extract_words(x_tolerance=1.5, y_tolerance=2.0)
             if 300 < w["x0"] < 480]

    def col_of(w):
        for i in range(len(C) - 1):
            if C[i] - 2 <= w["x0"] < C[i + 1]:
                return ["ratio", "class", "va", "p_turn", "price"][i]
        return None

    # merged Class/VA/pt cells: interval index -> trio dict
    trio_by_cell = {}
    for w in words:
        c = col_of(w)
        if c in ("class", "va", "p_turn") and re.fullmatch(r"[\d.]+", w["text"]):
            i = interval_of(yc(w), trio_bounds)
            if i is not None:
                trio_by_cell.setdefault(i, {})[c] = w["text"]

    buckets = {}
    for w in words:
        i = interval_of(yc(w), row_bounds)
        if i is not None:
            buckets.setdefault(i, []).append(w)

    model = printed_model = size = None
    for i in sorted(buckets):
        ws = sorted(buckets[i], key=lambda w: (w["top"], w["x0"]))
        text = line_text(ws)
        if (FOOTER_PAT.search(text) or BLURB_PAT.match(text)
                or build_bands(ws)):          # the table's own column-header row
            continue
        if text.startswith("Type:"):
            printed_model = text[len("Type:"):].strip()
            model = printed_model
            size = None
            continue
        if "INNER" in text and "WINDOW" in text:
            size = text
            continue
        ratio_ws = [w for w in ws if col_of(w) == "ratio"]
        price_ws = [w for w in ws if col_of(w) == "price"]
        if not ratio_ws or not price_ws:
            if ratio_ws or price_ws:
                add_skip(page_no, text, "page-6-right row without a ratio+price pair")
            continue
        if model is None:
            add_skip(page_no, text, "page-6-right row before any 'Type:' heading")
            continue
        ratio = " ".join(w["text"] for w in ratio_ws)
        price = parse_price([w["text"] for w in price_ws])
        if price is None:
            add_skip(page_no, text, "page-6-right unparseable price cell")
            continue

        specs = {}
        ti = interval_of(yc(ratio_ws[0]), trio_bounds)
        for k, v in (trio_by_cell.get(ti) or {}).items():
            specs[k] = v
        specs["ratio"] = ratio
        r = rating_from_ratio(ratio)
        if r:
            specs["rating"] = r
        if size:
            specs["size"] = size
        specs["series"] = model
        if not {"class", "va", "p_turn"} & set(specs):
            note(specs, "Class/VA/pt not printed for this row's merged block")

        desc = " | ".join([x for x in ["MLC (RESIN CAST)", "Type: " + model,
                                       size, ratio] if x])
        extra = ", ".join("%s %s" % (k.replace("_", "-"), specs[k])
                          for k in ("class", "va", "p_turn") if k in specs)
        if extra:
            desc += " | " + extra
        add_row(page_no, "MLC (RESIN CAST)", model, desc, price, specs, text)


# --------------------------------------------------------------------------
# text-line pages
# --------------------------------------------------------------------------

def page_lines(page):
    out = []
    for ln in (page.extract_text() or "").splitlines():
        ln = re.sub(r"\(cid:\d+\)", "", ln).strip()
        if ln and not FOOTER_PAT.search(ln):
            out.append(ln)
    return out


# ------------------------------------------------------------------ page 7

COLOUR_RE = re.compile(r"\b(RED|GREEN|YELLOW|BLUE)\b")
CONTACT_RE = re.compile(r"([1I]\s?N[OoCc](?:\s(?:OR|\+)\s?[1I]\s?N[OoCc])?)\s*$")
P7_NOISE = re.compile(r"\b(THESE CAN|BE PROVIDED|IN ONE|CONTACT|ARRANGEMENT|AS WELL)\b")


def parse_page7(page, page_no):
    lines = page_lines(page)

    # --- indication lamps: one printed price covers the whole colour list
    colours = {"FIL-22": [], "FIL-30": []}
    cur = None
    for ln in lines:
        if "22MM DIA" in ln:
            cur = "FIL-22"
        elif "30MM DIA" in ln:
            cur = "FIL-30"
        elif "PUSH BUTTON" in ln:
            cur = None
        if cur:
            # the colour may share the line with the model/price ("FIL-22 ? RED 60")
            for c in COLOUR_RE.findall(ln):
                if c not in colours[cur]:
                    colours[cur].append(c)
    for ln in lines:
        m = re.match(r"^(FIL-\d+)\b.*?(\d{2,4})\s*$", ln)
        if not m:
            continue
        model, price = m.group(1), int(m.group(2))
        dia = "22MM DIA" if model == "FIL-22" else "30MM DIA"
        cols = colours.get(model, [])
        specs = {"series": "FIL", "diameter": dia.replace(" DIA", ""), "colours": cols}
        note(specs, "one price printed for the whole colour list (%s); "
                    "no per-colour price in the PDF" % ", ".join(cols))
        add_row(page_no, "INDICATION LAMPS", model,
                "INDICATION LAMPS | %s | %s - COLOURS AVAILABLE: %s"
                % (model, dia, ", ".join(cols)), price, specs, ln)

    # --- push buttons
    for ln in lines:
        if not re.match(r"^F[A-Z]{2,}", ln) or " - " not in ln:
            continue
        m = re.match(r"^(.*?)\s(\d{2,4})\s*$", ln)
        if not m:
            continue
        body, price = m.group(1), int(m.group(2))
        body = re.sub(r"\s{2,}", " ", P7_NOISE.sub(" ", body)).strip()
        cm = CONTACT_RE.search(body)
        contact = cm.group(1) if cm else None
        if cm:
            body = body[:cm.start()].strip()
        model, desc_txt = body.split(" - ", 1)
        model = model.strip()
        series = "FMHB" if model.startswith("FMHB") else "FPB"
        specs = {"series": series}
        if contact:
            specs["contact_arrangement"] = contact
        cmatch = COLOUR_RE.search(desc_txt)
        if cmatch:
            specs["colour"] = cmatch.group(1)
        if model in ("FPBRS-NOC", "FPBGS-NOC"):
            note(specs, "the colour word printed on this line disagrees with the "
                        "R/G letter in the model code; kept exactly as printed")
        desc = "PUSH BUTTON | %s - %s" % (model, desc_txt.strip())
        if contact:
            desc += " | " + contact
        add_row(page_no, "PUSH BUTTON", model, desc, price, specs, ln)


# ------------------------------------------------------------------ page 8

def parse_page8(page, page_no):
    lines = page_lines(page)
    section = "PANEL METERS (Analogue)"
    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("PANEL METERS"):
            section = "PANEL METERS (Analogue)"
            i += 1
            continue
        if "SELECTOR SWITCHES" in ln.upper():
            if ln.upper().startswith("SELECTOR") or ln == "Selector SWITCHES":
                section = "SELECTOR SWITCHES"
                i += 1
                continue
            if ln.upper().startswith("AMPERE/VOLT"):
                i += 1
                continue
        # name line / price line / detail line
        if i + 1 < len(lines) and INT_RE.match(lines[i + 1]):
            name, price = ln, int(lines[i + 1])
            detail = (lines[i + 2] if i + 2 < len(lines)
                      and not INT_RE.match(lines[i + 2]) else "")
            specs = {}
            mm = re.match(r"^(F[A-Z]*\d*[A-Z]*-\d+[A-Z]*)\b", name)
            if mm:
                model = mm.group(1)
                # family = the code before the size suffix: FAM-96A -> FAM,
                # FS26-20 -> FS26, F26-20 -> F26 (printed without the S).
                specs["series"] = model.split("-")[0]
            else:
                model = re.sub(r"\s*SIZE:?\s*$", "", name.rstrip(": ")).strip()
                specs["series"] = model
                note(specs, "no catalogue code printed for this meter; the printed "
                            "product name is used as the model")
            sz = re.search(r"(\d+\s?X\s?\d+(?:\s?MM)?(?:,\s*\d+\s?X\s?\d+\s?MM)?)",
                           name + " " + detail)
            if sz:
                specs["size"] = sz.group(1)
            vm = re.search(r"\b(\d{3})V\b", name + " " + detail)
            if vm:
                specs["voltage"] = vm.group(1) + "V"
            ct = re.search(r"CT OPERATED:\s*(.+)$", detail)
            if ct:
                # the CT ratios this meter can be scaled to - one price covers all,
                # so they are NOT emitted as separate amperage variants.
                specs["ct_operated"] = ct.group(1).strip()
            pos = re.search(r"(\d+\s*POSITION[^,]*|-POSITION[^,]*)", detail)
            if pos:
                specs["positions"] = pos.group(1).strip(" -")
            desc = ("%s | %s | %s" % (section, name.rstrip(":"), detail)).strip(" |")
            add_row(page_no, section, model, desc, price, specs,
                    "%s / %s / %s" % (name, price, detail))
            i += 3 if detail else 2
            continue
        i += 1


# ------------------------------------------------------------- pages 9 - 11

def flush_fdm(page_no, section, block, pending):
    """One FDM product block: the single line ending in a bare integer carries
    the price; every other line is description text."""
    if not block:
        return
    price = None
    desc_lines = []
    for ln in block:
        m = re.match(r"^(.*?)\s(\d{3,5})$", ln)
        if price is None and m:
            price = int(m.group(2))
            desc_lines.append(m.group(1).strip())
        elif price is None and INT_RE.match(ln):
            price = int(ln)
        else:
            desc_lines.append(ln)
    head = block[0]
    mm = re.match(r"^(FDM[\s-]*[\w()/-]*(?:\s\d[\dA-Z]*)?)", head)
    model = re.split(r"\s-\s", mm.group(1).strip() if mm else head)[0].strip()
    desc = re.sub(r"\s{2,}", " ", " ".join(pending + desc_lines))
    specs = {"series": "FDM " + section}
    sz = re.search(r"(\d+\s?X\s?\d+(?:\s?X\s?\d+)?\s?MM)", desc)
    if sz:
        specs["size"] = sz.group(1)
    cm = re.search(r"CURRENT MEASURING RANGE\s*-\s*([\w.-]+A) AC", desc)
    if cm:
        specs["current_range"] = cm.group(1) + " AC"
    vm = re.search(r"VOLTAGE MEASURING RANGE\s*-\s*([\w.-]+V) AC", desc)
    if vm:
        specs["voltage_range"] = vm.group(1) + " AC"
    pr = re.search(r"\((\d+A TO \d+A PROGRAMMABLE)\)", desc)
    if pr:
        specs["rating"] = pr.group(1).replace("A TO ", "-").replace(
            " PROGRAMMABLE", "")          # '10A TO 9995A' -> '10-9995A'
        specs["programmable_range"] = pr.group(1)
    if "3 PHASE" in desc.upper():
        specs["phases"] = "3 PHASE"
    if price is None:
        add_skip(page_no, " / ".join(block), "FDM block with no printed price")
        return
    add_row(page_no, section, model, "%s | %s" % (section, desc), price, specs,
            " / ".join(block))


def parse_fdm_zone(lines, page_no, section_names):
    section = None
    block, pending = [], []
    for ln in lines:
        up = ln.upper()
        hit = next((s for s in section_names if s in up), None)
        if hit:
            flush_fdm(page_no, section, block, pending)
            block, pending, section = [], [], hit
            continue
        if up.startswith("FDM"):
            flush_fdm(page_no, section, block, pending)
            block, pending = [ln], []
        elif block:
            block.append(ln)
        else:
            pending.append(ln)
    flush_fdm(page_no, section, block, pending)


def parse_page9(page, page_no):
    lines = page_lines(page)
    section = "CHANGE OVER SWITCHES"
    fdm_zone = []
    for ln in lines:
        up = ln.upper()
        if "PHASE SELECTOR" in up:
            section = "PHASE SELECTOR SWITCHES"
            continue
        if "ROTARY SWITCHES" in up:
            section = "SERIES ROTARY SWITCHES"
            continue
        if "DIGITAL PANEL METER" in up or fdm_zone or "DIGITAL AC" in up:
            fdm_zone.append(ln)
            continue
        m = re.match(r"^(FS\d+-\d+)\s+(.*?)\s+(\d{3,5})$", ln)
        if not m:
            if re.search(r"\d{3,5}$", ln):
                add_skip(page_no, ln, "unparsed priced line on page 9")
            continue
        model, mid, price = m.group(1), m.group(2), int(m.group(3))
        specs = {"series": "%s %s" % (model.split("-")[0], section)}
        rm = re.search(r"\b(\d+)A\b", mid)
        if rm:
            specs["rating"] = rm.group(1) + "A"
            if model.endswith("-16") and rm.group(1) != "16":
                note(specs, "model code says -16 but the row prints %sA; "
                            "kept exactly as printed" % rm.group(1))
        pm = re.search(r"(\d)-?\s?POLE", mid)
        if pm:
            specs["poles"] = pm.group(1) + "P"
        posm = re.search(r"(\d-POSITION [\d-]+|OFF-ON)", mid)
        if posm:
            specs["positions"] = posm.group(1)
        elif "1-0-2" in mid:
            specs["positions"] = "1-0-2"
        add_row(page_no, section, model, "%s | %s %s" % (section, model, mid),
                price, specs, ln)
    parse_fdm_zone(fdm_zone, page_no, ["DIGITAL AC AMMETER", "DIGITAL AC VOLTMETER"])


def parse_page10(page, page_no):
    lines = page_lines(page)
    parse_fdm_zone(lines, page_no,
                   ["DIGITAL FREQUENCY METER", "DIGITAL WATT METER",
                    "DIGITAL DIN RAIL TYPE METER"])
    # the FDM-60A / FDM-80V pair repeats a model code with a different price
    seen60 = [r for r in rows if r["page"] == page_no and r["model"] == "FDM-60A"]
    if len(seen60) == 2:
        note(seen60[1]["specs"],
             "FDM-60A is printed twice in this table (890 and 540); this second "
             "row follows FDM-80V in the voltmeter pair and is most likely a "
             "misprint for FDM-60V - kept exactly as printed")


def parse_page11(page, page_no):
    lines = page_lines(page)
    section = model = None
    pa = []
    for ln in lines:
        up = ln.upper()
        if "DIGITAL VA METER" in up:
            section, model = "DIGITAL VA METER", "FDM-VA"
        elif "DIGITAL VAF METER" in up:
            section, model = "DIGITAL VAF METER", "FDM-VAF"
        elif "DIGITAL POWER ANALYSER" in up:
            section, model = "DIGITAL POWER ANALYSER", "FDM-PA"
        m = re.search(r"Rs\s*\.?\s*([\d,]+)", ln)
        if not m:
            continue
        price = int(m.group(1).replace(",", ""))
        if model == "FDM-VA":
            add_row(page_no, section, "FDM-VA",
                    "DIGITAL VA METER | FDM-VA | CURRENT MEASURING RANGE - 0-100A AC "
                    "| VOLTAGE MEASURING RANGE - 60-300V AC | 54 X 80 X 64 MM",
                    price, {"series": "FDM DIGITAL VA METER", "size": "54 X 80 X 64 MM",
                            "current_range": "0-100A AC", "voltage_range": "60-300V AC"},
                    ln)
        elif model == "FDM-VAF":
            add_row(page_no, section, "FDM-VAF",
                    "DIGITAL VAF METER | FDM-VAF(96 x 96 x 82) | PHASE TO NEUTRAL "
                    "VOLTAGES, PHASE TO PHASE VOLTAGES, PHASE CURRENT-IR,IY,IB, "
                    "AVG.PHASE TO PHASE VOLTAGE, AVG.PHASE PHASE CURRENT, FREQUENCY",
                    price, {"series": "FDM DIGITAL VAF METER", "size": "96 x 96 x 82"},
                    ln)
        elif model == "FDM-PA":
            pa.append((price, ln))
    # FDM-PA prints two prices in two ruled cells: 'Rs 8300/= without
    # communication interface.' and 'Rs 9800 with communication interface'
    # (verified on a 220-dpi render of page 11).
    variants = ["without communication interface", "with communication interface"]
    if len(pa) != len(variants):
        for price, ln in pa:
            add_skip(page_no, ln, "FDM-PA price found but its printed variant "
                                  "label could not be matched")
        return
    for (price, ln), var in zip(pa, variants):
        add_row(page_no, "DIGITAL POWER ANALYSER", "FDM-PA",
                "DIGITAL POWER ANALYSER | FDM-PA (96 x 96 x 82) | " + var,
                price, {"series": "FDM DIGITAL POWER ANALYSER",
                        "size": "96 x 96 x 82", "variant": var}, ln)


# ------------------------------------------------------------------ page 12

def parse_page12(page, page_no):
    lines = page_lines(page)
    section = "D FUSE Fitting"
    for ln in lines:
        up = ln.upper()
        if "FUSE LINK" in up and "KV" in up:
            section = "FUSE LINK (11 KV)"
            continue
        if up.startswith("D FUSE"):
            section = "D FUSE Fitting"
            continue
        m = re.match(r"^(.*?)\s*Rs\s*\.?\s*([\d,]+)\s*(?:/[-=])?$", ln)
        if not m:
            if re.search(r"\d{3}", ln):
                add_skip(page_no, ln, "unparsed priced line on page 12")
            continue
        name, price = m.group(1).strip(), int(m.group(2).replace(",", ""))
        if section == "FUSE LINK (11 KV)":
            specs = {"series": "FUSE LINK (11 KV)", "voltage": "11 KV",
                     "rating": name}
            note(specs, "rating is the printed K-type fuse-link size (%s), "
                        "exactly as printed" % name)
        else:
            specs = {"series": "D FUSE Fitting"}
            note(specs, "no catalogue code printed; the printed item name is "
                        "used as the model")
        add_row(page_no, section, name, "%s | %s" % (section, name),
                price, specs, ln)


# ------------------------------------------------------------------ page 13

def parse_page13(page, page_no):
    lines = page_lines(page)
    for ln in lines:
        # the section names are set vertically and interleave as single capitals
        clean = re.sub(r"^(?:[A-Z]\s+)+(?=\d)", "", ln)
        # '100 Amp (TPN)' - the parenthetical sits in the Rating cell, not Type
        m = re.match(r"^(\d+)\s+Amp\s*(\([A-Z]+\))?\s+(.+?)\s+(\d)\s+(\d{3,6})$", clean)
        if not m:
            if re.search(r"\d{3,6}$", clean) and "Amp" in clean:
                add_skip(page_no, ln, "unparsed priced line on page 13")
            continue
        amp, paren, typ, poles, price = (m.group(1), m.group(2), m.group(3).strip(),
                                         m.group(4), int(m.group(5)))
        section = "MAIN SWITCHES" if "Main Switch" in typ else "CHANGE OVER SWITCHES"
        rating_txt = "%s Amp%s" % (amp, " " + paren if paren else "")
        model = "%s %s" % (rating_txt, typ)   # no catalogue code is printed here
        specs = {"rating": amp + "A", "poles": poles + "P", "series": typ}
        if paren:
            specs["configuration"] = paren.strip("()")
        note(specs, "no catalogue code printed on this page; the printed "
                    "Rating/Type/Poles triple is used as the model. Page header "
                    "prints 'FICO ENTERPRISES'")
        add_row(page_no, section, model,
                "%s | %s %s | %s Pole" % (section, rating_txt, typ, poles),
                price, specs, ln)


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main():
    with pdfplumber.open(PDF) as pdf:
        n_pages = len(pdf.pages)
        raw_text = {i + 1: (pg.extract_text() or "") for i, pg in enumerate(pdf.pages)}

        def halves(page):
            ws = page.extract_words(x_tolerance=1.5, y_tolerance=2.0)
            return (cluster_lines([w for w in ws if w["x1"] <= 300]),
                    cluster_lines([w for w in ws if w["x1"] > 300]))

        for idx, (lsec, rsec) in ((2, ("ELC (ECONOMICAL CLASS)", "ILC (INNOVATIVE CLASS)")),
                                  (3, ("RLC SERIES", "SLC SERIES")),
                                  (4, ("SDH", "SPLIT CORE CURRENT TRANSFORMER"))):
            L, R = halves(pdf.pages[idx])
            parse_ct_half(idx + 1, L, lsec)
            parse_ct_half(idx + 1, R, rsec)

        p6 = pdf.pages[5]
        parse_page6_left(p6, 6)
        parse_page6_right(p6, 6)

        parse_page7(pdf.pages[6], 7)
        parse_page8(pdf.pages[7], 8)
        parse_page9(pdf.pages[8], 9)
        parse_page10(pdf.pages[9], 10)
        parse_page11(pdf.pages[10], 11)
        parse_page12(pdf.pages[11], 12)
        parse_page13(pdf.pages[12], 13)

    # ---------------- sanity band
    kept = []
    for r in rows:
        p = r["price_pkr"]
        if p is not None and (p < 10 or p > 10_000_000):
            add_skip(r["page"], r["_raw"],
                     "sanity: price %s outside the 10..10,000,000 PKR band" % p)
        else:
            kept.append(r)

    # ---------------- duplicates: same model AND same description AND same specs.
    # (model alone is not enough - page 8 sells two different FS26-20 selector
    #  switches at the same 935 price, and page 10 prints FDM-60A twice.)
    seen = {}
    final = []
    for r in kept:
        key = (r["model"], r["description"],
               json.dumps({k: v for k, v in r["specs"].items() if k != "note"},
                          sort_keys=True))
        if key in seen and seen[key] == r["price_pkr"]:
            add_skip(r["page"], r["_raw"],
                     "duplicate of an identical row (same model, description, "
                     "specs and price)")
            continue
        seen[key] = r["price_pkr"]
        final.append(r)

    # ---------------- per-page count assertion
    per_page = {}
    for r in final:
        per_page[r["page"]] = per_page.get(r["page"], 0) + 1
    if per_page != EXPECTED_PER_PAGE:
        raise RuntimeError("row counts changed: expected %s, got %s"
                           % (EXPECTED_PER_PAGE, per_page))

    prices = [r["price_pkr"] for r in final if r["price_pkr"] is not None]

    # ---------------- validation report
    P("=== rows per page (parsed vs pinned hand-count) ===")
    for pg in sorted(per_page):
        P("  page %-2d parsed=%-3d expected=%-3d %s"
          % (pg, per_page[pg], EXPECTED_PER_PAGE[pg],
             "OK" if per_page[pg] == EXPECTED_PER_PAGE[pg] else "MISMATCH"))

    P("")
    P("=== coverage: priced lines visible in the raw text vs parsed, 3 pages ===")
    checks = {
        4:  (r"\d+/\d+A\s+\d+\s+\d+\s+\d+\s+\d{3,5}", "ratio class va pt price"),
        9:  (r"\d{3,5}\s*$", "line ending in a price"),
        13: (r"Amp .*\d\s+\d{3,6}\s*$", "rating/type/poles/price line"),
    }
    for pg, (rx, what) in checks.items():
        raw_hits = 0
        for ln in raw_text[pg].splitlines():
            ln = ln.strip()
            if FOOTER_PAT.search(ln):        # the contact-phone footer is not a price
                continue
            raw_hits += len(re.findall(rx, ln))
        parsed = sum(1 for r in final if r["page"] == pg and r["price_pkr"] is not None)
        P("  page %-2d raw priced lines (%s) = %-3d   parsed priced = %d"
          % (pg, what, raw_hits, parsed))

    P("")
    P("=== price sanity ===")
    P("  min=%d  median=%s  max=%d  (n=%d)"
      % (min(prices), statistics.median(prices), max(prices), len(prices)))

    P("")
    P("=== 10 random parsed rows with their source line ===")
    random.seed(11)
    for r in random.sample(final, 10):
        P("  p%-2d %-28s Rs %-8s %s"
          % (r["page"], r["model"], r["price_pkr"], r["specs"].get("rating", "")))
        P("      raw : %s" % r["_raw"])
        P("      desc: %s" % r["description"])

    P("")
    P("=== skipped (%d) ===" % len(skipped))
    for s in skipped:
        P("  p%-2d [%s] %s" % (s["page"], s["reason"], s["raw"][:90]))

    for r in final:
        r.pop("_raw", None)

    out = {
        "source_pdf": os.path.basename(PDF),
        "rows": final,
        "skipped": skipped,
        "stats": {
            "pages": n_pages,
            "rows": len(final),
            "priced": len(prices),
            "skipped": len(skipped),
        },
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    P("")
    P("stats:", out["stats"])
    P("written:", OUT)


if __name__ == "__main__":
    main()
