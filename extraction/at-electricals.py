# -*- coding: utf-8 -*-
"""
Extractor for: AT ELECTRICALS PRICE LIST MARCH 2023.pdf  (13 pages)

Layout (verified by raw-text probe of every page):
  - Page 1: cover (skipped).
  - Pages 2-10: prose sections "A. TITLE" / "N ) TITLE" and numbered subsections
    "1. TITLE" (section L). Each product line is "Model: CODE [qualifier]" with
    the price "Rs: NNNN/=" either on the SAME line, on the NEXT line, or on the
    line BEFORE the model (items 11-13 p7, section D p3, N p8, S p10).
    Spec/feature lines (bullets, "Key : value") sit under each model.
  - Page 10 bottom: CT table  "ATM-40 20o 40/5A 5500/="  (code dia ratio price)
  - Page 11: capacitor tables "ZnPS 2.5 KVAR 440 VAC 10,000/=" and
    "VarKON 12-M 12-Steps 90,000/="
  - Pages 12-13: numbered tables "S.NO MODEL DISCRIPTION AMPERE LIST PRICE"
    e.g. "1 YPT205032 2-POLE CHANGE-OVER (1-0-2) 32 5500/=", with occasional
    wrapped continuation lines like "SWITCH(0-1-2-3-4)".

Brand: the extracted text prints only "AT Electricals" (cover contact block);
no "Tense" text appears anywhere, so brand = "AT Electricals".

Price fidelity:
  - A price is attached to a model ONLY from (a) the model's own line, (b) an
    immediately-following price-only line while that model is still unpriced, or
    (c) a price-only line / section-header price seen just before the model.
    A price is never carried between two models.
  - KON-TER-25/32/50/100 specs.rating comes from the model suffix; justified by
    the printed shared spec line "H. Current(overload)..: 25A / 32A / 50A / 100A".
  - Models printed with a trailing "*" (DJV-72S*, KON-TER-50*, KON-TER-100*)
    keep the code without the asterisk; specs.note records the mark (printed
    footnote, page 10: "* Till Stock Last.").
"""
import json
import random
import re
import statistics
from pathlib import Path

import pdfplumber

PDF = r"C:/Users/AWCD/Desktop/client/engmart (2)/product-details/AT ELECTRICALS PRICE LIST MARCH 2023.pdf"
OUT = r"C:/Users/AWCD/Desktop/client/engmart (2)/backend/extraction/out/at-electricals.json"
BRAND = "AT Electricals"

def P(s):  # cp1252-safe console print
    print(str(s).encode("ascii", "replace").decode())

PRICE_RE = re.compile(r"Rs\s*[.:]?\s*([\d,]+)\s*/=", re.I)
PRICE_ONLY_RE = re.compile(r"^Rs\s*[.:]?\s*([\d,]+)\s*/=\.?$", re.I)
SECTION_RE = re.compile(r"^([A-Z])\s*[\.\)]\s+(.+)$")
NUMSEC_RE = re.compile(r"^(\d{1,2})\.\s+([A-Z].*)$")
MODEL_RE = re.compile(r"^Model\s*(?:No\.?)?\s*[:.]?\s*(.+)$", re.I)
CT_RE = re.compile(r"^(ATM?-\d+)\s+(.*?)\s+(\d+/\d+A)\s+([\d,]+)\s*/=\s*$")
CAP_RE = re.compile(r"^(ZnPS|ZNPP)\s+([\d.]+)\s*KVAR\s+(\d+)\s*VAC\s+([\d,]+)\s*/=\s*$", re.I)
VARKON_RE = re.compile(r"^(VarKON\S*(?:\s+\S+)?)\s+(\d+-Steps)\s+([\d,]+)\s*/=\s*$", re.I)
TROW_AMP_RE = re.compile(r"^(\d{1,2})\s+(\S+)\s+(.+?)\s+(\d{1,3})\s+([\d,]+)\s*/=\s*$")
TROW_NOAMP_RE = re.compile(r"^(\d{1,2})\s+(\S+)(?:\s+(.+?))?\s+([\d,]+)\s*/=\s*$")
SERIES_LINE_RE = re.compile(r"^([A-Z]+)-SERIES:?$")

