"""
Extract product data from all 9 brand PDFs into JSON files.
Each PDF has a different format, so we handle each separately.

Output: One JSON file per brand in backend/extracted_data/
Format: {
    "brand": "CHINT",
    "products": [
        {
            "name": "NXB-63 MCB",
            "category": "MCB",
            "series": "NXB-63",
            "description": "Miniature Circuit Breaker",
            "variants": [
                {"cat_no": "", "description": "1P C6 6kA", "price": 604, "price_on_request": false, "specs": {"poles": "1P", "rating": "6A", "curve": "C", "breaking_capacity": "6kA"}},
            ]
        }
    ]
}
"""
import os
import sys
import json
import re
from PyPDF2 import PdfReader

PDF_DIR = r"c:\Users\AWCD\Desktop\client\engmart (2)\product-details"
OUTPUT_DIR = r"c:\Users\AWCD\Desktop\client\engmart (2)\backend\extracted_data"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def clean_price(price_str):
    """Convert price string to float, or return None if POR/0."""
    if not price_str:
        return None, True
    price_str = str(price_str).strip().replace(',', '').replace(' ', '')
    if price_str.lower() in ('por', 'p.o.r', 'p.o.r.', 'on request', '-', '', '0'):
        return None, True
    try:
        val = float(price_str)
        if val == 0:
            return None, True
        return val, False
    except ValueError:
        return None, True


