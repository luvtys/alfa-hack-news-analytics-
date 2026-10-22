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
OUT_DIR = r"C:\Users\posto\Documents\alfa-hack-news-analityc\alfa-hack-news-analytics-\backend\data\alfa_analytics_txt"

print(f"🔍 Ищу картинки в папке: {os.path.abspath(PAGES_DIR)}\n")

# 1. Проверяем, существует ли папка
if not os.path.exists(PAGES_DIR):
    print("❌ ОШИБКА: Папка не существует!")
    print("💡 РЕШЕНИЕ: Сначала запусти скрипт pdf_to_images.py, чтобы создать картинки.")
    exit()

# 2. Ищем все PNG файлы
all_pngs = glob.glob(os.path.join(PAGES_DIR, "*.png"))
print(f"📂 Найдено файлов .png через поиск: {len(all_pngs)}")

if len(all_pngs) == 0:
    print("❌ В папке НЕТ файлов с расширением .png")
    print("💡 РЕШЕНИЕ: Проверь, сохранил ли предыдущий скрипт картинки. Возможно, они сохранились как .jpg или в другую папку.")
    exit()

# 3. Группируем по документам
groups = {}
for path in all_pngs:
    filename = os.path.basename(path)
    # Ищем паттерн: имя_цифры.png (например, ALFA_p01.png)
    m = re.match(r"(.+)_p\d+\.png", filename)
    if m:
        doc_name = m.group(1)
        groups.setdefault(doc_name, []).append(path)
    else:
        print(f"⚠️ Файл '{filename}' не подошел под шаблон имени (должен быть типа 'название_p01.png')")

print(f"\n✅ Успешно сгруппировано документов: {len(groups)}")
if len(groups) > 0:
    print("📄 Список документов для обработки:", list(groups.keys()))
else:
    print("❌ Ни один файл не подошел под шаблон имени. Проверь, как называются файлы в папке.")
    exit()

# 4. Основной цикл обработки (тот же, что и был)
os.makedirs(OUT_DIR, exist_ok=True)
PROMPT = """Ты финансовый аналитик. Извлеки ВЕСЬ текст со страницы документа в формате Markdown: заголовки, абзацы, таблицы, цифры.
Для каждого графика/диаграммы добавь блок «Описание графика»: что показано (метрика, период), тренд, ключевые значения, краткий вывод.
Ничего не выдумывай. Верни только содержимое страницы."""

for doc_name, pages in groups.items():
    out_file = os.path.join(OUT_DIR, f"{doc_name}.txt")
    
    if os.path.exists(out_file) and os.path.getsize(out_file) > 100:
        print(f"⏭️ {doc_name}: уже готов, пропускаю")
        continue
    
    print(f"\n⏳ Обрабатываю {doc_name} ({len(pages)} стр.)...")
    chunks = []
    
    for page_path in pages:
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
                timeout=60.0
            )
            text = resp.choices[0].message.content
            chunks.append(f"--- СТРАНИЦА {os.path.basename(page_path)} ---\n{text}")
            print(f"   ✅ {os.path.basename(page_path)}")
        except Exception as e:
            print(f"   ❌ Ошибка на {os.path.basename(page_path)}: {e}")
        
        time.sleep(1.5)
    
    if chunks:
        with open(out_file, "w", encoding="utf-8") as f:
            f.write("\n\n".join(chunks))
        print(f"✅ {doc_name}: сохранено в {out_file}")

print("\n🎉 Готово! Все txt в папке alfa_analytics_txt")