import pdfplumber
p = r"C:/Users/AWCD/Desktop/client/engmart (2)/product-details/AT ELECTRICALS PRICE LIST MARCH 2023.pdf"
out = open(r"C:/Users/AWCD/AppData/Local/Temp/claude/C--Users-AWCD-Desktop-client/b98be00e-30f6-46b4-8d4f-99bca66a0bed/scratchpad/at_raw.txt","w",encoding="utf-8")
with pdfplumber.open(p) as pdf:
    for i, page in enumerate(pdf.pages):
        t = page.extract_text() or ""
        out.write("="*20 + f" PAGE {i+1} " + "="*20 + "\n")
        out.write(t + "\n")
out.close()
print("done")
