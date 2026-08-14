"""
Faithful extractor for "Himel price list 2022.pdf" (Powerhouse / Himel, 40 pages).

WHY THIS FILE LOOKS DIFFERENT FROM chint.py / pce.py
----------------------------------------------------
This PDF has almost no text layer.  On every product page the reference
numbers, descriptions, ratings and column headers were converted to VECTOR
OUTLINES by the designer: pdfplumber/PyMuPDF report ~1 font (ArialMT) per page
and only ~10-30 text characters, and those characters are the PRICES.  That is
why plain extract_text() looks "scrambled" - it is not scrambled, it is a bare
run of prices with every other column physically absent from the text layer.
No amount of x/y word clustering can recover text that is not there.

Two further traps in the text that IS there:

1. SUPERSEDED PRICE LAYER.  Pages 18, 19, 21 and 35 carry an OLD price run that
   was drawn first and then painted over with the opaque table row-bands (and
   on p35, moved off-page by a clip).  Both runs are real, black, opaque text
   at ~the same coordinates.  Taking the raw text gives 2x the prices and, for
   9 of the 19 rows on page 18, the WRONG one.  page_tokens() therefore keeps a
   token only if no later opaque filled rectangle covers it (z-order test).
   The coverage measure is perfectly bimodal over the whole document
   (694 tokens at 0.00, 25 at 1.00, 1 at 0.80) - there is no grey zone.
2. Stream order != visual order.  On page 14 the ACB prices are emitted as
   ... 376,000 501,400 463,450 ... while the rows read 1250A, 1600A, 2000A.
   Everything is therefore re-sorted by y before it is matched to a row.

HOW THE OUTLINED TEXT WAS RECOVERED
-----------------------------------
Every product page was rendered at 150 dpi and read off the rendered page, then
transcribed into the TABLES spec below (reference numbers, ratings, poles,
descriptions, section headings, spec-box values).  The transcription was
cross-checked against the pages where Himel did leave real text - page 11 rows
20-26, page 25, page 26, page 28, page 37 and page 38 all still carry live text
for the model column, and the transcription matches those byte for byte
(e.g. p11 'HDM3250S250B3XX 4 Pole 250 Amps 250 35 21', p28 'HAVXS4T0185G0220P
30 HP / 22 KW').

NO PRICE IN THIS FILE IS TRANSCRIBED.  Every price_pkr comes from the PDF text
layer, located by coordinate.  The spec only says WHICH rows exist and in which
y-band / price-column the price for each row must be found; if the number of
visible price tokens inside a table's band is not exactly the number of rows
that the spec says are priced, the script raises RuntimeError instead of
guessing (same fail-loud philosophy as chint.py's pinned blocks).

Price columns are declared as a right-edge window (px), because every price
column in this document is right-aligned to within ~2pt.  That window is also
what keeps the p11/p12 spec numbers (Frame / ICU / ICS, which are live text on
a few rows) and the p35 clipped ghost out of the price stream.

The reverse direction is checked too: after every table has taken its prices,
any price-shaped token still unclaimed on a product page is compared against
EXPECTED_LEFTOVERS (2 page numbers, 13 Frame/ICU/ICS figures, 1 clipped ghost).
If that set ever changes the run aborts, so a real price can never be silently
dropped by a band or window that has drifted.

PRICES NOT PRINTED
------------------
* "POR*" (= "*Price on request", printed on p12 and p14) -> price_pkr = null
  with specs.note.  10 rows.
* "-" cells in the two MCCB accessory matrices (Motor Mechanism is not offered
  on the 3 smallest frames) -> routed to "skipped", they are not products.
* Merged price cells: p18 "HFT6 Air Delayed Contact" prints ONE price per
  delay-type block, in a cell visually merged across its 3 reference numbers.
  Those 3 rows share that printed price and carry specs.note saying so.  This
  is the only place a price is reused across rows.

KNOWN PDF ANOMALIES, KEPT AS PRINTED
------------------------------------
* p32 "Indication Lamps 110 V DC" reprints the same reference numbers as
  "Indication Lamps 24V DC" (HLD1122D21B3/B4/B5/B8).  Both blocks are emitted;
  they differ only in the printed section voltage, which is recorded in specs.
* p18 row 5 prints "Mechanical I  terlock" (missing 'n').  Kept verbatim.
* p29's spec box is headed "HDRT8", which is the time-relay code, on the panel
  meter page.  Not used for series; series comes from the model prefixes.
* p30 prints "15-3 75" and "20 3 75" where the other rows print "15-3.75" /
  "20-3.75".  Kept verbatim.
* p7/p8 repeat a reference number at two different rating groups with two
  different prices (e.g. HDB3wL1C at "1/2/50/63Amps" 750 and at
  "6/10/16/20/25/32/40Amps" 700).  Both rows are emitted, as instructed.

Run:
    venv/Scripts/python.exe extraction/himel.py
Writes: extraction/out/himel.json
"""

import json
import os
import random
import re
import statistics

import fitz  # PyMuPDF

PDF_PATH = r"C:/Users/AWCD/Desktop/client/engmart (2)/product-details/Himel price list 2022.pdf"
OUT_PATH = r"C:/Users/AWCD/Desktop/client/engmart (2)/backend/extraction/out/himel.json"

BRAND = "Himel"


def p(s=""):
    print(str(s).encode("ascii", "replace").decode())


def norm(s):
    return re.sub(r"\s+", " ", s or "").strip()


# ---------------------------------------------------------------------------
# text layer: visible tokens only
# ---------------------------------------------------------------------------
def _inter(a, b):
    x0 = max(a[0], b[0]); y0 = max(a[1], b[1])
    x1 = min(a[2], b[2]); y1 = min(a[3], b[3])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    return (x1 - x0) * (y1 - y0)


def _emit(toks, cur, seq, fills):
    if not cur:
        return
    text = "".join(c[0] for c in cur).strip()
    if not text:
        return
    x0 = min(c[1][0] for c in cur); y0 = min(c[1][1] for c in cur)
    x1 = max(c[1][2] for c in cur); y1 = max(c[1][3] for c in cur)
    box = (x0, y0, x1, y1)
    area = max((x1 - x0) * (y1 - y0), 1e-6)
    cov = max((_inter(r, box) for sq, r in fills if sq > seq), default=0.0) / area
    toks.append({"text": text, "x0": x0, "y0": y0, "x1": x1, "y1": y1, "cov": cov})


def page_tokens(page):
    """Horizontal text tokens of a page with position and 'covered later' ratio."""
    fills = []
    for d in page.get_drawings():
        if d["type"] not in ("f", "fs") or d.get("fill") is None:
            continue
        if (d.get("fill_opacity") or 1.0) < 0.99:
            continue
        for it in d["items"]:
            if it[0] == "re":
                r = it[1]
                fills.append((d["seqno"], (r.x0, r.y0, r.x1, r.y1)))

    toks = []
    for span in page.get_texttrace():
        if span.get("dir") != (1.0, 0.0):
            continue  # rotated sidebar tabs ("Molded Case Circuit Breaker") - not data
        seq = span["seqno"]
        chars = [(chr(c[0]), c[3]) for c in span["chars"]]
        # group into visual lines by glyph mid-height, then into tokens by x-gap
        lines = []
        for ch, bb in sorted(chars, key=lambda t: (t[1][1] + t[1][3]) / 2):
            mid = (bb[1] + bb[3]) / 2
            if lines and abs(mid - lines[-1][0]) <= 2.5:
                lines[-1][1].append((ch, bb))
            else:
                lines.append((mid, [(ch, bb)]))
        for _, items in lines:
            items.sort(key=lambda t: t[1][0])
            cur = []
            for ch, bb in items:
                if cur and bb[0] - cur[-1][1][2] > 1.6:
                    _emit(toks, cur, seq, fills)
                    cur = []
                cur.append((ch, bb))
            _emit(toks, cur, seq, fills)
    return toks


PRICE_RE = re.compile(r"^\d{1,3}(?:,\s?\d{3})+$|^\d{2,7}$")


def price_tokens(page):
    """Visible, price-shaped tokens (superseded/overpainted runs removed)."""
    out = []
    for t in page_tokens(page):
        if t["cov"] >= 0.5:
            continue  # painted over by a later opaque band = superseded price
        if PRICE_RE.match(t["text"]):
            t = dict(t)
            t["value"] = int(t["text"].replace(",", "").replace(" ", ""))
            out.append(t)
    return out


# ---------------------------------------------------------------------------
# table spec
# ---------------------------------------------------------------------------
# Each table:
#   page      1-based page number
#   section   printed section / sub-heading text
#   series    product family used to group ampere variants (printed family code)
#   y         (y_lo, y_hi) band of the table body
#   px        (x1_lo, x1_hi) right-edge window of the price column
#   columns   printed column headers, parallel to each row tuple
#   keys      spec key per column; "MODEL" = reference no, "RATING" = amperage,
#             "DESC" = free description cell, None = do not store
#   rows      one tuple per printed row, cells exactly as printed
#   fixed     specs applied to every row, taken from the printed spec box
#   por       row indices whose price cell prints "POR*"
#   merged    groups of row indices that share one visually-merged price cell
#
# Matrix tables (MCCB accessory price grids) use kind="matrix".

POR_NOTE = 'price cell prints "POR*" (the page footnote reads "*Price on request")'

