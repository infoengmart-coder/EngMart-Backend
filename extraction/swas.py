"""
Faithful extractor for "SWAS PL Dec-2023 dated 11-12-23 Linked.pdf"
(SWAS Total Electrical Solutions, Pakistan - 93 pages, 89 product pages).

LAYOUT
------
Pages 1-2  : cover + general terms (non-product, skipped silently)
Pages 3-4  : "I N D E X" - one line per price-list section:
                 11-12-2023 PL - 18 LS MOULDED CASE CIRCUIT BREAKERS 3 POLE 20
             i.e. DATE | PL No. | BRAND | DESCRIPTION | printed page.
             The printed page number is always (pdf page - 2).  This index is
             the ONLY place the manufacturer of each page is named, so brand is
             taken from it (never guessed) and cross-checked against the
             "PL - n" stamp printed on the page itself.
Pages 5-93 : one price list per page (PL-1 .. PL-89).  Every page is a ruled
             table; pdfplumber's find_tables() returns row bands that coincide
             exactly with the product rows, which is what makes segmentation
             reliable: a price that is vertically centred over a two-line
             description (very common - "AR22-FOR-10G ... / 2,000/= / GREEN
             COLOUR") lands inside the same ruled row as its model, so it can
             never be attached to a neighbouring product.

ROW GRAMMAR
-----------
A priced line ends with a rupee token: "34,000/=", "6,500 /=", "1,400/ =",
"9,500/-", "1,600,000=-" (typo for /=) or the words "On Request".
Columns are recovered geometrically: the printed column captions
("MODEL", "RATINGS", "THERMAL TRIP", "OPERATIONAL", "(Rupees)" ...) are used as
x-anchors, so the MODEL cell is read as the words that fall inside the model
column - this is what lets multi-word catalogue numbers ("LC1 - D09",
"ABS103c - FMU", "iC 60 N", "NS 800 N", "MC-12b DC", "ZeroVAR PCS 12",
"GROUP: 00") come out exactly as printed instead of being guessed at by
tokenising.  Three fallbacks, in order, cover the tables that print no MODEL
caption:
  1. a ruled table split in two by a section row inherits the previous table's
     column, but only when the two tables' x-profiles agree (>=60% of column
     starts) - this is what stops an accessory table from inheriting the
     breaker table's model column;
  2. tables with no captions at all (pages 62-65, 70-74) get the column from the
     first horizontal gap wider than 14pt, accepted only if most rows agree;
  3. otherwise no model column exists, and the model is taken - in this order -
     from an inline "MODEL: xxx" label, a quoted accessory code ("UVR", "MX"),
     a catalogue code embedded in the description ("GV-AE11"), or the leading
     printed code on DESCRIPTION-column pages ("iPF40", "RH99M").
A cell that does not look like a catalogue number (too many words, or built
from descriptive words such as SHUNT / HANDLE / ROTARY) is refused, and the row
is emitted with model="" plus a specs.note - the storefront gets an honest
blank rather than a description masquerading as a part number.  74 of the 1220
rows genuinely print no catalogue number (RCCB descriptions on page 49,
capacitor kVAr ratings on page 81, industrial plugs on page 89, panel-meter
types on page 90, DOL/star-delta starters on pages 39-40, accessory lines).

AMPERE LADDERS (the point of this extractor)
--------------------------------------------
Breaker pages print a clean ampere ladder under a series heading and a
pole-count sub-header, e.g. page 47:
    COMPACT NSX SERIES / 4 - POLE ADJUSTABLE THERMAL TRIP - STANDARD MODELS
    16 AMPS 12.5 - 16 A NSX100F 36 KA 100 % 62,000/=
Each such line becomes ONE row with
    specs = {rating, rating_values, thermal_trip, breaking_capacity, icu_ics,
             poles, series, ...}
specs.rating is the amperage exactly as printed; specs.rating_values explodes a
multi-amp cell ("15, 20, 30, 40 & 50 AMPS.") into ["15A","20A","30A","40A","50A"]
for the storefront dropdown WITHOUT inventing extra priced rows - the PDF prints
one price for that whole cell, so one row is emitted.
Amperage is read from four printed places, never inferred from a model number:
  * the leading RATINGS cell (breaker/MCB/MCCB pages);
  * the RATINGS cell that follows the model on the air-circuit-breaker pages;
  * the "OPERATIONAL CURRENT / AMPERES" (AC-3) column on the contactor pages
    11, 33, 34, 55-57 and 59 - flagged as specs.rating_column;
  * an amperage printed mid-row ("RCCB D.P 63 AMPS ( 30 mA ... )", page 49).
Pages 91-93 are current transformers: the printed ratio goes to specs.ct_ratio
and its primary current to specs.rating.

PRICES
------
Every emitted price is read from that row's own price cell.  Nothing is
averaged, interpolated or carried.  Two printed typos are read as typography,
each flagged in specs.note and listed here:
  * page 46, NS1250N 1250 A : printed "480.000/=" (decimal point where every
    other price on the page uses a thousands comma) -> 480000.
  * page 52, NW25H2 3-pole  : printed "1,600,000=-" (=- instead of /=) -> 1600000.
"On Request" / "ON REQUEST" -> price_pkr = null + specs.note.

DITTO MARKS
-----------
Several tables repeat a value with a ditto mark (") in the model column -
pages 17, 35, 36, 39, 91, 92, 93.  A ditto is a *visually merged* cell, so the
model (never the price) is carried down from the row above and the row carries
specs.note recording that it was printed as a ditto.  Every price on those rows
is still read from that row's own price cell.

BRANDS
------
Brand is the manufacturer named in the index for that page, not the supplier:
LS 353 rows, SCHNEIDER 293, FUJI 203, TELEMECANIQUE 188, HANYOUNG 68, FICO 38,
KRK 22, BEMIS 19, SHIZUKI 10, VOLTRAN 10, EKON 6, E-POWER 4, SEW 4, BRETER 2.
Printed page 88 is the one page the index gives two brands (SEW panel meters +
BRETER cam switches); the BRETER block is named on the page itself
("'BRETER' BRAND CAM SWITCHES") and is switched on that heading.  SUPPLIER
("SWAS") is only a fallback for a page the index leaves without a brand token.

MULTI-PRICE ROWS
----------------
Eight pages print accessory / pole-variant tables where ONE ruled row carries
several prices under several column captions (e.g. page 26
"FOR TS400/630N - MOP 3  6,500/=  21,000/=  12,000/=  140,000/=" under
AUXILIARY SWITCH | UVT | SHUNT TRIP | MOTOR).  Those are expanded into one row
per printed price using the column captions pinned in MULTI_PRICE below; every
caption set is ASSERTED against the caption text actually extracted from the
page, so the script fails loudly rather than mislabelling a price.  A
multi-price row on any page not pinned here is routed to "skipped" with its raw
text - never guessed.

Run:  venv/Scripts/python.exe extraction/swas.py
Writes: extraction/out/swas.json
Debug: set SWAS_AUDIT=<path> to also dump every parsed row beside its raw line.
"""

import json
import os
import random
import re
import statistics

import pdfplumber

