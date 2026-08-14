"""
Import extracted JSON product data into the Django database.
Run: python manage.py import_products

Maps JSON files -> Brand (existing) -> Category (existing/best match) -> Products + Variants
"""
import os
import sys
import json
import re
from django.core.management.base import BaseCommand
from django.utils.text import slugify
from apps.brands.models import Brand
from apps.categories.models import Category
from apps.products.models import Product, ProductVariant


def sanitize_text(text):
    """Remove non-ASCII chars that crash Windows cp1252 console."""
    return text.encode('ascii', 'replace').decode('ascii')

JSON_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))), 'extracted_data')

# Map JSON brand names -> DB brand slugs
BRAND_MAP = {
    'CHINT': 'chint',
    'AT Electricals (Tense/Kondas/Opas)': 'tense',  # Primary brand for AT Electricals
    'FICO Hi-Tech': 'fico',
    'Himel': 'himel',
    'JC': 'kondas',  # JC products are from Kondas
    'PCE': 'pce',
    'ABB': 'abb',
    'Siemens': 'siemens',
    'SWAS': 'himel',  # SWAS distributes Himel/Schneider products
}

# Map category keywords -> DB category slugs
CATEGORY_KEYWORDS = {
    'mcb': ['mcb', 'miniature circuit breaker', 'nxb-63', 'sh200', 's200', 'ndb'],
    'mccb': ['mccb', 'molded case', 'moulded case', 'nxm', 'formula', 'hdm', 'tmax', 't max'],
    'contactors': ['contactor', 'nxc', 'nc1', 'a-line', 'magnetic contactor', 'hdc'],
    'current-transformers': ['current transformer', 'ct ', 'c.t.', 'window type', 'split core', 'msq'],
    'panel-meters': ['panel meter', 'voltmeter', 'ammeter', 'multifunction meter', 'watt meter', 'frequency meter', 'digital meter', 'analogue meter'],
    'capacitors': ['capacitor', 'kvar', 'power factor', 'pf controller', 'nwc', 'clmd'],
    'protection-relays': ['relay', 'overload', 'nxr', 'nr2', 'thermal relay', 'phase failure', 'under voltage', 'over voltage', 'uvr', 'ovr'],
    'plugs-sockets': ['plug', 'socket', 'connector', 'flanged', 'ip44', 'ip67', 'pce', 'industrial plug'],
    'acb': ['acb', 'air circuit breaker', 'emax', 'draw-out', 'drawout'],
    'motor-protection': ['motor protection', 'mpcb', 'motor starter', 'dol starter', 'manual motor'],
    'timers-controllers': ['timer', 'temperature controller', 'star delta', 'time relay', 'plc', 'programmable'],
    'cam-switches': ['cam switch', 'changeover', 'selector switch', 'rotary switch', 'phase selector'],
    'push-buttons': ['push button', 'indicator', 'pilot lamp', 'emergency stop', 'signal lamp'],
    'vfd': ['vfd', 'variable frequency', 'drive', 'inverter', 'nvf'],
    'fuses': ['fuse', 'hrc', 'fuse link', 'fuse base', 'main switch', 'd-fuse'],
    'consumer-boxes': ['consumer', 'distribution board', 'db box', 'enclosure', 'panel box'],
    'wiring-devices': ['switch', 'dimmer', 'usb outlet', 'data point', 'flush'],
    'surge-protection': ['surge', 'spd', 'lightning', 'arrester'],
    'rccb': ['rccb', 'elcb', 'earth leakage', 'residual current', 'nl1', 'nxble', 'rcbo'],
    'changeover-switches': ['changeover switch', 'transfer switch', 'ats', 'automatic transfer'],
}

