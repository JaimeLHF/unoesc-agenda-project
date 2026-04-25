"""
Teste end-to-end do pipeline scraper → parser, sem subir o servidor FastAPI.

Uso:
    python test_pipeline.py <usuario> <senha> [--max 2] [--no-parse]

Saída:
    - Lista de disciplinas encontradas e tamanho do conteúdo extraído
    - Eventos identificados pelo Gemini (a menos que --no-parse)
    - Salva em backend/debug_output_pipeline/
"""

import argparse
import asyncio
import json
from pathlib import Path

from app.scraper import ScraperService
from app.parser import ParserService

OUTPUT_DIR = Path(__file__).parent / "debug_output_pipeline"


async def main(user: str, pwd: str, max_subjects: int, no_parse: bool) -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)

    print("[pipeline] 1/2 - Scraping...")
    scraper = ScraperService()
    result = scraper.run(user, pwd)
    subjects = result["subjects"]
    calendar_events = result["calendar_events"]
    if max_subjects > 0:
        subjects = subjects[:max_subjects]

    print(f"[pipeline]   {len(subjects)} disciplina(s):")
    for s in subjects:
        print(f"      - {s['name']}  ({len(s['content'])} chars)")
        safe = s["name"].replace("/", "_").replace(" ", "_")[:60]
        (OUTPUT_DIR / f"content_{safe}.txt").write_text(s["content"], encoding="utf-8")

    print(f"\n[pipeline]   {len(calendar_events)} evento(s) do calendário Moodle:")
    for e in calendar_events:
        when = e["date"] + (f" {e['time']}" if e.get("time") else "")
        print(f"      - [{e['type']}] {when}  {e['title']}  ({e['subject']})")

    if no_parse:
        print("\n[pipeline] (--no-parse) pulando o Gemini.")
        (OUTPUT_DIR / "calendar_events.json").write_text(
            json.dumps(calendar_events, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return

    print("\n[pipeline] 2/2 - Parsing com Gemini (webconferências e outros)...")
    parser = ParserService()
    gemini_events = await parser.extract_events(subjects)
    print(f"[pipeline]   {len(gemini_events)} evento(s) do Gemini")

    # Mesma dedup do backend: calendário Moodle tem prioridade
    seen = {(e["subject"].strip().lower(), e["date"]) for e in calendar_events}
    merged = list(calendar_events)
    for e in gemini_events:
        key = (e.get("subject", "").strip().lower(), e.get("date", ""))
        if key not in seen:
            seen.add(key)
            merged.append(e)
    merged.sort(key=lambda e: (e["date"], e.get("time") or ""))

    print(f"\n[pipeline] {len(merged)} evento(s) consolidado(s):")
    for e in merged:
        when = e["date"] + (f" {e['time']}" if e.get("time") else "")
        src = "📅" if e.get("source") == "moodle_calendar" else "🤖"
        print(f"      {src} [{e['type']}] {when}  {e['title']}  ({e['subject']})")

    (OUTPUT_DIR / "events.json").write_text(
        json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\n[pipeline] Eventos salvos em {OUTPUT_DIR / 'events.json'}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("user")
    p.add_argument("password")
    p.add_argument("--max", type=int, default=0, dest="max_subjects",
                   help="Limita o número de disciplinas processadas (0 = todas)")
    p.add_argument("--no-parse", action="store_true",
                   help="Pula a etapa do Gemini (apenas scraping)")
    args = p.parse_args()
    asyncio.run(main(args.user, args.password, args.max_subjects, args.no_parse))