PDF_PATH = r"C:/Users/AWCD/Desktop/client/engmart (2)/product-details/SWAS PL Dec-2023 dated 11-12-23 Linked.pdf"
OUT_PATH = r"C:/Users/AWCD/Desktop/client/engmart (2)/backend/extraction/out/swas.json"

SUPPLIER = "SWAS"
FIRST_PRODUCT_PAGE = 5
PAGE_OFFSET = 2  # printed page number + 2 == pdf page number


def p(s=""):
    print(str(s).encode("ascii", "replace").decode())


def norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


# --------------------------------------------------------------------------- #
# price tokens
# --------------------------------------------------------------------------- #
# 12,500/=   6,500 /=   1,400/ =   9,500/-   1,600,000=-   480.000/=
PRICE_RX = re.compile(r"(\d[\d,]*(?:\.\d{3})?)\s*(?:/\s*=|/\s*-|=\s*-)")
ONREQ_RX = re.compile(r"\bon\s*request\b", re.I)
ANY_PRICE_RX = re.compile(PRICE_RX.pattern + r"|" + ONREQ_RX.pattern, re.I)

# footer / boiler-plate lines that are never products (skipped silently)
NOISE_RX = re.compile(
    r"^(I\s*N\s*D\s*E\s*X|P\s*R\s*I\s*C\s*E\s*L\s*I\s*S\s*T|P\s*RI\s*C\s*E\s*L\s*I\s*S\s*T)$"
    r"|^\d+\.\s*(This list is subject|The prices in the list|Discount/Multipliers)"
    r"|^\d{1,3}$"
    r"|^\d{2}-\d{2}-+\s?\d{4}$|^\d{2}-\d{2}-\s?\d{4}$|^11-12-\s*2023$"
    r"|^PL\s*[-–]?\s*\d+$"
    r"|A QUALITY PRODUCT LINE|LIMITLESS SATISFACTION|WORLD LEADER IN CONTROL",
    re.I,
)


def parse_price(text):
    """Return (value, kind). kind in {'num','onrequest',None}."""
    if ONREQ_RX.search(text):
        return None, "onrequest"
    hits = PRICE_RX.findall(text)
    if not hits:
        return None, None
    raw = hits[-1]
    return int(raw.replace(",", "").replace(".", "")), "num"


# --------------------------------------------------------------------------- #
# geometry helpers
# --------------------------------------------------------------------------- #
def page_lines(page, tol=3.0):
    """Words clustered into visual lines (list of dicts with words/text/top/bottom)."""
    ws = sorted(page.extract_words(), key=lambda w: (w["top"], w["x0"]))
    buckets = []
    for w in ws:
        if buckets and abs(w["top"] - buckets[-1][0]) <= tol:
            buckets[-1][1].append(w)
        else:
            buckets.append([w["top"], [w]])
    out = []
    for top, group in buckets:
        group.sort(key=lambda w: w["x0"])
        out.append(
            {
                "top": top,
                "bottom": max(w["bottom"] for w in group),
                "mid": (top + max(w["bottom"] for w in group)) / 2.0,
                "words": group,
                "text": norm(" ".join(w["text"] for w in group)),
            }
        )
    return out


def build_blocks(page, lines):
    """
    Group lines into blocks using the ruled table row bands.
    Returns list of dicts: {table, row, lines, top}.  Lines outside every table
    become their own single-line block with table=None.
    """
    bands = []  # (table_index, row_index, top, bottom)
    tables = page.find_tables()
    for ti, t in enumerate(tables):
        for ri, row in enumerate(t.rows):
            bands.append((ti, ri, row.bbox[1], row.bbox[3]))
    blocks = {}
    order = []
    for L in lines:
        key = None
        for ti, ri, top, bot in bands:
            if top - 1.0 <= L["mid"] <= bot + 1.0:
                key = (ti, ri)
                break
        if key is None:
            key = ("free", id(L))
        if key not in blocks:
            blocks[key] = {"table": key[0] if key[0] != "free" else None,
                           "row": key[1] if key[0] != "free" else None,
                           "lines": [], "top": L["top"]}
            order.append(key)
        blocks[key]["lines"].append(L)
    return [blocks[k] for k in order], tables


# --------------------------------------------------------------------------- #
# column anchors
# --------------------------------------------------------------------------- #
MODEL_LABELS = {"MODEL", "MODELS", "MODEL:", "TYPE"}
# printed captions that occupy the leftmost column INSTEAD of a model column
LEFT_CAPTIONS = {"DESCRIPTION", "DESCERIPTION", "RATINGS", "RATING",
                 "MOTOR-OUTPUT", "H.P", "SIZE"}


def caption_column(header_lines, labels):
    """
    From the printed column captions work out the x-range of the column whose
    caption is one of `labels`.  Returns (lo, hi) or None.  hi is the mid-point
    between the right edge of the caption and the left edge of the next caption
    to its right, which is what keeps e.g. page 10's data column "1250"@175 out
    of the model cell even though its caption "RATINGS" starts at 181.
    """
    anchors = []
    for L in header_lines:
        for w in L["words"]:
            anchors.append((w["x0"], w["x1"], w["text"]))
    if not anchors:
        return None
    want = {l.strip(":") for l in labels}
    hit = None
    for x0, x1, t in anchors:
        if t.upper().strip(":.") in want:
            if hit is None or x0 < hit[0]:
                hit = (x0, x1)
    if hit is None:
        return None
    right = [(x0, t) for x0, x1, t in anchors if x0 > hit[1] + 2]
    if not right:
        return (hit[0] - 6.0, 1e9)
    nx, nt = min(right)
    if nt.strip("()").upper() in {"RUPEES", "PRICE", "UNIT"}:
        # the only caption to the right is the price caption, so the column's
        # right edge is not printed anywhere - signal "unknown" to the caller
        return (hit[0] - 6.0, 1e9)
    return (hit[0] - 6.0, (hit[1] + nx) / 2.0)


def model_column(header_lines):
    return caption_column(header_lines, MODEL_LABELS)


def geometric_model_column(priced_lines):
    """
    Fallback for tables that print no column captions at all (pages 62-65, 70,
    71, 72, ...).  The model cell is the leading word-cluster of each row; the
    boundary is the first horizontal gap wider than GAP_MIN, and it must agree
    across most rows of the table or the column is refused.
    """
    GAP_MIN = 14.0
    if len(priced_lines) < 2:
        return None      # one row cannot establish a column boundary
    bounds = []
    for L in priced_lines:
        ws = L["words"]
        for i in range(len(ws) - 1):
            gap = ws[i + 1]["x0"] - ws[i]["x1"]
            if gap >= GAP_MIN:
                bounds.append((ws[i]["x1"] + ws[i + 1]["x0"]) / 2.0)
                break
    if len(bounds) < max(1, int(0.6 * len(priced_lines))):
        return None
    med = statistics.median(bounds)
    agree = sum(1 for b in bounds if abs(b - med) <= 8.0)
    if agree < 0.6 * len(priced_lines):
        return None
    return (0.0, med)