def extract_chint():
    """CHINT PRICE LIST 2020.pdf - 4 pages, well-structured table."""
    filepath = os.path.join(PDF_DIR, "CHINT PRICE LIST 2020.pdf")
    reader = PdfReader(filepath)
    
    products = []
    current_category = None
    current_product = None
    
    all_text = ""
    for page in reader.pages:
        all_text += page.extract_text() + "\n"
    
    lines = all_text.split('\n')
    
    mcb_variants = []
    mccb_3p_variants = []
    mccb_4p_variants = []
    contactor_variants = []
    relay_variants = []
    rccb_variants = []
    earth_leakage_variants = []
    
    current_section = None
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Detect sections by keywords
        if 'NXB-63' in line and '6kA' in line:
            # MCB line
            match = re.search(r'(NXB-63\s+\d+P\s+C\d+\s+6kA)\s+\w+\s+(\d+)', line)
            if match:
                desc = match.group(1).strip()
                price_str = match.group(2)
                price, por = clean_price(price_str)
                
                # Parse specs
                specs_match = re.search(r'(\d+P)\s+C(\d+)\s+(\d+kA)', desc)
                specs = {}
                if specs_match:
                    specs = {
                        'poles': specs_match.group(1),
                        'rating': f'{specs_match.group(2)}A',
                        'curve': 'C',
                        'breaking_capacity': specs_match.group(3),
                    }
                
                mcb_variants.append({
                    'cat_no': '',
                    'description': desc,
                    'price': price,
                    'price_on_request': por,
                    'specs': specs,
                })
        
        elif 'NXM-' in line and ('3300' in line or '4300' in line):
            # MCCB line
            match = re.search(r'(NXM[LE]*-\d+\w*/[34]300\w*\s+\d+A(?:\s+\(\d+P\))?)', line)
            price_match = re.search(r'(\d{3,})\s*$', line)
            if match:
                desc = match.group(1).strip()
                price = None
                por = True
                if price_match:
                    price, por = clean_price(price_match.group(1))
                
                # Parse specs
                rating_match = re.search(r'(\d+)A', desc)
                pole_match = re.search(r'([34])300', desc)
                specs = {}
                if rating_match:
                    specs['rating'] = f'{rating_match.group(1)}A'
                if pole_match:
                    specs['poles'] = f'{pole_match.group(1)}P'
                
                variant = {
                    'cat_no': '',
                    'description': desc,
                    'price': price,
                    'price_on_request': por,
                    'specs': specs,
                }
                if '4300' in desc or '4P' in desc:
                    mccb_4p_variants.append(variant)
                else:
                    mccb_3p_variants.append(variant)
        
        elif 'NXC-' in line or 'NC1-' in line:
            # Contactor line
            match = re.search(r'((?:NXC|NC1)-\d+)', line)
            price_match = re.search(r'(\d{3,})\s*$', line)
            if match:
                desc_parts = line.split(match.group(1))
                full_desc = match.group(1)
                if len(desc_parts) > 1:
                    full_desc = line[line.index(match.group(1)):].strip()
                
                price = None
                por = True
                if price_match:
                    price, por = clean_price(price_match.group(1))
                
                contactor_variants.append({
                    'cat_no': match.group(1),
                    'description': full_desc.split('Pcs')[0].strip() if 'Pcs' in full_desc else full_desc,
                    'price': price,
                    'price_on_request': por,
                    'specs': {},
                })
        
        elif 'NXR-' in line or 'NR2-' in line:
            # Thermal relay line
            match = re.search(r'((?:NXR|NR2)-\d+)', line)
            price_match = re.search(r'(\d{3,})\s*$', line)
            if match:
                price = None
                por = True
                if price_match:
                    price, por = clean_price(price_match.group(1))
                
                relay_variants.append({
                    'cat_no': match.group(1),
                    'description': line.split('Pcs')[0].strip() if 'Pcs' in line else line,
                    'price': price,
                    'price_on_request': por,
                    'specs': {},
                })
        
        elif 'NL1-63' in line or 'NXBLE' in line:
            # RCCB line
            match = re.search(r'((?:NL1-63|NXBLE)[^\s]*(?:\s+\d+P)?(?:\s+\d+A)?(?:\s+\d+mA)?)', line)
            price_match = re.search(r'(\d{3,})\s*$', line)
            if match:
                price = None
                por = True
                if price_match:
                    price, por = clean_price(price_match.group(1))
                
                rccb_variants.append({
                    'cat_no': '',
                    'description': line.split('Pcs')[0].strip() if 'Pcs' in line else line[:80],
                    'price': price,
                    'price_on_request': por,
                    'specs': {},
                })
    
    # Build product groups
    if mcb_variants:
        products.append({
            'name': 'NXB-63 Miniature Circuit Breaker',
            'category': 'mcb',
            'series': 'NXB-63',
            'description': 'CHINT NXB-63 series MCB, 6kA breaking capacity, C curve, 1P to 4P',
            'variants': mcb_variants,
        })
    
    if mccb_3p_variants:
        products.append({
            'name': 'NXM Series MCCB 3-Pole',
            'category': 'mccb',
            'series': 'NXM',
            'description': 'CHINT NXM series Molded Case Circuit Breaker, 3-Pole',
            'variants': mccb_3p_variants,
        })
    
    if mccb_4p_variants:
        products.append({
            'name': 'NXM Series MCCB 4-Pole',
            'category': 'mccb',
            'series': 'NXM',
            'description': 'CHINT NXM series Molded Case Circuit Breaker, 4-Pole',
            'variants': mccb_4p_variants,
        })
    
    if contactor_variants:
        products.append({
            'name': 'NXC/NC1 Magnetic Contactor',
            'category': 'contactors',
            'series': 'NXC/NC1',
            'description': 'CHINT magnetic contactors, 3-Pole and 4-Pole',
            'variants': contactor_variants,
        })
    
    if relay_variants:
        products.append({
            'name': 'NXR/NR2 Thermal Overload Relay',
            'category': 'protection-relays',
            'series': 'NXR/NR2',
            'description': 'CHINT thermal overload relays',
            'variants': relay_variants,
        })
    
    if rccb_variants:
        products.append({
            'name': 'NL1-63 / NXBLE RCCB',
            'category': 'rccb',
            'series': 'NL1-63',
            'description': 'CHINT Residual Current Circuit Breakers',
            'variants': rccb_variants,
        })
    
    return {'brand': 'CHINT', 'products': products}


