# -*- coding: utf-8 -*-
"""
Faithful extractor for "Price List AVS ABB OCTOBER 2019.pdf" (28 pages).
Brand: ABB (distributor: Ameejee Valleejee & Sons, Karachi). All prices PKR.

Layout notes (verified by pdfplumber word-position probes):
- Text extraction is clean; rows are single text lines except the cases below.
- p3/p4 (MCB): model cell is vertically merged across the rating ladder; the model
  prints on its own line in the middle of each block ("SH 201 1 Pole / 6KA" / "S 201").
  Rows inherit the block's model — justified: the PDF visually merges the MODEL cell.
- p5 (RCCB): "2 Pole"/"4 Pole" is a merged POLE cell printed once per group; poles are
  also encoded in the model (FH202=2P, FH204=4P). First row's AMPERE cell is blank in
  the PDF (verified by word positions); rating derived from model suffix "-025" and the
  identical model on the adjacent line — noted in specs.note.
- p6/p7 (Formula): long rating lists wrap; a line ending "," continues on the next line.
- p8 (Formula accessories): FOR column ("A1~A2", "A3") is a merged cell printed once in
  the middle of each 5-row group — group membership assigned by position (rows 1-5 =
  A1~A2, rows 6-10 = A3), justified: the PDF visually merges the FOR cell.
- p11/p12/p14 (T MAX motorized rows): rating cell wraps to 2-3 lines ("1250 A *" /
  "for motorized"); stitched back together.
- p15: an orphan price "19,200" sits in the price column of the UNDER VOLTAGE RELEASE
  section with NO model/description on its line (verified by word positions) -> skipped.
- p21 (interlocks): TYPE cell wraps around the priced line ("Mechanical &" above,
  "Electrical" below); stitched from adjacent fragment lines.
- Model cells split by column spacing ("AX09- 30- 10", "FH202 -025", "VM - 750H") are
  rejoined by collapsing whitespace adjacent to hyphens INSIDE the model cell only.
"""
import json
import random
import re
import statistics
import sys
from pathlib import Path

import pdfplumber

PDF = Path(r"C:/Users/AWCD/Desktop/client/engmart (2)/product-details/Price List AVS ABB OCTOBER 2019.pdf")
OUT = Path(r"C:/Users/AWCD/Desktop/client/engmart (2)/backend/extraction/out/abb-avs.json")

BRAND = "ABB"


def p(s=""):
    print(str(s).encode("ascii", "replace").decode())


def clean_model(s):
    """Collapse whitespace adjacent to hyphens inside a model cell: 'AX09- 30- 10' -> 'AX09-30-10'."""
    return re.sub(r"\s*-\s*", "-", s).strip()


def price_num(tok):
    """'8,800' -> 8800 ; 'On Request'/'ON REQUEST' -> None."""
    if re.fullmatch(r"[\d,]+", tok):
        return int(tok.replace(",", ""))
    return None


FOOTER_RES = [
    re.compile(r"^Power and productivity"),
    re.compile(r"^for a better world"),
    re.compile(r"^Note: The prices are subject"),
    re.compile(r"^This price list supersedes"),
    re.compile(r"^\d{2}`?$"),          # printed page number like "03" / "18`"
    re.compile(r"^MADE IN ", re.I),
    re.compile(r"^Made in ", re.I),
    re.compile(r"^According to IEC"),
]


def is_footer(line):
    return any(r.match(line) for r in FOOTER_RES)


rows = []
skipped = []


def add_row(page, section, model, description, price, specs, raw):
    rows.append({
        "page": page, "brand": BRAND, "section": section, "model": model,
        "description": description, "price_pkr": price, "specs": specs, "_raw": raw,
    })


def add_skip(page, raw, reason):
    skipped.append({"page": page, "raw": raw, "reason": reason})


# ---------------------------------------------------------------- p3: MCB 6kA (SH 200)
def parse_p3(page, lines):
    section = "Miniature Circuit Breakers 6KA"
    block_hdr = re.compile(r"^([1-4]) POLE MODEL")
    model_re = re.compile(r"^(SH ?20\d)\s+(\d) Pole / (\d+)KA$")
    row_re = re.compile(r"^(\d+A~\d+A|\d+A)\s+([\d,]+|On Request)$")
    # two passes: first find model per block, then emit rating rows
    blocks, cur = [], None
    for ln in lines:
        if block_hdr.match(ln):
            cur = {"lines": []}
            blocks.append(cur)
        elif cur is not None:
            cur["lines"].append(ln)
    for blk in blocks:
        model = poles = bc = None
        for ln in blk["lines"]:
            m = model_re.match(ln)
            if m:
                model = clean_model(m.group(1)) if "-" in m.group(1) else m.group(1).strip()
                poles, bc = m.group(2) + "P", m.group(3) + "KA"
        for ln in blk["lines"]:
            if model_re.match(ln) or ln == "PKR":
                continue
            m = row_re.match(ln)
            if not m:
                add_skip(page, ln, "unparsed line in MCB 6KA block")
                continue
            rating, ptok = m.group(1), m.group(2)
            price = price_num(ptok)
            specs = {"rating": rating, "poles": poles, "breaking_capacity": bc,
                     "series": model, "made_in": "Germany"}
            if price is None:
                specs["note"] = "On Request"
            add_row(page, section, model,
                    f"Miniature Circuit Breaker 6KA {model} {poles.replace('P',' Pole')} / {bc} - {rating}",
                    price, specs, ln)


