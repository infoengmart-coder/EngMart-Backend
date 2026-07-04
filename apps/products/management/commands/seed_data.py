"""
Seed the database with initial brands and categories.
Run: python manage.py seed_data
"""
from django.core.management.base import BaseCommand
from apps.brands.models import Brand
from apps.categories.models import Category


BRANDS = [
    {'name': 'ABB', 'slug': 'abb', 'origin_country': 'Switzerland', 'supplier_name': 'Ameejee Valleejee & Sons', 'color': '#FF0000', 'order': 1},
    {'name': 'CHINT', 'slug': 'chint', 'origin_country': 'China', 'supplier_name': 'HL PK Pvt Ltd', 'color': '#0066CC', 'order': 2},
    {'name': 'Himel', 'slug': 'himel', 'origin_country': 'International', 'supplier_name': 'Powerhouse', 'color': '#E30613', 'order': 3},
    {'name': 'FICO Hi-Tech', 'slug': 'fico', 'origin_country': 'Pakistan', 'supplier_name': 'Cognitive Solutions', 'color': '#1B4F8A', 'order': 4},
    {'name': 'PCE', 'slug': 'pce', 'origin_country': 'Germany', 'supplier_name': 'Powerhouse', 'color': '#F97316', 'order': 5},
    {'name': 'Tense', 'slug': 'tense', 'origin_country': 'Turkey', 'supplier_name': 'AT Electricals', 'color': '#C0392B', 'order': 6},
    {'name': 'Kondas', 'slug': 'kondas', 'origin_country': 'Turkey', 'supplier_name': 'AT Electricals', 'color': '#2980B9', 'order': 7},
    {'name': 'Opas', 'slug': 'opas', 'origin_country': 'Turkey', 'supplier_name': 'AT Electricals', 'color': '#27AE60', 'order': 8},
    {'name': 'Siemens', 'slug': 'siemens', 'origin_country': 'Germany', 'supplier_name': 'Siemens Pakistan', 'color': '#009999', 'order': 9},
]

