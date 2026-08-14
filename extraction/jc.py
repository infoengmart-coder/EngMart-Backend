"""
Faithful extractor for "JC price-list-2023[1].pdf"
(Jubilee Corporation / JC multi-brand distributor price list, 23-May-2023, 259 pages).

Layout
------
Pages 1-3 are the INDEX: a ruled table with columns
    S.NO | Ref. No. | BRAND NAME | DESCRIPTION | COUNTRY | PAGE NOs.
It is extracted with PyMuPDF find_tables() and gives an authoritative,
*printed* brand for every one of the 85 catalogue sections (S.No. 1..85).

Pages 4-259 are prose/table hybrid spec sheets, one section per page run.
Every product page carries a header line
    "Ref. No. TE01 / S.No. 1"
(all 256 product pages parse; note the code alone is ambiguous - "SC01" is used
for both SOCOMEC (S.No. 31) and SACI (S.No. 38) - so the brand is keyed on the
S.No., not the ref code). That is how `brand` is set per row: it is the brand
printed in the PDF's own index for the section the page belongs to.

The body text is NOT line-ordered by the PDF: a table row is drawn as several
independent text spans, so plain extract_text() breaks e.g.
    "3, 5 & 10 Amps" / "XS30NB * TB1 2.5KA/1.3KA" / "Rs. 25,000/="
onto three separate lines.  Rows are therefore rebuilt POSITIONALLY:
get_text("words") -> cluster words whose vertical centre is within 3pt ->
sort by x.  That reassembles
    "3, 5 & 10 Amps XS30NB * TB1 2.5KA/1.3KA 2.5KA/1.3KA Rs. 25,000/="
which is one printed table row.

Price handling
--------------
A row is emitted for every rebuilt line that prints a price. Printed forms, all
of which really occur:
    "Rs. 25,000/="  "Rs 1,410,000/="  "Rs.1,090,000/="  "Rs. 38,000 /="
    "Rs . 88,000/="  "Rs. .24,000/="  "Rs., 140,000/="  "RS. 130,000/="
    "Rs.108, 000/="  (thousands separated by a space)
    "(Rs. 2,900)"   - unit price of a component inside a printed assembly
                      example (LOVATO push-button pages); kept, flagged with a
                      specs.note, because the price really is printed for that
                      catalogue number.
    "Rs. On Request" / "On Request"  - emitted with price_pkr = null + a note,
                      but only when the line itself names a catalogue number.
Prices are never carried, averaged or invented.  A price is taken only from the
line it is printed on, and main() asserts for every emitted row that its price
is one of the prices printed on its own description line.
Where one printed line carries TWO price columns (SMC air-tubing:
"20 Meter Roll" / "100 Meter Roll") one row is emitted per printed price, each
flagged with specs.price_column and the printed column header line.
The Terasaki/Hyundai accessory MATRICES ("1. Auxiliary Switch 1C  18,200/=
18,200/= ... 31,000/=", one price per breaker frame, cells printed without any
"Rs." marker) cannot have a cell attributed to a catalogue number from the line
alone - every such line is put in `skipped` with its raw text rather than being
guessed at or silently dropped.

Model handling
--------------
There is no single model column across 85 different manufacturers' sheets, so
the catalogue number is found by a token scan over the part of the line left of
the price (see model_from()): enumerators ("31.", "iv.", "A)") are stripped, an
explicit "Model:"/"Type:"/"Cat.No:"/"Ref:" marker wins if present, spaced or
trailing hyphens are re-joined ("PRW08 - 2DP" -> "PRW08-2DP", "SRC1- 1220" ->
"SRC1-1220"), unit/spec tokens ("16A", "2.5KA/1.3KA", "48X48", "230VAC",
"IP67", "3P+2a2b", ...) are rejected, alphabetic-only codes are accepted only
when shaped like a code ("HGD-M", "EPC/PF", "RR-VTS"), and a short alphabetic
token immediately before a digit-leading code is glued back on ("S 1000SE",
"XM 50CS(B)").  Pure-numeric catalogue numbers (FAMATEL "23200") are accepted
only as the first token of a row and only when not followed by a unit word.
Four sections print their catalogue numbers in a house format that no generic
rule can read, so each has one narrow rule keyed on its S.No. (all of them read
text printed on that same line):
    S.No. 31 SOCOMEC  "1250 Amps. 2600 3121 3P ..."      -> "2600 3121"
    S.No. 36 FINDER   "40.51 Relay: 5Pin, ..."           -> "40.51"
    S.No. 18 LOVATO   "M0 P009 12 400 2V3 0.75KW/ 1hp"   -> "M0 P009 12 400 2V3"
    ETI / DF ELECTRIC fuses "Group : 00C  Ratings : ..." -> "Group 00C"
If no catalogue number can be identified on a priced line, the line is NOT
guessed at and NOT given a neighbour's model: it goes to `skipped` with its raw
text.  description always carries the complete printed line, so nothing printed
is lost even where the model token is imperfect.

specs
-----
Derived only from text on the row (or its printed section heading):
rating (amperage) and rating_list when one price covers several printed ratings
("3, 5 & 10 Amps" -> rating 3A, rating_list [3A,5A,10A]), voltage,
breaking_capacity, poles, ip_rating, frequency, sensitivity, setting_range,
ct_ratio, burden, power, plus series.
series = the printed "<X> Series" heading when the model starts with X (and the
heading is not so short that it would fuse unrelated frames), else the model
stem printed before the size suffix ("YPN312/100" -> "YPN312", "TX4S-14R" ->
"TX4S", FINDER "40.51" -> "40"), else the model itself.  The heading is never
used as the family when it does not match the model - that would group
unrelated products into one storefront product.

Duplicates
----------
Only an identical printed line (same model, specs, price and text) repeated in
the PDF is collapsed.  Rows sharing a model and price but printed on different
lines are all kept: the printed line is often the only record of what
distinguishes them (CT ratio, the 3P/4P section they sit in, motor rating).

Run:
    venv/Scripts/python.exe extraction/jc.py
Writes: extraction/out/jc.json
"""