def snap_column_left(col, priced_lines):
    """
    Column captions are not always flush with their data: on page 33 the caption
    "MODEL" starts at x=131 while the cell text "MC-12b" starts at x=123.  Nudge
    the left edge out to where the data of that column actually starts, but only
    when a majority of the table's rows agree, so a stray token cannot drag the
    boundary into the previous column.
    """
    if not col or not priced_lines:
        return col
    lo, hi = col
    minima = []
    for L in priced_lines:
        xs = [w["x0"] for w in L["words"] if lo - 16.0 <= w["x0"] < hi]
        if xs:
            minima.append(min(xs))
    if len(minima) < max(1, int(0.6 * len(priced_lines))):
        return col
    med = statistics.median(minima)
    return (min(lo, med - 0.5), hi)


def profile_of(lines):
    return {int(round(w["x0"] / 2.0)) for L in lines for w in L["words"]}


def profiles_match(a, b):
    if not a or not b:
        return False
    return len(a & b) / float(len(b)) >= 0.6


# --------------------------------------------------------------------------- #
# per-page pins
# --------------------------------------------------------------------------- #
# Pages whose MODEL column has no printed caption: the model sits in a fixed
# x-band.  Each is asserted against MODEL_ASSERT below.
MODEL_X_OVERRIDE = {
    91: (320.0, 470.0),   # RLC current transformers - captions are RATINGS/(Rupees) only
    92: (275.0, 470.0),   # ELC
    93: (340.0, 470.0),   # SLC (a second ditto column sits at x=232 - the shape column)
}
MODEL_ASSERT = {
    91: re.compile(r'^(RLC\s*[-–]\s*\d+|["“”]+)$'),
    92: re.compile(r'^(ELC\s*[-–]\s*\d+|["“”]+)$'),
    93: re.compile(r'^(SLC\s*[-–]\s*\d+K?|["“”]+)$'),
}

# Multi-price rows: printed column captions, left to right, one per price.
# assert_text must appear in the page's raw text (guards against drift).
MULTI_PRICE = {
    8: {
        "assert": "RATINGS SWITCH EXT. HANDLE UVT / SHUNT TRIP AUX./ALARM",
        # the middle cell prints two prices separated by "/" under "UVT / SHUNT TRIP"
        "labels": ["SWITCH EXT. HANDLE", "UVT", "SHUNT TRIP", "AUX./ALARM"],
        "split_slash": True,
        "left_is_model": False,   # the left cell is a RATINGS range, not a model
        "section": "ACCESSORIES FOR MCCB'S",
    },
    26: {
        "assert": "AUXILIARY UVT SHUNT TRIP MOTOR",
        "labels": ["AUXILIARY SWITCH", "UVT (415V AC)", "SHUNT TRIP (220 VAC)", "MOTOR (220 VAC)"],
        "left_is_model": True,    # the left cell is the printed MODELS column
        "section": "ACCESSORIES FOR ADJUSTABLE MCCBs",
    },
    31: {
        "assert": "RATINGS AUXILIARY SWITCH UVT (415V AC)",
        "labels": ["AUXILIARY SWITCH", "UVT (415V AC)", "SHUNT TRIP (220 VAC)"],
        "left_is_model": False,   # the left cell is a RATINGS range
        "section": "ACCESSORIES FOR MCCBs",
    },
    32: {
        "assert": "3 POLE 4 POLE",
        "labels": ["3 POLE", "4 POLE"],
        "poles": ["3P", "4P"],
        "left_is_model": True,
    },
    47: {
        "assert": "OPTIONAL ACCESSORIES NSX 100 / 250 NSX 400/630 NS800",
        "labels": ["NSX 100 / 250", "NSX 400/630", "NS800 - NS1600"],
        "left_is_model": False,   # the left cell is a DESCRIPTION
        "section": "OPTIONAL ACCESSORIES FOR MOULDED CASE CIRCUIT BREAKERS",
    },
    48: {
        "assert": "OPTIONAL ACCESSORIES EZC100 EZC250",
        "labels": ["EZC100", "EZC250"],
        "left_is_model": False,   # the left cell is a DESCRIPTION
        "section": "OPTIONAL ACCESSOREIS FOR EASY PACT MCCB'S",
    },
    51: {
        "assert": "Icu=Ics=Icw 3 POLE 4 POLE",
        "labels": ["3 POLE", "4 POLE"],
        "poles": ["3P", "4P"],
        "left_is_model": True,
    },
    52: {
        "assert": "Icu=Ics=Icw 3 POLE 4 POLE",
        "labels": ["3 POLE", "4 POLE"],
        "poles": ["3P", "4P"],
        "left_is_model": True,
    },
}

# Printed typos read as typography (documented in the module docstring).
PRICE_TYPO_NOTE = {
    "480.000": 'price printed as "480.000/=" (decimal point where every other '
               "price on this page uses a thousands comma) - read as 480,000 PKR",
    "1,600,000": 'price printed as "1,600,000=-" ("=-" instead of "/=") - read as 1,600,000 PKR',
}

# page 90 carries two index brands (SEW meters + BRETER cam switches); the
# BRETER block is named on the page itself.
BRAND_SECTION_OVERRIDE = {
    90: [("BRETER", re.compile(r"BRETER", re.I))],
}

