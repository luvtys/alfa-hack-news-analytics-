import os
import re
import glob
import base64
import time
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    base_url=os.getenv("LLM_BASE_URL"),
    api_key=os.getenv("LLM_API_KEY"),
)

MODEL_VL = "qwen/qwen3-vl-30b-a3b-instruct"

PAGES_DIR = r"C:\Users\posto\Documents\alfa-hack-news-analityc\alfa-hack-news-analytics-\backend\data\alfa_analytics_pages"
TXT_DIR = r"C:\Users\posto\Documents\alfa-hack-news-analityc\alfa-hack-news-analytics-\backend\data\alfa_analytics_txt"

PROMPT = """Ты финансовый аналитик. Перед тобой страница отчета Альфа-Банка (текст, таблица или скриншот графика).
Твоя задача:
1. Выпиши весь видимый текст и цифры, сохранив структуру.
2. Если на странице есть график/диаграмма, добавь блок "Описание графика": что измеряется, тренд, ключевые значения, краткий вывод.
3. Верни ответ в формате Markdown. Не выдумывай факты."""

# Собираем все PNG по документам
groups = {}
for path in sorted(glob.glob(os.path.join(PAGES_DIR, "*.png"))):
    m = re.match(r"(.+)_p(\d+)\.png", os.path.basename(path))
    if m:
        doc_name, page_num = m.group(1), int(m.group(2))
        groups.setdefault(doc_name, []).append((page_num, path))

total_missing = 0
total_done = 0

print(f"🔍 Проверяю {len(groups)} документов на наличие пропущенных страниц...\n")

for doc_name, pages in groups.items():
    txt_file = os.path.join(TXT_DIR, f"{doc_name}.txt")
    
    # Читаем, какие страницы УЖЕ есть в файле
    existing_pages = set()
    if os.path.exists(txt_file):
        with open(txt_file, "r", encoding="utf-8") as f:
            content = f.read()
        for m in re.finditer(r"СТРАНИЦА\s+\S+_p(\d+)\.png", content):
            existing_pages.add(int(m.group(1)))
    
    # Находим недостающие
    missing = [(num, path) for num, path in pages if num not in existing_pages]
    
    if not missing:
        total_done += len(pages)
        continue
    
    print(f" {doc_name}: найдено {len(missing)} пропущенных из {len(pages)}")
    
    for page_num, page_path in sorted(missing):
        print(f"   ⏳ Страница {page_num:02d}...", end=" ")
        try:
            with open(page_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            
            resp = client.chat.completions.create(
                model=MODEL_VL,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": PROMPT},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
                    ]
                }],
                max_tokens=1500,
                timeout=90.0  # Даем серверу 90 секунд на ответ
            )
            text = resp.choices[0].message.content
            
            # Дописываем в конец файла
            with open(txt_file, "a", encoding="utf-8") as f:
                f.write(f"\n\n--- СТРАНИЦА {os.path.basename(page_path)} ---\n{text}")
            
            print("✅")
            total_missing += 1
            time.sleep(1.5)
            
        except Exception as e:
            print(f"❌ ({type(e).__name__})")
            # Если снова таймаут — идем дальше, не ломаем цикл

print(f"\n🎉 Готово! Дообработано: {total_missing}, уже было готово: {total_done}")