# ---------------------------------------------------------------- p4: MCB 10kA (S 200)
def parse_p4(page, lines):
    section = "Miniature Circuit Breakers 10KA"
    block_hdr = re.compile(r"^([1-4]) POLE\b")
    model_re = re.compile(r"^(S ?20\d)$")
    merged_re = re.compile(r"^(\d+A ?[~,] ?\d+A)\s+(\d) Pole / (\d+)KA\s+([\d,]+|On Request)$")
    row_re = re.compile(r"^(\d+A ?[~,] ?\d+A|\d+A)\s+([\d,]+|On Request)$")
    blocks, cur = [], None
    for ln in lines:
        bh = block_hdr.match(ln)
        if bh:
            cur = {"poles": bh.group(1) + "P", "lines": []}
            blocks.append(cur)
        elif cur is not None:
            cur["lines"].append(ln)
    for blk in blocks:
        model, bc = None, "10KA"
        pend = []  # (rating, price_tok, raw)
        for ln in blk["lines"]:
            if ln in ("CAPACITY PRICE PKR", "PKR"):
                continue
            m = model_re.match(ln)
            if m:
                model = m.group(1)
                continue
            m = merged_re.match(ln)
            if m:
                pend.append((m.group(1), m.group(4), ln))
                bc = m.group(3) + "KA"
                continue
            m = row_re.match(ln)
            if m:
                pend.append((m.group(1), m.group(2), ln))
                continue
            add_skip(page, ln, "unparsed line in MCB 10KA block")
        for rating, ptok, raw in pend:
            price = price_num(ptok)
            specs = {"rating": rating, "poles": blk["poles"], "breaking_capacity": bc,
                     "series": model, "made_in": "Germany"}
            if price is None:
                specs["note"] = "On Request"
            add_row(page, section, model,
                    f"Miniature Circuit Breaker 10KA {model} {blk['poles'].replace('P',' Pole')} / {bc} - {rating}",
                    price, specs, raw)


# ---------------------------------------------------------------- p5: RCCB (FH200)
def parse_p5(page, lines):
    section = "Residual Current Circuit Breakers"
    row_re = re.compile(r"^(FH20[24]) (-0\d{2})\s+(?:(\d+A)\s+)?(\d+mA)\s+([\d,]+)$")
    for ln in lines:
        if re.match(r"^[24] Pole$", ln) or ln.startswith("MODEL POLE") or ln.startswith("SENSIVITY"):
            continue  # merged POLE cell label / table header
        m = row_re.match(ln)
        if not m:
            add_skip(page, ln, "unparsed line on RCCB page")
            continue
        fam, suffix, ampere, sens, ptok = m.groups()
        model = clean_model(fam + " " + suffix)
        poles = "2P" if fam == "FH202" else "4P"
        specs = {"poles": poles, "current_sensitivity": sens, "series": fam, "made_in": "Italy"}
        if ampere:
            specs["rating"] = ampere
        else:
            # PDF's AMPERE cell is blank on this line (verified by word positions);
            # rating is encoded in the printed model suffix -025 = 25A (same model on
            # the adjacent printed line shows 25A).
            specs["rating"] = "25A"
            specs["note"] = "AMPERE cell blank in PDF; 25A per model suffix -025"
        add_row(page, section, model,
                f"Residual Current Circuit Breaker {model} {poles.replace('P',' Pole')} {specs['rating']} {sens}",
                price_num(ptok), specs, ln)