import json
import os
import random
import re
import statistics
from collections import Counter

import fitz  # PyMuPDF

PDF_PATH = r"C:/Users/AWCD/Desktop/client/engmart (2)/product-details/JC price-list-2023[1].pdf"
OUT_PATH = r"C:/Users/AWCD/Desktop/client/engmart (2)/backend/extraction/out/jc.json"

INDEX_PAGES = (0, 1, 2)          # 1-based pages 1-3: the INDEX table
FALLBACK_BRAND = "JC"
# pages whose printed price lines were counted BY EYE against the rebuilt text
# (PANASONIC overload relays / PANASONIC-SUNX fibre sensors / AUTONICS photo sensors)
COVERAGE_PAGES = (33, 125, 209)  # eye-counted: 4, 3 and 7 priced lines respectively


def p(s=""):
    print(str(s).encode("ascii", "replace").decode())


def norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


# --------------------------------------------------------------------------
# positional line rebuilding
# --------------------------------------------------------------------------
def ylines(page, tol=3.0):
    """Rebuild printed rows: cluster words by vertical centre, order by x."""
    words = page.get_text("words")           # x0, y0, x1, y1, text, ...
    words.sort(key=lambda t: ((t[1] + t[3]) / 2.0, t[0]))
    clusters = []
    for x0, y0, x1, y1, txt, *_ in words:
        yc = (y0 + y1) / 2.0
        if clusters and abs(clusters[-1][0] - yc) <= tol:
            clusters[-1][1].append((x0, x1, txt))
            n = len(clusters[-1][1])
            clusters[-1][0] = (clusters[-1][0] * (n - 1) + yc) / n
        else:
            clusters.append([yc, [(x0, x1, txt)]])
    out = []
    for yc, ws in clusters:
        ws.sort()
        out.append({"y": round(yc, 1),
                    "text": " ".join(w[2] for w in ws),
                    "words": ws})
    return out


# --------------------------------------------------------------------------
# prices
# --------------------------------------------------------------------------
# "Rs. 25,000/=", "Rs 1,410,000/=", "Rs.1,090,000/=", "Rs. 38,000 /=", "Rs 1,000/-"
# the "Rs" marker is printed with erratic punctuation and spacing:
# "Rs. 25,000/="  "Rs 1,410,000/="  "Rs.1,090,000/="  "Rs . 88,000/="
# "Rs. .24,000/="  "Rs., 140,000/="  "RS. 130,000/="  "Rs.108, 000/="
PRICE_SLASH = re.compile(r"Rs[\s\.,:]*(\d[\d,]*(?:\s+\d{3})*)\s*/\s*[=\-]", re.I)
# "(Rs. 2,900)"  /  "(Rs.1,400)"   - printed component price inside brackets
PRICE_PAREN = re.compile(r"\(\s*Rs[\s\.,:]*(\d[\d,]*(?:\s+\d{3})*)\s*(?:x\s*\d+\s*)?\)", re.I)
ONREQ = re.compile(r"(?:Rs\s*[\.,:]?\s*)?\bOn\s*Request\b", re.I)
# any printed price cell, with or without the "Rs." marker (matrix accessory tables
# print bare cells: "18,200/= 18,200/= 18,200/=")
BARE_CELL = re.compile(r"(?<![A-Za-z0-9])\d[\d,]{2,}\s*/\s*[=\-]")


def to_amount(text):
    return int(re.sub(r"[,\s]", "", text))


def find_prices(text):
    """Return [(start, end, value_or_None, kind)] for every printed price on the line."""
    hits = []
    for m in PRICE_SLASH.finditer(text):
        hits.append((m.start(), m.end(), to_amount(m.group(1)), "rs"))
    for m in PRICE_PAREN.finditer(text):
        if any(s <= m.start() < e for s, e, _, _ in hits):
            continue
        hits.append((m.start(), m.end(), to_amount(m.group(1)), "paren"))
    for m in ONREQ.finditer(text):
        if any(s <= m.start() < e for s, e, _, _ in hits):
            continue
        hits.append((m.start(), m.end(), None, "onrequest"))
    hits.sort()
    return hits


