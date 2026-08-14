"""
Completeness audit: how many priced lines does each PDF actually contain, and
how many did we extract?

Counts price-shaped tokens in each PDF's text layer (1,234 / 1234/= / Rs. 1234)
and compares that to the rows we produced. This is an ESTIMATE — a page can
print a price in a header or a total — but a large shortfall means real product
lines were missed, which is what we want to catch.

    python extraction/coverage_audit.py
"""
import json
import os
import re

import pdfplumber

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'out')
PDF_DIR = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'product-details')

# A price in these lists: 4+ digit run, or comma-grouped, optionally Rs / "/="
PRICE_RE = re.compile(r'(?:Rs\.?\s*)?\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b|\b\d{3,7}(?:\.\d{1,2})?\s*/=')


def main():
    rows_total = est_total = 0
    print(f'{"file":24} {"pages":>5} {"price tokens":>13} {"rows extracted":>15} {"coverage":>9}')
    print('-' * 72)
    for fname in sorted(f for f in os.listdir(OUT) if f.endswith('.json')):
        with open(os.path.join(OUT, fname), encoding='utf-8') as fh:
            data = json.load(fh)
        rows = data.get('rows') or []
        pdf_path = os.path.join(PDF_DIR, data.get('source_pdf', ''))
        if not os.path.exists(pdf_path):
            print(f'{fname:24} SOURCE PDF MISSING')
            continue

        tokens = 0
        with pdfplumber.open(pdf_path) as pdf:
            pages = len(pdf.pages)
            for page in pdf.pages:
                text = page.extract_text() or ''
                tokens += len(PRICE_RE.findall(text))

        n = len(rows)
        rows_total += n
        est_total += tokens
        pct = (n / tokens * 100) if tokens else 0.0
        flag = '' if pct >= 85 or tokens == 0 else '  <-- CHECK'
        print(f'{fname.replace(".json",""):24} {pages:>5} {tokens:>13} {n:>15} {pct:>8.0f}%{flag}')

    print('-' * 72)
    pct = (rows_total / est_total * 100) if est_total else 0
    print(f'{"TOTAL":24} {"":>5} {est_total:>13} {rows_total:>15} {pct:>8.0f}%')
    print('\nNote: price tokens are an estimate — headers, totals and spec')
    print('values can look like prices, so >100% or <100% is expected. A large')
    print('shortfall on one file is the signal worth investigating.')


if __name__ == '__main__':
    main()