# ------------------------------------------------- p6/p7: Formula MCCB fixed (A1/A2/A3)
def parse_formula(page, lines, poles):
    section = f"New Sace Formula Series MCCB {poles} Fixed Type"
    sec_re = re.compile(r'^BREAKING CAPACITY ICU "(\d+KA)"$')
    row_re = re.compile(
        r"^(?P<rating>\d[\dA, ]*?A?)\s+(?P<model>A\d[A-Z] \d+)\s*(?P<ka>\(10kA\))?\s+"
        r"(?P<ics>\d+%)\s+(?P<price>[\d,]+|On Request)$")
    icu = None
    pending_rating = ""
    for ln in lines:
        if ln.startswith("RATING MODEL") or ln.endswith("PKR") and "415VAC" in ln:
            continue
        s = sec_re.match(ln)
        if s:
            icu = s.group(1)
            continue
        if ln.endswith(","):            # wrapped rating list, continues next line
            pending_rating = ln
            continue
        full = (pending_rating + " " + ln) if pending_rating else ln
        m = row_re.match(full)
        pending_rating = ""
        if not m:
            add_skip(page, ln, "unparsed line on Formula page")
            continue
        rating = re.sub(r"\s+", " ", m.group("rating")).strip()
        model = m.group("model")
        price = price_num(m.group("price"))
        specs = {"rating": rating, "poles": poles.replace("Pole", "P"),
                 "breaking_capacity": icu, "ics": m.group("ics"),
                 "series": "Formula " + model.split()[0], "made_in": "Italy"}
        if m.group("ka"):
            specs["icu_marked"] = "(10kA)"   # printed next to A1A 125 row
        if price is None:
            specs["note"] = "On Request"
        add_row(page, section, model,
                f"Sace Formula MCCB {poles} Fixed {model} ICU {icu} ICS {m.group('ics')} - {rating}",
                price, specs, full)


# ---------------------------------------------------- p8: Formula accessories (A1~A3)
def parse_p8(page, lines):
    section = "Accessories for Sace Formula"
    row_re = re.compile(r"^(?P<desc>.+?)\s+(?P<volt>220-250VAC/DC|-{4,})\s+(?P<price>[\d,]+)$")
    parsed = []
    for ln in lines:
        if ln.startswith("AVAILABLE") or ln.startswith("DESCRIPTION ACCESSORY") or ln == "VOLTAGE PKR":
            continue
        m = row_re.match(ln)
        if not m:
            add_skip(page, ln, "unparsed line on Formula accessories page")
            continue
        parsed.append((m, ln))
    # FOR column is a merged cell: first 5 rows belong to A1~A2, next 5 to A3
    # (labels "A1~A2" and "A3" print once mid-group in the PDF).
    for i, (m, ln) in enumerate(parsed):
        desc = m.group("desc")
        for_model = "A1~A2" if i < 5 else "A3"
        desc_clean = re.sub(r"\s+(A1~A2|A3)$", "", desc)
        specs = {"for_model": for_model, "series": "Formula Accessories", "made_in": "Italy"}
        if m.group("volt").startswith("220"):
            specs["voltage"] = m.group("volt")
        add_row(page, section, desc_clean,
                f"Sace Formula Accessory ({for_model}): {desc_clean}"
                + (f" {specs['voltage']}" if "voltage" in specs else ""),
                price_num(m.group("price")), specs, ln)


# ------------------------------------------------------- p9-14: T MAX MCCB adjustable
def parse_tmax(page, lines, poles):
    section = f"T MAX Series MCCB {poles} Thermo Magnetic and Electronic (Adjustable)"
    sec_re = re.compile(r'^(?:HIGH )?BREAKING CAPACITY ICU "(\d+KA)"$')
    row_re = re.compile(
        r"^(?:for motorized )?(?P<rating>\d+ A)?(?: ?\*)?\s*(?P<range>[\d\.]+ ?~ ?\d+A)\s+"
        r"(?P<model>(?:XT|T)\d[A-Z]? \d+(?: M)?)\s+(?P<ttype>THERMAL|ELECTRONIC)\s+"
        r"(?P<ics>\d+%)\s+(?P<price>[\d,]+|On Request)$")
    pend_rating_re = re.compile(r"^(\d+ A) ?\*$")
    icu = None
    pend_rating = None
    for ln in lines:
        if ln.startswith("RATING ADJUSTABLE") or ln.startswith("RANGE ELECTRONIC"):
            continue
        if ln == "for motorized":
            continue  # wrapped fragment of the rating cell, already noted via model " M"
        if ln.startswith("* Spring Charging Motor") or ln.startswith("Breaking capacity of"):
            continue  # page footnotes
        s = sec_re.match(ln)
        if s:
            icu = s.group(1)
            continue
        pm = pend_rating_re.match(ln)
        if pm:
            pend_rating = pm.group(1)   # rating cell wrapped: "1250 A *"
            continue
        m = row_re.match(ln)
        if not m:
            add_skip(page, ln, "unparsed line on T MAX page")
            continue
        rating = m.group("rating") or pend_rating
        pend_rating = None
        if not rating:
            add_skip(page, ln, "row without rating on T MAX page")
            continue
        rating_c = rating.replace(" A", "A")
        model = m.group("model")
        motorized = model.endswith(" M")
        price = price_num(m.group("price"))
        specs = {"rating": rating_c, "poles": poles.replace("Pole", "P"),
                 "adjustable_range": m.group("range"), "breaking_capacity": icu,
                 "trip_unit": m.group("ttype"), "ics": m.group("ics"),
                 "series": "T MAX " + model.split()[0], "made_in": "Italy"}
        if motorized:
            specs["note"] = "for motorized"
        if price is None:
            specs["note"] = (specs.get("note", "") + "; On Request").lstrip("; ")
        add_row(page, section, model,
                f"T MAX MCCB {poles} {model} {m.group('ttype')} ICU {icu} ICS {m.group('ics')} - "
                f"{rating} (adjustable {m.group('range')})" + (" for motorized" if motorized else ""),
                price, specs, ln)