SERIES_OVERRIDES = [
    (r"^BW\s*\d", "BW"), (r"^BX\s*-", "BX"), (r"^SA\s*-", "SA"),
    (r"^EW\d", "EW"), (r"^BCL", "BCL"), (r"^BT3", "BT3"),
    (r"^SC\s*-", "SC"), (r"^SH\s*-", "SH"), (r"^SZ\s*[-–]", "SZ"),
    (r"^TR-", "TR"), (r"^TK-", "TK"), (r"^TP\d", "TP"),
    (r"^MS4S", "MS4S"), (r"^AR22", "AR22"), (r"^AR30", "AR30"),
    (r"^DR22", "DR22"), (r"^DR30", "DR30"),
    (r"^AB[SNH]\s*[-–]?\s*\d", "AB"), (r"^TS\d", "TS"), (r"^TD\d", "TD"),
    (r"^MMS", "MMS"), (r"^BK[JNH]", "BK"), (r"^BS\s*[-–]\s*32", "BS"),
    (r"^RKN", "RKN"), (r"^BK\d0S", "BK-T2"),
    (r"^A[NS]-\d", "AN/AS"), (r"^MC-", "MC"), (r"^UA\s*[-–]", "UA"),
    (r"^AU\s*[-–]", "AU"), (r"^UR\s*[-–]", "UR"), (r"^AR\s*[-–]\s*\d", "AR"),
    (r"^MT-", "MT"), (r"^LSLV", "LSLV"), (r"^SV\d", "SV"),
    (r"^M\s*[-–]\s*\d$", "MOP-M"),
    (r"^iC\s*\d", "iC"), (r"^NSX", "NSX"), (r"^NS\s*\d", "NS"),
    (r"^EZC", "EZC"), (r"^CVS", "CVS"), (r"^NW\d", "NW"),
    (r"^DM\d", "DM"), (r"^PM\d", "PM"), (r"^VPL", "VPL"),
    (r"^LC1", "LC1"), (r"^CAD", "CAD"), (r"^LA[1DG]", "LA"),
    (r"^LAE", "LAE"), (r"^GV\d", "GV"), (r"^GV-", "GV"),
    (r"^LRD", "LRD"), (r"^RE\d", "RE"), (r"^RSL", "RSL"), (r"^RM\d", "RM"),
    (r"^RXM", "RXM"), (r"^RXZ", "RXZ"), (r"^EOCR", "EOCR"), (r"^LT4", "LT4"),
    (r"^XB\d", "XB"), (r"^ATS\d", "ATS"), (r"^ATV", "ATV"),
    (r"^HY", "HY"), (r"^KX", "KX"), (r"^NX", "NX"), (r"^HSR", "HSR"),
    (r"^LM3", "LM3"), (r"^BS6", "BS6"), (r"^MA4", "MA4"), (r"^GR\s*\d", "GR"),
    (r"^AR[FESKXP]-", "AR-HY"), (r"^L-\d", "L"), (r"^M-\d", "M"),
    (r"^ZCN", "ZCN"), (r"^HE\d", "HE"), (r"^DPS", "DPS"), (r"^UP\d", "UP"),
    (r"^RF", "RF"), (r"^RG", "RG"), (r"^MS-\d+Q", "MS-Q"),
    (r"^KM[AVM]", "KM"), (r"^KD[AV]", "KD"), (r"^S?KAD", "KAD"),
    (r"^SFMK", "SFMK"), (r"^SZR", "SZR"), (r"^KZR", "KZR"), (r"^SSR", "SSR"),
    (r"^KNA", "KNA"), (r"^KPC", "KPC"), (r"^ZeroVAR", "ZeroVAR"),
    (r"^ECM", "ECM"), (r"^SPM", "SPM"), (r"^GROUP", "NH FUSE"),
    (r"^RLC", "RLC"), (r"^ELC", "ELC"), (r"^SLC", "SLC"),
    (r"^HH\s*\d", "HH"), (r"^FW-", "FW"), (r"^SW-", "SW"), (r"^K244", "K244"),
    (r"^HXV", "HXV"), (r"^iPF", "iPF"), (r"^RH99", "RH99"),
    (r"^DOMAE", "DOMAE"), (r"^EZ9", "EZ9"), (r"^GMP", "GMP"),
    (r"^[GM]MR?\s*[-–]\s*8", "MR-8"), (r"^FX\s*[-–]", "FX"), (r"^LX\s*[-–]", "LX"),
]
SERIES_OVERRIDES = [(re.compile(rx), s) for rx, s in SERIES_OVERRIDES]

SERIES_HEADING_RX = re.compile(r"^(.*?)\s*[-–]?\s*SER(?:IES|EIS)\b", re.I)


def series_for(model, heading):
    m = norm(model)
    if not m:
        return heading or ""
    for rx, s in SERIES_OVERRIDES:
        if rx.match(m):
            return s
    if heading:
        flat = re.sub(r"\s+", "", m).upper()
        for tok in reversed(heading.split()):
            if re.search(r"[A-Za-z]", tok) and re.sub(r"\s+", "", tok).upper() in flat:
                return tok
    lead = re.match(r"[A-Za-z]+", m)
    if lead:
        rest = m[lead.end():]
        d = re.match(r"(\d+)(?=\s|[-–]|$)", rest)
        return lead.group(0) + (d.group(1) if d else "")
    return heading or m


# --------------------------------------------------------------------------- #
# spec extraction (all patterns read text printed on the row / its headings)
# --------------------------------------------------------------------------- #
RATING_LEAD_RX = re.compile(
    r"^\s*([\d][\d\s.,&/]*?)\s*(AMPS?\.?|AMPERES?\.?|Amps\.?|A)\b", re.I)
RANGE_RX = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(?:[-–—]|to|\.\.\.|…)\s*(\d+(?:\.\d+)?)\s*A(?:MPS?\.?)?\b", re.I)
# "30 / 5 A ( R O U N D )" - current-transformer ratio (pages 91-93)
CT_RATIO_RX = re.compile(r"^\s*(\d+)\s*/\s*(\d+)\s*A\b", re.I)
# amperage printed mid-row rather than in a leading RATINGS cell, e.g.
# "RCCB D.P 25, 40 AMPS ( 30 mA ... )" on page 49
MID_AMPS_RX = re.compile(r"(?<![-–/])\b(\d[\d,\s&.]*?)\s*(AMPS?\.?|AMPERES?\.?)\b", re.I)
KA_RX = re.compile(r"\b(\d+(?:\.\d+)?)\s*KA\b", re.I)
ICUICS_RX = re.compile(r"\b(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\b")
PCT_RX = re.compile(r"\b(\d{1,3})\s*%")
VOLT_RX = re.compile(r"\b(\d{3}(?:\s*/\s*\d{3})?)\s*V\s?(AC|DC)?\b")
MA_RX = re.compile(r"\b([\d/\s-]*\d)\s*mA\b")
POLE_WORDS = [
    (re.compile(r"\bSINGLE\s*POLE\b|\b1\s*[-–]?\s*POLE\b", re.I), "1P"),
    (re.compile(r"\bDOUBLE\s*POLE\b|\b2\s*[-–]?\s*POLE\b|\bD\.?\s?P\b", re.I), "2P"),
    (re.compile(r"\bTRIPLE\s*POLE\b|\bTHREE\s*POLE\b|\b3\s*[-–]?\s*POLE\b", re.I), "3P"),
    (re.compile(r"\bFOUR\s*POLE\b|\b4\s*[-–]?\s*POLE\b|\bF\.?\s?P\b", re.I), "4P"),
]


def poles_from(*texts):
    for t in texts:
        if not t:
            continue
        for rx, val in POLE_WORDS:
            if rx.search(t):
                return val
    return None


TITLE_STRIP_RX = re.compile(
    r"\b\d{2}\s*[-–]\s*\d{2}\s*[-–\s]+\d{4}\b|\bPL\s*[-–]\s*\d+\b|\bPL[-–]\d+\b")


def rating_from(left_text, has_rating_caption):
    """
    Amperage as printed at the head of the row, e.g.
      "16 AMPS."             -> ("16A",  ["16A"])
      "3, 5 & 10, AMPS."     -> ("3, 5 & 10 A", ["3A","5A","10A"])
      "15,20,30,40,50,60,75 & 100 AMPS." -> (..., 8 values)
    Returns (printed, values) or (None, None).
    """
    m = RATING_LEAD_RX.match(left_text)
    if not m:
        return None, None
    # a bare "A" unit only counts as amperage when the table really prints a
    # RATINGS caption (page 11 prints contactor SIZE "0A" in that position)
    if not has_rating_caption and not re.match(r"AMP", m.group(2), re.I):
        return None, None
    body = m.group(1)
    nums = re.findall(r"\d+(?:\.\d+)?", body)
    if not nums or all(float(n) == 0 for n in nums):
        return None, None
    # "30 / 5 A" is a CT ratio, not a product amperage
    if re.search(r"\d\s*/\s*\d", body):
        return None, None
    values = ["%sA" % n for n in nums]
    printed = ("%sA" % nums[0]) if len(nums) == 1 else (norm(body).rstrip(",&") + " A")
    return printed, values