def extract_generic_table_pdf(filepath, brand_name):
    """
    Generic extractor for PDFs with tabular price lists.
    Extracts all text, groups by detected product categories.
    """
    reader = PdfReader(filepath)
    products = []
    
    all_lines = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            all_lines.extend(text.split('\n'))
    
    current_category_name = None
    current_product_name = None
    current_variants = []
    
    for line in all_lines:
        line = line.strip()
        if not line:
            continue
        
        # Try to detect if this is a product/price line (has a number at end)
        price_match = re.search(r'(\d[\d,]*\.?\d*)\s*$', line)
        
        # Detect category headers (all caps, no numbers at end)
        if line.isupper() and len(line) > 5 and not price_match:
            if current_product_name and current_variants:
                products.append({
                    'name': current_product_name,
                    'category': 'general',
                    'series': '',
                    'description': current_product_name,
                    'variants': current_variants,
                })
                current_variants = []
            current_category_name = line
            current_product_name = line
            continue
        
        # If line has a price at the end, treat as variant
        if price_match:
            desc = line[:price_match.start()].strip()
            price_str = price_match.group(1)
            price, por = clean_price(price_str)
            
            if desc and len(desc) > 3:
                # Try to extract model number
                model_match = re.search(r'([A-Z0-9][\w-]{2,})', desc)
                cat_no = model_match.group(1) if model_match else ''
                
                current_variants.append({
                    'cat_no': cat_no,
                    'description': desc[:200],
                    'price': price,
                    'price_on_request': por,
                    'specs': {},
                })
    
    # Don't forget last group
    if current_product_name and current_variants:
        products.append({
            'name': current_product_name,
            'category': 'general',
            'series': '',
            'description': current_product_name,
            'variants': current_variants,
        })
    
    return {'brand': brand_name, 'products': products}


def extract_all_as_raw(filepath, brand_name):
    """
    Extract ALL text from a PDF as raw lines for manual review.
    Groups variants by detected section headers.
    """
    reader = PdfReader(filepath)
    all_products = []
    current_section = "General"
    current_variants = []
    
    for page_num, page in enumerate(reader.pages):
        text = page.extract_text()
        if not text:
            continue
        
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if not line or len(line) < 3:
                continue
            
            # Detect section headers: lines without prices, possibly all caps or short
            has_price = bool(re.search(r'\d[\d,]*\.?\d*\s*$', line))
            
            # Lines that look like headers
            is_header = (
                (line.isupper() and len(line) > 4 and not has_price) or
                (not has_price and not any(c.isdigit() for c in line) and len(line) > 5 and len(line) < 80)
            )
            
            if is_header and len(line) < 100:
                # Save previous section
                if current_variants:
                    all_products.append({
                        'name': current_section[:200],
                        'category': 'general',
                        'series': '',
                        'description': current_section[:200],
                        'variants': current_variants,
                    })
                    current_variants = []
                current_section = line
                continue
            
            # Try to extract price from end of line
            if has_price:
                price_match = re.search(r'([\d,]+\.?\d*)\s*$', line)
                desc = line[:price_match.start()].strip() if price_match else line
                price_str = price_match.group(1) if price_match else ''
                price, por = clean_price(price_str)
                
                if desc and len(desc) > 2:
                    # Extract model/cat number
                    model_match = re.match(r'^(\S+)', desc)
                    cat_no = model_match.group(1) if model_match else ''
                    
                    current_variants.append({
                        'cat_no': cat_no,
                        'description': desc[:300],
                        'price': price,
                        'price_on_request': por,
                        'specs': {},
                    })
    
    # Last section
    if current_variants:
        all_products.append({
            'name': current_section[:200],
            'category': 'general',
            'series': '',
            'description': current_section[:200],
            'variants': current_variants,
        })
    
    return {'brand': brand_name, 'products': all_products}