# --------------------------------------------------------------------------
# model detection
# --------------------------------------------------------------------------
ENUM = re.compile(r"^\s*(?:\(?(?:\d{1,3}|[ivxlcIVXLC]{1,5}|[A-Za-z])[\.\)]\s+)+")
MARKER = re.compile(r"\b(?:Model|MODEL|Models|Type|TYPE|Cat\.?\s*No\.?|Catalogue\s*No\.?|Ref)\s*[:.]\s*",
                    re.I)

# ETI / DF ELECTRIC fuse pages identify a product by its printed group / size only
GROUP_RE = re.compile(r"^\s*(Group|Size|Class)\s*:?\s*(.+?)\s*(?:Ratings?\b|Maximum\b|$)", re.I)

UNIT_WORD = {"a", "amp", "amps", "ampere", "amperes", "v", "vac", "vdc", "kv", "w", "kw",
             "hp", "kva", "kvar", "hz", "khz", "mm", "cm", "m", "meter", "meters", "kg",
             "ka", "steps", "step", "pole", "poles", "pcs", "no", "nos", "watts", "sec",
             "ohm", "ohms", "bar", "mpa", "each", "set", "sets"}

# printed in ALL CAPS but description / units, never a catalogue number
STOP_ALPHA = {"ON", "OFF", "AUTO", "MAN", "NO", "NC", "NA", "YES", "AND", "OR", "FOR",
              "WITH", "EACH", "TYPE", "MODEL", "MADE", "NOTE", "PRICE", "UNIT", "AC",
              "DC", "MIN", "MAX", "LED", "LCD", "USB", "PLC", "RTD", "PVC", "CT", "PT",
              "MCB", "MCCB", "ELCB", "RCCB", "RCBO", "ACB", "VCB", "VFD", "DOL", "IP",
              "EMI", "EMC", "THD", "LSI", "LSIG", "SS", "AL", "CU", "PF", "KVAR", "KW",
              "HP", "KA", "KV", "VA", "OL", "NEW", "SET", "STUD", "SIZE", "STEP", "STEPS",
              "PCS", "PER", "THE", "ALL", "ADD", "SUB", "TOP", "END", "II", "III", "IV",
              "VI", "VII", "VIII", "IX", "XI", "XII", "NH", "HRC", "PVT", "LTD", "ETC",
              "RS", "PKR", "FROM", "UPTO", "TO", "OF", "IN", "AT", "BY", "AS", "IS",
              "AMPS", "AMP", "VOLT", "VOLTS", "WATT", "WATTS", "OHM", "OHMS", "TRUE",
              "RMS", "PID", "PWM", "SPD", "MMS", "ATS", "APFC", "HV", "MV", "LV",
              "DIN", "IEC", "EN", "UL", "VDE", "CE", "SET", "PACK", "ROLL",
              # function abbreviations printed in front of the real catalogue number
              "UVT", "SHT", "AUX", "OCR", "ELR", "PTA", "MOD", "OFF-ON", "ON-OFF"}

NOT_MODEL = [
    re.compile(r"^\d+(?:\.\d+)?(?:a|ma|ka|kv|v|vac|vdc|va|w|kw|hp|hz|khz|mhz|mm|cm|kg|"
               r"kvar|kva|mpa|bar|c|k|p|amp|amps|ohm|ohms|sec|ms|lux|db|%)$", re.I),
    re.compile(r"^\d+(?:\.\d+)?\s*(?:ka|kv|a|v|w)\s*/", re.I),      # 2.5KA/1.3KA
    re.compile(r"^\d+(?:\.\d+)?(?:/\d+(?:\.\d+)?)+[a-z]*$", re.I),   # 1200/5A, 50/60Hz,
                                                                     # 400/415/440V
    re.compile(r"^\d+\s*[x×]\s*\d+", re.I),                          # 48X48, 8 x 5
    re.compile(r"^ip\d{2}$", re.I),
    re.compile(r"^(?:iec|en|ul|vde|cat|din|iso|bs)\d", re.I),
    re.compile(r"^\d+[-~]\d+", re.I),                                # 800-1800A, 12-24VDC
    re.compile(r"^\d+(?:\.\d+)?$"),
    re.compile(r"^\d{1,3}(?:,\d{3})+(?:\.\d+)?$"),
    re.compile(r"^\d+p(?:\+\d*[ab]\d*[ab]?)?$", re.I),               # 3P, 3P+2a2b
    re.compile(r"^\d{0,2}[ab]\d{0,2}[ab]?$"),                        # 1a1b, 2a2b, 4a (lowercase as printed)
    re.compile(r"^(?:ac|dc)[1-4]$", re.I),                           # AC3, AC1 categories
    re.compile(r"^\d+(?:\.\d+)?(?:kA|A)/\d", re.I),
    re.compile(r"^\d+/\d+$"),                                        # 2/4, page fractions
    re.compile(r"^[?\.\-,:;\+\*/=()\[\]]+$"),
    re.compile(r"^\d+(?:st|nd|rd|th)$", re.I),
    re.compile(r"^(?:rs|no|nos)\.?$", re.I),
    re.compile(r"^\d+\s*(?:mm|cm)\s*[x×]", re.I),
    re.compile(r"^\d+(?:\.\d+)?(?:mm|cm|m)[x×]", re.I),
    re.compile(r"^\d+°?c$", re.I),
    re.compile(r"^\d+(?:\.\d+)?kw/\d", re.I),                        # 30KW/40
    # "3-Phase", "1-Pole", "4-Wire", "12-Steps": a printed quantity, not a model
    re.compile(r"^\d+-(?:phase|ph|pole|poles|wire|wires|way|ways|step|steps|digit|digits|"
               r"element|elements|core|cores|module|modules|row|rows|pin|pins|min|mins|"
               r"sec|secs|hour|hours|channel|channels|stage|stages)$", re.I),
    # a unit carrying its value across a slash / hyphen: "HP/1.5", "KW/40", "V/50"
    re.compile(r"^(?:hp|kw|kva|kvar|ka|kv|va|vac|vdc|hz|khz|kg|ph)[/\-]\d+(?:\.\d+)?$", re.I),
    re.compile(r"^\d+(?:\.\d+)?(?:hp|kw|kva|kvar|ka|kv|va)[/\-]", re.I),
]