TABLES = [
    # ---------------------------------------------------------------- page 7
    dict(page=7, section="Miniature Circuit Breaker - 18mm Miniature Circuit Breaker",
         series="HDB3w", y=(260, 400), px=(530, 540),
         columns=["Reference No.", "Type", "Ratings", "Breaking Capacity"],
         keys=["MODEL", "poles", "RATING", "breaking_capacity"],
         fixed={"tripping_curve": "B, C and D Curves", "standard": "IEC 60898-1",
                "poles_range": "1P - 4P"},
         rows=[
             ("HDB3wL1C", "1 Pole", "1/2/50/63Amps", "4.5kA"),
             ("HDB3wL1C", "1 Pole", "6/10/16/20/25/32/40Amps", "4.5kA"),
             ("HDB3wL2C", "2 Pole", "6/10/16/20/32/40Amps", "4.5kA"),
             ("HDB3wL2C", "2 Pole", "50/ 63Amps", "4.5kA"),
             ("HDB3wL3C", "3 Pole", "6/10/16/25/32/40Amps", "4.5kA"),
             ("HDB3wL3C", "3 Pole", "50/63Amps", "4.5kA"),
         ]),
    dict(page=7, section="Miniature Circuit Breaker - 18mm Miniature Circuit Breaker",
         series="HDB3w", y=(400, 520), px=(530, 540),
         columns=["Reference No.", "Type", "Ratings", "Breaking Capacity"],
         keys=["MODEL", "poles", "RATING", "breaking_capacity"],
         fixed={"tripping_curve": "B, C and D Curves", "standard": "IEC 60898-1",
                "poles_range": "1P - 4P"},
         rows=[
             ("HDB3wN1C", "1 Pole", "1/2/50/63Amps", "6kA"),
             ("HDB3wN1C", "1 Pole", "6/10/16/20/25/32/40Amps", "6kA"),
             ("HDB3wN2C", "2 Pole", "6/10/16/20/32/40Amps", "6kA"),
             ("HDB3wN2C", "2 Pole", "50/63Amps", "6kA"),
             ("HDB3wN3C", "3 Pole", "6/10/16/20/25/32/40Amps", "6kA"),
             ("HDB3wN3C", "3 Pole", "50/63Amps", "6kA"),
         ]),
    # ---------------------------------------------------------------- page 8
    dict(page=8, section="Miniature Circuit Breaker - 18mm Miniature Circuit Breaker",
         series="HDB3w", y=(250, 400), px=(518, 526),
         columns=["Reference No.", "Type", "Ratings", "Breaking Capacity"],
         keys=["MODEL", "poles", "RATING", "breaking_capacity"],
         fixed={"tripping_curve": "C and D Curves", "standard": "IEC 60947-2"},
         rows=[
             ("HDB3wN4C16", "4 Pole", "16Amps", "6kA"),
             ("HDB3wN4C20", "4 Pole", "20Amps", "6kA"),
             ("HDB3wN4C25", "4 Pole", "25Amps", "6kA"),
             ("HDB3wN4C32", "4 Pole", "32Amps", "6kA"),
             ("HDB3wN4C40", "4 Pole", "40Amps", "6kA"),
             ("HDB3wN4C50", "4 Pole", "50Amps", "6kA"),
             ("HDB3wN4C63", "4 Pole", "63Amps", "6kA"),
         ]),
    dict(page=8, section="Miniature Circuit Breaker - 27mm Miniature Circuit Breaker",
         series="HD3w - 125", y=(570, 700), px=(516, 524),
         columns=["Reference No.", "Type", "Ratings", "Breaking Capacity"],
         keys=["MODEL", "poles", "RATING", "breaking_capacity"],
         fixed={"tripping_curve": "C and D Curves", "standard": "IEC 60947-2"},
         rows=[
             ("HDB3w125H3C80", "3 Pole", "80Amps", "10kA"),
             ("HDB3w125H3C100", "3 Pole", "100Amps", "10kA"),
             ("HDB3w125H3C125", "3 Pole", "125Amps", "10kA"),
             ("HDB3w125H4C80", "4 Pole", "80Amps", "10kA"),
             ("HDB3w125H4C100", "4 Pole", "100Amps", "10kA"),
             ("HDB3w125H4C125", "4 Pole", "125Amps", "10kA"),
         ]),
    dict(page=8, section="Miniature Circuit Breaker - Accessories",
         series="HDB3w accessories", y=(740, 800), px=(509, 516),
         # printed as: [accessory name] [reference] [price]; the reference code
         # sits in the unlabelled second column of the "Reference No." table.
         columns=["Description", "Reference No."],
         keys=["DESC", "MODEL"],
         fixed={},
         rows=[
             ("Contact Accessory", "OF"),
             ("Fault Indicating Accessory", "SD"),
             ("Shunt trip release", "MX + OF"),
         ]),
    # ---------------------------------------------------------------- page 9
    dict(page=9, section="Residual Current Devices - Electromagnetic Type Residual Current Switch (RCCB/ELCB)",
         series="HDB6VR / HDB3VR", y=(250, 400), px=(525, 532),
         columns=["Reference No.", "Type", "Ratings", "Sensitivity"],
         keys=["MODEL", "poles", "RATING", "sensitivity"],
         fixed={"type": "A/AC", "standard": "IEC 61008-1"},
         rows=[
             ("HDB6VR225SC/TC", "2 Pole", "25Amps", "30/300mA"),
             ("HDB6VR240SC/TC", "2 Pole", "40Amps", "30/300mA"),
             ("HDB6VR263SC/TC", "2 Pole", "63Amps", "30/300mA"),
             ("HDB6VR440SC/TC", "4 Pole", "40Amps", "30/300mA"),
             ("HDB6VR463SC/TC", "4 Pole", "63Amps", "30/300mA"),
             ("HDB6VR4100TC", "4 Pole", "100Amps", "300mA"),
         ]),
    dict(page=9, section="Surge Protective Devices",
         series="HDY1/HDY3", y=(600, 730), px=(525, 532),
         columns=["Reference No.", "Imax", "Pole", "Voltage"],
         keys=["MODEL", "imax", "poles", "voltage"],
         fixed={"standard": "IEC 61643"},
         rows=[
             ("HDY3201P275", "20kA", "1 Pole", "275V"),
             ("HDY3406275", "40kA", "4 Pole", "275V"),
             ("HDY1202275", "20kA", "2 Pole", "275V"),
             ("HDY1402275", "40kA", "2 Pole", "275V"),
             ("HDY1404420", "40kA", "4 Pole", "420V"),
             ("HDY1604420", "60kA", "4 Pole", "420V"),
             ("HDY1804420", "80kA", "4 Pole", "420V"),
         ]),
    # --------------------------------------------------------------- page 11
    dict(page=11, section="Molded Case Circuit Breaker (MCCB) - 3 Pole MCCB (Fixed Type)",
         series="HDM3", y=(210, 520), px=(533, 540),
         columns=["Reference No.", "Type", "Ratings", "Frame", "ICU (KA)", "ICS (KA)"],
         keys=["MODEL", "poles", "RATING", "frame", "icu_ka", "ics_ka"],
         fixed={"rated_frequency": "50/60Hz", "standard": "IEC 60947-2"},
         rows=[
             ("HDM3100S1633XX", "3 Pole", "16Amps", "100", "25", "18"),
             ("HDM3100S2033XX", "3 Pole", "20Amps", "100", "25", "18"),
             ("HDM3100S3233XX", "3 Pole", "32Amps", "100", "25", "18"),
             ("HDM3100S4033XX", "3 Pole", "40Amps", "100", "25", "18"),
             ("HDM3100S5033XX", "3 Pole", "50Amps", "100", "25", "18"),
             ("HDM3100S6333XX", "3 Pole", "63Amps", "100", "25", "18"),
             ("HDM3100S8033XX", "3 Pole", "80Amps", "100", "25", "18"),
             ("HDM3100S10033XX", "3 Pole", "100Amps", "100", "25", "18"),
             ("HDM3160S12533XX", "3 Pole", "125Amps", "160", "35", "21"),
             ("HDM3160S16033XX", "3 Pole", "160Amps", "160", "35", "21"),
             ("HDM3250S20033XX", "3 Pole", "200Amps", "250", "35", "21"),
             ("HDM3250S25033XX", "3 Pole", "250Amps", "250", "35", "21"),
             ("HDM3400F31533XX", "3 Pole", "315Amps", "400", "50", "30"),
             ("HDM3400F40033XX", "3 Pole", "400Amps", "400", "50", "30"),
             ("HDM3630F50033XX", "3 Pole", "500Amps", "630", "50", "30"),
             ("HDM3630F63033XX", "3 Pole", "630Amps", "630", "50", "30"),
             ("HDM3800F80033XX", "3 Pole", "800Amps", "800", "70", "40"),
             ("HDM31250N100033XX", "3 Pole", "1000Amps", "1250", "85", "45"),
             ("HDM31250N125033XX", "3 Pole", "1250Amps", "1250", "85", "45"),
         ]),
    dict(page=11, section="Molded Case Circuit Breaker (MCCB) - 4 Pole MCCB (Fixed Type)",
         series="HDM3", y=(570, 690), px=(534, 541),
         columns=["Reference No.", "Type", "Ratings", "Frame", "ICU (KA)", "ICS (KA)"],
         keys=["MODEL", "poles", "RATING", "frame", "icu_ka", "ics_ka"],
         fixed={"rated_frequency": "50/60Hz", "standard": "IEC 60947-2"},
         rows=[
             ("HDM3100S63B3XX", "4 Pole", "63Amps", "100", "25", "18"),
             ("HDM3100S100B3XX", "4 Pole", "100Amps", "100", "25", "18"),
             ("HDM3250S200B3XX", "4 Pole", "200Amps", "250", "35", "21"),
             ("HDM3250S250B3XX", "4 Pole", "250 Amps", "250", "35", "21"),
             ("HDM3400F400B3XX", "4 Pole", "400 Amps", "400", "50", "30"),
             ("HDM3630F630B3XX", "4 Pole", "630 Amps", "630", "50", "30"),
             ("HDM3800F800B3XX", "4 Pole", "800 Amps", "800", "70", "40"),
         ]),
    # --------------------------------------------------------------- page 12
    dict(page=12, kind="matrix",
         section="Accessories of MCCBs (Price in Rs.)", series="HDM3 accessories",
         cols=[("HDM3100S", 188, 193), ("HDM3S160", 243, 247), ("HDM3S250", 297, 301),
               ("HDM3S400", 352, 357), ("HDM3S630", 405, 410), ("HDM6S800", 459, 466),
               ("HDM3S1250", None, None)],
         rowbands=[('Auxiliary Contact "Right"', 75, 90),
                   ('Under Voltage Release "MN" 3P', 90, 112),
                   ('Shunt Release "MX"', 120, 140),
                   ("Motor Mechanism", 140, 160)],
         # cell kinds: "p" priced, "-" printed dash, "por" printed POR*
         cells=[["p", "p", "p", "p", "p", "p", "por"],
                ["p", "p", "p", "p", "p", "p", "por"],
                ["p", "p", "p", "p", "p", "p", "por"],
                ["-", "-", "-", "p", "p", "p", "por"]]),
    dict(page=12, section="Molded Case Circuit Breaker (MCCB) - 3 Pole MCCB (Adjustable Type)",
         series="HDM6", y=(405, 580), px=(524, 531),
         columns=["Reference No.", "Type", "Ratings", "Frame", "ICU (KA)", "ICS=ICU%"],
         keys=["MODEL", "poles", "RATING", "frame", "icu_ka", "ics_pct"],
         fixed={"rated_frequency": "50/60Hz", "standard": "IEC 60947-2",
                "trip_type": "Adjustable"},
         rows=[
             ("HDM6s100T01633", "3 Pole", "16Amps", "100", "30", "100%"),
             ("HDM6s100T02533", "3 Pole", "25Amps", "100", "30", "100%"),
             ("HDM6s100T04033", "3 Pole", "40Amps", "100", "30", "100%"),
             ("HDM6s100T06333", "3 Pole", "63Amps", "100", "30", "100%"),
             ("HDM6S100T10033", "3 Pole", "100Amps", "100", "30", "100%"),
             ("HDM6S250T12533", "3 Pole", "125Amps", "250", "30", "100%"),
             ("HDM6S250T16033", "3 Pole", "160Amps", "250", "30", "100%"),
             ("HDM6S250T20033", "3 Pole", "200Amps", "250", "30", "100%"),
             ("HDM6S250T25033", "3 Pole", "250Amps", "250", "30", "100%"),
             ("HDM6S400T40033", "3 Pole", "400Amps", "400", "40", "100%"),
             ("HDM6S630T63033", "3 Pole", "630Amps", "630", "40", "100%"),
         ]),
    # --------------------------------------------------------------- page 13
    dict(page=13, section="Molded Case Circuit Breaker (MCCB) - 3 Pole MCCB (Adjustable Type) Electronic Trip (L,S,I)",
         series="HDM3E", y=(240, 295), px=(535, 542),
         columns=["Reference No.", "Type", "Ratings", "Frame", "ICU (KA)"],
         keys=["MODEL", "poles", "RATING", "frame", "icu_ka"],
         fixed={"rated_frequency": "50/ 60Hz", "standard": "IEC 60947-2",
                "trip_type": "Electronic Trip (L,S,I)"},
         rows=[
             ("HDM3E250", "3 Pole", "250Amps", "250", "50"),
             ("HDM3E400", "3 Pole", "400Amps", "400", "70"),
             ("HDM3E800", "3 Pole", "800Amps", "800", "70"),
         ]),
    dict(page=13, kind="matrix",
         section="Accessories of MCCBs (Price in Rs.)", series="HDM6 accessories",
         cols=[("HDM6S063", 265, 270), ("HDM6S100", 320, 325), ("HDM6S250", 374, 379),
               ("HDM6S400", 428, 434), ("HDM6S630", 482, 487), ("HDM6S800", 536, 542)],
         rowbands=[('Auxiliary Contact "Right"', 405, 420),
                   ('Under Voltage Release "MN" 3P', 420, 437),
                   ('Shunt Release "MX"', 437, 452),
                   ("Motor Mechanism", 452, 470)],
         cells=[["p", "p", "p", "p", "p", "p"],
                ["p", "p", "p", "p", "p", "p"],
                ["p", "p", "p", "p", "p", "p"],
                ["-", "-", "-", "p", "p", "p"]]),
    # --------------------------------------------------------------- page 14
    dict(page=14, section="Air Circuit Breaker (ACB)",
         series="HDW3", y=(440, 560), px=(520, 527),
         columns=["Reference No.", "Type", "Ratings", "ICU", "ICS", "ICW (1S)"],
         keys=["MODEL", "poles", "RATING", "icu", "ics", "icw_1s"],
         fixed={"rated_operational_voltage": "400/ 415/ 660/ 690V",
                "rated_insulation_voltage_ui": "1000",
                "rated_impulse_withstand_voltage_uimp": "12",
                "rated_frequency": "50/60", "standard": "IEC 60947-2",
                "breaking_capacity_at": "400/ 415"},
         por=[7, 8, 9],
         rows=[
             ("HDW316S083FHM", "3 Pole", "800Amps", "42kA", "42kA", "42kA"),
             ("HDW316S103FHM", "3 Pole", "1000Amps", "42kA", "42kA", "42kA"),
             ("HDW320S123FHM", "3 Pole", "1250Amps", "65kA", "65kA", "65kA"),
             ("HDW320S163FHM", "3 Pole", "1600Amps", "65kA", "65kA", "65kA"),
             ("HDW320S203FHM", "3 Pole", "2000Amps", "65kA", "65kA", "65kA"),
             ("HDW332S253FHM", "3 Pole", "2500Amps", "65kA", "65kA", "65kA"),
             ("HDW332S323FHM", "3 Pole", "3200Amps", "65kA", "65kA", "65kA"),
             ("HDW340S403DHM (D/O)", "3 Pole", "4000Amps", "85kA", "85kA", "85kA"),
             ("HDW363S503DHM (D/O)", "3 Pole", "5000Amps", "85kA", "85kA", "85kA"),
             ("HDW363S633DHM (D/O)", "3 Pole", "6300Amps", "85kA", "85kA", "85kA"),
         ]),
    dict(page=14, section="Accessories of ACBs", series="HDW3 accessories",
         y=(685, 790), px=(520, 527),
         columns=["Reference No.", "Description"],
         keys=["MODEL", "DESC"],
         fixed={},
         rows=[
             ("MN2A", "Under Voltage Trip 220/415V AC"),
             ("MX/XF2A", "Shunt Trip 220/415V AC"),
             ("MNR2A", "Closing Coil"),
             ("MCH102A", "Motor Charged Spring Operating Mechanism"),
             ("MCH202A", "Motor Charged Spring Operating Mechanism"),
             ("MCH322A", "Motor Charged Spring Operating Mechanism"),
         ]),
    # --------------------------------------------------------------- page 16
    dict(page=16, section="Contactor", series="HDC3/HDC6",
         y=(300, 600), px=(519, 527),
         columns=["Reference No.", "Type", "AC-3 Ratings", "Auxiliary Contact",
                  "Rated Power (KW) 400V"],
         keys=["MODEL", "poles", "RATING", "auxiliary_contact", "rated_power_kw_400v"],
         fixed={"control_circuit_voltage": "24V - 440V AC, 50/60Hz",
                "matched_thermal_overload_relay": "HDR3/HDR6",
                "standard": "IEC/EN 60947-4-1"},
         rows=[
             ("HDC3 09 11M", "3 Pole", "9Amps", "1 NO + 1 NC", "4"),
             ("HDC3 12 11M", "3 Pole", "12Amps", "1 NO + 1 NC", "5.5"),
             ("HDC3 18 11M", "3 Pole", "18Amps", "1 NO + 1 NC", "7.5"),
             ("HDC3 25 11M", "3 Pole", "25Amps", "1 NO + 1 NC", "11"),
             ("HDC3 32 11M", "3 Pole", "32Amps", "1 NO + 1 NC", "15"),
             ("HDC3 40 11M", "3 Pole", "40Amps", "1 NO + 1 NC", "18.5"),
             ("HDC3 50 11M", "3 Pole", "50Amps", "1 NO + 1 NC", "22"),
             ("HDC3 65 11M", "3 Pole", "65Amps", "1 NO + 1 NC", "30"),
             ("HDC3 80 11M", "3 Pole", "80Amps", "1 NO + 1 NC", "37"),
             ("HDC3 95 11M", "3 Pole", "95Amps", "1 NO + 1 NC", "45"),
             ("HDC6 115 00M", "3 Pole", "115Amps", "-", "55"),
             ("HDC6 150 00M", "3 Pole", "150Amps", "-", "75"),
             ("HDC6 185 00M", "3 Pole", "185Amps", "-", "90"),
             ("HDC6 225 00M", "3 Pole", "225Amps", "-", "110"),
             ("HDC6 265 00M", "3 Pole", "265Amps", "-", "132"),
             ("HDC6 400 00M", "3 Pole", "400Amps", "-", "200"),
             ("HDC6 500 00M", "3 Pole", "500Amps", "-", "250"),
             ("HDC6 630 00M", "3 Pole", "630Amps", "-", "335"),
         ]),
    # --------------------------------------------------------------- page 17
    dict(page=17, section="Contactor - HJX2 4P AC Contactor", series="HJX2",
         y=(305, 515), px=(533, 542),
         columns=["Reference No.", "AC-3 Ratings", "AC-1 Ratings",
                  "Rated Power (KW) 400V", "hp"],
         keys=["MODEL", "RATING", "ac1_ratings", "rated_power_kw_400v", "hp"],
         fixed={"poles": "4P", "control_circuit_voltage": "24V - 440V AC, 50/60Hz",
                "matched_thermal_overload_relay": "HJR", "standard": "IEC/EN 60947-4"},
         rows=[
             ("HJX22504M", "25Amps", "40Amps", "11", "15"),
             ("HJX24004M", "40Amps", "60Amps", "18.5", "25"),
             ("HJX26504M", "65Amps", "80Amps", "30", "40"),
             ("HJX28004M", "80Amps", "125Amps", "37", "50"),
             ("HJX29504M", "95Amps", "125Amps", "45", "60"),
             ("HJX2F1154M", "115Amps", "200Amps", "55", "75"),
             ("HJX2F1504M", "150Amps", "250Amps", "75", "100"),
             ("HJX2F1854M", "185Amps", "275Amps", "90", "125"),
             ("HJX2F2254M", "225Amps", "275Amps", "110", "150"),
             ("HJX2F3304M", "330Amps", "400Amps", "160", "215"),
             ("HJX2F4004M", "400Amps", "450Amps", "200", "270"),
             ("HJX2F5004M", "500Amps", "630Amps", "250", "335"),
             ("HJX2F6304M", "630Amps", "800Amps", "335", "455"),
         ]),
    dict(page=17, section="Auxiliary Contact Block", series="HF4/HF6",
         y=(585, 690), px=(533, 540),
         columns=["Reference No.", "Description", "Contact Arrangement"],
         keys=["MODEL", "DESC", "contact_arrangement"],
         fixed={},
         rows=[
             ("HF4 02", "Top Auxiliary Contact", "2 NC"),
             ("HF4 11", "Top Auxiliary Contact", "1 NO + 1 NC"),
             ("HF4 22", "Top Auxiliary Contact", "2 NO + 2 NC"),
             ("HF6 02", "Side Auxiliary Contact", "2 NC"),
             ("HF6 11", "Side Auxiliary Contact", "1NO + 1 NC"),
             ("HF6 20", "Side Auxiliary Contact", "2 NO"),
         ]),
    # --------------------------------------------------------------- page 18
    dict(page=18, section="Contactor - Mechanical Interlocks/ Operating Coils",
         series="HFR6/HX", y=(120, 400), px=(517, 524),
         columns=["Reference No.", "Description", "Contactor"],
         keys=["MODEL", "DESC", "contactor"],
         fixed={},
         rows=[
             ("HFR6 ~ 32 H", "Mechanical Interlock", "HDC6 9 ~ 32 A"),
             ("HFR6 ~ 95 H", "Mechanical Interlock", "HDC6 40 ~ 95 A"),
             ("HFR 6FFH", "Mechanical Interlock", "HDC6 115 ~ 150 A"),
             ("HFR 6GGH", "Mechanical Interlock", "HDC6 185 ~ 225 A"),
             ("HFR 6HHH", "Mechanical I  terlock", "HDC6 265 ~ 330"),
             ("HFR 6KKH", "Mechanical Interlock", "HDC 6 400 ~ 500"),
             ("HFR6 LL H", "Mechanical Interlock", "HFR6 ~ 630"),
             ("HX318", "Coil 110/220V", "HDC3-9~18"),
             ("HX332", "Coil 110/220V", "HDC3-25~32"),
             ("HX365", "Coil 110/220V", "HDC3- 40~65"),
             ("HX395", "Coil 110/220V", "HDC3- 80~95"),
             ("HX6150", "Coil 220/400V", "HDC6 115 ~ 150"),
             ("HX6185-265", "Coil 220/400V", "HDC6 185-265"),
             ("HX6330", "Coil 220/400V", "HDC6 330"),
             ("HX6400", "Coil 220/400V", "HDC6400"),
             ("HX6500", "Coil 220/400V", "HDC6500"),
             ("HX6630", "Coil 220/400V", "HDC6630"),
         ]),
    dict(page=18, section="HFT6 Air Delayed Contact", series="HFT6",
         y=(570, 670), px=(517, 524),
         columns=["Reference No.", "Delay Range", "Delay Type"],
         keys=["MODEL", "delay_range", "delay_type"],
         fixed={},
         # one printed price per delay-type block, in a cell merged over 3 rows
         merged=[[0, 1, 2], [3, 4, 5]],
         rows=[
             ("HFT6-20", "0.1-3s", "Making time-delay"),
             ("HFT6-22", "0.1-30s", "Making time-delay"),
             ("HFT6-24", "10-180s", "Making time-delay"),
             ("HFT6-30", "0.1-3s", "Breaking time-delay"),
             ("HFT6-32", "0.1-30s", "Breaking time-delay"),
             ("HFT6-34", "10-180s", "Breaking time-delay"),
         ]),
    # --------------------------------------------------------------- page 19
    dict(page=19, section="Modular Contactors", series="HDCH8P",
         y=(265, 335), px=(522, 529),
         columns=["Reference No.", "Type", "Contact"],
         keys=["MODEL", "TYPE_POLE_RATING", "contact"],
         fixed={"rated_insulation_voltage_ui": "500V", "rated_voltage_ue": "230V",
                "coil_voltage": "220/230V", "standard": "IEC 61095"},
         rows=[
             ("HDCH8P20211", "2 Pole/ 20Amps", "1 NO + 1 NC"),
             ("HDCH8P40211", "2 Pole/ 40Amps", "1 NO + 1 NC"),
             ("HDCH8P20422", "4 Pole/ 20Amps", "2 NO + 2 NC"),
             ("HDCH8P25422", "4 Pole/ 25Amps", "2 NO + 2 NC"),
         ]),
    # --------------------------------------------------------------- page 20
    dict(page=20, section="Thermal Overload Relay", series="HDR3/HDR6", rating_mode="range",
         y=(285, 690), px=(514, 521),
         columns=["Reference No.", "Setting Range", "Contactor Model"],
         keys=["MODEL", "RATING", "contactor_model"],
         fixed={"protections": "Overload, phase failure protection, manual auto reset",
                "tripping_class": "10, 10A", "matched_contactor": "HDC3/HDC6",
                "standard": "IEC/EN 60947-4"},
         rows=[
             ("HDR3251", "0.63~1 A", "HDC3 9 ~ 38"),
             ("HDR3251P6", "1 ~1.6 A", "HDC3 9 ~ 38"),
             ("HDR3252P5", "1.6 ~2.5 A", "HDC3 9 ~ 38"),
             ("HDR3254", "2.5 ~4 A", "HDC3 9 ~ 38"),
             ("HDR3256", "4 ~ 6 A", "HDC3 9 ~ 38"),
             ("HDR3258", "5.5 ~ 8 A", "HDC3 9 ~ 38"),
             ("HDR32510", "7 ~ 10 A", "HDC3 9 ~ 38"),
             ("HDR32513", "9 ~ 13 A", "HDC3 9 ~ 38"),
             ("HDR32518", "12 ~ 18 A", "HDC3 9 ~ 38"),
             ("HDR32525", "17 ~ 25 A", "HDC3 9 ~ 38"),
             ("HDR33632", "23 ~ 32 A", "HDC3 25 ~ 32"),
             ("HDR33640", "30 ~ 40 A", "HDC3 32 ~ 38"),
             ("HDR39332", "23~ 32 A", "HDC3-40 ~ 95"),
             ("HDR39340", "30 ~ 40 A", "HDC3-40 ~ 95"),
             ("HDR39350", "37 ~ 50 A", "HDC3-50~95"),
             ("HDR39365", "48 ~ 65 A", "HDC3-50~95"),
             ("HDR39370", "55~70 A", "HDC3-65~95"),
             ("HDR39380", "63 ~ 80 A", "HDC3-80~95"),
             ("HDR39393", "80 ~ 93 A", "HDC3-95"),
             ("HDR6185115", "90 ~ 115 A", "HDC6- 115 ~ 185"),
             ("HDR6185150", "120 ~ 150 A", "HDC6- 115 ~ 185"),
             ("HDR6185185", "150 ~ 185 A", "HDC6- 115 ~ 185"),
             ("HDR6630200", "145 ~ 200 A", "HDC6 225 ~ 630"),
             ("HDR6630320", "230 ~ 320 A", "HDC6 225 ~ 630"),
             ("HDR6630400F", "290 ~ 400 A", "HDC6 225 ~ 630"),
         ]),
    dict(page=20, section="Thermal Overload Relay - Base", series="HDR3/HDR6",
         y=(720, 780), px=(514, 521),
         columns=["Reference No.", "Description"],
         keys=["MODEL", "DESC"],
         fixed={},
         rows=[("HDR618J", "Base"), ("HDR632J", "Base"), ("HDR695J", "Base")]),
    # --------------------------------------------------------------- page 21
    dict(page=21, section="Motor Protection Breaker - MPCB", series="HDP6", rating_mode="range",
         y=(340, 570), px=(534, 541),
         columns=["Reference No.", "Setting Current", "Current Id", "ICU (KA)",
                  "ICS (KA)", "Rated Operating Power", "Contactor"],
         keys=["MODEL", "RATING", "current_id", "icu_ka", "ics_ka",
               "rated_operating_power", "contactor"],
         fixed={"frame": "32", "rated_insulation_voltage_ui": "690V",
                "rated_impulse_withstand_voltage_uimp": "6KV",
                "rated_operational_voltage_ue": "690V",
                "rated_operational_frequency": "50/60Hz", "trip_class": "10A",
                "standard": "IEC 60947-1, IEC 60947-2, IEC 60947-4-1"},
         rows=[
             ("HDP6 32 P63", "0.4-0.63A", "8A", "100KA", "100KA", "0.12KW", "HDC3-0911"),
             ("HDP6 32 1", "0.63-1A", "13A", "100KA", "100KA", "0.25KW", "HDC3-0911"),
             ("HDP6 32 1P6", "1-1.6A", "22.5A", "100KA", "100KA", "0.37KW", "HDC3-0911"),
             ("HDP6 32 2P5", "1.6-2.5A", "33.5A", "100KA", "100KA", "0.75KW", "HDC3-0911"),
             ("HDP6 32 4", "2.5-4A", "51A", "100KA", "100KA", "1.5KW", "HDC3-0911"),
             ("HDP6 32 6P3", "4-6.3A", "78A", "100KA", "100KA", "2.2KW", "HDC3-0911"),
             ("HDP6 32 10", "6-10A", "138A", "100KA", "100KA", "4KW", "HDC3-0911"),
             ("HDP6 32 14", "9-14A", "170A", "15KA", "7.5KA", "5.5KW", "HDC3-1211"),
             ("HDP6 32 18", "13-18A", "223A", "15KA", "7.5KA", "7.5KW", "HDC3-1811"),
             ("HDP6 32 23", "17-23A", "327A", "15KA", "6KA", "9KW", "HDC3-2511"),
             ("HDP6 32 25", "20-25A", "327A", "15KA", "6KA", "11KW", "HDC3-2511"),
             ("HDP6 32 32", "24-32A", "416A", "10KA", "5KA", "15KW", "HDC3-3211"),
         ]),
    dict(page=21, section="Motor Protection Breaker - Accessories", series="HDP6 accessories",
         y=(600, 680), px=(534, 541),
         columns=["Reference No.", "Description"],
         keys=["MODEL", "DESC"],
         fixed={},
         rows=[
             ("HAE11", "Top Auxiliary Block (1NO+1NC)"),
             ("HAN11", "Side Auxiliary Block (1NO+1NC)"),
             ("HAN20", "Side Auxiliary Block (2NO)"),
             ("HDP632MC", "Water Proof Cover"),
         ]),
    # --------------------------------------------------------------- page 22
    dict(page=22, section="Magnetic Starter - DOL", series="HDS2/ HDS3", rating_mode="range",
         y=(265, 415), px=(515, 519),
         columns=["Reference No.", "Setting Current", "Motor Capacity at 380 V"],
         keys=["MODEL", "RATING", "motor_capacity_at_380v"],
         fixed={"coil_voltage": "36V, 110V, 127V, 220V, 230V, 380V,400V",
                "rated_operational_voltage": "400, 690V",
                "rated_insulation_voltage": "690V",
                "rated_operational_frequency": "50/60Hz", "standard": "IEC 60947-4"},
         rows=[
             ("HDS213B1P6M5", "1 - 1.6A", "0.37KW"),
             ("HDS213B2P5M5", "1.6 - 2.5A", "0.75KW"),
             ("HDS213B04M5", "2.5 - 4A", "1.5KW"),
             ("HDS213B06M5", "4 - 6A", "2.2KW"),
             ("HDS213B08M5", "5.5 - 8A", "3KW"),
             ("HDS213B10M5", "7 - 10A", "4KW"),
             ("HDS213B13M5", "9 - 13A", "5.5KW"),
             ("HDS225B18M5", "12 - 18A", "7.5KW"),
             ("HDS225B25M7", "17 - 25A", "11KW"),
         ]),
    dict(page=22, section="Relay - Miniature Relay", series="HDZ8P/ HDZ9",
         y=(630, 770), px=(518, 522),
         columns=["Reference No.", "Description"],
         keys=["MODEL", "DESC"],
         fixed={"rated_current": "3A, 5A, 10A",
                "coil_voltage": "AC6V-380V, DC6V-220V", "poles_range": "2P, 3P, 4P"},
         rows=[
             ("HDZ8P052LBZ1", "Miniature Relay, 8 Pin Flat 24VDC"),
             ("HDZ9052LM", "Miniature Relay, 8 Pin Flat 220VAC"),
             ("HPYF08A", "Base"),
             ("HDZ8P054LB1", "Miniature Relay, 14 Pin Flat 24VDC"),
             ("HDZ8P054LM1", "Miniature Relay, 14 Pin Flat 220VAC"),
             ("HDZ8PPYF14A", "Base"),
             ("HDZ8P053M1", "Miniature Relay, 8 Pin 220V, AC, No Indication"),
             ("HDZ8PPYF11AXXKH", "Base"),
         ]),
    # --------------------------------------------------------------- page 23
    dict(page=23, section="Relay - Phase Failure Relay", series="HXJ9",
         y=(245, 300), px=(527, 534),
         columns=["Reference No.", "Voltage", "Function"],
         keys=["MODEL", "voltage", "function"],
         fixed={"contactor_mode": "1NO+1NC", "contactor_endurance": "5A Resistive",
                "standard": "IEC 60947-5-1"},
         rows=[
             ("HXJ9380", "380V",
              "Phase Failure, Phase Sequence Protection, Over/Under Voltage Protection"),
             ("HXJ9400", "400V",
              "Phase Failure, Phase Sequence Protection, Over/Under Voltage Protection"),
         ]),
    dict(page=23, section="Relay - Time Relay", series="HDRT8",
         y=(505, 570), px=(527, 534),
         columns=["Reference No.", "Limit Delay Type", "Delay Type"],
         keys=["MODEL", "limit_delay_type", "delay_type"],
         fixed={"rated_operational_voltage": "230V AC", "rated_current": "AC-15 5A",
                "standard": "IEC 60947-5"},
         rows=[
             ("HDRT810B", "10s", "10s"),
             ("HDRT8120B", "120s", "120s"),
             ("HDRT8480B", "480s", "480s"),
             ("HDRT8480A", "480s", "480s"),
         ]),
    dict(page=23, section="Relay - Electronic Timer", series="HJSZ3",
         y=(715, 750), px=(527, 534),
         columns=["Reference No.", "Delay Range", "Rated Working Voltage"],
         keys=["MODEL", "delay_range", "rated_working_voltage"],
         fixed={"working_mode": "Relay after power-on"},
         rows=[
             ("HJSZ3AC240", "0.5-5s/50s/5m/30m", "240V AC"),
             ("HTP28XEDZ", "Base 8 Pin round", ""),
         ]),
    # --------------------------------------------------------------- page 25
    dict(page=25, section="HBSM Low Voltage Capacitor - HBSM Series", series="HBSM",
         y=(428, 490), px=(494, 501),
         columns=["Reference No.", "Description", "Voltage/Frequency"],
         keys=["MODEL", "DESC", "voltage_frequency"],
         fixed={"standard": "IEC60831", "appearance": "Box",
                "inside_dipping_material": "Polypropylene metallized film"},
         rows=[
             ("HBSM00415000753D", "Power Capacitor 7.5kVar", "415VAC/50Hz"),
             ("HBSM00415001203D", "Power Capacitor 12.5kVar", "415VAC/50Hz"),
             ("HBSM00415002503D", "Power Capacitor 25kVAr", "415VAC/50Hz"),
             ("HBSM00415005003Q", "Power Capacitor 50kVAr", "415VAC/50Hz"),
         ]),
    # --------------------------------------------------------------- page 26
    dict(page=26, section="Power Factor Controller - HJKL Series", series="HJKL",
         y=(605, 640), px=(475, 482),
         columns=["Reference No.", "Description", "Sampling Voltage"],
         keys=["MODEL", "DESC", "sampling_voltage"],
         fixed={},
         rows=[
             ("HJKL5CQ6S", "6 Stages", "380V/50Hz"),
             ("HJKL5CQ12S", "12 Stages", "380V/50Hz"),
         ]),
    # --------------------------------------------------------------- page 28
    dict(page=28, section="Variable Frequency Drives (VFD) - Basic & Expert Series",
         series="HAV", y=(625, 790), px=(478, 485),
         columns=["Reference No.", "Series", "Rated Motor"],
         keys=["MODEL", "vfd_series", "rated_motor"],
         fixed={"voltage_range": "380V(-15%)~440V(+10%)"},
         rows=[
             ("HAVBA4T0007G", "Basic", "1 HP / 0.75 KW"),
             ("HAVBA4T0015G", "Basic", "2 HP / 1.5 KW"),
             ("HAVBA4T0022G", "Basic", "3 HP / 2.2 KW"),
             ("HAVBA4T0040G", "Basic", "5 HP / 4 KW"),
             ("HAVBA4T0055G", "Basic", "7 HP / 5.5 KW"),
             ("HAVXS4T0055G0075P", "Expert", "10 HP / 7.5 KW"),
             ("HAVXS4T0075G0110P", "Expert", "15 HP / 11 KW"),
             ("HAVXS4T0110G0150P", "Expert", "20 HP / 15 KW"),
             ("HAVXS4T0150G0185P", "Expert", "25 HP / 18.5 KW"),
             ("HAVXS4T0185G0220P", "Expert", "30 HP / 22 KW"),
         ]),
    # --------------------------------------------------------------- page 29
    dict(page=29, section="Panel Meter - Analogue Ampere Meter", series="H96TA", rating_mode="ratio",
         y=(260, 495), px=(523, 530),
         columns=["Reference No.", "Description*"],
         keys=["MODEL", "RATING"],
         fixed={"specification": "96*96mm, 72*72mm", "response_time": "<=4s",
                "standard": "IEC 60051",
                "note_footnote": "*Analogue AC Ampere Meter with 5A CT Operated"},
         rows=[
             ("H96TA30", "30/5A"), ("H96TA50", "50/5A"), ("H96TA75", "75/5A"),
             ("H96TA100", "100/5A"), ("H96TA150", "150/5A"), ("H96TA200", "200/5A"),
             ("H96TA250", "250/5A"), ("H96TA300", "300/5A"), ("H96TA400", "400/5A"),
             ("H96TA600", "600/5A"), ("H96TA800", "800/5A"), ("H96TA1000", "1000/5A"),
             ("H96TA1600", "1600/5A"), ("H96TA5000", "5000/5A"),
         ]),
    dict(page=29, section="Panel Meter - Analogue AC Voltmeter", series="H96TV",
         y=(555, 595), px=(523, 530),
         columns=["Reference No.", "Description"],
         keys=["MODEL", "DESC"],
         fixed={"standard": "IEC 60051"},
         rows=[("H96TV500", "500V AC"), ("H96TV300", "300V AC")]),
    dict(page=29, section="Panel Meter - Analogue Frequency Meter", series="H96THZ",
         y=(645, 675), px=(524, 531),
         columns=["Reference No.", "Description"],
         keys=["MODEL", "DESC"],
         fixed={"standard": "IEC 60051"},
         rows=[("H96THZ01200", "200V AC - 45 - 55 Hz")]),
    dict(page=29, section="Panel Meter - Ammeters", series="HPAL",
         y=(715, 790), px=(524, 531),
         columns=["Reference No.", "Description"],
         keys=["MODEL", "DESC"],
         fixed={},
         rows=[("HPAL48X1250", "Digital Ammeter"), ("HPAL48X15", "Digital Ammeter"),
               ("HPAL96X1250", "Digital Ammeter"), ("HPAL96X15", "Digital Ammeter")]),
    # --------------------------------------------------------------- page 30
    dict(page=30, section="Panel Meter - Voltmeters", series="HPZL",
         y=(105, 140), px=(518, 525),
         columns=["Reference No.", "Description"],
         keys=["MODEL", "DESC"],
         fixed={},
         rows=[("HPZL48X1500", "Digital Voltmeter"), ("HPZL96X1500", "Digital Voltmeter")]),
    dict(page=30, section="Panel Meter - Frequency Meters", series="HPPL",
         y=(195, 235), px=(518, 525),
         columns=["Reference No.", "Description"],
         keys=["MODEL", "DESC"],
         fixed={},
         rows=[("HPPL48X1", "Digital Frequency Meter"), ("HPPL96X1", "Digital Frequency Meter")]),
    dict(page=30, section="Current Transformer", series="HLMK", rating_mode="ratio",
         y=(480, 780), px=(518, 525),
         columns=["Reference No.", "Current Ratio (A)", "Rated Load (VA)", "Diameter (mm)"],
         keys=["MODEL", "RATING", "rated_load_va", "diameter_mm"],
         fixed={"secondary_approval": "5A,1A", "maximum_voltage": "0.66kV",
                "class": "0.5 , 1.0 , 3.0", "short_time_thermal_current": "Ith=100Ih",
                "rated_security_coefficient": "FS<5", "standard": "IEC 60044-1"},
         rows=[
             ("HLMKP63030", "30/5", "5-3.75", "20"),
             ("HLMKP65030", "50/5", "5-3.75", "20"),
             ("HLMKP67530", "75/5", "5-3.75", "20"),
             ("HLMKP610030", "100/5", "5-3.75", "20"),
             ("HLMKP615030", "150/5", "5-3.75", "20"),
             ("HLMKP620040", "200/5", "5-3.75", "20"),
             ("HLMKP630040", "300/5", "5-3.75", "20"),
             ("HLMKP640050", "400/5", "10-3.75", "35"),
             ("HLMKP660080", "600/5", "10-3.75", "50"),
             ("HLMKP680080", "800/5", "10-3.75", "50"),
             ("HLMKP61000100", "1000/5", "10-3.75", "60"),
             ("HLMKP61200100", "1200/5", "15-3 75", "60"),
             ("HLMKP61500100", "1500/5", "15-3.75", "60"),
             ("HLMKP62000100", "2000/5", "15-3.75", "60"),
             ("HLMKP62500100", "2500/5", "20-3.75", "60"),
             ("HLMKP63000100", "3000/5", "20-3.75", "60"),
             ("HLMKP64000120", "4000/5", "20-3.75", "60"),
             ("HLMK65000120", "5000/5", "20 3 75", "60"),
         ]),
    # --------------------------------------------------------------- page 31
    dict(page=31, section="Control Signal - Push Button Switches", series="HLAY7",
         y=(315, 415), px=(520, 528),
         columns=["Reference No.", "Description"],
         keys=["MODEL", "DESC"],
         fixed={"ip_degree": "IP55",
                "specification": "AC-15:660V/1.1A, 380V/2.0A/220V/3.3A; DC-13:440V/0.25, 220V/0.5A, 110V/1A"},
         rows=[
             ("HLAY5EA42", "Red, OFF 1NC"),
             ("HLAY5EA31", "Green, ON 1NO"),
             ("HLAY5EW33M1L", "Green, 1NO LED 220V"),
             ("HLAY5EW34M2L", "Red, 1NC LED 220V"),
             ("HLAY5BE101", "Auxiliary Contact, 1NO"),
             ("HLAY5BE102", "Auxiliary Contact, 1NC"),
         ]),
    dict(page=31, section="Control Signal - Emergency Pushbutton (Mushroom)", series="HLAY7",
         y=(478, 498), px=(520, 528),
         columns=["Reference No.", "Description"],
         keys=["MODEL", "DESC"], fixed={"ip_degree": "IP55"},
         rows=[("HLAY5ES645", "Emergency OFF")]),
    dict(page=31, section="Control Signal - Selector Switch", series="HLAY7",
         y=(680, 715), px=(520, 528),
         columns=["Reference No.", "Description"],
         keys=["MODEL", "DESC"], fixed={"ip_degree": "IP55"},
         rows=[("HLAY5ED21", "Selector Switch (2 Position)"),
               ("HLAY5ED33", "Selector Switch (3 Position)")]),
    # --------------------------------------------------------------- page 32
    dict(page=32, section="Control Signal - Indication Lamps  220V AC", series="HLD11",
         y=(270, 340), px=(514, 521),
         columns=["Reference No.", "Description"],
         keys=["MODEL", "DESC"],
         fixed={"ip_degree": "IP65", "voltage": "220V AC"},
         rows=[("HLD1122D41M3", "Green"), ("HLD1122D41M4", "Red"),
               ("HLD1122D41M5", "Yellow"), ("HLD1122D41M8", "Blue")]),
    dict(page=32, section="Control Signal - Indication Lamps 24V DC", series="HLD11",
         y=(425, 490), px=(514, 521),
         columns=["Reference No.", "Description"],
         keys=["MODEL", "DESC"],
         fixed={"ip_degree": "IP65", "voltage": "24V DC"},
         rows=[("HLD1122D21B3", "Green"), ("HLD1122D21B4", "Red"),
               ("HLD1122D21B5", "Yellow"), ("HLD1122D21B8", "Blue")]),
    dict(page=32, section="Control Signal - Indication Lamps 110 V DC", series="HLD11",
         y=(575, 640), px=(514, 521),
         columns=["Reference No.", "Description"],
         keys=["MODEL", "DESC"],
         fixed={"ip_degree": "IP65", "voltage": "110 V DC",
                "note": "the PDF reprints the 24V DC reference numbers under the "
                        "110 V DC heading; kept exactly as printed"},
         rows=[("HLD1122D21B3", "Green"), ("HLD1122D21B4", "Red"),
               ("HLD1122D21B5", "Yellow"), ("HLD1122D21B8", "Blue")]),
    # --------------------------------------------------------------- page 33
    dict(page=33, section="Fuse - HRC Fuse", series="HRT16", rating_mode="text_amps",
         y=(225, 370), px=(521, 528),
         columns=["Reference No.", "Description"],
         keys=["MODEL", "RATING"],
         fixed={"rated_operation_voltage": "500/ 690V",
                "rated_working_current": "2 - 630A",
                "rated_breaking_capacity": "120kA - 500V"},
         rows=[
             ("HRT160032", "10A,16A, 25A, 32A Fuse Link"),
             ("HRT160063", "63A Fuse Link"),
             ("HRT1600125", "100A,125 A Fuse Link"),
             ("HRT1600160", "160A Fuse Link"),
             ("HRT161250", "250A Fuse Link"),
             ("HRT162315", "315A Fuse Link"),
             ("HRT162400", "400A Fuse Link"),
             ("HRT163500", "500A Fuse Link"),
             ("HRT163630", "630A Fuse Link"),
         ]),
    dict(page=33, section="Fuse - HRC Fuse Base", series="HRT16 Base (Resin)", rating_mode="text_amps",
         y=(520, 585), px=(526, 532),
         columns=["Reference No.", "Description"],
         keys=["MODEL", "RATING"],
         fixed={"base_type": "00, 1, 2, 3", "in": "160, 250, 400, 630"},
         rows=[("HRT1600ZS", "Base up to 160Amps"), ("HRT161ZS", "Base up to 250Amps"),
               ("HRT162ZS", "Base up to 400Amps"), ("HRT163ZS", "Base up to 630Amps")]),
    dict(page=33, section="Fuse - HRT18 Cylindrical Fuse", series="HRT18", rating_mode="text_amps",
         y=(705, 755), px=(522, 529),
         columns=["Reference No.", "Description"],
         keys=["MODEL", "RATING"],
         fixed={"cylindrical_fuse_type": "32, 63", "in": "2 - 63A"},
         rows=[("HRT1810382", "Cylindrical Fuse 2A"), ("HRT1810384", "Cylindrical Fuse 4A"),
               ("HRT18103810", "Cylindrical Fuse 10A")]),
    # --------------------------------------------------------------- page 34
    dict(page=34, section="Fuse - HRT18 Fuse Holder", series="HRT18 Fuse Holder", rating_mode="text_amps",
         y=(230, 262), px=(508, 515),
         columns=["Reference No.", "Description"],
         keys=["MODEL", "RATING"],
         fixed={"holder_type": "32X,  32, 63X, 63", "in": "32, 63",
                "rated_operating_voltage": "380V", "standard": "IEC 60269"},
         rows=[("HRT1832ZXB", "Fuse holder, 1 Pole, 32A, with indicator"),
               ("HRT1832Z", "Fuse holder, 1 Pole, 32A, without indicator")]),
    dict(page=34, section="Consumer Box - Full Plastic Consumer Box", series="HDPZ50",
         y=(535, 600), px=(509, 516),
         columns=["Reference No.", "Type"],
         keys=["MODEL", "ways_installation"],
         fixed={"installation": "Surface/ Flush", "standard": "IEC60439-1 IEC 60670",
                "note_footnote": "No multipliers/factors will be offered on Consumer Boxes."},
         rows=[
             ("HDPZ50PM6NF", "6 Way Surface Installation"),
             ("HDPZ50PM12NF", "12 Way Surface Installation"),
             ("HDPZ50PR18IP30F", "18 Way Surface Installation"),
             ("HDPZ50PR24IP30F", "24 Way Flush Installation"),
         ]),
    dict(page=34, section="Consumer Box - Metal Box and Plastic Cover Consumer Box",
         series="HDPZ50", y=(675, 755), px=(509, 516),
         columns=["Reference No.", "Type"],
         keys=["MODEL", "ways_installation"],
         fixed={"installation": "Surface/ Flush", "standard": "IEC60439-1 IEC 60670",
                "note_footnote": "No multipliers/factors will be offered on Consumer Boxes."},
         rows=[
             ("HDPZ50M8", "8 Way Surface Installation"),
             ("HDPZ50M12", "12 Way Surface Installation"),
             ("HDPZ50M16", "16 Way Surface Installation"),
             ("HDPZ50R16", "16 Way Flush Installation"),
             ("HDPZ50R24", "24 Way Flush Installation"),
         ]),
    # --------------------------------------------------------------- page 35
    dict(page=35, section="Prime Series - Flush Switches", series="Prime Series", rating_mode="text_amps",
         y=(640, 780), px=(474, 481),
         columns=["Reference No.", "Description"],
         keys=["MODEL", "DESC"],
         fixed={"range": "Wiring Devices - PRIME SERIES"},
         rows=[
             ("HWDYLK1", "10A 1 Gang 1 Way Switch"),
             ("HWDYLK2", "10A 1 Gang 2 Way Switch"),
             ("HWDYL2K1", "10A 2 Gang 1 Way Switch"),
             ("HWDYL3K1", "10A 3 Gang 1 Way Switch"),
             ("HWDYL4K1", "10A 4 Gang 1 Way Switch"),
             ("HWDY245K1", "20A Double Pole Switch with Neon"),
             ("HWDYLKB", "Bell Press"),
             ("HWDYLB", "Blank Plate"),
         ]),
    # --------------------------------------------------------------- page 36
    dict(page=36, section="Prime Series - Fan & Light Dimmers", series="Prime Series", rating_mode="text_amps",
         y=(195, 225), px=(475, 482),
         columns=["Reference No.", "Description"],
         keys=["MODEL", "DESC"], fixed={"range": "Wiring Devices - PRIME SERIES"},
         rows=[("HWDYLTs", "Fan Speed Controller"), ("HWDYLTg", "Light Dimmer Switch")]),
    dict(page=36, section="Prime Series - Socket Outlets", series="Prime Series", rating_mode="text_amps",
         y=(395, 480), px=(480, 486),
         columns=["Reference No.", "Description"],
         keys=["MODEL", "DESC"], fixed={"range": "Wiring Devices - PRIME SERIES"},
         rows=[
             ("HWDYLK1SW", "13A International Switch Socket (Neon)"),
             ("HWDYL2K12SW", "13A Duplex International Switch Socket (Neon)"),
             ("HWDYLSW2USB", "2 USB with Inetrnational Socket"),
             ("HWDYLK1SF131P", "13 Switch Socket Flat (Neon)"),
             ("HWDYLK1SC15", "15 Switch Socket"),
         ]),
    dict(page=36, section="Prime Series - Telecommunication Accessories", series="Prime Series", rating_mode="text_amps",
         y=(655, 755), px=(480, 487),
         columns=["Reference No.", "Description"],
         keys=["MODEL", "DESC"], fixed={"range": "Wiring Devices - PRIME SERIES"},
         rows=[
             ("HWDYLTel", "1 Gang Shuttered Telephone Outlet"),
             ("HWDY2Tel", "2 Gang Shuttered Telephone Outlet"),
             ("HWDYLTV", "1 Gang TV Outlet"),
             ("HWDYL2TV", "2 Gang TV Outlet"),
             ("HWDYLD", "1 Gang Data Outlet (Cat5e)"),
             ("HWDYL2D", "2 Gang Data Outlet (Cat5e)"),
         ]),
    # --------------------------------------------------------------- page 37
    dict(page=37, section="Prime V2 Series - Flush Switches", series="Prime V2 Series", rating_mode="text_amps",
         y=(640, 790), px=(487, 496),
         columns=["Reference No.", "Description"],
         keys=["MODEL", "DESC"], fixed={"range": "Wiring Devices - PRIME V2 SERIES"},
         rows=[
             ("HWDPS1G1W", "1 Gang 1 Way Switch"),
             ("HWDPS2G1W", "2 Gang 1 Way Switch"),
             ("HWDPS3G1W", "3 Gang 1 Way Switch"),
             ("HWDPS4G1W", "4 Gang 1 Way Switch"),
             ("HWDPS5G1W", "5 Gang 1 Way Switch"),
             ("HWDPS6G1W", "6 Gang 1 Way Switch"),
             ("HWDP20A", "20A Switch with Neon"),
             ("HWDPSDB", "Doorbell Switch"),
             ("HWDPBP3", "Blank Plate 3X3"),
         ]),
    # --------------------------------------------------------------- page 38
    dict(page=38, section="Prime V2 Series - Fan Controller", series="Prime V2 Series", rating_mode="text_amps",
         y=(210, 228), px=(493, 500),
         columns=["Reference No.", "Description"],
         keys=["MODEL", "DESC"], fixed={"range": "Wiring Devices - PRIME V2 SERIES"},
         rows=[("HWDPFS3", "Fan Speed Controller")]),
    dict(page=38, section="Prime V2 Series - Socket Outlets", series="Prime V2 Series", rating_mode="text_amps",
         y=(370, 505), px=(484, 492),
         columns=["Reference No.", "Description"],
         keys=["MODEL", "DESC"], fixed={"range": "Wiring Devices - PRIME V2 SERIES"},
         rows=[
             ("HWDPMFS", "13A, Multi Sw.Socket"),
             ("HWDP213ASSN", "13A, Duplex Multi"),
             ("HWDPMFSN2USB", "2USB with Multi Socket"),
             ("HWDP13ASSN", "13A, Sw.Socket Flat"),
             ("HWDP15SS", "15A Switch Socket"),
             ("HWDP2MFSN2USB", "2x5Pin Multi Sw.Sock+2USB"),
             ("HWDP2G1W22P", "2Gang Switch with 2Gang 2Pin Socket"),
             ("HWDP2G1W2P", "2Gang Switch with 1Gang 2Pin Socket"),
         ]),
    dict(page=38, section="Prime V2 Series - Telecommunication Accessories",
         series="Prime V2 Series", y=(660, 760), px=(482, 490),
         columns=["Reference No.", "Description"],
         keys=["MODEL", "DESC"], fixed={"range": "Wiring Devices - PRIME V2 SERIES"},
         rows=[
             ("HWDPTEL", "1Gang Telephone"),
             ("HWDP2TEL", "2Gang Telephone"),
             ("HWDPTV", "1Gang TV"),
             ("HWDP2TV", "2Gang TV"),
             ("HWDPCOM", "1Gang Data"),
             ("HWDP2COM", "2Gang Data"),
         ]),
]