SKIP_EXACT = {"MARCH-2023", "Made In Turkey", "Note:", "FEATURES:",
              "General Specifications:", "TECHNICAL PROPERTIES:",
              "Technical Properties:", "* Till Stock Last."}
SKIP_PREFIX = ("Page No:", "Measuring, Control", "This list is subject to change",
               "Discount/Multipliers", "PRODUCT CODE", "S.NO ",
               "Adjustable Control Setting Ranges")

def clean(s):
    return re.sub(r"\(cid:\d+\)", "", s).strip()

def num(s):
    return int(s.replace(",", ""))

def series_from_model(model, group=None):
    if not re.search(r"\d", model):
        # no digits: N.C / HOT / COLD / USB-CON / FR-GR / DT-D
        if group and len(model) <= 4:
            return group
        segs = model.split("-")
        if len(segs) > 1 and len(segs[-1]) == 1:
            return "-".join(segs[:-1])  # DT-D -> DT (single-letter variant suffix)
        return model
    if "-" in model:
        keep = []
        for seg in model.split("-"):
            if re.search(r"\d", seg):
                break
            keep.append(seg)
        if keep:
            return "-".join(keep)
    m = re.match(r"^([A-Za-z]+)", model)
    return m.group(1) if m else model

def extract(pdf_path):
    rows, skipped, raws = [], [], []
    with pdfplumber.open(pdf_path) as pdf:
        n_pages = len(pdf.pages)
        section = None        # {"title","subtitle":[],"pre_long":[],"rows":[]}
        group = None          # ALL-CAPS group header (table pages)
        group_last_li = -10
        pending_price = None  # (value, raw_line)
        open_row = None       # last prose row still without a price
        open_row_gap = 0
        cur_row = None        # row currently receiving detail lines
        last_table_idx = None
        prev_was_table = False
        pageno = 0

        def close_section():
            """Shared spec block printed after the LAST model of a multi-model
            section (RGT, KON-TER) -> specs.section_details for every row; a
            pre-model long block (Q temperature controllers) likewise."""
            nonlocal section
            if section and len(section["rows"]) > 1:
                idxs = section["rows"]
                withd = [i for i in idxs if rows[i]["specs"].get("details")]
                if withd == [idxs[-1]]:
                    shared = rows[idxs[-1]]["specs"].pop("details")
                    for i in idxs:
                        rows[i]["specs"]["section_details"] = shared
            if section and section["pre_long"] and section["rows"]:
                sd = "; ".join(section["pre_long"])
                for i in section["rows"]:
                    rows[i]["specs"].setdefault("section_details", sd)
            section = None

        def mark_unpriced(row):
            row["specs"]["note"] = "no price printed for this line in PDF"
            row["specs"].pop("price_note", None)

        def emit_prose(model_txt, qualifier, price, raw, price_raw=None):
            nonlocal cur_row, open_row, open_row_gap
            model = model_txt.strip()
            note = None
            if model.endswith("*"):
                model = model.rstrip("*").strip()
                note = "marked * in list (page-10 footnote: '* Till Stock Last.')"
            sec_title = section["title"] if section else (group or "")
            subs = section["subtitle"][:2] if section else []
            desc = " - ".join(p for p in
                              [sec_title] + subs +
                              [(model + (" " + qualifier if qualifier else ""))] if p)
            specs = {"series": series_from_model(model)}
            if note:
                specs["note"] = note
            hay = " ".join([sec_title] + subs + [qualifier or ""])
            m = re.search(r"\b(\d+(?:\.\d+)?)[- ]Steps\b", hay, re.I)
            if m:
                specs["steps"] = m.group(1) + "-Steps"
            m = re.search(r"\((\d+\s*[\*x\u00d7]\s*\d+(?:\s*mm)?)\)", hay, re.I)
            if m:
                specs["size"] = m.group(1).replace(" ", "")
            m = re.search(r"\b([13])-PHASE\b", hay, re.I)
            if m:
                specs["phase"] = m.group(1) + "-Phase"
            elif re.search(r"\bMONOPHASE\b", hay, re.I):
                specs["phase"] = "Monophase"
            m = re.match(r"^KON-TER-(\d+)$", model)
            if m:
                specs["rating"] = m.group(1) + "A"  # see module docstring
            else:
                m = re.search(r"\((\d+)\s*A\)", " ".join([sec_title] + subs))
                if m:
                    specs["rating"] = m.group(1) + "A"
            row = {"page": pageno, "brand": BRAND, "section": sec_title,
                   "model": model, "description": desc,
                   "price_pkr": price, "specs": specs}
            rows.append(row)
            raws.append(raw + ((" | " + price_raw) if price_raw else ""))
            if section is not None:
                section["rows"].append(len(rows) - 1)
            cur_row = row
            if price is None:
                open_row, open_row_gap = row, 0
            else:
                open_row = None

        def emit_table(model, desc_txt, price, sec_title, specs, raw):
            nonlocal prev_was_table, last_table_idx
            rows.append({"page": pageno, "brand": BRAND, "section": sec_title,
                         "model": model, "description": desc_txt,
                         "price_pkr": price, "specs": specs})
            raws.append(raw)
            prev_was_table = True
            last_table_idx = len(rows) - 1

        for pi in range(n_pages):
            pageno = pi + 1
            if pageno == 1:
                continue  # cover page
            # ---- page-boundary reset (no section/price crosses a page break:
            # verified — pages 6 and 7 open with their own numbered headers) ----
            if pending_price is not None:
                skipped.append({"page": pageno - 1, "raw": pending_price[1],
                                "reason": "price line with no adjacent model"})
                pending_price = None
            if open_row is not None:
                mark_unpriced(open_row)
                open_row = None
            close_section()
            group, group_last_li = None, -10
            cur_row = None
            prev_was_table, last_table_idx = False, None

            text = pdf.pages[pi].extract_text() or ""
            for li, raw_line in enumerate(text.splitlines()):
                line = clean(raw_line)
                if not line:
                    continue
                if line in SKIP_EXACT or any(line.startswith(p) for p in SKIP_PREFIX) \
                        or SERIES_LINE_RE.match(line):
                    prev_was_table = False
                    continue

                # ---- table-style rows ----
                m = CT_RE.match(line)
                if m:
                    code, dia, ratio, price = m.group(1), m.group(2).strip(), m.group(3), num(m.group(4))
                    st = section["title"] if section else (group or "")
                    emit_table(code, " - ".join(p for p in [st, code, dia, ratio] if p),
                               price, st,
                               {"series": series_from_model(code), "diameter": dia,
                                "current_ratio": ratio, "rating": ratio}, raw_line)
                    continue
                m = CAP_RE.match(line)
                if m:
                    code, kvar, volt, price = m.group(1), m.group(2), m.group(3), num(m.group(4))
                    st = section["title"] if section else (group or "")
                    emit_table(code,
                               " - ".join(p for p in [st, "%s %s KVAR %s VAC" % (code, kvar, volt)] if p),
                               price, st,
                               {"series": code, "rating": kvar + " KVAR",
                                "voltage": volt + " VAC"}, raw_line)
                    continue
                m = VARKON_RE.match(line)
                if m:
                    code, steps, price = m.group(1).strip(), m.group(2), num(m.group(3))
                    st = section["title"] if section else (group or "")
                    emit_table(code, " - ".join(p for p in [st, code + " " + steps] if p),
                               price, st,
                               {"series": code.split()[0], "steps": steps}, raw_line)
                    continue
                if pageno >= 12:
                    m = TROW_AMP_RE.match(line)
                    m2 = None if m else TROW_NOAMP_RE.match(line)
                    if m or m2:
                        if m:
                            model, dcol, amp, price = m.group(2), m.group(3).strip(), m.group(4), num(m.group(5))
                        else:
                            model, dcol, price = m2.group(2), (m2.group(3) or "").strip(), num(m2.group(4))
                            amp = None
                        specs = {"series": series_from_model(model, group)}
                        if amp:
                            specs["rating"] = amp + "A"
                        pm = re.search(r"\b(\d)-POLE\b", dcol, re.I)
                        if pm:
                            specs["poles"] = pm.group(1) + "P"
                        dparts = [group or "", (model + " " + dcol).strip()]
                        if amp:
                            dparts.append(amp + "A")
                        emit_table(model, " - ".join(p for p in dparts if p),
                                   price, group or "", specs, raw_line)
                        continue
                # wrapped continuation of the previous table row ("SWITCH(0-1-2-3-4)")
                # -- never a section header like "B. LV CAPACITORS BOX (DRY) TYPE"
                if (prev_was_table and last_table_idx is not None
                        and "(" in line and ")" in line
                        and not SECTION_RE.match(line) and not NUMSEC_RE.match(line)):
                    rows[last_table_idx]["description"] += " " + line
                    raws[last_table_idx] += " / " + raw_line
                    prev_was_table = False
                    continue
                prev_was_table = False

                # ---- prose logic ----
                m = PRICE_ONLY_RE.match(line)
                if m:
                    val = num(m.group(1))
                    if open_row is not None and open_row_gap <= 2:
                        open_row["price_pkr"] = val
                        open_row["specs"].pop("price_note", None)
                        raws[rows.index(open_row)] += " | " + raw_line
                        open_row = None
                    else:
                        if pending_price is not None:
                            skipped.append({"page": pageno, "raw": pending_price[1],
                                            "reason": "price line with no adjacent model"})
                        pending_price = (val, raw_line)
                    continue

                sm = SECTION_RE.match(line)
                nm = None if sm else NUMSEC_RE.match(line)
                if sm or nm:
                    close_section()
                    if open_row is not None:
                        mark_unpriced(open_row)
                        open_row = None
                    title = (sm or nm).group(2)
                    pm = PRICE_RE.search(title)
                    if pm:
                        pending_price = (num(pm.group(1)), raw_line)
                        title = PRICE_RE.sub("", title).strip()
                    title = re.sub(r"\s*PRICE EACH\s*$", "", title).strip().rstrip(".").strip()
                    section = {"title": title, "subtitle": [], "pre_long": [], "rows": []}
                    cur_row = None
                    continue

                m = MODEL_RE.match(line)
                if m:
                    rest = m.group(1).strip()
                    pm = PRICE_RE.search(rest)
                    price = None
                    if pm:
                        price = num(pm.group(1))
                        rest = PRICE_RE.sub("", rest).strip()
                    toks = rest.split(None, 1)
                    model = toks[0] if toks else rest
                    qual = toks[1].strip() if len(toks) > 1 else ""
                    if open_row is not None:
                        mark_unpriced(open_row)
                        open_row = None
                    if price is None and pending_price is not None:
                        emit_prose(model, qual, pending_price[0], raw_line,
                                   price_raw=pending_price[1])
                        pending_price = None
                    else:
                        emit_prose(model, qual, price, raw_line)
                    continue

                # plain detail / subtitle / group-header line
                if open_row is not None:
                    open_row_gap += 1
                if cur_row is not None:
                    d = cur_row["specs"].get("details", "")
                    cur_row["specs"]["details"] = (d + "; " if d else "") + line
                    sm2 = re.match(r"^Size:\s*(.+)$", line)
                    if sm2:
                        cur_row["specs"]["size"] = sm2.group(1).strip()
                elif section is not None:
                    if (len(line) <= 60 and not line.startswith(("\u2022", "?", "-"))
                            and not re.search(r"[:=]|\.\.", line)):
                        section["subtitle"].append(line)
                    else:
                        section["pre_long"].append(line)
                elif (line.upper() == line and not PRICE_RE.search(line)
                        and re.search(r"[A-Z]{3}", line)):
                    if group is not None and group_last_li == li - 1:
                        group = group + " " + line   # wrapped caps header
                    else:
                        group = line
                    group_last_li = li
                else:
                    skipped.append({"page": pageno, "raw": raw_line, "reason": "unparsed"})
        # ---- end of document ----
        if pending_price is not None:
            skipped.append({"page": pageno, "raw": pending_price[1],
                            "reason": "price line with no adjacent model"})
        if open_row is not None:
            mark_unpriced(open_row)
        close_section()
    return n_pages, rows, raws, skipped