def save_json(data, filename):
    """Save extracted data to JSON file."""
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    # Count totals
    total_products = len(data['products'])
    total_variants = sum(len(p['variants']) for p in data['products'])
    priced = sum(1 for p in data['products'] for v in p['variants'] if not v['price_on_request'])
    por = total_variants - priced
    
    print(f"  Saved: {filepath}")
    print(f"  Products: {total_products}, Variants: {total_variants} (Priced: {priced}, POR: {por})")


def main():
    print("=" * 80)
    print("ENG-MART PDF PRODUCT EXTRACTION")
    print("=" * 80)
    
    # 1. CHINT (well-structured, custom parser)
    print("\n[1/9] CHINT...")
    try:
        data = extract_chint()
        save_json(data, "chint.json")
    except Exception as e:
        print(f"  ERROR: {e}")
    
    # 2. AT Electricals (Tense/Kondas/Opas)
    print("\n[2/9] AT Electricals (Tense/Kondas/Opas)...")
    try:
        filepath = os.path.join(PDF_DIR, "AT ELECTRICALS PRICE LIST MARCH 2023.pdf")
        data = extract_all_as_raw(filepath, "AT Electricals (Tense/Kondas/Opas)")
        save_json(data, "at_electricals.json")
    except Exception as e:
        print(f"  ERROR: {e}")
    
    # 3. FICO
    print("\n[3/9] FICO Hi-Tech...")
    try:
        filepath = os.path.join(PDF_DIR, "FICO LIST.pdf")
        data = extract_all_as_raw(filepath, "FICO Hi-Tech")
        save_json(data, "fico.json")
    except Exception as e:
        print(f"  ERROR: {e}")
    
    # 4. Himel
    print("\n[4/9] Himel...")
    try:
        filepath = os.path.join(PDF_DIR, "Himel price list 2022.pdf")
        data = extract_all_as_raw(filepath, "Himel")
        save_json(data, "himel.json")
    except Exception as e:
        print(f"  ERROR: {e}")
    
    # 5. JC
    print("\n[5/9] JC...")
    try:
        filepath = os.path.join(PDF_DIR, "JC price-list-2023[1].pdf")
        data = extract_all_as_raw(filepath, "JC")
        save_json(data, "jc.json")
    except Exception as e:
        print(f"  ERROR: {e}")
    
    # 6. PCE
    print("\n[6/9] PCE...")
    try:
        filepath = os.path.join(PDF_DIR, "PCE - Industrial Price List June 2020.pdf")
        data = extract_all_as_raw(filepath, "PCE")
        save_json(data, "pce.json")
    except Exception as e:
        print(f"  ERROR: {e}")
    
    # 7. ABB
    print("\n[7/9] ABB...")
    try:
        filepath = os.path.join(PDF_DIR, "Price List AVS ABB OCTOBER 2019.pdf")
        data = extract_all_as_raw(filepath, "ABB")
        save_json(data, "abb.json")
    except Exception as e:
        print(f"  ERROR: {e}")
    
    # 8. Siemens
    print("\n[8/9] Siemens...")
    try:
        filepath = os.path.join(PDF_DIR, "Siemens Components Price List1.pdf")
        data = extract_all_as_raw(filepath, "Siemens")
        save_json(data, "siemens.json")
    except Exception as e:
        print(f"  ERROR: {e}")
    
    # 9. SWAS (large - 93 pages)
    print("\n[9/9] SWAS...")
    try:
        filepath = os.path.join(PDF_DIR, "SWAS PL Dec-2023 dated 11-12-23 Linked.pdf")
        data = extract_all_as_raw(filepath, "SWAS")
        save_json(data, "swas.json")
    except Exception as e:
        print(f"  ERROR: {e}")
    
    print("\n" + "=" * 80)
    print("EXTRACTION COMPLETE!")
    print(f"JSON files saved to: {OUTPUT_DIR}")
    print("=" * 80)


if __name__ == '__main__':
    main()
