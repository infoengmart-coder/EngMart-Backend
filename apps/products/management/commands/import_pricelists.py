"""
Import the supplier price-list extractions (backend/extraction/out/*.json)
into the catalog as Products + ampere ProductVariants.

    python manage.py import_pricelists --dry-run          # report only, no writes
    python manage.py import_pricelists                    # apply
    python manage.py import_pricelists --only chint,pce   # subset
    python manage.py import_pricelists --report out.csv   # audit trail

Design rules (deliberate, do not "simplify" away):

* IDEMPOTENT. Re-running must not duplicate anything. Products are keyed by
  (brand, series-or-model); variants by (product, cat_no, rating). A second run
  updates prices in place and reports what changed.

* UPSERT ONLY, NEVER DELETE. Variants absent from a newer price list are left
  alone — a supplier omitting a line does not mean the client stopped selling
  it, and silent deletion would destroy admin-entered data (this is the same
  trap that once wiped variants on every product edit).

* NEVER INVENT DATA. Every price traces to a PDF row. Rows without a price
  become price_on_request variants; no defaults, no averages, no placeholders.

* NO IMAGES. Per the signed quotation, images for PDF-only products are out of
  scope; the client adds them through the admin panel. Imported products keep
  image empty and simply render the neutral placeholder.
"""
import csv
import json
import os
import re
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from apps.brands.models import Brand
from apps.categories.models import Category
from apps.common.cache import bump_catalog_version
from apps.products.models import Product, ProductVariant

EXTRACTION_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))),
    'extraction', 'out',
)

# Brand name in the PDFs -> canonical brand already in the DB. Anything not
# listed is created with the printed name (never silently merged).
BRAND_ALIASES = {
    'FICO': 'FICO Hi-Tech',
    'FICO Hi-TECH': 'FICO Hi-Tech',
    'AT Electricals': 'AT Electricals',
    'Tense': 'AT Electricals',
    'JC': 'JC',
}