# Pages with no priced product table (covers, dividers, index, marketing, back
# matter).  Skipped silently, as instructed.
NON_PRODUCT_PAGES = {1, 2, 3, 4, 5, 6, 10, 15, 24, 27, 39, 40}

# Every price-shaped token on a product page that is deliberately NOT a price.
# Pinned so that a future re-run cannot silently start ignoring a real price:
# the run fails if the leftover set stops matching this list exactly.
#   (page, text, reason)
EXPECTED_LEFTOVERS = [   # listed in top-to-bottom order within each page
    (11, "250", "Frame column figure, live text on the 4P row HDM3250S200B3XX"),
    (11, "250", "Frame column figure, live text on the 4P row HDM3250S250B3XX"),
    (11, "35", "ICU column figure, live text on the 4P row HDM3250S250B3XX"),
    (11, "21", "ICS column figure, live text on the 4P row HDM3250S250B3XX"),
    (11, "400", "Frame column figure, live text on the 4P row HDM3400F400B3XX"),
    (11, "50", "ICU column figure, live text on the 4P row HDM3400F400B3XX"),
    (11, "30", "ICS column figure, live text on the 4P row HDM3400F400B3XX"),
    (11, "630", "Frame column figure, live text on the 4P row HDM3630F630B3XX"),
    (11, "50", "ICU column figure, live text on the 4P row HDM3630F630B3XX"),
    (11, "30", "ICS column figure, live text on the 4P row HDM3630F630B3XX"),
    (11, "800", "Frame column figure, live text on the 4P row HDM3800F800B3XX"),
    (11, "70", "ICU column figure, live text on the 4P row HDM3800F800B3XX"),
    (11, "40", "ICS column figure, live text on the 4P row HDM3800F800B3XX"),
    (11, "06", "printed page number in the footer"),
    (14, "09", "printed page number in the footer"),
    (35, "1,200",
     "ghost: drawn inside a clipping path that sits entirely off-page "
     "(clip x=-615..-20), so it does not render; the Flush Switches row 1 price "
     "actually printed there is 230.  It is also 8pt left of the price column."),
]