# ------------------------------------------------------------ p15: T MAX accessories
def parse_p15(page, lines):
    section = "Accessories for T MAX MCCBs"
    sub_re = re.compile(r"^(AUXILIARY CONTACTS|SHUNT OPENING RELEASE|UNDER VOLTAGE RELEASE|STORED ENERGY MOTOR)$")
    row_re = re.compile(
        r"^(?P<for>(?:XT|T)[\dXTM~/ \-]*?)\s+(?P<desc>(?:Auxiliary|Shunt|Under|Direct|Stored|Spring).+?)\s+(?P<price>[\d,]+)$")
    sub = None
    for ln in lines:
        if ln.startswith("FOR MODEL") or ln == "PKR" or ln.startswith("Note: Motor cannot"):
            continue
        s = sub_re.match(ln)
        if s:
            sub = s.group(1)
            continue
        if re.fullmatch(r"[\d,]+", ln):
            # orphan price in the price column with no model/description on its line
            add_skip(page, ln, "unattributed price in %s section (no model/description printed)" % sub)
            continue
        m = row_re.match(ln)
        if not m:
            add_skip(page, ln, "unparsed line on T MAX accessories page")
            continue
        for_model = m.group("for").strip()
        desc = m.group("desc").strip()
        specs = {"for_model": for_model, "series": "T MAX Accessories",
                 "accessory_type": sub.title() if sub else None, "made_in": "Italy"}
        volt = re.search(r"(\d+ ?- ?\d+V AC(?:/DC)?|220…240VAC|- \d+V AC(?:/DC)?)", desc)
        if volt:
            specs["voltage"] = volt.group(1).lstrip("- ")
        add_row(page, section, desc,
                f"T MAX MCCB Accessory ({for_model}): {desc}",
                price_num(m.group("price")), specs, ln)


# ----------------------------------------------------------------- p16/17: ACB (Emax)
def parse_acb(page, lines, poles):
    section = f"Air Circuit Breakers (ACB) {poles} Adjustable"
    sec_re = re.compile(r"^BREAKING CAP\. ICU (\d+ KA)$")
    row_re = re.compile(
        r"^(?P<rating>\d+) AMPS\s+(?P<range>\d+ ~ \d+A)\s+(?P<model>E\d\.\d[NH] \d+)\s+"
        r"(?P<icu>\d+ KA)\s+(?P<ics>\d+%)\s+(?P<price>[\d,]+|ON REQUEST)$")
    for ln in lines:
        if ln.startswith("RATING ADJUSTABLE") or ln.startswith("RANGE AT") or ln == "ICU ICS":
            continue
        if ln == "Other types available on request":
            continue
        if sec_re.match(ln):
            continue  # row carries its own ICU column value
        m = row_re.match(ln)
        if not m:
            add_skip(page, ln, "unparsed line on ACB page")
            continue
        model = m.group("model")
        price = price_num(m.group("price"))
        specs = {"rating": m.group("rating") + "A", "poles": poles.replace(" Pole", "P"),
                 "adjustable_range": m.group("range"), "breaking_capacity": m.group("icu").replace(" ", ""),
                 "ics": m.group("ics"), "series": "Emax " + model.split()[0], "made_in": "Italy"}
        if price is None:
            specs["note"] = "On Request"
        add_row(page, section, model,
                f"Air Circuit Breaker {poles} {model} ICU {m.group('icu')} ICS {m.group('ics')} - "
                f"{m.group('rating')} AMPS (adjustable {m.group('range')})",
                price, specs, ln)