# Section/series keyword -> (parent category, subcategory). Matched
# case-insensitively against section + description + series.
CATEGORY_RULES = [
    (r'\bACB\b|air circuit breaker', ('Circuit Protection', 'ACB')),
    (r'\bMCCB\b|moulded case|molded case|t\s*max|nsx|compact ns', ('Circuit Protection', 'MCCB')),
    (r'\bRCBO\b', ('Circuit Protection', 'RCBO')),
    (r'\bRCCB\b|residual current|earth leakage|\bELCB\b', ('Circuit Protection', 'RCCB')),
    (r'\bMCB\b|miniature circuit', ('Circuit Protection', 'MCB')),
    (r'\bfuse\b|fuses', ('Circuit Protection', 'Fuses')),
    (r'surge', ('Circuit Protection', 'Surge Protection')),
    (r'overload relay|thermal overload', ('Contactors & Relays', 'Overload Relays')),
    (r'contactor', ('Contactors & Relays', 'Contactors')),
    (r'\brelay\b', ('Contactors & Relays', 'Relays')),
    (r'\bVFD\b|variable frequency|inverter drive', ('Motor Control', 'VFDs')),
    (r'soft starter', ('Motor Control', 'Soft Starters')),
    (r'motor starter|\bMPCB\b|motor protection', ('Motor Control', 'Motor Starters')),
    (r'changeover|\bATS\b|transfer switch', ('Switching Devices', 'Changeover Switches')),
    (r'isolator|disconnect', ('Switching Devices', 'Isolators')),
    (r'main switch', ('Switching Devices', 'Main Switches')),
    (r'push\s*button', ('Switches & Indicators', 'Push Buttons')),
    (r'selector switch|cam switch', ('Switches & Indicators', 'Selector Switches')),
    (r'pilot lamp|indication lamp|indicator lamp', ('Switches & Indicators', 'Pilot Lamps')),
    (r'current transformer|\bCT\b', ('Metering', 'Current Transformers')),
    (r'analyz|analys|multimeter|ammeter|voltmeter|panel meter|energy meter', ('Metering', 'Panel Meters')),
    (r'power factor|\bPFC\b|capacitor bank', ('Power Factor Correction', 'PF Controllers')),
    (r'capacitor', ('Power Factor Correction', 'Capacitors')),
    (r'socket|plug', ('Plugs & Sockets', 'Industrial Sockets')),
    (r'timer', ('Timers & Controllers', 'Timers')),
    (r'counter', ('Timers & Controllers', 'Counters')),
    (r'sensor|photo\s*electric|proximity', ('Sensors & Automation', 'Sensors')),
    (r'\bPLC\b|\bHMI\b', ('Sensors & Automation', 'Automation')),
    (r'terminal|cable|wiring', ('Wiring & Accessories', 'Wiring Devices')),
    # Signals taken from the actual column headers these price lists print,
    # added after 57% of the first import fell through to the generic bucket.
    (r'\bAC-?3\b|\bAC-?1\b|current rating ac', ('Contactors & Relays', 'Contactors')),
    (r'class\s*10\s*\(iec|iec\s*947-4', ('Contactors & Relays', 'Overload Relays')),
    (r'\bburden\b|\bVA\b\s*[-–]\s*burden|economical class|innovative class',
     ('Metering', 'Current Transformers')),
    (r'\bPT\b|potential transformer|X/100V|X/110V', ('Metering', 'Potential Transformers')),
    (r'indication light|\bLED\b\s*indicat', ('Switches & Indicators', 'Pilot Lamps')),
    (r'voltage monitoring|phase failure|monitoring relay', ('Contactors & Relays', 'Relays')),
    (r'\bTPN\b|single pole|double pole|triple pole|four pole',
     ('Circuit Protection', 'MCB')),
    # Second pass, mined from the descriptions that still fell through.
    (r'auxiliary contact|shunt (opening )?release|undervoltage release|'
     r'motor mechanism|rotary handle|door interlock|mccbs?\b',
     ('Circuit Protection', 'MCCB Accessories')),
    (r'window type|reflective|through beam|diffuse', ('Sensors & Automation', 'Sensors')),
    (r'\bdrain\b|inner (door|plate)|mounting (plate|rail)|enclosure|\bcabinet\b',
     ('Enclosures & Accessories', 'Enclosure Accessories')),
    (r'change ?over', ('Switching Devices', 'Changeover Switches')),
    (r'\bswitch(es)?\b', ('Switches & Indicators', 'Switches')),
    (r'digital (meter|display)|\bsetting\b.*\bvoltage\b', ('Metering', 'Panel Meters')),
]

FALLBACK_CATEGORY = ('Electrical Equipment', 'General')


def ascii_safe(text):
    """cp1252 consoles crash on the ° and — that litter these PDFs."""
    return str(text or '').encode('ascii', 'replace').decode('ascii')


def classify(row):
    """Pick (parent, sub) category from the row's own printed text."""
    haystack = ' '.join(str(row.get(k) or '') for k in ('section', 'description', 'model'))
    specs = row.get('specs') or {}
    haystack += ' ' + str(specs.get('series') or '')
    for pattern, pair in CATEGORY_RULES:
        if re.search(pattern, haystack, re.I):
            return pair
    return FALLBACK_CATEGORY


def product_key(row):
    """
    Group rows into one product. Rows sharing a series (e.g. every NXB-63
    ampere) become ONE product with many variants — that is what makes the
    storefront amperage dropdown work.
    """
    specs = row.get('specs') or {}
    series = (specs.get('series') or '').strip()
    return series or (row.get('model') or '').strip()


def build_product_name(brand_name, key, row):
    """Readable title from printed text only — no invented marketing copy."""
    _, sub = classify(row)
    key = key.strip()
    if sub.lower() in key.lower():
        return f'{brand_name} {key}'.strip()
    return f'{brand_name} {key} {sub}'.strip()


