"""
Import engmart_final.json into the Django database (Supabase PostgreSQL).

Run: python manage.py import_final
     python manage.py import_final --dry-run
     python manage.py import_final --clear

This replaces the old import_products command and works with the new
variant-grouped JSON format.
"""
import os
import json
import re
from django.core.management.base import BaseCommand
from django.utils.text import slugify
from django.db import transaction
from apps.brands.models import Brand
from apps.categories.models import Category
from apps.products.models import Product, ProductVariant


def sanitize(text):
    """Remove non-ASCII chars that crash Windows console."""
    if not text:
        return ""
    return text.encode('ascii', 'replace').decode('ascii')


# Map JSON brand names -> clean brand name + metadata
BRAND_DATA = {
    "ABB": {"name": "ABB", "origin": "Switzerland", "color": "#FF000F"},
    "AT Electricals": {"name": "AT Electricals", "origin": "Turkey", "color": "#0056A0"},
    "CHINT": {"name": "CHINT", "origin": "China", "color": "#003DA5"},
    "FICO": {"name": "FICO", "origin": "Pakistan", "color": "#00A651"},
    "Fuji Electric": {"name": "Fuji Electric", "origin": "Japan", "color": "#E60012"},
    "Himel": {"name": "Himel", "origin": "China", "color": "#F7941D"},
    "LS Electric": {"name": "LS Electric", "origin": "South Korea", "color": "#E31E24"},
    "Lovato": {"name": "Lovato", "origin": "Italy", "color": "#1B3F8B"},
    "PCE": {"name": "PCE", "origin": "Austria", "color": "#FF6600"},
    "SMC": {"name": "SMC", "origin": "Pakistan", "color": "#2E3192"},
    "Schneider Electric": {"name": "Schneider Electric", "origin": "France", "color": "#3DCD58"},
    "Siemens": {"name": "Siemens", "origin": "Germany", "color": "#009999"},
    "SWAS": {"name": "SWAS", "origin": "Pakistan", "color": "#333333"},
    "Terasaki": {"name": "Terasaki", "origin": "Japan", "color": "#0033A0"},
    "Hyundai": {"name": "Hyundai", "origin": "South Korea", "color": "#002C5F"},
    "ETI": {"name": "ETI", "origin": "Slovenia", "color": "#C8102E"},
    "C&S Electric": {"name": "C&S Electric", "origin": "India", "color": "#00539F"},
    "Hager": {"name": "Hager", "origin": "Germany", "color": "#009640"},
    "Eaton": {"name": "Eaton", "origin": "Ireland", "color": "#00A3E0"},
    "Mitsubishi": {"name": "Mitsubishi", "origin": "Japan", "color": "#CC0000"},
}

# Map subcategory strings -> parent category + subcategory
CATEGORY_MAP = {
    "MCB": ("Circuit Protection", "MCB"),
    "MCCB": ("Circuit Protection", "MCCB"),
    "ACB": ("Circuit Protection", "ACB"),
    "RCCB": ("Circuit Protection", "RCCB"),
    "ELCB": ("Circuit Protection", "ELCB"),
    "RCBO": ("Circuit Protection", "RCBO"),
    "Fuse": ("Circuit Protection", "Fuses"),
    "Fuses": ("Circuit Protection", "Fuses"),
    "Surge Protector": ("Circuit Protection", "Surge Protection"),
    "Surge Protection": ("Circuit Protection", "Surge Protection"),
    "Contactor": ("Contactors & Relays", "Contactors"),
    "Contactors": ("Contactors & Relays", "Contactors"),
    "Overload Relay": ("Contactors & Relays", "Overload Relays"),
    "Thermal Overload Relay": ("Contactors & Relays", "Overload Relays"),
    "Relay": ("Contactors & Relays", "Relays"),
    "Motor Starter": ("Motor Control", "Motor Starters"),
    "VFD": ("Motor Control", "VFDs"),
    "Soft Starter": ("Motor Control", "Soft Starters"),
    "Inverter": ("Motor Control", "Inverters"),
    "Selector Switch": ("Switches & Indicators", "Selector Switches"),
    "Push Button": ("Switches & Indicators", "Push Buttons"),
    "Pilot Lamp": ("Switches & Indicators", "Pilot Lamps"),
    "Indicator": ("Switches & Indicators", "Indicators"),
    "Isolator": ("Switches & Indicators", "Isolators"),
    "Changeover Switch": ("Switches & Indicators", "Changeover Switches"),
    "Current Transformer": ("Metering", "Current Transformers"),
    "Meter": ("Metering", "Panel Meters"),
    "Capacitor": ("Power Factor Correction", "Capacitors"),
    "PF Controller": ("Power Factor Correction", "PF Controllers"),
    "Wiring Accessories": ("Wiring & Accessories", "Wiring Devices"),
    "Cable": ("Wiring & Accessories", "Cables"),
    "Terminal": ("Wiring & Accessories", "Terminals"),
    "Industrial Plug": ("Plugs & Sockets", "Industrial Plugs"),
    "Industrial Socket": ("Plugs & Sockets", "Industrial Sockets"),
    "Timer": ("Timers & Controllers", "Timers"),
    "Counter": ("Timers & Controllers", "Counters"),
    "General": ("Electrical Equipment", "General"),
    "Main Switches": ("Switching Devices", "Main Switches"),
}