# ------------------------------------------------------------- p18: ACB accessories
def parse_p18(page, lines):
    section = "Air Circuit Breakers (ACB) Optional Accessories"
    row_re = re.compile(r"^(?P<desc>.+?)\s+(?P<price>[\d,]+|On Request)$")
    for ln in lines:
        if ln in ("UNIT PRICE", "PKR", "ACCESSORY DESCRIPTION"):
            continue
        if ln.startswith("Accessories for other voltages") or ln.startswith("24VDC,"):
            continue  # availability notes, not priced items
        m = row_re.match(ln)
        if not m:
            add_skip(page, ln, "unparsed line on ACB accessories page")
            continue
        desc = m.group("desc")
        price = price_num(m.group("price"))
        specs = {"series": "ACB Accessories", "made_in": "Italy"}
        code = re.search(r"\b(Y[UOC])\b", desc)
        if code:
            specs["code"] = code.group(1)
        volt = re.search(r"(\d+…\d+V(?: AC/DC| AC)?|220/250VAC)", desc)
        if volt:
            specs["voltage"] = volt.group(1)
        if price is None:
            specs["note"] = "On Request"
        add_row(page, section, desc, f"ACB Optional Accessory: {desc}", price, specs, ln)


# ---------------------------------------------------------- p19: 3P contactors AX/AF
def parse_p19(page, lines):
    section = "3 Pole Magnetic Contactors"
    row_re = re.compile(
        r"^(?P<model>A[XF]\d+- ?30- ?1[01])\s+(?P<aux>\d ?NO(?:\+\d ?NC)?)\s+"
        r"(?P<kw>[\d\.]+ / [\d\.]+)\s+(?P<amp>\d+)\s+(?P<ith>\d+)\s+(?P<price>[\d,]+)$")
    for ln in lines:
        if ln.startswith("MODEL AUXILIARY") or ln.startswith("CONTACTS KW/HP") or ln in ("AMPERE", "AC-3", "AC-1"):
            continue
        m = row_re.match(ln)
        if not m:
            add_skip(page, ln, "unparsed line on 3P contactors page")
            continue
        model = clean_model(m.group("model"))
        specs = {"rating": m.group("amp") + "A", "poles": "3P",
                 "auxiliary_contacts": m.group("aux"), "capacity_kw_hp": m.group("kw"),
                 "operational_current_ac3": m.group("amp") + "A", "ith_thermal_ac1": m.group("ith") + "A",
                 "series": model.split("-")[0][:2], "made_in": "France / Sweden / Bulgaria"}
        add_row(page, section, model,
                f"3 Pole Magnetic Contactor {model} {m.group('kw')} KW/HP {m.group('amp')}A AC-3 "
                f"(Ith {m.group('ith')}A) aux {m.group('aux')}",
                price_num(m.group("price")), specs, ln)


# ---------------------------------------------------------- p20: 4P contactors AF/EK
def parse_p20(page, lines):
    section = "4 Pole Magnetic Contactors"
    row_re = re.compile(
        r"^(?P<model>(?:AF|EK)\d+-40(?:-11)?)\s+(?P<kw>[\d\.]+(?: / [\d\.]+)?)\s+"
        r"(?P<amp>\d+)\s+(?P<price>[\d,]+)$")
    for ln in lines:
        if ln.startswith("MODEL CAPACITY") or ln.startswith("KW / HP") or ln == "690V AC-1":
            continue
        m = row_re.match(ln)
        if not m:
            add_skip(page, ln, "unparsed line on 4P contactors page")
            continue
        model = m.group("model")
        specs = {"rating": m.group("amp") + "A", "poles": "4P",
                 "capacity_kw_hp": m.group("kw"), "operational_current_690v_ac1": m.group("amp") + "A",
                 "series": model[:2], "made_in": "France / Sweden"}
        add_row(page, section, model,
                f"4 Pole Magnetic Contactor {model} {m.group('kw')} KW/HP {m.group('amp')}A at 690V AC-1",
                price_num(m.group("price")), specs, ln)