CODE_CHARS = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-/\.\+\(\)&#_]*$")
ALPHA_CODE = re.compile(r"^[A-Za-z]{2,10}(?:[-/][A-Za-z0-9]{1,10})+$")   # HGD-M, EPC/PF


def clean_token(tok):
    """Strip printers' furniture (bullets, footnote marks, quotes) from both ends."""
    t = tok.strip()
    while t and not t[0].isalnum():
        t = t[1:]
    while t and not (t[-1].isalnum() or t[-1] == ")"):
        t = t[:-1]
    if t.endswith(")") and "(" not in t:
        t = t[:-1]
    return t


def is_stop_alpha(t):
    return t.upper() in STOP_ALPHA


def upperish(t):
    letters = [c for c in t if c.isalpha()]
    if not letters:
        return False
    return sum(1 for c in letters if c.isupper()) / len(letters) >= 0.5


def looks_like_code(tok):
    """A token that can plausibly be a printed catalogue number."""
    t = clean_token(tok)
    if len(t) < 2:
        return False
    if not CODE_CHARS.match(t):
        return False
    for rx in NOT_MODEL:
        if rx.match(t):
            return False
    if t.lower() in UNIT_WORD:
        return False
    has_alpha = any(c.isalpha() for c in t)
    has_digit = any(c.isdigit() for c in t)
    if has_alpha and has_digit:
        # words like "50/60Hz", "230VAC" already rejected; reject plain english+digit
        if re.match(r"^\d+(?:\.\d+)?[a-z]{1,3}$", t) and t.lower()[-1] in "aivwc":
            return False
        return True
    # alphabetic-only catalogue codes, only when shaped like one: HGD-M, EPC/PF, RR-VTS
    if has_alpha and ALPHA_CODE.match(t) and upperish(t):
        if all(is_stop_alpha(part) for part in re.split(r"[-/]", t)):
            return False
        return True
    return False


def join_hyphens(tokens):
    """'PRW08 - 2DP' -> 'PRW08-2DP';  'SRC1- 1220' -> 'SRC1-1220'."""
    out = []
    i = 0
    while i < len(tokens):
        if (0 < i < len(tokens) - 1 and tokens[i] == "-"
                and out and re.match(r"^[A-Za-z0-9][A-Za-z0-9\-/]*$", out[-1])
                and re.match(r"^[A-Za-z0-9][A-Za-z0-9\-/]*$", tokens[i + 1])):
            out[-1] = out[-1] + "-" + tokens[i + 1]
            i += 2
            continue
        if (out and out[-1].endswith("-") and len(out[-1]) > 1
                and re.match(r"^[A-Za-z0-9][A-Za-z0-9\-/]*$", out[-1])
                and re.match(r"^[A-Za-z0-9][A-Za-z0-9\-/]*$", tokens[i])):
            out[-1] = out[-1] + tokens[i]
            i += 1
            continue
        out.append(tokens[i])
        i += 1
    return out


# tokens that end a multi-token model printed behind a "Model:" marker
MARKER_BREAK = [NOT_MODEL[0],                                   # 16A, 230VAC, 5.5KW
                re.compile(r"^\d+(?:\.\d+)?/\d"),               # 1/4", 1200/5A
                re.compile(r"^\d+\s*[x×]", re.I),               # 96x96mm
                re.compile(r"^ip\d{2}$", re.I),
                re.compile(r"^\d+[-~]\d+$"),                    # 20-30 (numeric range)
                re.compile(r"^\d{1,3}(?:,\d{3})+$")]


def tidy_model(model):
    model = model.strip(" .,:;")
    model = re.sub(r"[\*\+]+$", "", model).strip()
    model = re.sub(r"[\(\[]$", "", model).strip()
    return model