def variant_description(row):
    """Human label for the dropdown option, e.g. '32A 3P 6kA'."""
    specs = row.get('specs') or {}
    bits = []
    for field in ('rating', 'poles', 'voltage', 'breaking_capacity', 'sensitivity'):
        val = specs.get(field)
        if val:
            bits.append(str(val))
    if bits:
        return ' '.join(bits)[:300]
    desc = (row.get('description') or row.get('model') or '').strip()
    return desc[:300] or 'Standard'


def get_or_create_by_name_or_slug(model, name, parent=None):
    """
    Resolve a Brand/Category by name, falling back to its slug.

    Plain get_or_create(name=...) explodes here: the catalog already contains
    categories whose name differs slightly from an imported one but whose slug
    collides (e.g. "Plugs & Sockets" -> plugs-sockets). Matching the slug too
    reuses the existing row instead of violating the unique constraint.
    """
    qs = model.objects.all()
    if parent is not None:
        obj = qs.filter(name__iexact=name, parent=parent).first()
    else:
        obj = qs.filter(name__iexact=name).first()
    if obj:
        return obj, False

    base = slugify(name)[:95] or 'item'
    if parent is not None and hasattr(model, 'parent'):
        by_slug = qs.filter(slug=base, parent=parent).first()
    else:
        by_slug = qs.filter(slug=base).first()
    if by_slug:
        return by_slug, False

    slug, n = base, 2
    while model.objects.filter(slug=slug).exists():
        slug = f'{base}-{n}'[:100]
        n += 1

    kwargs = {'name': name, 'slug': slug, 'is_active': True}
    if parent is not None:
        kwargs['parent'] = parent
    return model.objects.create(**kwargs), True


def to_decimal(value):
    if value is None:
        return None
    try:
        dec = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    # Guard rails: the extractors already flag outliers, this is belt-and-braces
    # so a parser bug can never write a PKR 0.01 or PKR 99,000,000 price.
    if dec <= 0 or dec > Decimal('20000000'):
        return None
    return dec.quantize(Decimal('0.01'))