# ----------------------------------------------- p21: contactor accessories (3 tables)
def parse_p21(page, lines):
    aux_re = re.compile(
        r"^(?P<contacts>\d ?N[OC](?: ?\+ ?\d ?N[OC])?)\s+(?P<model>CA[A-Z0-9\-]+)\s+"
        r"(?P<mount>Front|Side)\s+(?P<range>A[XF]\d+ ~ A[XF]\d+)\s+(?P<price>[\d,]+)$")
    lock_re = re.compile(
        r"^(?P<model>V[ME] ?-? ?\d+(?:-\d+)?H?)\s+(?:(?P<type>Mechanical)\s+)?"
        r"(?P<range>A[XF] ?\d+ ~ A[XF] ?\d+)\s+(?P<price>[\d,]+)$")
    nf_re = re.compile(r"^(?P<model>NF\d+E)\s+(?P<arr>\d ?NO ?\+ ?\d ?NC)\s+(?P<price>[\d,]+)$")
    frag_re = re.compile(r"^(Mechanical ?&?|Electrical|Interlock)$")
    sub = None
    for i, ln in enumerate(lines):
        if ln.startswith("AUXILIARY CONTACTS"):
            sub = "aux"
            continue
        if ln.startswith("MECHANICAL INTERLOCKS"):
            sub = "lock"
            continue
        if ln.startswith("NF-CONTACTOR RELAYS"):
            sub = "nf"
            continue
        if ln.startswith("CONTACTS MODEL") or ln.startswith("MODEL TYPE RANGE") or ln.startswith("MODEL CONTACT"):
            continue
        if frag_re.match(ln):
            continue  # wrapped TYPE-cell fragments, consumed by lookaround below
        if sub == "aux":
            m = aux_re.match(ln)
            if not m:
                add_skip(page, ln, "unparsed line in contactor auxiliary contacts table")
                continue
            model = m.group("model")
            specs = {"contacts": m.group("contacts"), "mounting": m.group("mount"),
                     "for_range": m.group("range"), "series": "Contactor Accessories",
                     "made_in": "France / Sweden"}
            add_row(page, "Accessories for Contactors - Auxiliary Contacts", model,
                    f"Contactor Auxiliary Contact {model} {m.group('contacts')} {m.group('mount')} "
                    f"mounting for {m.group('range')}",
                    price_num(m.group("price")), specs, ln)
        elif sub == "lock":
            m = lock_re.match(ln)
            if not m:
                add_skip(page, ln, "unparsed line in mechanical interlocks table")
                continue
            model = clean_model(m.group("model"))
            # TYPE cell wraps around the priced line: fragment above + fragment below
            ttype = m.group("type")
            if not ttype:
                before = lines[i - 1] if i > 0 else ""
                after = lines[i + 1] if i + 1 < len(lines) else ""
                parts = []
                if frag_re.match(before):
                    parts.append(before)
                if frag_re.match(after):
                    parts.append(after)
                ttype = " ".join(parts) if parts else None
            specs = {"type": ttype, "for_range": m.group("range"),
                     "series": "Contactor Accessories", "made_in": "France / Sweden"}
            add_row(page, "Accessories for Contactors - Mechanical Interlocks (AF Series)", model,
                    f"Contactor Interlock {model} ({ttype}) for {m.group('range')}",
                    price_num(m.group("price")), specs, ln)
        elif sub == "nf":
            m = nf_re.match(ln)
            if not m:
                add_skip(page, ln, "unparsed line in NF contactor relays table")
                continue
            model = m.group("model")
            specs = {"contact_arrangement": m.group("arr"), "series": "NF Contactor Relays",
                     "made_in": "France"}
            add_row(page, "NF-Contactor Relays", model,
                    f"NF Contactor Relay {model} {m.group('arr')}",
                    price_num(m.group("price")), specs, ln)
        else:
            add_skip(page, ln, "line outside known table on contactor accessories page")


# -------------------------------------------------------- p22: thermal overload relays
def parse_p22(page, lines):
    section = "Thermal Over Load Relays"
    note = None
    for ln in lines:
        if ln in ("UNIT", "PKR") or ln.startswith("MODEL AMPERE"):
            continue
        if ln.startswith("For direct coupling"):
            note = ln
            continue
        toks = ln.split()
        model = None
        if re.fullmatch(r"T[AF]\d+", toks[0]):
            model, rest = toks[0], toks[1:]
        elif len(toks) > 2 and toks[0] in ("TA", "TF") and toks[1].isdigit():
            model, rest = toks[0] + " " + toks[1], toks[2:]
        if not model or not re.fullmatch(r"[\d,]+", toks[-1]):
            add_skip(page, ln, "unparsed line on thermal overload relays page")
            continue
        rng = " ".join(rest[:-1])
        specs = {"rating": rng, "ampere_range": rng, "series": model,
                 "made_in": "Germany / Bulgaria"}
        if note:
            specs["note"] = note
        add_row(page, section, model,
                f"Thermal Over Load Relay {model} {rng}" + (f" ({note})" if note else ""),
                price_num(toks[-1]), specs, ln)