# ---------------------------------------------------------------------------
# spec helpers
# ---------------------------------------------------------------------------
AMPS_RE = re.compile(r"^\s*([\d./ ]+?)\s*(?:Amps|Amp|A)\s*$", re.I)
TEXT_AMPS_RE = re.compile(r"(?<![\d.kK])(\d+(?:\.\d+)?)\s*A(?:mps?)?\b")
RANGE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(?:A)?\s*[-~]\s*(\d+(?:\.\d+)?)\s*(?:Amps?|A)?\s*$", re.I)


def _num(v):
    return float(v) if "." in v else int(v)


def rating_from_cell(text, mode):
    """Printed amperage text -> (rating, extras dict).  Nothing is invented:
    every number placed in specs is read out of the printed cell.

    mode:
      "amps_cell"  '16Amps'->'16A'; '6/10/16Amps'->'6/10/16A' + rating_amps list
                   (on these tables '/' separates alternative ratings of one
                   reference number, e.g. HDB3wL1C "1/2/50/63Amps")
      "range"      setting ranges, '0.63~1 A' / '1 - 1.6A' / '0.4-0.63A'
                   -> rating kept verbatim + rating_min_a / rating_max_a
      "ratio"      CT / meter primary-secondary ratios, '400/5A' -> ct_ratio
                   kept verbatim, rating_amps = [primary] only
      "text_amps"  amperage embedded in prose ('63A Fuse Link',
                   '13A, Sw.Socket Flat') -> every printed <n>A collected
    """
    t = norm(text)
    extras = {}
    if not t:
        return None, extras

    if mode == "ratio":
        m = re.match(r"^(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\s*A?$", t)
        if m:
            extras["ct_ratio"] = t
            extras["rating_amps"] = [_num(m.group(1))]
            return t, extras
        return t, extras

    if mode == "range":
        m = RANGE_RE.match(t)
        if m:
            extras["rating_min_a"] = _num(m.group(1))
            extras["rating_max_a"] = _num(m.group(2))
        return t, extras

    if mode == "text_amps":
        vals = [_num(v) for v in TEXT_AMPS_RE.findall(t)]
        if vals:
            extras["rating_amps"] = vals
            return ("/".join(str(v) for v in vals) + "A") if len(vals) > 1 \
                else (str(vals[0]) + "A"), extras
        return None, extras

    m = AMPS_RE.match(t)                       # "amps_cell"
    if m:
        body = m.group(1).replace(" ", "")
        if re.fullmatch(r"\d+(?:\.\d+)?(?:/\d+(?:\.\d+)?)*", body):
            extras["rating_amps"] = [_num(v) for v in body.split("/")]
        return body + "A", extras
    return t, extras