def build_specs(row_text, left_text, model, section, page_title, series_heading,
                poles_hint=None, has_rating_caption=False, page_headings=None):
    specs = {}
    # the RATINGS column is leftmost on most pages but sits AFTER the model on
    # the air-circuit-breaker pages, so try again with the model text removed
    printed, values = rating_from(left_text, has_rating_caption)
    if not printed and model:
        stripped = norm(left_text.replace(model, " ", 1))
        printed, values = rating_from(stripped, has_rating_caption)
    ct = CT_RATIO_RX.match(left_text)
    if ct:
        specs["ct_ratio"] = "%s/%sA" % (ct.group(1), ct.group(2))
        printed, values = ct.group(1) + "A", [ct.group(1) + "A"]
    if not printed:
        # amperage printed further along the row (page 49 RCCB/RCBO, page 69)
        m = MID_AMPS_RX.search(left_text)
        if m and not re.search(r"\b(TO|UP\s*TO)\s*$", left_text[:m.start()], re.I):
            nums = re.findall(r"\d+(?:\.\d+)?", m.group(1))
            if nums and any(float(n) > 0 for n in nums):
                values = ["%sA" % n for n in nums]
                printed = values[0] if len(nums) == 1 else norm(m.group(1)).rstrip(",&") + " A"
    if printed:
        specs["rating"] = printed
        specs["rating_values"] = values
    m = RANGE_RX.search(left_text)
    # "125 TO 225 AMPS" on the accessory tables is a ratings range, not a trip
    # setting; a printed trip range always spells its unit "A" ("500 to 1250 A")
    if m and not re.search(r"\bto\s+[\d.]+\s*AMP", m.group(0), re.I):
        specs["thermal_trip"] = norm(m.group(0))
    ka = KA_RX.search(row_text)
    if ka:
        specs["breaking_capacity"] = "%sKA" % ka.group(1)
    if "Icu" in page_title or "Icu" in (section or "") or re.search(r"\(KA\)|IEC\s*947", page_title, re.I):
        mm = ICUICS_RX.search(left_text)
        if mm and not ka:
            specs["breaking_capacity"] = "%sKA" % mm.group(1)
            specs["icu_ics"] = "%s / %s KA" % (mm.group(1), mm.group(2))
    pc = PCT_RX.search(left_text)
    if pc and ("Ics" in page_title or "Ics" in (section or "")):
        specs["ics_percent"] = pc.group(1) + "%"
    pol = poles_hint or poles_from(section, page_headings or page_title)
    if pol:
        specs["poles"] = pol
    v = VOLT_RX.search(row_text) or VOLT_RX.search(page_title)
    if v:
        specs["voltage"] = norm(v.group(1)).replace(" ", "") + "V" + (v.group(2) or "")
    ma = MA_RX.search(row_text)
    if ma:
        specs["sensitivity"] = norm(ma.group(1)) + "mA"
    # series groups a product's ampere variants; with no model and no printed
    # series heading the printed section heading is the only honest grouping key
    specs["series"] = series_for(model, series_heading) or norm(section or page_title)[:60]
    if series_heading:
        specs["series_heading"] = series_heading
    return specs


# --------------------------------------------------------------------------- #
# index (brands)
# --------------------------------------------------------------------------- #
INDEX_RX = re.compile(
    r"^\d{2}-\d{2}-\d{4}\s+PL\s*[-–]\s*(\d+)\s+([A-Z][A-Z\-]*)\s+(.*?)\s+(\d+)$")


def read_index(pdf):
    """printed page -> list of (pl_no, brand, description), taken from pages 3-4."""
    out = {}
    for pno in (3, 4):
        for line in (pdf.pages[pno - 1].extract_text() or "").splitlines():
            m = INDEX_RX.match(norm(line))
            if m:
                pl, brand, desc, page = int(m.group(1)), m.group(2), m.group(3), int(m.group(4))
                out.setdefault(page, []).append((pl, brand, norm(desc)))
    return out