def model_after_marker(tokens):
    """Model printed behind an explicit 'Model:' / 'Type:' / 'Cat.No:' marker."""
    first = clean_token(tokens[0]) if tokens else ""
    if len(first) < 2 or not CODE_CHARS.match(first):
        return None
    if first.isalpha() and (is_stop_alpha(first) or not upperish(first)):
        return None
    parts = [first]
    for i, tok in enumerate(tokens[1:4], start=1):
        if tok.startswith("("):
            break              # "(2CO)", "(96x96mm)" - a note, not part of the model
        t = clean_token(tok)
        if len(t) < 2 or not CODE_CHARS.match(t):
            break
        if t.lower() in UNIT_WORD or any(rx.match(t) for rx in MARKER_BREAK):
            break
        has_digit = any(c.isdigit() for c in t)
        if not has_digit and (is_stop_alpha(t) or not upperish(t)):
            break
        if has_digit and not any(c.isalpha() for c in t):
            # a bare number continues the model only when what follows is not a unit
            # ("EXP10 12 Opto-isolated..." yes; "FL1D 25 KVAR" no)
            nxt = clean_token(tokens[i + 1]) if i + 1 < len(tokens) else ""
            if (nxt.lower() in UNIT_WORD
                    or (nxt and any(rx.match(nxt) for rx in MARKER_BREAK))):
                break
        parts.append(t)
    return tidy_model(" ".join(parts))


def model_from(left, sno=None):
    """Find the printed catalogue number in the text left of the price."""
    seg = ENUM.sub("", left).strip()

    # ---- per-section printed formats (all read text printed on that same line) ----
    if sno == 31:            # SOCOMEC: catalogue numbers printed as "2600 3121"
        m = re.search(r"(?<![\d/])(\d{4}\s+\d{4})(?![\d/])", seg)
        if m:
            return norm(m.group(1))
    if sno == 18:            # LOVATO DOL starters: "M0 P009 12 400 2V3  0.75KW/ 1hp ..."
        m = re.match(r"^(M\d\s+P\d{3}\s+\d+\s+\d+\s+\S+)\s", seg)
        if m:
            return norm(m.group(1))
    if sno == 36:            # FINDER: type numbers printed as "40.51", "72.501"
        m = re.search(r"(?<![\d.])(\d{2,3}(?:\.\d{1,3}){1,2})(?![\d])", seg)
        if m:
            return m.group(1)
    gm = GROUP_RE.match(seg)  # ETI / DF ELECTRIC fuses: "Group : 00C  Ratings : ..."
    if gm and gm.group(2).strip():
        val = norm(gm.group(2)).rstrip(":,").strip()
        val = re.sub(r"[^A-Za-z0-9)\]]+$", "", val).strip()
        if val and len(val) <= 24:
            return norm("%s %s" % (gm.group(1).title(), val))

    marked = False
    m = MARKER.search(seg)
    if m:
        tail = seg[m.end():].strip()
        if tail:
            seg, marked = tail, True

    tokens = join_hyphens(seg.split())
    if not tokens:
        return None

    if marked:
        mm = model_after_marker(tokens)
        if mm and len(mm) >= 2:
            return mm

    for i, tok in enumerate(tokens):
        t = clean_token(tok)
        if not t:
            continue
        if "," in tok:
            # "UAB60R,UAB100C" - several models printed on one line, keep the first
            head = clean_token(tok.split(",")[0])
            if head and looks_like_code(head):
                t = head
        # pure-numeric catalogue number (FAMATEL 23200) - only as first token
        if i == 0 and re.fullmatch(r"\d{4,6}", t):
            nxt = clean_token(tokens[1]) if len(tokens) > 1 else ""
            if nxt.lower().rstrip(".") not in UNIT_WORD:
                return t
        # "BGX 1022+", "HiMC 300": a short code whose number is printed apart
        if not marked and i > 0 and re.fullmatch(r"\d{3,5}", t):
            prev = clean_token(tokens[i - 1])
            nxt = clean_token(tokens[i + 1]) if i + 1 < len(tokens) else ""
            if (2 <= len(prev) <= 8 and prev.isalpha() and upperish(prev)
                    and not is_stop_alpha(prev) and prev.lower() not in UNIT_WORD
                    and nxt.lower().rstrip(".") not in UNIT_WORD):
                return tidy_model(prev + " " + t)
        if not looks_like_code(t):
            continue
        model = t
        # glue a short alphabetic prefix printed as its own token: "S 1000SE"
        if not marked and i > 0 and re.match(r"^\d", model):
            prev = clean_token(tokens[i - 1])
            if (2 <= len(prev) <= 8 and prev.isalpha() and upperish(prev)
                    and prev.lower() not in UNIT_WORD
                    and not is_stop_alpha(prev)
                    and prev.lower() not in ("for", "and", "the", "with", "type", "model",
                                             "series", "size", "set", "each", "new", "to",
                                             "or", "of", "up", "at", "in", "on", "per")):
                model = prev + " " + model
            elif len(prev) == 1 and prev.isalpha() and prev.isupper():
                model = prev + " " + model
        model = tidy_model(model)
        if len(model) >= 2:
            return model

    # last resort: "HiMCOL 500W", "HGCTIP 130", "UMCTIP 40" - an alphabetic code whose
    # size is printed as a separate token. Only used when the line carries no ordinary
    # catalogue number at all, so it can never override a real code (e.g. it must not
    # turn "AMMETERS: 96 x 96mm (4 Digit) DH3EM" into "AMMETERS 96").
    for i, tok in enumerate(tokens[:-1]):
        t = clean_token(tok)
        if t.isalpha() and len(t) >= 4 and upperish(t) and not is_stop_alpha(t):
            nxt = clean_token(tokens[i + 1])
            if nxt and nxt[:1].isdigit():
                return tidy_model(t + " " + nxt)
    return None