class Command(BaseCommand):
    help = 'Import extracted supplier price lists into the catalog'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Report what would change without writing')
        parser.add_argument('--update-prices', action='store_true',
                            help='Also overwrite prices of variants that already exist '
                                 '(default: only add new products/variants, never touch '
                                 'a price the store is already selling at)')
        parser.add_argument('--only', type=str, default='',
                            help='Comma-separated extraction slugs to import')
        parser.add_argument('--reclassify', action='store_true',
                            help='Also move already-imported products into the '
                                 'category the current rules choose (safe: only '
                                 'moves products currently in the generic bucket)')
        parser.add_argument('--dir', type=str, default=EXTRACTION_DIR)
        parser.add_argument('--report', type=str, default='',
                            help='Write a per-row CSV audit trail to this path')

    def handle(self, *args, **opts):
        dry = opts['dry_run']
        update_prices = opts['update_prices']
        only = {s.strip() for s in opts['only'].split(',') if s.strip()}
        src_dir = opts['dir']

        files = sorted(f for f in os.listdir(src_dir) if f.endswith('.json'))
        if only:
            files = [f for f in files if os.path.splitext(f)[0] in only]
        if not files:
            self.stderr.write('No extraction files found.')
            return

        self.stdout.write(self.style.MIGRATE_HEADING(
            f'{"DRY RUN — " if dry else ""}Importing {len(files)} extraction file(s)'
        ))

        stats = {
            'rows': 0, 'skipped_rows': 0,
            'products_created': 0, 'products_matched': 0,
            'variants_created': 0, 'variants_price_updated': 0,
            'variants_unchanged': 0, 'por_variants': 0,
            'price_changes_pending': 0, 'price_downgrades_blocked': 0,
            'products_reclassified': 0,
        }
        audit = []
        # Cache so a 5,000-row import does not re-query brands/categories.
        brand_cache, category_cache = {}, {}

        # Preload the whole catalog into memory. The database is in another
        # region (~170 ms per round trip), so per-row lookups would make this
        # import take hours; two upfront queries make it seconds.
        # Keyed case-insensitively: slugs are lowercased, so treating "HDB3W"
        # and "HDB3w" as different series would miss the existing product and
        # then collide on its slug.
        product_index = {}   # (brand_id, series.casefold()) -> Product
        for prod in Product.objects.all().only('id', 'brand_id', 'series', 'slug'):
            if prod.series:
                product_index[(prod.brand_id, prod.series.strip().casefold())] = prod
        variant_index = {}   # (product_id, cat_no, rating) -> ProductVariant
        for var in ProductVariant.objects.all().only(
                'id', 'product_id', 'cat_no', 'description', 'price',
                'price_on_request', 'specs'):
            rating = ''
            if isinstance(var.specs, dict):
                rating = str(var.specs.get('rating') or '')
            variant_index[(var.product_id, var.cat_no, rating)] = var
        existing_slugs = set(Product.objects.values_list('slug', flat=True))
        self.stdout.write(
            f'  preloaded {len(product_index)} keyed products, '
            f'{len(variant_index)} variants'
        )

        for fname in files:
            path = os.path.join(src_dir, fname)
            with open(path, encoding='utf-8') as fh:
                payload = json.load(fh)
            rows = payload.get('rows') or []
            self.stdout.write(f'\n  {fname}: {len(rows)} rows')

            # Decide each product's category from ALL of its rows, not just the
            # first one seen. A price list often names the product type only in
            # one row of a block ("Accessories of MCCBs") while the rest are
            # bare rating lines; without this, most of a series lands in the
            # generic bucket and customers cannot browse to it.
            series_votes = {}
            for row in rows:
                pair = classify(row)
                if pair == FALLBACK_CATEGORY:
                    continue
                k = ((row.get('brand') or '').strip(), product_key(row))
                series_votes.setdefault(k, {})
                series_votes[k][pair] = series_votes[k].get(pair, 0) + 1
            series_category = {
                k: max(v.items(), key=lambda kv: kv[1])[0]
                for k, v in series_votes.items()
            }

            per_file = {'created': 0, 'updated': 0, 'products': 0}

            with transaction.atomic():
                for row in rows:
                    stats['rows'] += 1
                    model = (row.get('model') or '').strip()
                    if not model:
                        stats['skipped_rows'] += 1
                        continue

                    raw_brand = (row.get('brand') or '').strip() or 'Generic'
                    brand_name = BRAND_ALIASES.get(raw_brand, raw_brand)

                    brand = brand_cache.get(brand_name)
                    if brand is None:
                        brand, made = get_or_create_by_name_or_slug(Brand, brand_name)
                        brand_cache[brand_name] = brand
                        if made and not dry:
                            self.stdout.write(f'    + brand: {ascii_safe(brand_name)}')

                    parent_name, sub_name = series_category.get(
                        (raw_brand, product_key(row)), classify(row))
                    cat_key = (parent_name, sub_name)
                    category = category_cache.get(cat_key)
                    if category is None:
                        parent, _ = get_or_create_by_name_or_slug(Category, parent_name)
                        category, _ = get_or_create_by_name_or_slug(
                            Category, sub_name, parent=parent)
                        category_cache[cat_key] = category

                    key = product_key(row)
                    if not key:
                        stats['skipped_rows'] += 1
                        continue

                    name = build_product_name(brand.name, key, row)
                    # series is the grouping key: every ampere row of one series
                    # collapses into a single product with many variants, which
                    # is what the storefront amperage dropdown renders.
                    series_key = key[:100]
                    index_key = (brand.id, series_key.strip().casefold())
                    product = product_index.get(index_key)
                    if product is None:
                        base = slugify(f'{brand.name}-{series_key}')[:280] or slugify(name)[:280]
                        slug, n = base, 2
                        while slug in existing_slugs:
                            slug = f'{base}-{n}'[:290]
                            n += 1
                        existing_slugs.add(slug)
                        product = Product(
                            name=name[:300], slug=slug, brand=brand, category=category,
                            series=series_key,
                            short_description=(row.get('description') or '')[:500],
                            is_active=True,
                        )
                        if not dry:
                            product.save()
                        # Index it either way so later rows of the same series
                        # group onto it — that keeps the dry-run preview honest.
                        product_index[index_key] = product
                        stats['products_created'] += 1
                        per_file['products'] += 1
                    else:
                        stats['products_matched'] += 1
                        # Only ever promote OUT of the generic bucket — never
                        # overwrite a category the client may have set by hand
                        # in the admin panel.
                        if (opts['reclassify']
                                and cat_key != FALLBACK_CATEGORY
                                and product.category_id != category.id
                                and product.category
                                and product.category.name == FALLBACK_CATEGORY[1]):
                            product.category = category
                            if not dry:
                                product.save(update_fields=['category'])
                            stats['products_reclassified'] += 1

                    price = to_decimal(row.get('price_pkr'))
                    por = price is None
                    if por:
                        stats['por_variants'] += 1

                    specs = row.get('specs') or {}
                    rating = str(specs.get('rating') or '').strip()
                    desc = variant_description(row)

                    # Variant identity = (product, cat_no, rating). Two ampere
                    # ratings of one model are different variants; the same
                    # rating re-imported is the same row and updates in place.
                    vkey = (product.pk, model[:100], rating)
                    variant = variant_index.get(vkey)

                    if variant is None:
                        new_variant = ProductVariant(
                            product=product, cat_no=model[:100], description=desc,
                            price=price, price_on_request=por, specs=specs,
                            is_active=True,
                        )
                        if not dry:
                            new_variant.save()
                            variant_index[(product.pk, model[:100], rating)] = new_variant
                        else:
                            # Keep the preview honest about duplicate rows.
                            variant_index[vkey] = new_variant
                        stats['variants_created'] += 1
                        per_file['created'] += 1
                        action = 'created'
                    elif variant.price != price or variant.price_on_request != por:
                        old = variant.price
                        # Never downgrade a real price to "on request": the PDF
                        # omitting a figure is not the client withdrawing a
                        # price the store is already selling at.
                        if price is None and old is not None:
                            stats['price_downgrades_blocked'] += 1
                            action = f'kept {old} (new list has no price)'
                        elif not update_prices:
                            stats['price_changes_pending'] += 1
                            action = f'PENDING price {old} -> {price}'
                        else:
                            variant.price = price
                            variant.price_on_request = por
                            variant.specs = specs or variant.specs
                            if not dry and variant.pk:
                                variant.save(update_fields=['price', 'price_on_request', 'specs'])
                            stats['variants_price_updated'] += 1
                            per_file['updated'] += 1
                            action = f'price {old} -> {price}'
                    else:
                        stats['variants_unchanged'] += 1
                        action = 'unchanged'

                    audit.append([fname, row.get('page'), brand.name, key, model,
                                  rating, str(price or ''), action])

                if dry:
                    transaction.set_rollback(True)

            self.stdout.write(
                f'    products +{per_file["products"]}  '
                f'variants +{per_file["created"]}  updated {per_file["updated"]}'
            )

        self.stdout.write(self.style.MIGRATE_HEADING('\nSummary'))
        for k, v in stats.items():
            self.stdout.write(f'  {k:24} {v}')

        if opts['report']:
            with open(opts['report'], 'w', newline='', encoding='utf-8') as fh:
                w = csv.writer(fh)
                w.writerow(['file', 'page', 'brand', 'series', 'model',
                            'rating', 'price_pkr', 'action'])
                w.writerows(audit)
            self.stdout.write(f'  audit trail -> {opts["report"]}')

        if dry:
            self.stdout.write(self.style.WARNING(
                '\nDRY RUN — rolled back, nothing was written.'))
        else:
            # This command writes through the ORM, so it bypasses the API's
            # write-path cache invalidation. Without this bump the storefront
            # keeps serving the pre-import catalog from cache.
            bump_catalog_version()
            self.stdout.write('  catalog cache invalidated')
            self.stdout.write(self.style.SUCCESS('\nImport complete.'))