class Command(BaseCommand):
    help = 'Import engmart_final.json into the database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Show what would be imported without saving',
        )
        parser.add_argument(
            '--clear', action='store_true',
            help='Clear all existing products before importing',
        )
        parser.add_argument(
            '--file', type=str,
            default=os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))),
                '..', 'product', 'engmart_final.json'
            ),
            help='Path to the JSON file to import',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        clear = options['clear']
        json_path = options['file']

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE'))

        # Load JSON
        self.stdout.write(f'Loading: {json_path}')
        with open(json_path, 'r', encoding='utf-8') as f:
            products_data = json.load(f)
        self.stdout.write(f'Loaded {len(products_data)} products')

        if clear and not dry_run:
            self.stdout.write(self.style.WARNING('Clearing all existing products...'))
            ProductVariant.objects.all().delete()
            Product.objects.all().delete()
            self.stdout.write('Cleared.')

        # Phase 1: Ensure all brands exist
        self.stdout.write('\n--- Phase 1: Brands ---')
        brand_names = set(p.get('brand', '') for p in products_data)
        brand_cache = {}
        for brand_name in sorted(brand_names):
            if not brand_name:
                continue
            brand_slug = slugify(brand_name)
            brand_data = BRAND_DATA.get(brand_name, {})

            brand, created = Brand.objects.get_or_create(
                slug=brand_slug,
                defaults={
                    'name': brand_data.get('name', brand_name),
                    'origin_country': brand_data.get('origin', ''),
                    'color': brand_data.get('color', ''),
                    'is_active': True,
                }
            )
            brand_cache[brand_name] = brand
            status = 'CREATED' if created else 'EXISTS'
            self.stdout.write(f'  [{status}] {brand.name}')

        # Phase 2: Ensure all categories exist
        self.stdout.write('\n--- Phase 2: Categories ---')
        cat_cache = {}
        parent_cache = {}

        for p in products_data:
            cat = p.get('category', 'Electrical Equipment')
            subcat = p.get('subcategory', 'General')
            mapped = CATEGORY_MAP.get(subcat)
            if mapped:
                parent_name, sub_name = mapped
            else:
                parent_name = cat
                sub_name = subcat

            if parent_name not in parent_cache:
                parent_slug = slugify(parent_name)
                parent, created = Category.objects.get_or_create(
                    slug=parent_slug,
                    defaults={
                        'name': parent_name,
                        'is_active': True,
                    }
                )
                parent_cache[parent_name] = parent
                if created:
                    self.stdout.write(f'  [CREATED] Parent: {parent_name}')

            cache_key = f"{parent_name}|{sub_name}"
            if cache_key not in cat_cache:
                sub_slug = slugify(sub_name)
                existing = Category.objects.filter(slug=sub_slug).first()
                if existing:
                    cat_cache[cache_key] = existing
                else:
                    sub_cat = Category.objects.create(
                        name=sub_name,
                        slug=sub_slug,
                        parent=parent_cache[parent_name],
                        short_name=sub_name[:50],
                        is_active=True,
                    )
                    cat_cache[cache_key] = sub_cat
                    self.stdout.write(f'  [CREATED] Sub: {parent_name} > {sub_name}')

        # Phase 3: Import products with variants
        self.stdout.write('\n--- Phase 3: Products ---')

        created_products = 0
        created_variants = 0
        skipped = 0
        used_slugs = set(Product.objects.values_list('slug', flat=True))

        with transaction.atomic():
            for i, pd in enumerate(products_data):
                name = (pd.get('product_name') or '').strip()
                if not name or len(name) < 3:
                    skipped += 1
                    continue

                brand_name = pd.get('brand', '')
                brand = brand_cache.get(brand_name)
                if not brand:
                    skipped += 1
                    continue

                cat = pd.get('category', 'Electrical Equipment')
                subcat = pd.get('subcategory', 'General')
                mapped = CATEGORY_MAP.get(subcat)
                if mapped:
                    parent_name, sub_name = mapped
                else:
                    parent_name = cat
                    sub_name = subcat

                cache_key = f"{parent_name}|{sub_name}"
                category = cat_cache.get(cache_key)
                if not category:
                    category = Category.objects.first()

                base_slug = slugify(f"{brand.name}-{name}")[:280]
                slug = base_slug
                counter = 1
                while slug in used_slugs:
                    slug = f"{base_slug}-{counter}"
                    counter += 1
                used_slugs.add(slug)

                short_desc = (pd.get('description') or '')[:500]
                full_desc = pd.get('description') or ''
                tech_specs = pd.get('technical_specs') or ''
                if tech_specs and tech_specs not in full_desc:
                    full_desc = f"{full_desc}\n\nTechnical Specs: {tech_specs}"

                if dry_run:
                    vcount = len(pd.get('variants') or []) or 1
                    self.stdout.write(sanitize(
                        f'  [DRY] {brand.name} - {name} [{vcount} variants]'
                    ))
                    created_products += 1
                    created_variants += vcount
                    continue

                img_rel = pd.get('image')
                image_val = f"extracted_images/{img_rel}" if img_rel else ""

                product = Product.objects.create(
                    name=name[:300],
                    slug=slug,
                    brand=brand,
                    category=category,
                    series=(pd.get('product_code') or '')[:200],
                    short_description=short_desc,
                    full_description=full_desc,
                    image=image_val,
                    is_active=True,
                )
                created_products += 1

                # Add extra images if any
                all_imgs = pd.get('image_all', [])
                for idx, extra_img in enumerate(all_imgs[:5]):
                    ProductImage.objects.create(
                        product=product,
                        image=f"extracted_images/{extra_img}",
                        alt_text=f"{product.name} Image {idx+1}",
                        is_primary=(idx == 0),
                        order=idx
                    )

                variants = pd.get('variants')
                if variants:
                    for j, v in enumerate(variants):
                        price = v.get('price')
                        por = price is None
                        desc = v.get('variant_label', '') or v.get('full_name', '')

                        ProductVariant.objects.create(
                            product=product,
                            cat_no=(pd.get('product_code') or '')[:100],
                            description=desc[:300],
                            price=price,
                            price_on_request=por,
                            specs={
                                'technical_specs': v.get('technical_specs', ''),
                                'full_name': v.get('full_name', ''),
                            },
                            is_active=True,
                            order=j,
                        )
                        created_variants += 1
                else:
                    price = pd.get('unit_price')
                    por = price is None

                    ProductVariant.objects.create(
                        product=product,
                        cat_no=(pd.get('product_code') or '')[:100],
                        description=name[:300],
                        price=price,
                        price_on_request=por,
                        specs={'technical_specs': tech_specs},
                        is_active=True,
                        order=0,
                    )
                    created_variants += 1

                if (i + 1) % 100 == 0:
                    self.stdout.write(f'  ... processed {i+1}/{len(products_data)}')

        self.stdout.write(self.style.SUCCESS(
            f'\n{"="*60}\n'
            f'IMPORT COMPLETE\n'
            f'  Products: {created_products}\n'
            f'  Variants: {created_variants}\n'
            f'  Skipped: {skipped}\n'
            f'  Brands: {len(brand_cache)}\n'
            f'  Categories: {len(cat_cache)}\n'
            f'{"="*60}'
        ))
