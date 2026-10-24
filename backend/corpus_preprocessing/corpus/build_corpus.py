#!/usr/bin/env python3
"""
Препроцессинг корпуса аналитики Альфа-Банка.

Все девять PDF — сканы без текстового слоя: pdffonts не находит ни одного
встроенного шрифта, pdftotext возвращает ноль слов. Наивный парсер построит
пустой индекс. Этот скрипт распознаёт страницы один раз, кладёт результат в
репозиторий и больше к моделям не обращается.

    pdf/*.pdf  ->  corpus/<doc_id>/page_NN.md  ->  corpus/chunks.jsonl

Запуск:
    python3 build_corpus.py --pdf-dir pdf --out corpus --backend tesseract
    python3 build_corpus.py --pdf-dir pdf --out corpus --backend vlm
    python3 build_corpus.py --pdf-dir pdf --out corpus --backend mock --dry-run

Бэкенды распознавания:
    tesseract  pdftoppm + tesseract -l rus. Бесплатно, быстро, текст берёт
               хорошо, подписи к графикам — хуже.
    vlm        Qwen3-VL-30B-A3B-Instruct через OpenAI-совместимый эндпоинт.
               Берёт и графики, и таблицы. Платно: считает токены и
               останавливается по --max-cost-rub.
    text       если у PDF вдруг есть текстовый слой.
    mock       заглушка для проверки конвейера без распознавания.

Идемпотентность: уже распознанные страницы пропускаются, если нет --force.
Это важно при лимите в 500 рублей — повторный запуск ничего не тратит.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# Дисклеймеры почти идентичны во всех документах и семантически близки к
# любому финансовому запросу: «ценные бумаги», «риски», «валютный риск».
# Без явного отсева они съедают топ выдачи. Девять страниц из 64.
DISCLAIMER_MARKERS = [
    r"Генеральн\w*\s+лиценз\w*\s+ЦБ\s*РФ",
    r"Несанкционированное\s+копирование",
    r"не\s+является\s+индивидуальной\s+инвестиционной\s+рекомендацией",
    r"исключительной\s+собственностью\s+Альфа-Банка",
]
DISCLAIMER_RE = re.compile("|".join(DISCLAIMER_MARKERS), re.IGNORECASE)

TITLE_PAGE_MAX_WORDS = 12
MIN_CHUNK_CHARS = 220
MAX_CHUNK_CHARS = 1800

VLM_PROMPT = (
    "Это страница аналитического отчёта Альфа-Банка на русском языке. "
    "Перепиши всё её содержимое в Markdown, сохраняя структуру. "
    "Заголовки — через #. Таблицы — разметкой Markdown, все строки и столбцы. "
    "Для каждого графика выпиши его заголовок, подписи осей и все видимые "
    "числовые значения рядов в виде списка или таблицы. "
    "Ничего не додумывай и не обобщай: если значение неразличимо, напиши "
    "[неразборчиво]. Не добавляй комментариев от себя."
)


# ---------------------------------------------------------------- утилиты
def log(msg: str) -> None:
    print(msg, flush=True)


def require(binary: str) -> None:
    if shutil.which(binary) is None:
        sys.exit(f"не найден {binary}. Установите poppler-utils "
                 f"(apt-get install poppler-utils) и tesseract-ocr-rus")


def page_count(pdf: Path) -> int:
    out = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True).stdout
    m = re.search(r"^Pages:\s+(\d+)", out, re.MULTILINE)
    return int(m.group(1)) if m else 0


def has_text_layer(pdf: Path) -> bool:
    fonts = subprocess.run(["pdffonts", str(pdf)], capture_output=True, text=True).stdout
    return len(fonts.strip().splitlines()) > 2


# ---------------------------------------------------------------- бэкенды
class Backend:
    name = "base"
    tokens_in = 0
    tokens_out = 0
    cost_rub = 0.0

    def page_text(self, pdf: Path, page: int, workdir: Path, dpi: int) -> str:
        raise NotImplementedError

    def render(self, pdf: Path, page: int, workdir: Path, dpi: int) -> Path:
        stem = workdir / f"{pdf.stem}_p{page:03d}"
        png = Path(f"{stem}-{page}.png")
        if not png.exists():
            subprocess.run(
                ["pdftoppm", "-r", str(dpi), "-png", "-f", str(page), "-l", str(page),
                 str(pdf), str(stem)],
                check=True, capture_output=True)
            produced = sorted(workdir.glob(f"{pdf.stem}_p{page:03d}-*.png"))
            if not produced:
                raise RuntimeError(f"не удалось растрировать {pdf.name} стр. {page}")
            png = produced[0]
        return png


class TextBackend(Backend):
    name = "text"

    def page_text(self, pdf: Path, page: int, workdir: Path, dpi: int) -> str:
        out = subprocess.run(
            ["pdftotext", "-enc", "UTF-8", "-f", str(page), "-l", str(page), str(pdf), "-"],
            capture_output=True, text=True).stdout
        return out.strip()


class TesseractBackend(Backend):
    name = "tesseract"

    def __init__(self, lang: str = "rus") -> None:
        require("tesseract")
        langs = subprocess.run(["tesseract", "--list-langs"],
                               capture_output=True, text=True).stdout
        if lang not in langs.split():
            sys.exit(f"у tesseract нет языка '{lang}'. "
                     f"apt-get install tesseract-ocr-rus")
        self.lang = lang

    def page_text(self, pdf: Path, page: int, workdir: Path, dpi: int) -> str:
        png = self.render(pdf, page, workdir, dpi)
        out = subprocess.run(
            ["tesseract", str(png), "stdout", "-l", self.lang, "--psm", "3"],
            capture_output=True, text=True).stdout
        return out.strip()


class VLMBackend(Backend):
    """Qwen3-VL через OpenAI-совместимый эндпоинт.

    Переменные окружения: LLM_BASE_URL, LLM_API_KEY, LLM_VISION_MODEL.
    """
    name = "vlm"

    def __init__(self, price_in_rub_per_1m: float, price_out_rub_per_1m: float,
                 max_cost_rub: float) -> None:
        self.base_url = os.environ.get("LLM_BASE_URL", "").rstrip("/")
        self.api_key = os.environ.get("LLM_API_KEY", "")
        self.model = os.environ.get("LLM_VISION_MODEL", "Qwen3-VL-30B-A3B-Instruct")
        if not self.base_url or not self.api_key:
            sys.exit("для backend=vlm нужны LLM_BASE_URL и LLM_API_KEY")
        self.p_in = price_in_rub_per_1m
        self.p_out = price_out_rub_per_1m
        self.max_cost = max_cost_rub

    def page_text(self, pdf: Path, page: int, workdir: Path, dpi: int) -> str:
        import urllib.request

        if self.cost_rub >= self.max_cost:
            raise RuntimeError(
                f"достигнут лимит стоимости {self.max_cost} руб. "
                f"Распознано не всё; повторный запуск продолжит с этого места")

        png = self.render(pdf, page, workdir, dpi)
        b64 = base64.b64encode(png.read_bytes()).decode()
        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": VLM_PROMPT},
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/png;base64,{b64}"}},
                ],
            }],
        }
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.api_key}"},
        )
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=180) as r:
                    data = json.loads(r.read())
                break
            except Exception as exc:                      # noqa: BLE001
                if attempt == 2:
                    raise
                log(f"      повтор после ошибки: {exc}")
                time.sleep(2 ** attempt)

        usage = data.get("usage", {})
        self.tokens_in += usage.get("prompt_tokens", 0)
        self.tokens_out += usage.get("completion_tokens", 0)
        self.cost_rub = (self.tokens_in / 1e6 * self.p_in
                         + self.tokens_out / 1e6 * self.p_out)
        return data["choices"][0]["message"]["content"].strip()


class MockBackend(Backend):
    name = "mock"

    def page_text(self, pdf: Path, page: int, workdir: Path, dpi: int) -> str:
        self.render(pdf, page, workdir, dpi)
        return (
            f"# Заглушка распознавания\n\n"
            f"Страница {page} файла {pdf.name}. Этот текст подставлен, чтобы "
            f"проверить конвейер целиком без обращения к моделям: "
            f"растрирование, классификацию страниц, запись Markdown с "
            f"метаданными, нарезку на чанки и сборку манифеста.\n\n"
            f"## Второй блок\n\n"
            f"Отдельный абзац нужен, чтобы на странице получалось больше "
            f"одного чанка и было видно работу разделителя смысловых блоков.\n\n"
            f"| Показатель | Значение |\n| --- | --- |\n| Страница | {page} |\n"
        )


BACKENDS = {"text": TextBackend, "tesseract": TesseractBackend,
            "vlm": VLMBackend, "mock": MockBackend}


# ---------------------------------------------------------------- логика
@dataclass
class PageResult:
    doc_id: str
    page: int
    page_type: str
    chars: int
    skipped: bool
    reason: str = ""


@dataclass
class Stats:
    pages_total: int = 0
    pages_ocr: int = 0
    pages_cached: int = 0
    pages_skipped: int = 0
    chunks: int = 0
    per_doc: list = field(default_factory=list)


def classify_page(declared: str, text: str) -> str:
    """Тип страницы.

    Порядок важен. Дисклеймер по тексту перебивает всё: если юридический
    шаблон распознан, страница не индексируется независимо от реестра.
    Дальше первичен реестр — он составлен человеком, который видел страницы.
    Эвристика по числу слов применяется ТОЛЬКО когда реестр молчит: страница
    с графиками и десятком подписей — это содержание, а не титул, и
    выбрасывать её по счётчику слов нельзя.
    """
    if DISCLAIMER_RE.search(text):
        return "disclaimer"
    if declared in {"disclaimer", "title", "tables", "content"}:
        return declared
    if len(text.split()) <= TITLE_PAGE_MAX_WORDS:
        return "title"
    return "content"


def front_matter(doc: dict, page: int, page_type: str, text: str) -> str:
    fm = {
        "doc_id": doc["doc_id"],
        "title": doc["title"],
        "publisher": doc["publisher"],
        "publisher_code": doc["publisher_code"],
        "as_of_date": doc["as_of_date"],
        "page": page,
        "pages_total": doc["pages"],
        "page_type": page_type,
        "source_file": doc["file"],
        "topics": doc.get("topics", []),
        "stale": bool(doc.get("stale")),
        "priority": doc.get("priority", 5),
        "sha256": hashlib.sha256(text.encode()).hexdigest()[:16],
    }
    lines = ["---"]
    for k, v in fm.items():
        lines.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
    lines.append("---")
    return "\n".join(lines)


def split_chunks(text: str) -> list[str]:
    """Чанк — смысловой блок, а не окно фиксированной длины.

    Режем по заголовкам Markdown и пустым строкам, склеиваем короткие куски,
    разбиваем слишком длинные по границам предложений. Таблицы не режем:
    разорванная пополам таблица прогнозов хуже, чем длинный чанк.
    """
    blocks, buf = [], []
    for line in text.splitlines():
        if line.startswith("|"):
            buf.append(line)
            continue
        if line.startswith("#") and buf:
            blocks.append("\n".join(buf).strip())
            buf = [line]
        elif not line.strip() and buf:
            blocks.append("\n".join(buf).strip())
            buf = []
        else:
            buf.append(line)
    if buf:
        blocks.append("\n".join(buf).strip())

    merged: list[str] = []
    for b in [x for x in blocks if x]:
        if merged and len(merged[-1]) < MIN_CHUNK_CHARS and not merged[-1].startswith("|"):
            merged[-1] = merged[-1] + "\n\n" + b
        else:
            merged.append(b)

    out: list[str] = []
    for b in merged:
        if len(b) <= MAX_CHUNK_CHARS or b.lstrip().startswith("|"):
            out.append(b)
            continue
        parts, cur = re.split(r"(?<=[.!?])\s+", b), ""
        for s in parts:
            if len(cur) + len(s) + 1 > MAX_CHUNK_CHARS and cur:
                out.append(cur.strip())
                cur = s
            else:
                cur = f"{cur} {s}".strip()
        if cur:
            out.append(cur.strip())
    return [c for c in out if len(c) >= 40]


def process(args: argparse.Namespace) -> int:
    require("pdftoppm")
    require("pdfinfo")

    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    out = Path(args.out)
    workdir = out / "_render"
    out.mkdir(parents=True, exist_ok=True)
    workdir.mkdir(exist_ok=True)

    backend: Backend = (
        VLMBackend(args.price_in, args.price_out, args.max_cost_rub)
        if args.backend == "vlm" else BACKENDS[args.backend]()
    )

    stats = Stats()
    chunk_rows: list[dict] = []

    for doc in registry["documents"]:
        if doc.get("exclude_from_index") and not args.include_stale:
            log(f"{doc['doc_id']}: пропущен целиком ({doc.get('note','устарел')[:60]})")
            continue

        pdf = Path(args.pdf_dir) / doc["file"]
        if not pdf.exists():
            log(f"{doc['doc_id']}: ФАЙЛ НЕ НАЙДЕН — {pdf}")
            continue

        actual = page_count(pdf)
        if actual != doc["pages"]:
            log(f"{doc['doc_id']}: ВНИМАНИЕ, в реестре {doc['pages']} страниц, "
                f"в файле {actual}. Реестр устарел — проверьте вручную")

        doc_dir = out / doc["doc_id"]
        doc_dir.mkdir(exist_ok=True)
        if has_text_layer(pdf) and args.backend != "text":
            log(f"{doc['doc_id']}: у файла ЕСТЬ текстовый слой — "
                f"быстрее прогнать с --backend text")

        kept = 0
        for page in range(1, actual + 1):
            stats.pages_total += 1
            declared = doc.get("page_types", {}).get(str(page), "content")

            if declared == "disclaimer" and not args.keep_disclaimers:
                stats.pages_skipped += 1
                continue
            if declared == "title" and not args.keep_titles:
                stats.pages_skipped += 1
                continue

            md_path = doc_dir / f"page_{page:02d}.md"
            if md_path.exists() and not args.force:
                stats.pages_cached += 1
                text = md_path.read_text(encoding="utf-8").split("---", 2)[-1].strip()
            else:
                if args.dry_run:
                    log(f"  {doc['doc_id']} стр. {page}: было бы распознано ({declared})")
                    continue
                try:
                    text = backend.page_text(pdf, page, workdir, args.dpi)
                except RuntimeError as exc:
                    log(f"  ОСТАНОВ: {exc}")
                    break
                stats.pages_ocr += 1
                page_type = classify_page(declared, text)
                if page_type == "disclaimer" and not args.keep_disclaimers:
                    log(f"  {doc['doc_id']} стр. {page}: распознан дисклеймер, отброшен")
                    stats.pages_skipped += 1
                    continue
                md_path.write_text(
                    front_matter(doc, page, page_type, text) + "\n\n" + text,
                    encoding="utf-8")

            page_type = classify_page(declared, text)
            if page_type in {"disclaimer", "title"} and not (
                    args.keep_disclaimers or args.keep_titles):
                continue

            for i, chunk in enumerate(split_chunks(text)):
                chunk_rows.append({
                    "chunk_id": f"{doc['doc_id']}_p{page:02d}_c{i:02d}",
                    "doc_id": doc["doc_id"],
                    "title": doc["title"],
                    "publisher_code": doc["publisher_code"],
                    "as_of_date": doc["as_of_date"],
                    "page": page,
                    "page_type": page_type,
                    "priority": doc.get("priority", 5),
                    "stale": bool(doc.get("stale")),
                    "topics": doc.get("topics", []),
                    "ref": f"corpus://{doc['doc_id']}#p{page}",
                    "text": chunk,
                })
            kept += 1

        stats.per_doc.append({"doc_id": doc["doc_id"], "pages_kept": kept})
        log(f"{doc['doc_id']}: оставлено страниц {kept} из {actual}")

    chunks_path = out / "chunks.jsonl"
    with chunks_path.open("w", encoding="utf-8") as f:
        for row in chunk_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    stats.chunks = len(chunk_rows)

    manifest = {
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "backend": backend.name,
        "dpi": args.dpi,
        "registry_sha256": hashlib.sha256(
            Path(args.registry).read_bytes()).hexdigest()[:16],
        "pages_total": stats.pages_total,
        "pages_recognised": stats.pages_ocr,
        "pages_from_cache": stats.pages_cached,
        "pages_skipped": stats.pages_skipped,
        "chunks": stats.chunks,
        "tokens_in": backend.tokens_in,
        "tokens_out": backend.tokens_out,
        "cost_rub": round(backend.cost_rub, 2),
        "per_doc": stats.per_doc,
        "documents_by_date": sorted(
            [{"doc_id": d["doc_id"], "as_of_date": d["as_of_date"]}
             for d in registry["documents"]],
            key=lambda x: x["as_of_date"], reverse=True),
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    if not args.keep_render:
        shutil.rmtree(workdir, ignore_errors=True)

    log("")
    log(f"страниц всего {stats.pages_total}, распознано {stats.pages_ocr}, "
        f"из кэша {stats.pages_cached}, отброшено {stats.pages_skipped}")
    log(f"чанков: {stats.chunks} -> {chunks_path}")
    if backend.cost_rub:
        log(f"токены: вход {backend.tokens_in}, выход {backend.tokens_out}, "
            f"стоимость {backend.cost_rub:.2f} руб.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pdf-dir", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--registry", default="corpus_registry.json")
    ap.add_argument("--backend", choices=list(BACKENDS), default="tesseract")
    ap.add_argument("--dpi", type=int, default=200,
                    help="200 для tesseract, 150 хватает для VLM и дешевле")
    ap.add_argument("--force", action="store_true", help="перераспознать всё")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--include-stale", action="store_true",
                    help="включить отчёт по стали 2021 года")
    ap.add_argument("--keep-disclaimers", action="store_true")
    ap.add_argument("--keep-titles", action="store_true")
    ap.add_argument("--keep-render", action="store_true", help="не удалять PNG")
    ap.add_argument("--max-cost-rub", type=float, default=100.0)
    ap.add_argument("--price-in", type=float, default=60.0,
                    help="руб. за 1 млн входных токенов")
    ap.add_argument("--price-out", type=float, default=180.0,
                    help="руб. за 1 млн выходных токенов")
    return process(ap.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