# --------------------------------------------------------------------------- #
# main parse
# --------------------------------------------------------------------------- #
def main():
    rows_out, skipped = [], []
    coverage = {}

    with pdfplumber.open(PDF_PATH) as pdf:
        n_pages = len(pdf.pages)
        index = read_index(pdf)
        if len(index) < 80:
            raise RuntimeError("index parse failed: only %d printed pages found" % len(index))

        for pageno in range(FIRST_PRODUCT_PAGE, n_pages + 1):
            page = pdf.pages[pageno - 1]
            printed_page = pageno - PAGE_OFFSET
            entries = index.get(printed_page)
            if not entries:
                raise RuntimeError("page %d: no index entry for printed page %d"
                                   % (pageno, printed_page))
            # the index names the manufacturer of every page; SUPPLIER is only a
            # fallback for a page the index leaves without a brand token
            default_brand = entries[0][1] or SUPPLIER
            pl_numbers = {e[0] for e in entries}

            raw_text = page.extract_text() or ""
            # cross-check the PL stamp printed on the page against the index
            stamp = re.search(r"\bPL\s*[-–]\s*(\d+)\b", raw_text.replace("PL–", "PL – ").replace("PL-", "PL - "))
            if stamp and int(stamp.group(1)) not in pl_numbers:
                raise RuntimeError("page %d: printed stamp PL-%s not in index entries %s"
                                   % (pageno, stamp.group(1), sorted(pl_numbers)))

            lines = page_lines(page)
            blocks, tables = build_blocks(page, lines)

            # ---- page title = the non-noise lines above the first table -----
            first_tab_top = min([t.bbox[1] for t in tables], default=1e9)
            title_lines = [L for L in lines if L["top"] < first_tab_top]
            title_bits = [norm(TITLE_STRIP_RX.sub("", L["text"]))
                          for L in title_lines if not NOISE_RX.match(L["text"])]
            title_bits = [t for t in title_bits if t]
            page_title = norm(" | ".join(title_bits))
            # pole counts are only taken from heading lines: a bulleted feature
            # list can mention e.g. "A 2-POLE BUS JUMPER" (page 63) about an
            # accessory, which says nothing about the products on the page
            page_headings = norm(" | ".join(
                t for t in title_bits if not re.match(r"^[•∗*■\-]", t)))
            # does this page print a RATINGS/RATING column caption at all?
            has_rating_caption = bool(re.search(r"\bRATINGS?\b", raw_text))

            series_heading = None
            for bit in title_bits:
                m = SERIES_HEADING_RX.match(bit)
                if m and m.group(1).strip():
                    series_heading = norm(m.group(1))

            multi = MULTI_PRICE.get(pageno)
            if multi and multi["assert"].lower() not in norm(raw_text).lower():
                raise RuntimeError("page %d: expected multi-price captions %r not found"
                                   % (pageno, multi["assert"]))

            # ---- pre-pass: priced lines / x-profile per ruled table ---------
            priced_by_table = {}
            for blk in blocks:
                for L in blk["lines"]:
                    if ANY_PRICE_RX.search(L["text"]) and not NOISE_RX.match(L["text"]):
                        priced_by_table.setdefault(blk["table"], []).append(L)
            profiles = {ti: profile_of(ls) for ti, ls in priced_by_table.items()}
            resolved_mcol = {}      # table index -> (lo, hi) or None
            captioned = set()       # tables whose column came from printed captions

            def resolve_mcol(ti, hdr):
                key = (ti, id(hdr) if hdr else None)
                if key in resolved_mcol:
                    return resolved_mcol[key]
                if pageno in MODEL_X_OVERRIDE:
                    val = MODEL_X_OVERRIDE[pageno]
                    captioned.add(key)
                elif hdr and model_column(hdr):
                    val = snap_column_left(model_column(hdr),
                                           priced_by_table.get(ti, []))
                    if val[1] > 1e8:
                        # "MODEL" is the only caption left of the price column,
                        # so its right edge is unknown - take it from the data
                        geo = geometric_model_column(priced_by_table.get(ti, []))
                        val = (val[0], geo[1] if geo else val[1])
                    captioned.add(key)
                elif hdr and any(w["text"].upper().strip(":") in LEFT_CAPTIONS
                                 for L in hdr for w in L["words"] if w["x0"] < 320):
                    val = None       # leftmost caption is DESCRIPTION / RATINGS:
                    captioned.add(key)   # this table prints no model column
                else:
                    val = None
                    for (tj, _hid), v in resolved_mcol.items():
                        if v and (tj, _hid) in captioned and tj is not None and ti is not None \
                                and tj < ti and profiles_match(profiles.get(tj), profiles.get(ti)):
                            val = v                  # continuation of a ruled
                            captioned.add(key)       # table split by a section row
                            break
                    if val is None:
                        val = geometric_model_column(priced_by_table.get(ti, []))
                resolved_mcol[key] = val
                return val

            section = None
            brand = default_brand
            header_lines_by_table = {}
            n_parsed = 0

            for blk in blocks:
                btext = norm(" ".join(L["text"] for L in blk["lines"]))
                if not btext:
                    continue

                # ---- header block: remember its captions for this table -----
                is_header = ("(Rupees)" in btext or "UNIT PRICE" in btext.upper()
                             or "( Rupees )" in btext)
                if is_header and not ANY_PRICE_RX.search(btext):
                    header_lines_by_table[blk["table"]] = blk["lines"]
                    continue

                # ---- lines with no price -------------------------------------
                if not ANY_PRICE_RX.search(btext):
                    clean = [L["text"] for L in blk["lines"] if not NOISE_RX.match(L["text"])]
                    if clean:
                        cand = norm(" ".join(clean))
                        # a section / sub-heading, otherwise descriptive prose
                        cand = norm(TITLE_STRIP_RX.sub("", cand))
                        if (cand and len(cand) <= 90 and not cand.endswith(".")
                                and not re.match(r"^[•∗*■\-]", cand)
                                and len(re.findall(r"[A-Za-z]", cand)) >= 3):
                            section = cand
                            m = SERIES_HEADING_RX.match(cand)
                            if m and m.group(1).strip():
                                series_heading = norm(m.group(1))
                        for pg, rules in BRAND_SECTION_OVERRIDE.items():
                            if pg == pageno:
                                for b, rx in rules:
                                    if rx.search(cand):
                                        brand = b
                    continue

                # ---- model column geometry for this table -------------------
                hdr_now = header_lines_by_table.get(blk["table"])
                mcol = resolve_mcol(blk["table"], hdr_now)
                # contactor pages print the AC-3 rating under an "OPERATIONAL
                # CURRENT / AMPERES" caption (pages 11, 33, 34, 55-57, 59)
                # (page 11 prints that caption just above the ruled table, so the
                # page's title lines are searched as well as the header block)
                ocol = caption_column((hdr_now or []) + title_lines, {"OPERATIONAL"})

                # ---- segment the block into products ------------------------
                for prod_lines in segment_block(blk["lines"]):
                    made = emit_product(
                        prod_lines, pageno, brand, section, page_title,
                        series_heading, mcol, multi, rows_out, skipped,
                        has_rating_caption, ocol, page_headings)
                    n_parsed += made

            coverage[pageno] = (
                sum(1 for L in lines
                    if ANY_PRICE_RX.search(L["text"]) and not NOISE_RX.match(L["text"])),
                n_parsed,
            )

    # ---------------------------------------------------------------- ditto ---
    carry_dittos(rows_out)

    # ------------------------------------------------------------ sanity band -
    kept = []
    for r in rows_out:
        v = r["price_pkr"]
        if v is not None and (v < 10 or v > 10_000_000):
            skipped.append({"page": r["page"], "raw": r["_raw"],
                            "reason": "sanity: price %s outside 10..10,000,000 PKR" % v})
            continue
        kept.append(r)
    rows_out = kept

    # --------------------------------------------------------------- dedupe ---
    seen, deduped = {}, []
    for r in rows_out:
        key_specs = {k: v for k, v in r["specs"].items() if k != "note"}
        key = (r["page"], r["brand"], r["section"], r["model"],
               json.dumps(key_specs, sort_keys=True), r["description"])
        if key in seen and seen[key]["price_pkr"] == r["price_pkr"]:
            skipped.append({"page": r["page"], "raw": r["_raw"],
                            "reason": "duplicate of an identical row (same model, specs and price)"})
            continue
        seen[key] = r
        deduped.append(r)
    rows_out = deduped

    report(rows_out, skipped, coverage, n_pages)


# --------------------------------------------------------------------------- #
def segment_block(lines):
    """
    Split one ruled row into products.  A ruled row normally holds exactly one
    product (price vertically centred over its description); a few hold several
    stacked products (pages 26, 83, 84, 85).  Rule: accumulate lines until a
    priced line is seen -> that pending group + the priced line is one product.
    Anything left over at the end of the row belongs to the last product (it is
    the tail of its description, e.g. "GREEN COLOUR" under a push button).
    """
    products, pending = [], []
    for L in lines:
        pending.append(L)
        if ANY_PRICE_RX.search(L["text"]):
            products.append(pending)
            pending = []
    if pending:
        if products:
            products[-1].extend(pending)
        else:
            products.append(pending)
            return []  # no price anywhere -> not a product
    return products


def words_in(prod_lines, lo, hi):
    out = []
    for L in prod_lines:
        for w in L["words"]:
            if lo <= w["x0"] < hi:
                out.append((L["top"], w["x0"], w["text"]))
    out.sort()
    return norm(" ".join(t for _, _, t in out))


DITTO_RX = re.compile(r'^["“”\']+(\s*["“”\']+)*$')
LEAD_JUNK_RX = re.compile(r'^(FOR|MODEL:?|∗|\*|•|■)\s+', re.I)

# Words that occur in the descriptive left-hand cells of the accessory tables.
# A model cell containing any of them is not a catalogue number, so it is
# refused and the quoted code (e.g. "UVR", "MX") is used instead - or nothing.
NOT_A_MODEL_WORDS = {
    "UNDER", "VOLTAGE", "SHUNT", "TRIP", "DEVICE", "CLOSING", "COIL", "KEY",
    "LOCK", "LOCKING", "MOTOR", "CHARGING", "CHARGED", "MECHANISM",
    "MECHANICAL", "INTERLOCK", "SPRING", "AUX", "AUX.", "AUXILIARY", "SWITCH",
    "RELAY", "ALARM", "DIRECT", "ROTARY", "HANDLE", "EXTENDED", "EXT",
    "EXT.", "TOGGLE", "RELEASE", "DELAYED", "EARTHFAULT", "EARTH", "FAULT",
    "FLEXIBLE", "RIGID", "OPERATION", "SUITABLE", "THERMOCOUPLE", "SUPPLY",
    "SIZE", "RANGE", "DIGITAL", "SETTING", "INDICATION", "STANDARD", "SLIM",
    "AMMETERS:", "VOLTMETERS", "FREQUENCY", "POWER", "FACTOR", "METER",
    "SELECTOR", "PILOT", "LIGHT", "PUSH", "BUTTON", "OPTIONAL", "ACCESSORIES",
    "Auxiliary", "Switch,",
}
QUOTED_CODE_RX = re.compile(
    r"[\"“”‘’']{1,2}\s*([A-Z0-9][A-Z0-9/\-]{0,11})\s*[\"“”‘’']{1,2}")
