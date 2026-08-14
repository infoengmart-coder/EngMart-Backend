"""
Independent audit of the extractions: pick random parsed rows and confirm the
model AND its price appear in the raw text of the page they claim.

This does not trust the parsers — it re-opens the PDFs and looks, because these
numbers become live shop prices.

TWO KNOWN FALSE-ALARM MODES — read before acting on a CHECK result:

1. **Outlined text.** Some lists (Himel 2022) draw model names as vector
   outlines, so they are not in the text layer at all and every model "fails".
   That is a property of the PDF, not evidence of bad data. Confirm by
   rendering the page (fitz `get_pixmap`) and looking at it.

2. **Superseded price layers.** Some pages (Himel 18/19/21/35) draw an OLD
   price run first and paint an opaque band over it. `extract_text()` returns
   the hidden old number, so a parser that correctly reads the *visible* price
   appears to be wrong here. Again: render the page and look.

A genuine problem looks like a model AND price that appear nowhere in the
document and cannot be seen on the rendered page.

    python extraction/verify_against_pdf.py [slug ...]
"""
import json
import os
import random
import re
import sys

import pdfplumber

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'out')
PDF_DIR = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'product-details')

SAMPLE = 12
random.seed(20260731)  # deterministic so re-runs are comparable


def norm(s):
    """Collapse whitespace/punctuation so '12,500' matches '12500' and
    'NXB-63 1P' matches 'NXB-63  1P'."""
    return re.sub(r'[\s,]+', '', str(s or '')).upper()


def price_forms(value):
    """Every way a price is printed in these lists: 12500, 12,500, 12500/=."""
    if value is None:
        return []
    iv = int(value) if float(value) == int(float(value)) else float(value)
    return [norm(iv), norm(f'{iv:,}')]


def ascii_safe(t):
    return str(t or '').encode('ascii', 'replace').decode('ascii')


def main(slugs):
    files = sorted(f for f in os.listdir(OUT) if f.endswith('.json'))
    if slugs:
        files = [f for f in files if os.path.splitext(f)[0] in slugs]

    grand_ok = grand_checked = 0
    for fname in files:
        with open(os.path.join(OUT, fname), encoding='utf-8') as fh:
            data = json.load(fh)
        rows = [r for r in (data.get('rows') or []) if r.get('price_pkr') is not None]
        if not rows:
            continue
        pdf_path = os.path.join(PDF_DIR, data.get('source_pdf', ''))
        if not os.path.exists(pdf_path):
            print(f'{fname}: SOURCE PDF NOT FOUND ({data.get("source_pdf")})')
            continue

        sample = random.sample(rows, min(SAMPLE, len(rows)))
        page_cache = {}
        ok = 0
        problems = []
        with pdfplumber.open(pdf_path) as pdf:
            for row in sample:
                pno = int(row.get('page') or 0)
                if pno < 1 or pno > len(pdf.pages):
                    problems.append((row, 'page out of range'))
                    continue
                if pno not in page_cache:
                    page_cache[pno] = norm(pdf.pages[pno - 1].extract_text() or '')
                text = page_cache[pno]
                model = norm(row.get('model'))
                model_ok = model in text
                if not model_ok and '-' in str(row.get('model')):
                    # Wide tables wrap a model across lines ("3WT8121-" /
                    # "5UN30-" / "0AA2") with description text in between, so a
                    # contiguous match fails on a correctly reassembled model.
                    # Require every fragment to be present instead.
                    parts = [norm(p) for p in str(row['model']).split('-') if norm(p)]
                    model_ok = all(p in text for p in parts)
                price_ok = any(p in text for p in price_forms(row['price_pkr']))
                if model_ok and price_ok:
                    ok += 1
                else:
                    why = []
                    if not model_ok:
                        why.append('model not on page')
                    if not price_ok:
                        why.append('price not on page')
                    problems.append((row, ', '.join(why)))

        grand_ok += ok
        grand_checked += len(sample)
        status = 'OK ' if ok == len(sample) else 'CHECK'
        print(f'{status} {fname:22} {ok}/{len(sample)} sampled rows verified against the PDF')
        for row, why in problems[:4]:
            print(f'      p{row.get("page")} {ascii_safe(row.get("model"))[:22]:24}'
                  f' PKR {row.get("price_pkr")}  <-- {why}')

    print(f'\nTOTAL {grand_ok}/{grand_checked} sampled rows found verbatim in their source PDF page')


if __name__ == '__main__':
    main(set(sys.argv[1:]))