# Skip these "products" — they're header noise from PDF extraction
SKIP_PATTERNS = [
    r'^AMEEJEE', r'^HL PK', r'^PRICE LIST', r'^Price List',
    r'^Dear Valued', r'^Note:', r'^for a better', r'^Power and',
    r'^PAGE$', r'^W\.E\.F', r'^Product\s+Cat', r'^Serial\s+No',
    r'^S No', r'^Tel\b', r'^E mail', r'^General Terms',
    r'^Date of Implementation', r'^Warranty', r'^Sales Return',
    r'^Insurance', r'^Changes in Price', r'^Pricing', r'^Thank you',
    r'^Head Office', r'^Catalogue Ref', r'^Total Electrical',
    r'^Low Voltage Switchgear', r'^Dated:',
    r'^\d{1,2}-\d{1,2}$',
    # FICO noise
    r'^Distributor$', r'^Karachi', r'^Company Outlet',
    r'^SALES TAX', r'^1 YEAR', r'^WARRANTY',
    r'^Highly compact', r'^HAVING OPTION',
    r'^Ratio\s+Class', r'^Ration\s+Class', r'^Price Rs$',
    r'^CurrentBurden', r'^A/5 VA', r'^DESCRIPTION PRICE',
    r'^Industrial automation', r'^4 DIGIT PASSWORD',
    r'^CONSUMPTION', r'^Current Transducer',
    r'^MLC \(RESIN', r'^\d+/5A$', r'^\d+/5\s',
    r'^Rating Type Poles', r'^\d+K\d+K$',
    # Himel noise
    r'^WIRING DEVICES', r'^www\.', r'^\(L,S,I\)',
    r'^Low-voltage Capacitor$',
    # ABB noise
    r'^MADE IN', r'^According to',
    r'^for a better worldTM$',
    # SWAS noise
    r'^Dear Valued Customer',
    r'^The following conditions',
    r'^Misuse', r'^Modification', r'^Faulty',
    r'^In case of returns',
    r'^All dispatches',
    r'^The prices provided',
    r'^applicable',
    r'^FDM\s+\d+\s*[B3]?\s*[V-]',
    r'^WSB-',
    r'^4VA OPERATING',
    r'^200K40K',
    r'^\d+/5\s+\d+\s+\d+\s+\d+',
    # Himel/SWAS spaced-letter headers
    r'P\s+R\s+I\s+C\s+E',
    r'I\s+N\s+D\s+E\s+X',
    r'I\s+C\s+E\s+L\s+I',
    r'C\s+E\s+L\s+I\s+S',
    r'E\s+L\s+I\s+S\s+T',
    r'A\s+T\s+U\s+R\s+E',
    r'F\s+E\s+A\s+T\s+U',
    # More Himel/SWAS noise
    r'^RATINGS?\s*\(AMPERES\)',
    r'^RATING\s+MODEL\s+BREAKING',
    r'^RATIN\s*G\s+THERMAL',
    r'^DESCRIPTION\s+UNIT PRICE',
    r'^\(Rupees\)',
    r'^PTIONAL ACCESSORIES',
    r'^FAILURE PROTECTION',
    r'^REQUIRED DRIVES',
    r'^MICROLOGIC',
    r'^HIGH BREAKING CAPACITY$',
    r'^BACKLIT LCD',
    r'^IGITAL DISPLAY',
    r'^VOLTAGE\s*:\s*0',
    r'^LED DISPLAY',
    r'^L VOLTMETERS',
    r'^INGLE PHASE',
    r'^LCD DISPLAY WITH RS',
    r'^OUTPUT:\s+THREE PHASE',
    r'^POWER SUP\s*PLY',
    r'^DESIGNED.*MANUFACTURED.*TESTED',
    r'^AUX\.\s+CONTACT BLOCKS',
    r'^POWER CONTROL',
    r'^DIFFERENTIAL TYPE$',
    r'^ON / OFF RELAY',
    r'^ALARM OUTPUT',
    r'^SIZE:\s+\d+\s+X\s+\d+',
    r'^\d+\s+P\s+R\s+I',
    r'^he prices in the list',
    r'^AS PER K',
    r'^TRIP RELAY',
    r'^\* POWER$',
]


def should_skip_product(name):
    """Check if a product name is actually noise from PDF headers."""
    if not name or len(name.strip()) < 4:
        return True
    name_clean = name.strip()
    for pattern in SKIP_PATTERNS:
        if re.search(pattern, name_clean, re.IGNORECASE):
            return True
    # Skip if it's just numbers or very short
    if re.match(r'^[\d\s\-\.]+$', name_clean):
        return True
    # Skip if mostly non-alphanumeric
    alpha_count = sum(1 for c in name_clean if c.isalpha())
    if alpha_count < 3:
        return True
    # Skip if name is too long (likely a paragraph, not a product name)
    if len(name_clean) > 150:
        return True
    return False


def guess_category(product_name, product_desc, variants):
    """Guess the category based on product name, description, and variant descriptions."""
    # Combine all text for matching
    search_text = f"{product_name} {product_desc} "
    for v in variants[:5]:
        search_text += f"{v.get('description', '')} "
    search_text = search_text.lower()
    
    # Score each category
    best_cat = None
    best_score = 0
    
    for cat_slug, keywords in CATEGORY_KEYWORDS.items():
        score = 0
        for kw in keywords:
            if kw.lower() in search_text:
                score += len(kw)  # Longer matches get higher score
        if score > best_score:
            best_score = score
            best_cat = cat_slug
    
    return best_cat or 'mcb'  # Default to MCB if can't determine