def spec_key_value(specs, key, value):
    value = norm(value)
    if not value or value == "-":
        return
    if key == "poles":
        m = re.match(r"^([1-4])\s*Pole$", value, re.I)
        specs["poles"] = (m.group(1) + "P") if m else value
    else:
        specs[key] = value


def build_row(tbl, cells, price, note=None):
    columns, keys = tbl["columns"], tbl["keys"]
    mode = tbl.get("rating_mode", "amps_cell")
    specs = {}
    model = None
    desc_cells = []
    for col, key, val in zip(columns, keys, cells):
        val_n = norm(val)
        if key == "MODEL":
            model = val_n
            continue
        if val_n:
            desc_cells.append(val_n)
        if key is None or not val_n:
            continue
        if key == "RATING":
            rating, extras = rating_from_cell(val_n, mode)
            if rating:
                specs["rating"] = rating
                if rating != val_n:
                    specs["rating_printed"] = val_n
                specs.update(extras)
        elif key == "DESC":
            if mode == "text_amps":     # amperage printed inside the description
                rating, extras = rating_from_cell(val_n, "text_amps")
                if rating and "rating" not in specs:
                    specs["rating"] = rating
                    specs["rating_printed"] = val_n
                    specs.update(extras)
        elif key == "TYPE_POLE_RATING":
            # printed as e.g. "2 Pole/ 20Amps" in one cell
            m = re.match(r"^([1-4])\s*Pole/\s*(.+)$", val_n, re.I)
            if m:
                specs["poles"] = m.group(1) + "P"
                rating, extras = rating_from_cell(m.group(2), "amps_cell")
                specs["rating"] = rating
                specs["rating_printed"] = val_n
                specs.update(extras)
            else:
                specs["type"] = val_n
        else:
            spec_key_value(specs, key, val_n)

    for k, v in tbl.get("fixed", {}).items():
        specs.setdefault(k, v)
    specs["series"] = tbl["series"]
    if note:
        specs["note"] = note

    description = " - ".join([tbl["section"], model] + desc_cells)
    raw = " | ".join(str(c) for c in cells) + " | " + (str(price) if price is not None else "(no price printed)")
    return {
        "page": tbl["page"],
        "brand": BRAND,
        "section": tbl["section"],
        "model": model,
        "description": description,
        "price_pkr": price,
        "specs": specs,
        "_raw": raw,
    }