# "MODEL: HY8000S-R08" - pages 70/71 label the catalogue number inline
INLINE_MODEL_RX = re.compile(r"^MODEL\s*:\s*(\S+)", re.I)
# a catalogue code embedded in a descriptive accessory line, e.g. "GV-AE11"
EMBEDDED_CODE_RX = re.compile(r"^[A-Za-z]{1,5}\d*[-–][A-Za-z0-9./]{1,10}$")
# a leading catalogue code on pages whose left column caption is DESCRIPTION
# ("iPF40 3P+N, 40KA A9L15688", "RH99M (SENSITIVITY: ...)")
LEAD_CODE_RX = re.compile(r"^[A-Za-z][A-Za-z]*\d[A-Za-z0-9\-./]*$")
# a catalogue code printed with spaces around its dash ("MR - 8", "UA - 2")
SPACED_CODE_RX = re.compile(r"^[A-Za-z]{1,4}\s*[-–]\s*[A-Za-z]?\d+[A-Za-z0-9]*\b")


def model_cell_ok(cell):
    """A model cell must look like a catalogue number, not a description."""
    if not cell:
        return False
    toks = cell.split()
    if len(toks) > 4:
        return False
    for t in toks:
        if t.upper().strip(".,") in {w.upper().strip(".,") for w in NOT_A_MODEL_WORDS}:
            return False
    return True


def emit_product(prod_lines, pageno, brand, section, page_title, series_heading,
                 mcol, multi, rows_out, skipped, has_rating_caption=False,
                 ocol=None, page_headings=None):
    text = norm(" ".join(L["text"] for L in prod_lines))
    if NOISE_RX.match(text):
        return 0

    price_line = None
    for L in prod_lines:
        if ANY_PRICE_RX.search(L["text"]):
            price_line = L
    if price_line is None:
        return 0

    n_prices = len(PRICE_RX.findall(price_line["text"])) + len(ONREQ_RX.findall(price_line["text"]))

    # ------------------------------------------------ multi-price rows -------
    if n_prices >= 2:
        if not multi:
            skipped.append({"page": pageno, "raw": text,
                            "reason": "row prints %d prices but page has no pinned column captions" % n_prices})
            return 0
        return emit_multi(prod_lines, price_line, pageno, brand, section,
                          page_title, series_heading, mcol, multi, rows_out,
                          skipped, has_rating_caption, page_headings)

    value, kind = parse_price(price_line["text"])
    if kind is None:
        skipped.append({"page": pageno, "raw": text, "reason": "no parseable price token"})
        return 0

    # left part of the priced line = everything before the price token; when the
    # price is printed on a line of its own the whole ruled row is the left part
    left = norm(PRICE_RX.sub("", ONREQ_RX.sub("", price_line["text"])).strip(" .-"))
    if not left:
        left = norm(PRICE_RX.sub("", ONREQ_RX.sub("", text)).strip(" .-"))
    model, note = extract_model(prod_lines, price_line, mcol, pageno, left)

    specs = build_specs(text, left, model, section, page_title, series_heading,
                        has_rating_caption=has_rating_caption,
                        page_headings=page_headings)
    if "rating" not in specs and ocol:
        hi = ocol[1]
        if hi > 1e8:
            # no caption sits between OPERATIONAL and the price column, so stop
            # the column at the price cell of this very row
            price_x = [w["x0"] for w in price_line["words"]
                       if ANY_PRICE_RX.match(w["text"])]
            hi = (min(price_x) - 3.0) if price_x else hi
        cell = words_in([price_line], ocol[0], hi)
        m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*A?", cell)
        if m and float(m.group(1)) > 0:
            specs["rating"] = m.group(1) + "A"
            specs["rating_values"] = [m.group(1) + "A"]
            specs["rating_column"] = "OPERATIONAL CURRENT (AMPERES), AC-3"
    if kind == "onrequest":
        specs["note"] = 'PDF prints "On Request" instead of a price'
    if note:
        specs["note"] = (specs.get("note", "") + ("; " if specs.get("note") else "") + note)

    mm = PRICE_RX.search(price_line["text"])
    if mm and mm.group(1) in PRICE_TYPO_NOTE:
        specs["note"] = (specs.get("note", "") + ("; " if specs.get("note") else "")
                         + PRICE_TYPO_NOTE[mm.group(1)])

    desc = norm(re.sub(r"\s+", " ", text))
    rows_out.append({
        "page": pageno, "brand": brand, "section": norm(section or page_title),
        "model": model, "description": desc, "price_pkr": value,
        "specs": specs, "_raw": text,
    })
    return 1


def emit_multi(prod_lines, price_line, pageno, brand, section, page_title,
               series_heading, mcol, multi, rows_out, skipped,
               has_rating_caption=False, page_headings=None):
    txt = price_line["text"]
    # collect the printed price tokens left to right
    tokens = []
    for m in re.finditer(PRICE_RX.pattern + r"|" + ONREQ_RX.pattern, txt, re.I):
        tokens.append(m)
    labels = multi["labels"]
    vals = []
    for m in tokens:
        v, k = parse_price(m.group(0))
        vals.append(v if k == "num" else None)
    if multi.get("split_slash"):
        # Page 8 prints the "UVT / SHUNT TRIP" cell as one token pair
        # "45000/24,000/=" - the first number carries no "/=" of its own, so it
        # is recovered from the raw text and inserted in its printed position.
        pair = re.search(r"(\d[\d,]*)\s*/\s*(\d[\d,]*)\s*/\s*=", txt)
        if pair:
            plain = [v for v in vals if v is not None]
            vals = [plain[0],
                    int(pair.group(1).replace(",", "")),
                    int(pair.group(2).replace(",", "")),
                    plain[-1]]

    if len(vals) != len(labels):
        skipped.append({"page": pageno, "raw": txt,
                        "reason": "multi-price row has %d prices but %d pinned captions"
                                  % (len(vals), len(labels))})
        return 0

    left = txt
    for m in reversed(tokens):
        left = left[:m.start()] + left[m.end():]
    left = norm(re.sub(r"\d[\d,]*\s*/\s*$", "", left).strip(" .-"))

    # on the accessory tables the left cell is a RATINGS range or a DESCRIPTION,
    # not a catalogue number - so the printed model column is not consulted
    model, note = extract_model(prod_lines, price_line,
                                mcol if multi.get("left_is_model") else None,
                                pageno, left)
    made = 0
    for lab, val, in zip(labels, vals):
        specs = build_specs(txt, left, model, multi.get("section", section),
                            page_title, series_heading,
                            poles_hint=(multi["poles"][labels.index(lab)]
                                        if multi.get("poles") else None),
                            has_rating_caption=has_rating_caption,
                            page_headings=page_headings)
        specs["price_column"] = lab
        if left:
            specs["applies_to"] = left
        if val is None:
            specs["note"] = 'PDF prints "On Request" in the "%s" column' % lab
        if note:
            specs["note"] = (specs.get("note", "") + ("; " if specs.get("note") else "") + note)
        if val == 1600000 and "=-" in txt:
            specs["note"] = (specs.get("note", "") + ("; " if specs.get("note") else "")
                             + PRICE_TYPO_NOTE["1,600,000"])
        mdl = model if model else lab
        rows_out.append({
            "page": pageno, "brand": brand,
            "section": norm(multi.get("section") or section or page_title),
            "model": mdl,
            "description": norm("%s - %s" % (left, lab)) if left else lab,
            "price_pkr": val, "specs": specs, "_raw": txt,
        })
        made += 1
    return made


