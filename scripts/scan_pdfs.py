"""
Quick scan of all PDFs to understand their structure.
Extracts first 2 pages of text + checks for images.
"""
import os
import sys
from PyPDF2 import PdfReader

PDF_DIR = r"c:\Users\AWCD\Desktop\client\engmart (2)\product-details"

for filename in sorted(os.listdir(PDF_DIR)):
    if not filename.endswith('.pdf'):
        continue
    
    filepath = os.path.join(PDF_DIR, filename)
    print(f"\n{'='*80}")
    print(f"FILE: {filename}")
    print(f"{'='*80}")
    
    try:
        reader = PdfReader(filepath)
        total_pages = len(reader.pages)
        print(f"Total pages: {total_pages}")
        
        # Check for images
        total_images = 0
        for page in reader.pages[:5]:  # Check first 5 pages for images
            if '/XObject' in page.get('/Resources', {}):
                xobject = page['/Resources']['/XObject'].get_object()
                for obj_name in xobject:
                    obj = xobject[obj_name].get_object()
                    if obj.get('/Subtype') == '/Image':
                        total_images += 1
        
        print(f"Images found (first 5 pages): {total_images}")
        
        # Extract text from first 2 pages
        for i in range(min(2, total_pages)):
            text = reader.pages[i].extract_text()
            if text:
                lines = text.strip().split('\n')
                print(f"\n--- Page {i+1} (first 30 lines) ---")
                for line in lines[:30]:
                    print(f"  {line}")
                if len(lines) > 30:
                    print(f"  ... ({len(lines) - 30} more lines)")
    except Exception as e:
        print(f"ERROR: {e}")