# ---------------------------------------------------------------------------
# table processing
# ---------------------------------------------------------------------------
def process_plain(tbl, toks, rows_out, skipped):
    y_lo, y_hi = tbl["y"]
    x_lo, x_hi = tbl["px"]
    found = sorted(
        (t for t in toks if y_lo <= t["y0"] < y_hi and x_lo <= t["x1"] <= x_hi),
        key=lambda t: t["y0"],
    )

    por = set(tbl.get("por", []))
    merged = tbl.get("merged", [])
    merged_of = {}
    for grp in merged:
        for i in grp:
            merged_of[i] = grp[0]

    # rows that must consume one printed price token
    consumers = [i for i in range(len(tbl["rows"]))
                 if i not in por and merged_of.get(i, i) == i]
    if len(found) != len(consumers):
        raise RuntimeError(
            "page %d %r: expected %d printed price(s) in y=%s x1=%s, found %d (%s) "
            "- layout drifted, refusing to guess"
            % (tbl["page"], tbl["section"], len(consumers), tbl["y"], tbl["px"],
               len(found), [t["text"] for t in found]))

    price_by_row = {}
    for idx, tok in zip(consumers, found):
        price_by_row[idx] = tok["value"]
        tok["used"] = True

    for i, cells in enumerate(tbl["rows"]):
        note = None
        if i in por:
            price = None
            note = POR_NOTE
        elif i in merged_of:
            price = price_by_row[merged_of[i]]
            note = ("price read from one cell visually merged across reference "
                    "numbers %s; the PDF prints it once for the whole block"
                    % ", ".join(tbl["rows"][j][0] for j in
                                next(g for g in merged if i in g)))
        else:
            price = price_by_row[i]
        rows_out.append(build_row(tbl, cells, price, note))


