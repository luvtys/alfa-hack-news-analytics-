import os
import glob
import chromadb
from chromadb.utils import embedding_functions

# Относительные пути (чтобы работало в Docker и на любой ОС)
DATA_DIR = os.path.join("data", "alfa_analytics_txt")
CHROMA_DIR = "chroma_db"
COLLECTION_NAME = "alfa_analytics"
EMBED_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

# Инициализируем модель ОДИН раз при импорте модуля
# Это сэкономит память и время при запросах через API
ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)
client = chromadb.PersistentClient(path=CHROMA_DIR)


def chunk_text(text: str, size=800, overlap=150):
    chunks, start = [], 0
    while start < len(text):
        piece = text[start:start + size].strip()
        if len(piece) > 50:
            chunks.append(piece)
        start += size - overlap
    return chunks


def build_index():
    """Загружает txt в ChromaDB. Запускать ОДИН раз перед стартом."""
    files = glob.glob(os.path.join(DATA_DIR, "*.txt"))
    if not files:
        raise FileNotFoundError(f"В {DATA_DIR} нет .txt файлов!")

    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
        
    col = client.create_collection(COLLECTION_NAME, embedding_function=ef)

    total = 0
    for file_path in files:
        with open(file_path, 'r', encoding='utf-8') as f:
            text = f.read()
        
        chunks = chunk_text(text)
        ids = [f"{os.path.basename(file_path)}_{i}" for i in range(len(chunks))]
        metadatas = [{"source": os.path.basename(file_path), "chunk_idx": i} for i in range(len(chunks))]
        
        col.add(ids=ids, documents=chunks, metadatas=metadatas)
        total += len(chunks)
        
    print(f"Векторная БД собрана: {total} чанков из {len(files)} документов")


def search(query: str, top_k: int = 3):
    """Ищет релевантные куски текста по запросу"""
    try:
        col = client.get_collection(COLLECTION_NAME, embedding_function=ef)
        res = col.query(query_texts=[query], n_results=top_k)
        
        results = []
        for doc, meta in zip(res["documents"][0], res["metadatas"][0]):
            results.append({
                "text": doc,
                "source": meta["source"]
            })
        return results
    except Exception as e:
        print(f"Ошибка поиска в RAG: {e}")
        return []

if __name__ == "__main__":
    build_index()
    test_res = search("ключевая ставка прогноз инфляция", top_k=2)
    print("\nТест поиска:")
    for r in test_res:
        print(f"   {r['source']}: {r['text'][:100]}...")