CATEGORIES = [
    {'name': 'Miniature Circuit Breakers', 'slug': 'mcb', 'short_name': 'MCBs', 'icon': '⚡', 'color': '#F97316', 'order': 1,
     'description': '1-Pole to 4-Pole MCBs, 4.5kA to 10kA breaking capacity, B/C/D curves from ABB, CHINT & Himel'},
    {'name': 'Molded Case Circuit Breakers', 'slug': 'mccb', 'short_name': 'MCCBs', 'icon': '🔌', 'color': '#1E3A5F', 'order': 2,
     'description': 'Fixed & adjustable MCCBs from 16A to 1600A, 25kA to 70kA from ABB, CHINT & Himel'},
    {'name': 'Magnetic Contactors', 'slug': 'contactors', 'short_name': 'Contactors', 'icon': '🔧', 'color': '#0F4C81', 'order': 3,
     'description': '3-Pole & 4-Pole contactors from 9A to 750A, 4kW to 400kW motor ratings'},
    {'name': 'Current Transformers', 'slug': 'current-transformers', 'short_name': 'CTs', 'icon': '🔄', 'color': '#7C3AED', 'order': 4,
     'description': 'Window, split-core, resin-cast & bar-type CTs, 30/5A to 8000/5A, Class 0.5 to 1'},
    {'name': 'Digital & Analogue Meters', 'slug': 'panel-meters', 'short_name': 'Panel Meters', 'icon': '📊', 'color': '#0891B2', 'order': 5,
     'description': 'Voltmeters, ammeters, frequency, watt & multifunction panel meters — 48mm to 96mm'},
    {'name': 'Power Capacitors & PF Controllers', 'slug': 'capacitors', 'short_name': 'Capacitors', 'icon': '⚙️', 'color': '#059669', 'order': 6,
     'description': 'LV capacitors (dry type), power factor controllers, 2.5 to 50 KVAR'},
    {'name': 'Protection Relays', 'slug': 'protection-relays', 'short_name': 'Relays', 'icon': '🛡️', 'color': '#DC2626', 'order': 7,
     'description': 'Under/over voltage relays, phase failure relays, thermal overload relays'},
    {'name': 'Industrial Plugs & Sockets', 'slug': 'plugs-sockets', 'short_name': 'Plugs & Sockets', 'icon': '🔌', 'color': '#D97706', 'order': 8,
     'description': 'Industrial plugs, wall sockets, connectors, flanged sockets — 16A to 125A, IP44/IP67'},
    {'name': 'Air Circuit Breakers', 'slug': 'acb', 'short_name': 'ACBs', 'icon': '⚡', 'color': '#4338CA', 'order': 9,
     'description': 'Draw-out and fixed ACBs from 800A to 6300A, 42kA to 100kA'},
    {'name': 'Motor Protection', 'slug': 'motor-protection', 'short_name': 'MPCBs', 'icon': '🏭', 'color': '#7C3AED', 'order': 10,
     'description': 'Motor protection circuit breakers, DOL starters, manual motor starters'},
    {'name': 'Timers & Controllers', 'slug': 'timers-controllers', 'short_name': 'Timers', 'icon': '⏱️', 'color': '#0D9488', 'order': 11,
     'description': 'Star-delta timers, programmable timers, temperature controllers, PLC timers'},
    {'name': 'Cam Switches & Selector Switches', 'slug': 'cam-switches', 'short_name': 'Switches', 'icon': '🔀', 'color': '#6366F1', 'order': 12,
     'description': 'Changeover switches, phase selectors, volt/ampere cam switches'},
    {'name': 'Push Buttons & Indicators', 'slug': 'push-buttons', 'short_name': 'Push Buttons', 'icon': '🔴', 'color': '#EF4444', 'order': 13,
     'description': 'Panel push buttons, indicator lights, selector switches, emergency stops'},
    {'name': 'Variable Frequency Drives', 'slug': 'vfd', 'short_name': 'VFDs', 'icon': '🔋', 'color': '#2563EB', 'order': 14,
     'description': 'Basic and expert VFDs for motor speed control, 0.75kW to 132kW'},
    {'name': 'Fuses & Fuse Gear', 'slug': 'fuses', 'short_name': 'Fuses', 'icon': '💡', 'color': '#CA8A04', 'order': 15,
     'description': 'HRC fuses, fuse links, fuse bases, main switches, D-fuse fittings'},
    {'name': 'Consumer Boxes & Enclosures', 'slug': 'consumer-boxes', 'short_name': 'Enclosures', 'icon': '📦', 'color': '#64748B', 'order': 16,
     'description': 'Distribution boards, consumer units, 6 to 24 way boxes'},
    {'name': 'Wiring Devices', 'slug': 'wiring-devices', 'short_name': 'Wiring', 'icon': '🏠', 'color': '#8B5CF6', 'order': 17,
     'description': 'Flush switches, sockets, dimmers, USB outlets, data points'},
    {'name': 'Surge Protection', 'slug': 'surge-protection', 'short_name': 'SPDs', 'icon': '🌩️', 'color': '#F59E0B', 'order': 18,
     'description': 'Surge protective devices, 20–80kA, Type 1+2 protection'},
    {'name': 'RCCBs & ELCBs', 'slug': 'rccb', 'short_name': 'RCCBs', 'icon': '🔒', 'color': '#10B981', 'order': 19,
     'description': 'Residual current circuit breakers, 2P/4P, 30mA/300mA sensitivity'},
    {'name': 'Change Over & Transfer Switches', 'slug': 'changeover-switches', 'short_name': 'ATS', 'icon': '🔄', 'color': '#6D28D9', 'order': 20,
     'description': 'Manual and automatic transfer switches, 30A to 2500A'},
]


class Command(BaseCommand):
    help = 'Seed database with initial brands and categories from plan.txt'

    def handle(self, *args, **options):
        # Seed brands
        brand_count = 0
        for data in BRANDS:
            brand, created = Brand.objects.update_or_create(
                slug=data['slug'],
                defaults=data,
            )
            if created:
                brand_count += 1
                self.stdout.write(f'  [+] Created brand: {brand.name}')
            else:
                self.stdout.write(f'  [=] Updated brand: {brand.name}')

        # Seed categories
        cat_count = 0
        for data in CATEGORIES:
            category, created = Category.objects.update_or_create(
                slug=data['slug'],
                defaults=data,
            )
            if created:
                cat_count += 1
                self.stdout.write(f'  [+] Created category: {category.name}')
            else:
                self.stdout.write(f'  [=] Updated category: {category.name}')

        self.stdout.write(self.style.SUCCESS(
            f'\nDone! {brand_count} brands created, {cat_count} categories created.'
        ))