def process_matrix(tbl, toks, rows_out, skipped):
    for r, (row_label, y_lo, y_hi) in enumerate(tbl["rowbands"]):
        for c, (col_header, x_lo, x_hi) in enumerate(tbl["cols"]):
            kind = tbl["cells"][r][c]
            raw = "%s | %s | %s" % (tbl["section"], row_label, col_header)
            if kind == "-":
                skipped.append({"page": tbl["page"], "raw": raw + " | -",
                                "reason": 'matrix cell prints "-" (accessory not '
                                          "offered for this MCCB frame) - not a product"})
                continue
            if kind == "por":
                price = None
                note = POR_NOTE
            else:
                hits = [t for t in toks
                        if y_lo <= t["y0"] < y_hi and x_lo <= t["x1"] <= x_hi]
                if len(hits) != 1:
                    raise RuntimeError(
                        "page %d matrix cell (%s / %s): expected exactly 1 price "
                        "token in y=%s x1=%s, found %d (%s)"
                        % (tbl["page"], row_label, col_header, (y_lo, y_hi),
                           (x_lo, x_hi), len(hits), [t["text"] for t in hits]))
                price = hits[0]["value"]
                hits[0]["used"] = True
                note = None
            specs = {
                "accessory": row_label,
                "for_mccb": col_header,
                "series": tbl["series"],
            }
            if note:
                specs["note"] = note
            specs["matrix_note"] = (
                "price taken from the printed accessory price matrix: the row is the "
                "accessory type, the column head is the MCCB reference it fits; the "
                "PDF prints no separate catalogue number for the accessory itself")
            rows_out.append({
                "page": tbl["page"],
                "brand": BRAND,
                "section": tbl["section"],
                "model": col_header,
                "description": "%s - %s for %s" % (tbl["section"], row_label, col_header),
                "price_pkr": price,
                "specs": specs,
                "_raw": raw + " | " + (str(price) if price is not None else "POR*"),
            })