# --------------------------------------------------------------------------
# specs
# --------------------------------------------------------------------------
AMP = re.compile(r"(?<![A-Za-z0-9\./])(\d+(?:\.\d+)?)\s*(?:A\b|Amps?\b|AMPS?\b|amp\b)")
# "3, 5 & 10 Amps" / "16, 20, 25. 32 & 40A" - one price covering several printed ratings
AMP_LIST = re.compile(r"(?<![A-Za-z0-9\./])((?:\d+(?:\.\d+)?\s*(?:[,&]|\.\s)\s*)+\d+(?:\.\d+)?)"
                      r"\s*(?:A\b|Amps?\b|AMPS?\b)")
AMP_SPLIT = re.compile(r"\s*[,&]\s*|\.\s+")
VOLT = re.compile(r"(?<![A-Za-z0-9\.])(\d{2,4})\s*V(AC|DC)?\b")
KA = re.compile(r"(?<![A-Za-z0-9\.])(\d+(?:\.\d+)?)\s*KA\b", re.I)
POLES = re.compile(r"(?<![A-Za-z0-9])(\d)\s*-?\s*(?:P\b|Pole[s]?\b)", re.I)
IPR = re.compile(r"\bIP\d{2}\b")
FREQ = re.compile(r"\b(50/60\s*Hz|50\s*Hz|60\s*Hz)\b", re.I)
SENS = re.compile(r"\b(\d+(?:\.\d+)?)\s*mA\b")
CT_RATIO = re.compile(r"(?<![A-Za-z0-9\./])(\d{1,5}\s*/\s*[15])\s*A\b")     # 1200/5A
BURDEN = re.compile(r"(?<![A-Za-z0-9\.])(\d+(?:\.\d+)?)\s*VA\b")
SET_RANGE = re.compile(r"(?<![A-Za-z0-9\./])(\d+(?:\.\d+)?)\s*(?:A\s*)?(?:to|~|\-\-|–)\s*"
                       r"(\d+(?:\.\d+)?)\s*A\b")
POWER_KW = re.compile(r"(?<![A-Za-z0-9\.])(\d+(?:\.\d+)?)\s*KW\b", re.I)
SERIES_HEAD = re.compile(r"([A-Za-z][A-Za-z0-9\-\+]{1,15})\s+Series\b", re.I)


def build_specs(line, model, series_hint):
    specs = {}
    amps = []
    covered = []
    for m in AMP_LIST.finditer(line):
        covered.append((m.start(), m.end()))
        amps.extend(x.strip() for x in AMP_SPLIT.split(m.group(1)) if x.strip())
    for m in AMP.finditer(line):
        if any(s <= m.start() < e for s, e in covered):
            continue
        amps.append(m.group(1))
    if amps:
        uniq = []
        for a in amps:
            if a not in uniq:
                uniq.append(a)
        specs["rating"] = uniq[0] + "A"
        if len(uniq) > 1:
            specs["rating_list"] = [a + "A" for a in uniq]
    m = VOLT.search(line)
    if m:
        specs["voltage"] = m.group(1) + "V" + (m.group(2) or "")
    m = KA.search(line)
    if m:
        specs["breaking_capacity"] = m.group(1) + "kA"
    m = POLES.search(line)
    if m:
        specs["poles"] = m.group(1) + "P"
    m = IPR.search(line)
    if m:
        specs["ip_rating"] = m.group(0)
    m = FREQ.search(line)
    if m:
        specs["frequency"] = norm(m.group(1))
    m = SENS.search(line)
    if m:
        specs["sensitivity"] = m.group(1) + "mA"
    m = CT_RATIO.search(line)
    if m:
        specs["ct_ratio"] = norm(m.group(1)).replace(" ", "") + "A"
    m = BURDEN.search(line)
    if m:
        specs["burden"] = m.group(1) + "VA"
    m = SET_RANGE.search(line)
    if m:
        specs["setting_range"] = "%s-%sA" % (m.group(1), m.group(2))
    m = POWER_KW.search(line)
    if m:
        specs["power"] = m.group(1) + "KW"
    specs["series"] = series_for(model, series_hint)
    return specs


def series_for(model, series_hint):
    """Product family used to group ampere variants of one product.

    Priority: a printed "<X> Series" heading when the model actually starts with X
    (strong evidence), then the model stem printed before the size suffix
    ("YPN312/100" -> "YPN312", "TX4S-14R" -> "TX4S", "40.51" -> "40"), else the
    model itself.  The section heading is never used as the family when it does
    not match the model - that would group unrelated products together.
    """
    base = model.strip()
    if series_hint:
        h = series_hint.rstrip("-").upper().replace(" ", "")
        flat = base.upper().replace(" ", "")
        # only when the heading really names this model's family AND is not so short
        # that it would fuse unrelated frames ("HG" would swallow HGM100E + HGE250S)
        if h and flat.startswith(h) and len(flat) - len(h) <= 4:
            return series_hint
    if re.fullmatch(r"\d{2}\.\d{1,3}", base):        # FINDER 40.51 -> series 40
        return base.split(".")[0]
    if "/" in base:
        stem = base.split("/")[0].strip()
        if len(stem) >= 2:
            return stem
    m = re.match(r"^([A-Za-z][A-Za-z0-9]{1,7})-\d", base)
    if m:
        return m.group(1)
    return base