# ----------------------------------------------------- p23/24: motor protection (MS)
def parse_mpcb(page, lines):
    sec_re = re.compile(r"^(MS \d+) SERIES$")
    row_re = re.compile(r"^(?P<model>MS1\d\d-[\d\.]+)\s+(?P<range>[\d\.]+~[\d\.]+A?)\s+(?P<bc>\d+ KA)\s+(?P<price>[\d,]+)$")
    acc_re = re.compile(
        r"^(?P<for>MS \d+(?:/ ?MS \d+)?)\s+(?P<model>[A-Z]+\d*-\d+)\s+(?P<arr>1NO ?\+ ?1NC)\s+"
        r"(?P<func>AUXILLIARY|SIGNAL)\s+(?P<mount>SIDE|FRONT)\s+(?P<price>[\d,]+)$")
    series = None
    in_acc = False
    for ln in lines:
        if ln.startswith("MODEL TYPE RANGE") or ln == "CONTACT" or ln.startswith("FOR MODEL FUNCTION") or ln == "ARRANGEMENT":
            continue
        s = sec_re.match(ln)
        if s:
            series, in_acc = s.group(1), False
            continue
        if ln == "ADD-ON ACCESSORIES":
            in_acc = True
            continue
        if in_acc:
            m = acc_re.match(ln)
            if not m:
                add_skip(page, ln, "unparsed line in MPCB add-on accessories table")
                continue
            specs = {"for_model": m.group("for"), "contact_arrangement": m.group("arr"),
                     "function": m.group("func"), "mounting": m.group("mount"),
                     "series": "MPCB Accessories", "made_in": "Germany"}
            add_row(page, "Motor Protection Circuit Breakers - Add-On Accessories", m.group("model"),
                    f"MPCB Add-On Accessory {m.group('model')} for {m.group('for')}: {m.group('arr')} "
                    f"{m.group('func')} {m.group('mount')} mounting",
                    price_num(m.group("price")), specs, ln)
        else:
            m = row_re.match(ln)
            if not m:
                add_skip(page, ln, "unparsed line on MPCB page")
                continue
            specs = {"rating": m.group("range"), "breaking_capacity": m.group("bc").replace(" ", ""),
                     "series": series, "made_in": "Germany"}
            add_row(page, f"Motor Protection Circuit Breakers {series} Series", m.group("model"),
                    f"Motor Protection Circuit Breaker {m.group('model')} {m.group('range')} {m.group('bc')}",
                    price_num(m.group("price")), specs, ln)


# ------------------------------------------------------------------ p25: capacitors
def parse_p25(page, lines):
    section = "Power Capacitors"
    row_re = re.compile(r"^(?P<desc>.+?)\s+(?P<price>[\d,]+)$")
    for ln in lines:
        if ln in ("UNIT PRICE", "PKR", "DESCRIPTION"):
            continue
        m = row_re.match(ln)
        if not m:
            add_skip(page, ln, "unparsed line on capacitors page")
            continue
        desc = m.group("desc")
        specs = {"series": "Power Capacitors"}
        kvar = re.search(r"([\d\.]+) KVAR", desc)
        volt = re.search(r"(\d+/\d+V)", desc)
        if kvar:
            specs["kvar"] = kvar.group(1) + " KVAR"
        if volt:
            specs["voltage"] = volt.group(1)
        add_row(page, section, desc, f"Power Capacitors: {desc}",
                price_num(m.group("price")), specs, ln)


# ------------------------------------------------------------- p26: control products
def parse_p26(page, lines):
    sec_names = ["LED Indication Lights 230VCAC", "Selector Switch / Push Button",
                 "Emergency Push Button", "Voltage Monitoring / Measurement rela",
                 "Electronic Timing Relays"]
    row_re = re.compile(r"^(?P<model>C[A-Z0-9\.\-]+)\s+(?P<desc>.+?)\s+(?P<price>[\d,]+)$")
    sub = None
    for ln in lines:
        if ln.startswith("FOR MODEL") or ln == "PKR":
            continue
        if ln in sec_names:
            sub = ln
            continue
        m = row_re.match(ln)
        if not m:
            add_skip(page, ln, "unparsed line on control products page")
            continue
        model, desc = m.group("model"), m.group("desc")
        specs = {"series": "Control Products - " + (sub or "Misc"), "function": desc, "made_in": "Italy"}
        add_row(page, f"Control Products - {sub}", model,
                f"{sub}: {model} {desc}", price_num(m.group("price")), specs, ln)


# =====================================================================================
PAGE_PARSERS = {
    3: parse_p3, 4: parse_p4, 5: parse_p5,
    6: lambda pg, ls: parse_formula(pg, ls, "3Pole"),
    7: lambda pg, ls: parse_formula(pg, ls, "4Pole"),
    8: parse_p8,
    9: lambda pg, ls: parse_tmax(pg, ls, "3Pole"),
    10: lambda pg, ls: parse_tmax(pg, ls, "3Pole"),
    11: lambda pg, ls: parse_tmax(pg, ls, "3Pole"),
    12: lambda pg, ls: parse_tmax(pg, ls, "3Pole"),
    13: lambda pg, ls: parse_tmax(pg, ls, "4Pole"),
    14: lambda pg, ls: parse_tmax(pg, ls, "4Pole"),
    15: parse_p15,
    16: lambda pg, ls: parse_acb(pg, ls, "3 Pole"),
    17: lambda pg, ls: parse_acb(pg, ls, "4 Pole"),
    18: parse_p18, 19: parse_p19, 20: parse_p20, 21: parse_p21,
    22: parse_p22, 23: parse_mpcb, 24: parse_mpcb, 25: parse_p25, 26: parse_p26,
}
# pages 1 (cover), 2 (index), 27 (terms), 28 (blank) skipped silently