def main():
    n_pages, rows, raws, skipped = extract(PDF)

    # ---- sanity: price bounds ----
    keep, keep_raws = [], []
    for r, rw in zip(rows, raws):
        p = r["price_pkr"]
        if p is not None and (p < 10 or p > 10_000_000):
            skipped.append({"page": r["page"], "raw": rw, "reason": "sanity"})
        else:
            keep.append(r); keep_raws.append(rw)
    rows, raws = keep, keep_raws

    # ---- duplicates: same model + same non-detail specs ----
    seen, dedup, dedup_raws = {}, [], []
    for r, rw in zip(rows, raws):
        key = (r["model"], json.dumps(
            {k: v for k, v in r["specs"].items()
             if k not in ("details", "section_details")}, sort_keys=True))
        if key in seen and seen[key]["price_pkr"] == r["price_pkr"]:
            skipped.append({"page": r["page"], "raw": rw,
                            "reason": "duplicate (same model+specs+price)"})
            continue
        seen[key] = r
        dedup.append(r); dedup_raws.append(rw)
    rows, raws = dedup, dedup_raws

    priced = [r for r in rows if r["price_pkr"] is not None]
    out = {"source_pdf": Path(PDF).name, "rows": rows, "skipped": skipped,
           "stats": {"pages": n_pages, "rows": len(rows),
                     "priced": len(priced), "skipped": len(skipped)}}
    Path(OUT).parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=True)

    # ---- validation report ----
    import collections
    P("stats: %s" % out["stats"])
    prices = [r["price_pkr"] for r in priced]
    P("price min/median/max: %s / %s / %s" %
      (min(prices), statistics.median(prices), max(prices)))
    per_page = collections.Counter(r["page"] for r in priced)
    with pdfplumber.open(PDF) as pdf:
        for pg in (4, 8, 12):
            t = pdf.pages[pg - 1].extract_text() or ""
            P("coverage page %d: price-marks-in-raw-text=%d parsed=%d" %
              (pg, len(re.findall(r"/=", t)), per_page.get(pg, 0)))
        P("per-page parsed: %s" % dict(sorted(per_page.items())))
        total = sum(len(re.findall(r"/=", pdf.pages[i].extract_text() or ""))
                    for i in range(1, len(pdf.pages)))
        P("total price marks pages 2-13: %d  vs priced rows: %d" % (total, len(priced)))

    random.seed(42)
    P("---- spot-check 10 random rows ----")
    for i in sorted(random.sample(range(len(rows)), min(10, len(rows)))):
        r = rows[i]
        P("p%-2d %-12s Rs %-8s | %s" % (r["page"], r["model"], r["price_pkr"],
                                        r["description"][:80]))
        P("     RAW: %s" % raws[i][:110])
    for s in skipped:
        P("skipped p%d [%s] %s" % (s["page"], s["reason"], s["raw"][:90]))
    for r in rows:
        if r["price_pkr"] is None:
            P("UNPRICED p%d %s" % (r["page"], r["model"]))


if __name__ == "__main__":
    main()