def clean_variant_description(desc):
    """Clean up variant description."""
    desc = desc.strip()
    # Remove leading serial numbers
    desc = re.sub(r'^\d+\s+', '', desc)
    # Remove trailing "Pcs" / "pcs" / "Nos" etc.
    desc = re.sub(r'\s+(Pcs|pcs|Nos|nos|Each|each|Set|set)\s*$', '', desc)
    return desc[:300]


class Command(BaseCommand):
    help = 'Import extracted JSON product data into the database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be imported without saving',
        )
        parser.add_argument(
            '--file',
            type=str,
            help='Import a specific JSON file only (e.g., chint.json)',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        specific_file = options.get('file')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - no data will be saved'))
        
        # Load all JSON files
        json_files = []
        if specific_file:
            json_files = [specific_file]
        else:
            json_files = sorted(f for f in os.listdir(JSON_DIR) if f.endswith('.json'))
        
        total_products = 0
        total_variants = 0
        
        for json_file in json_files:
            filepath = os.path.join(JSON_DIR, json_file)
            self.stdout.write(f'\n{"="*60}')
            self.stdout.write(f'Processing: {json_file}')
            self.stdout.write(f'{"="*60}')
            
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            brand_name = data.get('brand', '')
            brand_slug = BRAND_MAP.get(brand_name)
            
            if not brand_slug:
                self.stdout.write(self.style.WARNING(f'  Unknown brand: {brand_name}, skipping'))
                continue
            
            try:
                brand = Brand.objects.get(slug=brand_slug)
            except Brand.DoesNotExist:
                self.stdout.write(self.style.WARNING(f'  Brand not found in DB: {brand_slug}, skipping'))
                continue
            
            self.stdout.write(f'  Brand: {brand.name}')
            
            file_products = 0
            file_variants = 0
            
            for product_data in data.get('products', []):
                name = product_data.get('name', '').strip()
                
                # Skip noise
                if should_skip_product(name):
                    continue
                
                variants_data = product_data.get('variants', [])
                if not variants_data:
                    continue
                
                # Filter out bad variants
                good_variants = []
                for v in variants_data:
                    desc = v.get('description', '').strip()
                    if desc and len(desc) > 3 and not should_skip_product(desc):
                        good_variants.append(v)
                
                if not good_variants:
                    continue
                
                # Guess category
                cat_slug = product_data.get('category', 'general')
                if cat_slug == 'general':
                    cat_slug = guess_category(name, product_data.get('description', ''), good_variants)
                
                try:
                    category = Category.objects.get(slug=cat_slug)
                except Category.DoesNotExist:
                    category = Category.objects.first()  # Fallback
                
                # Create product slug
                product_slug = slugify(f"{brand.name}-{name}")[:300]
                
                # Ensure unique slug
                base_slug = product_slug
                counter = 1
                while Product.objects.filter(slug=product_slug).exists():
                    product_slug = f"{base_slug}-{counter}"
                    counter += 1
                
                if dry_run:
                    self.stdout.write(sanitize_text(f'  [DRY] Product: {brand.name} - {name} ({category.short_name or category.name}) [{len(good_variants)} variants]'))
                    file_products += 1
                    file_variants += len(good_variants)
                    continue
                
                # Create product
                product = Product.objects.create(
                    name=name[:300],
                    slug=product_slug,
                    brand=brand,
                    category=category,
                    series=product_data.get('series', '')[:200],
                    short_description=product_data.get('description', '')[:500],
                    full_description=product_data.get('description', ''),
                    is_active=True,
                )
                file_products += 1
                
                # Create variants
                for i, v in enumerate(good_variants):
                    desc = clean_variant_description(v.get('description', ''))
                    price = v.get('price')
                    por = v.get('price_on_request', False)
                    
                    # If price is 0 or None, set POR
                    if price is None or price == 0:
                        por = True
                        price = None
                    
                    ProductVariant.objects.create(
                        product=product,
                        cat_no=v.get('cat_no', '')[:100],
                        description=desc,
                        price=price,
                        price_on_request=por,
                        specs=v.get('specs', {}),
                        is_active=True,
                        order=i,
                    )
                    file_variants += 1
                
                self.stdout.write(sanitize_text(f'  [+] {brand.name} - {name} ({category.short_name}) [{len(good_variants)} variants]'))
            
            total_products += file_products
            total_variants += file_variants
            self.stdout.write(f'  Subtotal: {file_products} products, {file_variants} variants')
        
        self.stdout.write(self.style.SUCCESS(
            f'\nIMPORT COMPLETE: {total_products} products, {total_variants} variants'
        ))
