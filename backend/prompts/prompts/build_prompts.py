#!/usr/bin/env python3
"""Сборка системных промптов четырёх режимов.

Системный промпт = общий блок + блок режима. Файлы хранятся отдельно,
чтобы правку правила не приходилось вносить в четыре места.

    python3 build_prompts.py --out build          собрать все четыре
    python3 build_prompts.py --mode analyst       напечатать один
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).parent
SHARED = ROOT / "00_shared.md"
MODES = {
    "planner": ("01_planner.md", "qwen3.6-35b-a3b"),
    "analyst": ("02_analyst.md", "deepseek-v4.1-flash"),
    "critic": ("03_critic.md", "qwen3.6-35b-a3b"),
    "writer": ("04_writer.md", "gemma-4-26b-a4b"),
}

# Токенизатора Qwen под рукой нет, поэтому оценка грубая: для русского
# текста с JSON-вставками около 3,1 символа на токен. Погрешность порядка
# 10%, для планирования бюджета этого достаточно.
CHARS_PER_TOKEN = 3.1


def estimate_tokens(text: str) -> int:
    return round(len(text) / CHARS_PER_TOKEN)


def build(mode: str) -> str:
    fname, _ = MODES[mode]
    return (SHARED.read_text(encoding="utf-8").rstrip()
            + "\n\n---\n\n"
            + (ROOT / fname).read_text(encoding="utf-8").strip() + "\n")


def json_blocks(text: str) -> list[dict]:
    """Все ```json блоки файла, разобранные в объекты."""
    out = []
    for m in re.finditer(r"```json\s*\n(.*?)\n```", text, re.DOTALL):
        out.append(json.loads(m.group(1)))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path)
    ap.add_argument("--mode", choices=list(MODES))
    a = ap.parse_args()

    if a.mode:
        print(build(a.mode))
        return 0

    out = a.out or ROOT / "build"
    out.mkdir(parents=True, exist_ok=True)
    index = {}
    for mode, (_, model) in MODES.items():
        text = build(mode)
        fp = out / f"system_{mode}.md"
        fp.write_text(text, encoding="utf-8")
        tok = estimate_tokens(text)
        index[mode] = {"file": fp.name, "model": model,
                       "chars": len(text), "tokens_estimate": tok}
        print(f"{mode:<9} {model:<22} {len(text):>6} симв.  ~{tok:>5} токенов")

    total = sum(v["tokens_estimate"] for v in index.values())
    (out / "index.json").write_text(
        json.dumps({"modes": index, "total_tokens_estimate": total},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nсистемные промпты всех режимов вместе: ~{total} токенов")
    print(f"на один инсайт грузятся не все сразу: планировщик + аналитик + "
          f"критик = ~{index['planner']['tokens_estimate'] + index['analyst']['tokens_estimate'] + index['critic']['tokens_estimate']} токенов")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
