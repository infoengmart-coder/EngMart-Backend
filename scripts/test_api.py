import requests

r = requests.get('http://localhost:8000/api/products/', params={'page_size': '3'})
d = r.json()
print(f"Status: {r.status_code}")
print(f"Total: {d['count']} products")
print()
for p in d['results']:
    brand = p.get('brand_name', p.get('brand', {}).get('name', '?'))
    cat = p.get('category_name', p.get('category', {}).get('name', '?'))
    name = p.get('name', '?')
    vc = p.get('variant_count', 0)
    fv = p.get('first_variant')
    pr = p.get('price_range')
    print(f"  {brand} - {name} ({cat}) [{vc} variants]")
    if fv:
        print(f"    First variant: {fv['cat_no']} - {fv['description'][:50]}")
    if pr:
        print(f"    Price: {pr['min']} - {pr['max']}")
    print()

# Test detail
print("--- Testing product detail ---")
slug = d['results'][0]['slug'] if d['results'] else None
if slug:
    r2 = requests.get(f'http://localhost:8000/api/products/{slug}/')
    p2 = r2.json()
    print(f"Product: {p2.get('name')}")
    print(f"Brand: {p2.get('brand', {}).get('name')}")
    print(f"Variants: {len(p2.get('variants', []))}")
    print(f"Related: {len(p2.get('related_products', []))}")
    if p2.get('variants'):
        v = p2['variants'][0]
        print(f"  First variant: {v.get('cat_no')} - {v.get('description')[:50]} - Price: {v.get('price')}")
