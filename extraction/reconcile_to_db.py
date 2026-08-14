"""
Prove every row extracted from the 9 PDFs actually reached the live catalog.

For each row in extraction/out/*.json this finds the matching ProductVariant in
the database and reports anything that did not land. This is the check that
answers the client's actual requirement: "whatever is in the PDFs, show it".

    python extraction/reconcile_to_db.py
    python extraction/reconcile_to_db.py --list-missing
"""
import json
import os
import re
import sys

import django

HERE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE_DIR))  # backend/ — so `config` imports
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.products.models import ProductVariant  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'out')


def norm(text):
    """Loose key: case/space/punctuation-insensitive."""
    return re.sub(r'[^a-z0-9]', '', str(text or '').lower())


def main():
    list_missing = '--list-missing' in sys.argv

    # Index the catalog once: cat_no and description both act as identifiers,
    # because rows without a printed catalogue number use their description.
    by_catno, by_desc = {}, {}
    for v in ProductVariant.objects.all().only('id', 'cat_no', 'description', 'price'):
        if v.cat_no:
            by_catno.setdefault(norm(v.cat_no), []).append(v)
        if v.description:
            by_desc.setdefault(norm(v.description)[:80], []).append(v)

    grand_rows = grand_found = 0
    print(f'{"file":18} {"rows":>6} {"in catalog":>11} {"missing":>8}')
    print('-' * 48)
    missing_all = []

    for fname in sorted(f for f in os.listdir(OUT) if f.endswith('.json')):
        with open(os.path.join(OUT, fname), encoding='utf-8') as fh:
            rows = (json.load(fh).get('rows') or [])
        found = 0
        missing = []
        for row in rows:
            model = norm(row.get('model'))
            desc = norm(row.get('description'))[:80]
            hit = (by_catno.get(model) or by_desc.get(desc)
                   or by_desc.get(norm(row.get('model'))[:80]))
            if hit:
                found += 1
            else:
                missing.append(row)
        grand_rows += len(rows)
        grand_found += found
        missing_all.extend((fname, m) for m in missing)
        pct = found / len(rows) * 100 if rows else 100
        flag = '' if not missing else '  <--'
        print(f'{fname.replace(".json",""):18} {len(rows):>6} {found:>10} ({pct:.0f}%) {len(missing):>7}{flag}')

    print('-' * 48)
    pct = grand_found / grand_rows * 100 if grand_rows else 100
    print(f'{"TOTAL":18} {grand_rows:>6} {grand_found:>10} ({pct:.1f}%) {grand_rows-grand_found:>7}')

    if missing_all and list_missing:
        print('\nRows not found in the catalog:')
        for fname, row in missing_all[:40]:
            print(f'  {fname:14} p{str(row.get("page")):<4} '
                  f'{str(row.get("model"))[:34]:36} '
                  f'{row.get("price_pkr")}')
    elif missing_all:
        print(f'\n{len(missing_all)} rows unaccounted for — re-run with --list-missing')


if __name__ == '__main__':
    main()
