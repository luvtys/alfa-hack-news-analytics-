import os
import glob
from pypdf import PdfReader

# АБСОЛЮТНЫЕ пути (r"" сверху строки — важно, чтобы бэкслэши не ломались)
SRC = r"C:\Users\posto\Documents\alfa-hack-news-analityc\alfa-hack-news-analytics-\backend\data\alfa_analytics"
OUT = r"C:\Users\posto\Documents\alfa-hack-news-analityc\alfa-hack-news-analytics-\backend\data\alfa_analytics_txt"

os.makedirs(OUT, exist_ok=True)

print(f"🔍 Ищу PDF по пути: {SRC}")

pdf_files = glob.glob(os.path.join(SRC, "*.pdf")) + glob.glob(os.path.join(SRC, "*.PDF"))
print(f"📂 Найдено PDF-файлов: {len(pdf_files)}")

if not pdf_files:
    print("⚠️ PDF не найдены. Проверь, что файлы с расширением .pdf лежат прямо в папке SRC.")

for path in pdf_files:
    name = os.path.splitext(os.path.basename(path))[0]
    print(f"⏳ Читаю: {name}...")
    try:
        reader = PdfReader(path)
        text = "\n\n".join((p.extract_text() or "") for p in reader.pages)

        if len(text.strip()) > 200:
            out_file = os.path.join(OUT, f"{name}.txt")
            with open(out_file, "w", encoding="utf-8") as f:
                f.write(text)
            print(f"✅ {name}: сохранено ({len(text)} символов)")
        else:
            print(f"⚠️ {name}: текста почти нет (скан) -> пойдем через Qwen-VL")
    except Exception as e:
        print(f"❌ Ошибка при чтении {name}: {e}")