TITLE_LINE_RES = [  # page-top title lines consumed before dispatch
    re.compile(r"^(Miniature Circuit Breakers|Residual Current Circuit Breakers|New Sace Formula Series|"
               r"Moulded Case Circuit Breakers|T MAX Series|Accessories for|Air Circuit Breakers|"
               r"\d POLE MAGNETIC CONTACTORS|ACCESSORIES FOR CONTACTORS|Thermal Over Load Relays|"
               r"Motor Protection Circuit Breakers|POWER CAPACITORS|Control Products)"),
    re.compile(r"^\d+ KA$"),
    re.compile(r"^[34] ?Pole (Thermo|Fixed|Adjustable)"),
    re.compile(r"^[34] Pole Adjustable$"),
    re.compile(r"^Optional Accessories$"),
]


def main():
    page_lines = {}
    with pdfplumber.open(PDF) as pdf:
        n_pages = len(pdf.pages)
        for i, pg in enumerate(pdf.pages, start=1):
            txt = pg.extract_text() or ""
            lines = [l.strip() for l in txt.splitlines() if l.strip()]
            lines = [l for l in lines if not is_footer(l)]
            page_lines[i] = lines

    for pageno, parser in PAGE_PARSERS.items():
        lines = page_lines[pageno]
        body = [l for l in lines if not any(r.match(l) for r in TITLE_LINE_RES)
                or pageno in (3, 4)]  # p3/p4 "N POLE" headers are block markers, keep
        # For p3/p4 keep everything except pure titles handled inside; simplest: pass all
        parser(pageno, lines if pageno in (3, 4) else body)

    # ---------------- dedupe: same (model + specs + description) ----------------
    seen = {}
    deduped = []
    for r in rows:
        key = (r["model"], json.dumps(r["specs"], sort_keys=True, ensure_ascii=False), r["description"])
        if key in seen:
            prev = seen[key]
            if prev["price_pkr"] == r["price_pkr"]:
                add_skip(r["page"], r["_raw"], "duplicate of identical row (same model/specs/price) - deduped")
                continue
        seen[key] = r
        deduped.append(r)

    # ---------------- sanity ----------------
    final_rows = []
    for r in deduped:
        pr = r["price_pkr"]
        if pr is not None and (pr < 10 or pr > 10_000_000):
            add_skip(r["page"], r["_raw"], "sanity")
            continue
        final_rows.append(r)

    prices = [r["price_pkr"] for r in final_rows if r["price_pkr"] is not None]
    stats = {"pages": n_pages, "rows": len(final_rows), "priced": len(prices), "skipped": len(skipped)}

    out = {
        "source_pdf": PDF.name,
        "rows": [{k: v for k, v in r.items() if k != "_raw"} for r in final_rows],
        "skipped": skipped,
        "stats": stats,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    # ---------------- validation report ----------------
    p(f"STATS: {stats}")
    p(f"PRICE min={min(prices)} median={statistics.median(prices)} max={max(prices)}")

    # coverage: count priced lines in raw text of 3 pages vs parsed priced rows
    p("\nCOVERAGE CHECK (raw priced-line count vs parsed priced rows):")
    price_tail = re.compile(r"[\d,]{3,}$")
    for cp in (10, 19, 24):
        raw_count = 0
        for ln in page_lines[cp]:
            if price_tail.search(ln) and not is_footer(ln) and price_num(ln.split()[-1]) is not None \
               and not re.fullmatch(r"[\d,]+", ln):
                raw_count += 1
        parsed = sum(1 for r in final_rows if r["page"] == cp and r["price_pkr"] is not None)
        p(f"  page {cp}: raw priced lines={raw_count}  parsed priced rows={parsed}")

    p("\nSPOT-CHECK (10 random rows with source raw line):")
    random.seed(7)
    for r in random.sample(final_rows, 10):
        p(f"  p{r['page']} [{r['model']}] {r['price_pkr']} PKR :: {r['specs'].get('rating','-')}")
        p(f"      raw: {r['_raw']}")
        p(f"      desc: {r['description']}")

    p("\nSKIPPED:")
    for s in skipped:
        p(f"  p{s['page']} ({s['reason']}): {s['raw'][:100]}")


if __name__ == "__main__":
    sys.exit(main())
