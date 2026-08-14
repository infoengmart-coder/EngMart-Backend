"""Probe the 9 supplier PDFs: page counts, text-layer presence, and sample
rows from a middle page, so per-PDF parsers can be designed accurately."""
import os
import sys
import glob

import pdfplumber

PDF_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'product-details')


def sanitize(t):
    return (t or '').encode('ascii', 'replace').decode('ascii')


for path in sorted(glob.glob(os.path.join(PDF_DIR, '*.pdf'))):
    name = os.path.basename(path)
    try:
        with pdfplumber.open(path) as pdf:
            n = len(pdf.pages)
            # sample a page from the middle where tables live
            mid = pdf.pages[min(n - 1, max(0, n // 2))]
            text = mid.extract_text() or ''
            tables = mid.extract_tables()
            print('=' * 70)
            print(f'{name}  pages={n}  midpage_chars={len(text)}  midpage_tables={len(tables)}')
            lines = [sanitize(l) for l in text.split('\n') if l.strip()]
            for l in lines[:14]:
                print('   |', l[:110])
            if tables:
                t0 = tables[0]
                print(f'   TABLE rows={len(t0)} cols={len(t0[0]) if t0 else 0}; first 3 rows:')
                for row in t0[:3]:
                    print('   #', ' | '.join(sanitize(str(c))[:22] for c in row))
    except Exception as e:
        print(f'{name}  FAILED: {e}')
