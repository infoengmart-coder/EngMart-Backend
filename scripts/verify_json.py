import json

for fname in ['chint.json', 'abb.json', 'pce.json']:
    d = json.load(open(f'extracted_data/{fname}', 'r', encoding='utf-8'))
    print(f"\n=== {d['brand']} ===")
    print(f"Products: {len(d['products'])}")
    for p in d['products'][:3]:
        print(f"\n  Product: {p['name']}")
        print(f"  Category: {p['category']}")
        print(f"  Variants: {len(p['variants'])}")
        for v in p['variants'][:3]:
            price_str = f"Rs {v['price']}" if v['price'] else "POR"
            print(f"    - {v['description'][:50]:50s} {price_str}")