# --------------------------------------------------------------------------
# headings
# --------------------------------------------------------------------------
PAGE_HDR = re.compile(r"^\s*Ref\.?\s*No|^\s*\d{1,2}(?:st|nd|rd|th)?\s+\w+\s+20\d\d\s*$|"
                      r"^\s*Page\s*No|^\s*-\s*\d+\s*-\s*$|^\s*\d{1,3}\s*$", re.I)
COLHDR = re.compile(r"\bprice\b|\bunit\s*price\b|\blist\s*price\b|price-each", re.I)
BULLET = re.compile(r"^\s*[\?\u2022\u25cf\*\u25a0\u2013\u2014]")
NOTE_LINE = re.compile(r"^\s*(NOTE|Note|NOTES|Notes)\b")


def is_heading(text):
    t = norm(text)
    if not t or len(t) > 110:
        return False
    if PAGE_HDR.match(t) or COLHDR.search(t) or BULLET.match(t) or NOTE_LINE.match(t):
        return False
    letters = [c for c in t if c.isalpha()]
    if len(letters) < 3:
        return False
    upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
    if t.endswith(":"):
        return True
    if upper_ratio >= 0.6:
        return True
    if re.match(r"^(?:\(?(?:[IVXivx]{1,5}|[A-Za-z]|\d{1,2})[\.\)])\s+[A-Z]", t):
        return True
    return False


# --------------------------------------------------------------------------
# index (pages 1-3)
# --------------------------------------------------------------------------
def read_index(doc):
    idx = {}
    for pno in INDEX_PAGES:
        for tab in doc[pno].find_tables().tables:
            for r in tab.extract():
                if not r or not r[0]:
                    continue
                m = re.fullmatch(r"\s*(\d{1,2})\s*", r[0] or "")
                if not m:
                    continue
                n = int(m.group(1))
                brand = norm((r[2] or "").replace("\n", " "))
                brand = re.sub(r"\s*/\s*", "/", brand)
                desc = norm((r[3] or "").replace("\n", " "))
                country = norm((r[4] or "").replace("\n", " "))
                if n not in idx:
                    idx[n] = {"ref": norm((r[1] or "").replace("\n", "")),
                              "brand": brand or FALLBACK_BRAND,
                              "desc": desc,
                              "country": country}
    return idx


HDR_RE = re.compile(r"Ref\.?\s*No\.?\s*:?\s*([A-Za-z]{2,4}\s?\d{2})\s*/\s*S\.?\s*No\.?\s*:?\s*(\d+)")