# ---------------------------------------------------------------------------
def main():
    doc = fitz.open(PDF_PATH)
    n_pages = doc.page_count
    toks_by_page = {i + 1: price_tokens(doc[i]) for i in range(n_pages)}

    rows_out, skipped = [], []
    for tbl in TABLES:
        toks = toks_by_page[tbl["page"]]
        if tbl.get("kind") == "matrix":
            process_matrix(tbl, toks, rows_out, skipped)
        else:
            process_plain(tbl, toks, rows_out, skipped)

    # ---------------------------------------------------------------- sanity
    kept = []
    for r in rows_out:
        v = r["price_pkr"]
        if v is not None and (v < 10 or v > 10_000_000):
            skipped.append({"page": r["page"], "raw": r["_raw"],
                            "reason": "sanity: price %s outside 10..10,000,000" % v})
            continue
        kept.append(r)
    rows_out = kept

    # ------------------------------------------------------------- duplicates
    seen = {}
    deduped = []
    for r in rows_out:
        key_specs = {k: v for k, v in r["specs"].items()
                     if k not in ("note", "matrix_note")}
        key = (r["model"], json.dumps(key_specs, sort_keys=True))
        if key in seen and seen[key]["price_pkr"] == r["price_pkr"]:
            skipped.append({"page": r["page"], "raw": r["_raw"],
                            "reason": "duplicate of identical row (same model, same "
                                      "specs, same price)"})
            continue
        seen[key] = r
        deduped.append(r)
    rows_out = deduped

    prices = [r["price_pkr"] for r in rows_out if r["price_pkr"] is not None]

    # ------------------------------------------------------------- validation
    p("=== coverage: visible price tokens on the page vs prices consumed/emitted ===")
    p("  (leftover = visible price-shaped token on a product page that no table"
      " claimed; each one is listed so it can be eyeballed)")
    grand_tok = grand_used = grand_row = 0
    leftovers = []
    for pg in range(1, n_pages + 1):
        if pg in NON_PRODUCT_PAGES:
            continue
        toks = toks_by_page[pg]
        n_tok = len(toks)
        n_used = sum(1 for t in toks if t.get("used"))
        n_row = sum(1 for r in rows_out if r["page"] == pg and r["price_pkr"] is not None)
        grand_tok += n_tok
        grand_used += n_used
        grand_row += n_row
        rest = [t for t in toks if not t.get("used")]
        leftovers += [(pg, t) for t in rest]
        p("  page %2d: visible price-shaped tokens=%3d  consumed=%3d  leftover=%d  "
          "priced rows emitted=%3d" % (pg, n_tok, n_used, len(rest), n_row))
    p("  TOTAL   : tokens=%d  consumed=%d  priced rows=%d "
      "(rows > consumed only where a merged cell is shared, p18 HFT6)"
      % (grand_tok, grand_used, grand_row))
    got = sorted((pg, t["text"]) for pg, t in leftovers)
    want = sorted((pg, txt) for pg, txt, _ in EXPECTED_LEFTOVERS)
    if got != want:
        raise RuntimeError(
            "unclaimed price-shaped tokens changed.\n  expected: %s\n  got:      %s\n"
            "Every leftover must be known non-price page furniture; refusing to "
            "publish prices while an unexplained number is floating on a product page."
            % (want, got))
    p("  leftover tokens (all pinned as non-price page furniture):")
    reasons = {}
    for pg, txt, why in EXPECTED_LEFTOVERS:
        reasons.setdefault((pg, txt), []).append(why)
    for pg, t in sorted(leftovers, key=lambda pt: (pt[0], pt[1]["y0"])):
        why = reasons[(pg, t["text"])].pop(0)
        p("    page %2d  %-8s at x=%.1f-%.1f y=%.1f  <- %s"
          % (pg, t["text"], t["x0"], t["x1"], t["y0"], why))

    p("=== price sanity ===")
    p("  min=%d  median=%s  max=%d" % (min(prices), statistics.median(prices), max(prices)))

    p("=== 10 random parsed rows with their source line ===")
    random.seed(11)
    for r in random.sample(rows_out, 10):
        p("  p%-2d %-20s %10s  %s" % (r["page"], r["model"], r["price_pkr"], r["description"]))
        p("       raw: %s" % r["_raw"])
        p("       specs: %s" % json.dumps(r["specs"], ensure_ascii=False))

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
    p("  %s" % out["stats"])
    p("  written: %s" % OUT_PATH)


if __name__ == "__main__":
    main()
