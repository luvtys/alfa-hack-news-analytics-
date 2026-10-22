# backend/pdf_to_images.py
import os, glob
import pymupdf  # pip install PyMuPDF

SRC = r"C:\Users\posto\Documents\alfa-hack-news-analityc\alfa-hack-news-analytics-\backend\data\alfa_analytics"
OUT = r"C:\Users\posto\Documents\alfa-hack-news-analityc\alfa-hack-news-analytics-\backend\data\alfa_analytics_pages"
os.makedirs(OUT, exist_ok=True)

total = 0
for path in sorted(glob.glob(os.path.join(SRC, "*.pdf"))):
    name = os.path.splitext(os.path.basename(path))[0]
    doc = fitz.open(path)
    print(f"📄 {name}: страниц = {len(doc)}")
    for i, page in enumerate(doc):
        pix = page.get_pixmap(dpi=150)
        pix.save(os.path.join(OUT, f"{name}_p{i+1:02d}.png"))
        total += 1
    doc.close()

print(f"✅ Всего страниц-картинок: {total}")