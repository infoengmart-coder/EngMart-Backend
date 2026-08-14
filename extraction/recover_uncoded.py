"""
Recover priced product lines that were skipped for having no printed catalogue
number, e.g.

    1. Auxiliary Switch 1C   Rs. 18,200/=

These are real sellable items (breaker accessories, mostly). The parser refused
to guess a model code — correctly — so they were parked in `skipped`. Here we
promote them using their printed DESCRIPTION as the model, which is exactly what
the FICO parser already does for its un-coded rows.

Nothing is invented: the description and price are taken verbatim from the
line, and the row is tagged so it can be found again.

    python extraction/recover_uncoded.py            # preview
    python extraction/recover_uncoded.py --apply    # write back into out/<slug>.json
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'out')

PRICE = re.compile(r'Rs\.?\s*([\d,]+(?:\.\d+)?)\s*/?=?', re.I)
LEAD_NUM = re.compile(r'^\s*(?:\(?[ivx]+\)|\(?\d+\)|\d+\.)\s*')
NOTE = re.compile(r'^\(?[a-z0-9]*\)?\s*note\b|available on request', re.I)


def clean_description(raw):
    """Strip the leading list marker and everything from the first price on."""
    text = LEAD_NUM.sub('', str(raw or '').strip())
    m = PRICE.search(text)
    if m:
        text = text[:m.start()]
    return re.sub(r'\s+', ' ', text).strip(' .:-')


def fill_empty_models(data):
    """
    Some parsers emitted rows with a price and description but an EMPTY model
    (the PDF prints no catalogue number for accessory lines). The importer skips
    anything without a model, so those products never reach the site. Promote
    the printed description to the model — same rule as the skipped-row path.

    Returns the number of rows repaired.
    """
    fixed = 0
    for row in data.get('rows') or []:
        if str(row.get('model') or '').strip():
            continue
        desc = clean_description(row.get('description'))
        # Strip a trailing printed price fragment (e.g. '... " 270,000/=')
        desc = re.sub(r'[“"\*∗]', ' ', desc)
        desc = re.sub(r'[\d,]+\s*/=\s*$', '', desc).strip(' .:-')
        desc = re.sub(r'\s+', ' ', desc)
        if len(desc) < 4 or not re.search(r'[A-Za-z]{3}', desc):
            # No product wording — this is a rating rung whose model sits in a
            # merged cell (e.g. "2  2.5 - 4 A  19,000/="). It still belongs to
            # its printed series, so keep it as a VARIANT of that series and
            # take the amp range from the line as its identity.
            specs = row.setdefault('specs', {})
            series = str(specs.get('series') or row.get('section') or '').strip()
            amps = re.search(r'(\d+(?:\.\d+)?\s*-\s*\d+(?:\.\d+)?\s*A|'
                             r'[\d,\s&]+\d\s*A)\b', desc)
            if not series or not amps:
                continue
            rating = re.sub(r'\s+', ' ', amps.group(1)).strip()
            specs.setdefault('rating', rating)
            specs.setdefault(
                'note',
                'Model printed in a merged cell; identified by its rating '
                'within the printed series.')
            row['model'] = f'{series[:60]} {rating}'.strip()[:100]
            row['description'] = f'{series[:80]} — {rating}'
            fixed += 1
            continue
        row['model'] = desc[:100]
        row['description'] = desc
        specs = row.setdefault('specs', {})
        specs.setdefault(
            'note',
            'No catalogue number printed on this line; the printed description '
            'is used as the identifier.')
        specs.setdefault('series', (specs.get('series') or desc)[:60])
        fixed += 1
    return fixed


def recover(slug, apply_changes):
    path = os.path.join(OUT, f'{slug}.json')
    with open(path, encoding='utf-8') as fh:
        data = json.load(fh)

    kept, promoted = [], []
    for entry in data.get('skipped') or []:
        raw = str(entry.get('raw') or '')
        if 'no identifiable catalogue' not in str(entry.get('reason') or '').lower():
            kept.append(entry)
            continue
        if NOTE.search(raw):
            kept.append(entry)
            continue
        m = PRICE.search(raw)
        desc = clean_description(raw)
        # Needs a price and a description with real words — not a bare number.
        if not m or len(desc) < 4 or not re.search(r'[A-Za-z]{3}', desc):
            kept.append(entry)
            continue
        try:
            price = float(m.group(1).replace(',', ''))
        except ValueError:
            kept.append(entry)
            continue
        if price <= 0:
            kept.append(entry)
            continue

        promoted.append({
            'page': entry.get('page'),
            'brand': data.get('default_brand') or 'JC',
            'section': entry.get('section') or 'Accessories',
            # No catalogue number is printed, so the printed description IS the
            # identifier. Flagged in specs so it is never mistaken for a code.
            'model': desc[:100],
            'description': desc,
            'price_pkr': price,
            'specs': {
                'note': 'No catalogue number printed on this line; the printed '
                        'description is used as the identifier.',
                'series': desc[:60],
            },
        })

    filled = fill_empty_models(data)
    return data, path, kept, promoted, filled


def main():
    apply_changes = '--apply' in sys.argv
    slugs = [a for a in sys.argv[1:] if not a.startswith('--')] or ['jc']
    grand = 0
    for slug in slugs:
        data, path, kept, promoted, filled = recover(slug, apply_changes)
        grand += len(promoted) + filled
        print(f'{slug}: {len(promoted)} skipped lines recoverable, '
              f'{filled} empty-model rows repaired ({len(kept)} stay skipped)')
        for row in promoted[:4]:
            print(f'    p{row["page"]:<4} {row["description"][:52]:54} PKR {row["price_pkr"]:,.0f}')
        if apply_changes and (promoted or filled):
            data['rows'] = (data.get('rows') or []) + promoted
            data['skipped'] = kept
            st = data.setdefault('stats', {})
            st['rows'] = len(data['rows'])
            st['priced'] = sum(1 for r in data['rows'] if r.get('price_pkr') is not None)
            st['skipped'] = len(kept)
            st['recovered_uncoded'] = len(promoted)
            with open(path, 'w', encoding='utf-8') as fh:
                json.dump(data, fh, indent=1)
            print(f'    -> written back to {os.path.basename(path)}')
    print(f'\nTOTAL recoverable: {grand}')
    if not apply_changes:
        print('(preview only — re-run with --apply to write)')


if __name__ == '__main__':
    main()