def extract_model(prod_lines, price_line, mcol, pageno, left):
    """Model exactly as printed in the MODEL column; ('' , note) if none printed."""
    note = None
    model = ""
    if mcol:
        model = words_in([price_line], mcol[0], mcol[1])
        if not model:
            # the model is printed on an earlier line of the same ruled row
            # (wrapped rows such as page 71 "MODEL: KX2N" / "30,000/=")
            for L in prod_lines:
                cand = words_in([L], mcol[0], mcol[1])
                if cand:
                    model = cand
                    break

    if pageno in MODEL_ASSERT and model:
        if not MODEL_ASSERT[pageno].match(model):
            raise RuntimeError("page %d: model cell %r fails the pinned assertion"
                               % (pageno, model))

    if DITTO_RX.match(model or ""):
        return "\x00DITTO", 'model cell printed as a ditto mark (") - carried from the row above'

    model = model or ""
    # cam-switch codes are printed digit-by-digit ("1 4 2 2 1 1")
    toks = model.split()
    if len(toks) >= 4 and all(len(t) == 1 and t.isdigit() for t in toks):
        model = "".join(toks)
    if model.endswith("*"):
        model = model[:-1].strip()
        note = 'model printed with a "*" footnote marker ("* TILL STOCKS ARE AVAILABLE")'
    model = LEAD_JUNK_RX.sub("", model).strip(" ,.-")

    if not model_cell_ok(model):
        model = ""
        m = INLINE_MODEL_RX.match(left or "")
        if m:
            model = m.group(1)
            note = ((note + "; ") if note else "") + \
                'catalogue number labelled inline on the row as "MODEL: ..."'
        if not model:
            q = QUOTED_CODE_RX.findall(left or "")
            if q:
                model = q[0]
                note = ((note + "; ") if note else "") + \
                    ('no MODEL column is printed for this line; the quoted code %r '
                     "printed on the row is used as the model" % model)
        if not model:
            for tok in (left or "").split():
                t = tok.strip("(),.")
                if EMBEDDED_CODE_RX.match(t) and re.search(r"\d", t):
                    model = t
                    note = ((note + "; ") if note else "") + \
                        ("no MODEL column is printed for this line; the catalogue "
                         "code %r printed inside the description is used as the model" % t)
                    break
        if not model:
            m = SPACED_CODE_RX.match(LEAD_JUNK_RX.sub("", left or ""))
            if m:
                model = norm(m.group(0))
                note = ((note + "; ") if note else "") + \
                    ("no MODEL column is printed for this line; the leading "
                     "catalogue code %r is used as the model" % model)
        if not model:
            first = (left or "").split()
            if first and LEAD_CODE_RX.match(first[0].strip(",")):
                model = first[0].strip(",")
                note = ((note + "; ") if note else "") + \
                    ("this page prints a DESCRIPTION column rather than a MODEL "
                     "column; the leading printed code %r is used as the model" % model)
    if not model:
        note = ((note + "; ") if note else "") + \
            "no catalogue number is printed for this line; description carries the printed text"
    return model, note


def carry_dittos(rows):
    last = {}
    for r in rows:
        key = (r["page"], r["section"])
        if r["model"] == "\x00DITTO":
            prev = last.get(r["page"])
            if prev:
                r["model"] = prev
                r["specs"]["series"] = series_for(prev, r["specs"].get("series_heading"))
            else:
                r["model"] = ""
        elif r["model"]:
            last[r["page"]] = r["model"]
    return rows


# --------------------------------------------------------------------------- #
def report(rows_out, skipped, coverage, n_pages):
    prices = [r["price_pkr"] for r in rows_out if r["price_pkr"] is not None]

    p("=== coverage: priced lines in raw text vs rows emitted, per page ===")
    bad = []
    for pg in sorted(coverage):
        raw_n, parsed_n = coverage[pg]
        flag = "" if parsed_n >= raw_n else "   <-- SHORT"
        if parsed_n < raw_n:
            bad.append(pg)
        p("  page %2d: raw priced lines=%-3d rows emitted=%-3d%s" % (pg, raw_n, parsed_n, flag))
    p("  pages emitting fewer rows than raw priced lines: %s" % (bad or "none"))

    p("=== price sanity ===")
    p("  min=%s  median=%s  max=%s  (n=%d)"
      % (min(prices), statistics.median(prices), max(prices), len(prices)))

    p("=== spot-check: 10 random parsed rows vs their source line ===")
    random.seed(11)
    for r in random.sample(rows_out, min(10, len(rows_out))):
        p("  p%-2d %-22s %-10s %s" % (r["page"], r["model"][:22],
                                      str(r["price_pkr"]), json.dumps(r["specs"], ensure_ascii=False)[:150]))
        p("      raw: %s" % r["_raw"][:180])

    audit = os.environ.get("SWAS_AUDIT")
    if audit:
        with open(audit, "w", encoding="utf-8") as fh:
            cur = None
            for r in rows_out:
                if r["page"] != cur:
                    cur = r["page"]
                    fh.write("\n===== PAGE %d  brand=%s =====\n" % (cur, r["brand"]))
                fh.write("%-26s | %-10s | %-42s | %s\n     raw: %s\n"
                         % (r["model"][:26], r["price_pkr"], r["section"][:42],
                            json.dumps(r["specs"], ensure_ascii=False), r["_raw"][:170]))
        p("  audit written: %s" % audit)

    empties = [r for r in rows_out if not r["model"]]
    by_page = {}
    for r in empties:
        by_page[r["page"]] = by_page.get(r["page"], 0) + 1
    p("=== rows with no printed catalogue number: %d (pages %s) ==="
      % (len(empties), sorted(by_page)))

    for r in rows_out:
        del r["_raw"]

    out = {
        "source_pdf": os.path.basename(PDF_PATH),
        "rows": rows_out,
        "skipped": skipped,
        "stats": {"pages": n_pages, "rows": len(rows_out),
                  "priced": len(prices), "skipped": len(skipped)},
    }
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    p("=== stats ===")
    p("  %s" % out["stats"])
    p("  written: %s" % OUT_PATH)


if __name__ == "__main__":
    main()
