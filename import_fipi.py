"""Import only explicitly printed headwords/forms from FIPI's 2026 orthoepic list.

Usage: python import_fipi.py [path/to/ru-1-fonetika-2026.pdf]
The source PDF is retained in source/ for audit. No inflection is generated.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "source/ru-1-fonetika-2026.pdf"
OUT = ROOT / "data/words.json"
REPORT = ROOT / "data/import-report.json"
URL = "https://doc.fipi.ru/navigator-podgotovki/navigator-ege/2026/ru-1-fonetika.pdf"
HEAD = re.compile(r"^([А-Яа-яЁё]+)([12])?(?=$|[, ;(])")
VOWELS = "аеёиоуыэюяАЕЁИОУЫЭЮЯ"
CATEGORIES = {
    "Имена существительные": "существительные",
    "Имена прилагательные": "прилагательные",
    "Глаголы": "глаголы",
    "Причастия и отглагольные прилагательные": "причастия",
    "Деепричастия": "деепричастия",
    "Наречия": "наречия",
}


def parse(source=SOURCE):
    pdf = PdfReader(str(source))
    rows = []
    category = None
    for page_num, page in enumerate(pdf.pages, 1):
        lines = (page.extract_text() or "").splitlines()
        for raw in lines:
            line = raw.strip()
            if line in CATEGORIES:
                category = CATEGORIES[line]
                continue
            if line.startswith("Обратите внимание!"):
                category = None
            if not category or not line or line.startswith(("Навигатор", "©", "1 У слов", "2 В контрольных", "3 Орфоэпический")) or line.isdigit():
                continue
            # Only a line beginning with an explicitly stressed form is a list item.
            first = HEAD.match(line)
            if not first or sum(c in VOWELS and c.isupper() for c in first[1]) != 1:
                continue
            parts = line.split(";")
            for part_idx, part in enumerate(parts):
                part = part.strip()
                # A comma series may list several explicitly printed forms
                # ("зАнял, занялА, зАняли"). Stop at grammatical prose.
                candidates = []
                rest = part
                while True:
                    match = HEAD.match(rest)
                    if not match:
                        break
                    printed = match[1]
                    if sum(c in VOWELS and c.isupper() for c in printed) != 1:
                        break
                    candidates.append((printed, match[2]))
                    tail = rest[match.end():]
                    next_form = re.match(r"^,\s+([А-Яа-яЁё]+)(?=,|$)", tail)
                    if not next_form or sum(c in VOWELS and c.isupper() for c in next_form[1]) != 1:
                        break
                    rest = tail[2:].lstrip()
                for form_idx, (printed, explicit_footnote) in enumerate(candidates):
                    stress = next(i for i, c in enumerate(printed) if c in VOWELS and c.isupper())
                    footnote = explicit_footnote or ("2" if "ч. 2 глаг." in part else None)
                    key = f"{category}|{page_num}|{line}|{part_idx}|{form_idx}"
                    rows.append({
                        "id": hashlib.sha256(key.encode()).hexdigest()[:16],
                        "form": printed.lower(), "stress_index": stress,
                        "marked": printed, "category": category,
                        "note": part[len(printed):].strip(" ,") if form_idx == 0 else "Форма в ряду: " + part,
                        "source_line": line, "source_page": page_num,
                        "footnote": footnote, "audio_url": None,
                    })
    return rows


def main():
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else SOURCE
    rows = parse(source)
    assert len(rows) > 150, f"Suspiciously short import: {len(rows)}"
    assert len({r['id'] for r in rows}) == len(rows)
    assert all(r['form'][r['stress_index']].lower() in VOWELS.lower() for r in rows)
    assert any("ё" in r['form'] for r in rows)
    OUT.parent.mkdir(exist_ok=True)
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    payload = {"source": {"publisher": "ФИПИ", "title": "Орфоэпический список — 2026", "year": 2026, "url": URL, "sha256": source_hash,
                          "footnotes": {"1": "У слов, которые могут произноситься с побочным ударением, отмечается только основное ударение.",
                                        "2": "В КИМ наряду с формой 3-го лица единственного числа может использоваться любая личная форма глагола."}},
               "entries": rows}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = {"source_sha256": source_hash, "entries": len(rows), "by_category": {c: sum(r['category'] == c for r in rows) for c in CATEGORIES.values()},
              "unique_written_forms": len({r['form'] for r in rows}), "with_notes": sum(bool(r['note']) for r in rows),
              "with_footnotes": sum(bool(r['footnote']) for r in rows), "source_pdf": source.name,
              "method": "Only explicitly capitalized stressed headwords or forms at the start of list lines or after semicolons; no generated inflections."}
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