# --------------------------------------------------------------------------
def main():
    doc = fitz.open(PDF_PATH)
    n_pages = doc.page_count
    index = read_index(doc)

    rows = []
    skipped = []
    raw_priced_per_page = {}

    prev_sno = None
    section = ""
    series_hint = ""

    for pno in range(3, n_pages):                     # pages 4..259 (1-based)
        page = doc[pno]
        pageno = pno + 1
        lines = ylines(page)
        text = page.get_text()
        m = HDR_RE.search(text)
        sno = int(m.group(2)) if m else None
        meta = index.get(sno, {"brand": FALLBACK_BRAND, "desc": "", "country": "", "ref": ""})
        brand = meta["brand"] or FALLBACK_BRAND
        if sno != prev_sno:                            # new catalogue section
            section = meta["desc"]
            series_hint = ""
            prev_sno = sno

        n_priced_here = 0

        for li, ln in enumerate(lines):
            raw = norm(ln["text"])
            if not raw:
                continue
            if PAGE_HDR.match(raw) and not find_prices(raw):
                continue
            hits = find_prices(raw)
            if not hits:
                if BARE_CELL.search(raw):
                    # printed price cells with no "Rs." marker: the 7-column accessory
                    # matrices (Terasaki p9 etc.). Which frame column each cell belongs
                    # to cannot be read off the line, so nothing is emitted - but the
                    # line is recorded rather than silently dropped.
                    n_priced_here += 1
                    skipped.append({"page": pageno, "raw": raw,
                                    "reason": "printed price cell(s) without an 'Rs.' marker: "
                                              "multi-column accessory matrix, price cannot be "
                                              "attributed to a single catalogue number"})
                    continue
                if is_heading(raw):
                    section = raw
                    sm = SERIES_HEAD.search(raw)
                    if sm:
                        series_hint = sm.group(1)
                continue

            n_priced_here += 1
            left = raw[:hits[0][0]].strip()
            model = model_from(left, sno)
            if model is None:
                # the printed line may put the model to the right of the price
                right = raw[hits[-1][1]:].strip()
                model = model_from(right, sno) if right else None
            if model is None:
                skipped.append({"page": pageno, "raw": raw,
                                "reason": "priced line with no identifiable catalogue number "
                                          "(model not printed on this line) - not guessed"})
                continue

            multi = len(hits) > 1
            col_header = ""
            if multi:
                for back in range(li - 1, max(-1, li - 8), -1):
                    cand = norm(lines[back]["text"])
                    if COLHDR.search(cand) or re.search(r"\bRoll\b|\bMeter\b", cand, re.I):
                        col_header = cand
                        break

            for ci, (s, e, value, kind) in enumerate(hits, start=1):
                specs = build_specs(raw, model, series_hint)
                notes = []
                if kind == "onrequest":
                    notes.append('PDF prints "On Request" instead of a price for this line')
                if kind == "paren":
                    notes.append("price printed in brackets as a component of the "
                                 "assembly example on this page")
                if multi:
                    specs["price_column"] = "%d of %d" % (ci, len(hits))
                    if col_header:
                        specs["price_column_header"] = col_header
                    notes.append("this printed line carries %d price columns; one row is "
                                 "emitted per printed price" % len(hits))
                if notes:
                    specs["note"] = "; ".join(notes)

                if value is not None and (value < 10 or value > 10_000_000):
                    skipped.append({"page": pageno, "raw": raw,
                                    "reason": "sanity: price %d outside 10..10,000,000" % value})
                    continue

                rows.append({
                    "page": pageno,
                    "brand": brand,
                    "section": norm(section) or meta["desc"],
                    "model": model,
                    "description": raw,
                    "price_pkr": value,
                    "specs": specs,
                    "_raw": raw,
                    "_sno": sno,
                })
        raw_priced_per_page[pageno] = n_priced_here

    # ---------------------------------------------------------------- dedupe
    # An identical printed line (same model, specs, price and text) repeated in the PDF
    # is emitted once - e.g. the LOVATO assembly examples list the same mounting adaptor
    # on four pages.  Rows that share a model and price but come from DIFFERENT printed
    # lines are all kept: the printed line is the only complete record of what
    # distinguishes them (CT ratio, pole count from the section, motor rating, ...),
    # and dropping one would silently delete a real catalogue entry.
    seen = {}
    deduped = []
    for r in rows:
        key_specs = {k: v for k, v in r["specs"].items() if k not in ("note",)}
        key = (r["model"], json.dumps(key_specs, sort_keys=True), r["price_pkr"],
               r["description"])
        if key in seen:
            skipped.append({"page": r["page"], "raw": r["_raw"],
                            "reason": "duplicate: same model, same specs and same price as "
                                      "the row already emitted from page %d" % seen[key]["page"]})
            continue
        seen[key] = r
        deduped.append(r)
    rows = deduped

    prices = [r["price_pkr"] for r in rows if r["price_pkr"] is not None]

    # ------------------------------------------------------------ validation
    # (0) provenance: every emitted price must be one of the prices printed on that
    #     row's own line.  This makes it impossible for a price to have been carried
    #     over from a neighbouring row.
    for r in rows:
        printed = [v for _, _, v, _ in find_prices(r["description"])]
        if r["price_pkr"] not in printed:
            raise RuntimeError("price %r not printed on its own line: %r"
                               % (r["price_pkr"], r["description"]))

    p("=== coverage: priced lines in the rebuilt raw text vs rows emitted ===")
    p("  (raw priced lines counted independently: any line printing a price cell)")
    for pg in COVERAGE_PAGES:
        parsed = sum(1 for r in rows if r["page"] == pg)
        skp = sum(1 for s in skipped if s["page"] == pg)
        p("  page %d: raw priced lines=%d  rows emitted=%d  skipped=%d"
          % (pg, raw_priced_per_page.get(pg, 0), parsed, skp))
    random.seed(11)
    for pg in sorted(random.sample([pg for pg, c in raw_priced_per_page.items() if c > 0], 3)):
        parsed = sum(1 for r in rows if r["page"] == pg)
        skp = sum(1 for s in skipped if s["page"] == pg)
        p("  page %d: raw priced lines=%d  rows emitted=%d  skipped=%d"
          % (pg, raw_priced_per_page[pg], parsed, skp))
    tot_raw = sum(raw_priced_per_page.values())
    p("  ALL pages: raw priced lines=%d  rows=%d  skipped=%d" % (tot_raw, len(rows), len(skipped)))

    p("=== price sanity ===")
    p("  min=%d median=%s max=%d  (priced rows=%d, null-price rows=%d)"
      % (min(prices), statistics.median(prices), max(prices), len(prices),
         len(rows) - len(prices)))

    p("=== rows per brand ===")
    for b, c in Counter(r["brand"] for r in rows).most_common():
        p("  %-22s %d" % (b, c))

    p("=== spot-check: 10 random rows with their source line ===")
    random.seed(5)
    for r in random.sample(rows, 10):
        p("  p%-4d %-20s %-10s %s" % (r["page"], r["model"], r["price_pkr"], r["brand"]))
        p("       raw : %s" % r["_raw"])
        p("       spec: %s" % r["specs"])

    p("=== skipped reasons ===")
    for reason, c in Counter(re.split(r"[:(]", s["reason"])[0] for s in skipped).most_common():
        p("  %-60s %d" % (reason.strip(), c))

    for r in rows:
        del r["_raw"]
        del r["_sno"]

    out = {
        "source_pdf": os.path.basename(PDF_PATH),
        "rows": rows,
        "skipped": skipped,
        "stats": {"pages": n_pages, "rows": len(rows),
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
