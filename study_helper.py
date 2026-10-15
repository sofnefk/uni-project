import json
import os
import sys
import time
from pathlib import Path

from docx import Document
from dotenv import load_dotenv
from google import genai
from pypdf import PdfReader

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

MODEL = "gemini-3.8-flash"
MAX_CHARS = 300_000  # hard limit per document
CHUNK_SIZE = 40_000  # longer texts are split into parts of this size
SUPPORTED = {".pdf", ".docx", ".txt", ".md"}

RULES = """Write everything in the same language as the text.
Only use information from the text. If it contains several separate works
(e.g. several poems or chapters), cover ALL of them and name each by title."""

CHUNK_PROMPT = (
    """You are a study assistant for a university student.
The text below is one part of a long reading. Make detailed study notes for
this part so the student could learn it without reading it: names, dates,
definitions, arguments, examples, cause and effect.
Reply with ONLY valid JSON:
{"sections": [{"title": "...", "notes": ["specific, detailed point", "..."]}]}
"""
    + RULES
    + "\n\nTEXT:\n"
)

PACK_PROMPT = (
    """You are a study assistant for a university student.
Reply with ONLY valid JSON, no extra words.
The goal: the student should be able to learn this material WITHOUT reading
the original, so the notes must be specific (names, dates, definitions,
arguments, examples), never vague.

JSON structure:
{
  "overview": "3-4 sentences: what this text is and its central argument or theme",
  "must_know": ["the 5 most important takeaways, one sentence each"],
  "sections": [{"title": "...", "notes": ["specific, detailed point", "..."]}],
  "keywords": [{"term": "...", "definition": "one short line"}],
  "questions": [{"q": "...", "a": "short answer"}],
  "flashcards": [{"front": "...", "back": "..."}],
  "multiple_choice": [{"question": "...", "options": ["A", "B", "C", "D"], "answer_index": 0, "explanation": "..."}],
  "true_false": [{"statement": "...", "answer": true, "explanation": "..."}]
}

Give: 5 must_know, 3-12 sections (4-8 notes each), 10 keywords,
exactly 10 questions, 15 flashcards, exactly 10 multiple choice,
exactly 10 true/false.
Questions must test recall and understanding, not trivia, and be spread
across the whole text. Vary which option is correct in multiple choice.
"""
    + RULES
    + "\n\nTEXT:\n"
)


def read_file(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".pdf":
        reader = PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    if ext == ".docx":
        doc = Document(str(path))
        return "\n".join(p.text for p in doc.paragraphs)
    return path.read_text(encoding="utf-8", errors="ignore")


def clean_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


def call_ai(prompt: str, retries: int = 5) -> dict:
    for attempt in range(retries):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "max_output_tokens": 20000,
                },
            )
            return clean_json(response.text)
        except Exception as e:
            msg = str(e)
            temporary = (
                "503" in msg
                or "429" in msg
                or "UNAVAILABLE" in msg
                or isinstance(e, json.JSONDecodeError)
            )
            if temporary and attempt < retries - 1:
                wait = 10 * 2**attempt  # 10s, 20s, 40s, 80s
                print(f"  Problem ({type(e).__name__}), retrying in {wait}s ...")
                time.sleep(wait)
            else:
                raise


def split_text(text: str, size: int = CHUNK_SIZE) -> list:
    paragraphs = []
    for p in text.split("\n"):
        while len(p) > size:  # a single huge paragraph gets cut too
            paragraphs.append(p[:size])
            p = p[size:]
        paragraphs.append(p)

    chunks, current = [], ""
    for p in paragraphs:
        if current and len(current) + len(p) + 1 > size:
            chunks.append(current)
            current = ""
        current += p + "\n"
    if current.strip():
        chunks.append(current)
    return chunks


def analyse(text: str) -> dict:
    # short text: one call
    if len(text) <= CHUNK_SIZE:
        return call_ai(PACK_PROMPT + text)

    # long text: notes per part, then one final study pack
    chunks = split_text(text)
    all_sections = []
    for i, chunk in enumerate(chunks, 1):
        print(f"  Part {i}/{len(chunks)} ...")
        header = f"This is PART {i} of {len(chunks)} of a long reading.\n"
        part = call_ai(header + CHUNK_PROMPT + chunk)
        all_sections.extend(part.get("sections", []))

    print("  Building the final study pack ...")
    condensed = json.dumps(all_sections, ensure_ascii=False)
    return call_ai(
        PACK_PROMPT
        + "[These are condensed notes of a long reading, in order]\n"
        + condensed
    )


def to_markdown(name: str, data: dict) -> str:
    lines = [f"# {name}", ""]
    if "overview" in data:
        lines += ["## Overview", data["overview"], "", "## Must know"]
        lines += [f"- {m}" for m in data.get("must_know", [])]
        for s in data.get("sections", []):
            lines += ["", f"## {s['title']}"]
            lines += [f"- {n}" for n in s["notes"]]
    else:
        lines += ["## Summary", data.get("summary", ""), "", "## Key points"]
        lines += [f"- {b}" for b in data.get("bullet_points", [])]
    lines += ["", "## Keywords"]
    lines += [f"- **{k['term']}**: {k['definition']}" for k in data.get("keywords", [])]
    lines += ["", "## Questions"]
    for item in data.get("questions", []):
        lines += [f"**Q:** {item['q']}", f"**A:** {item['a']}", ""]
    return "\n".join(lines)


def main():
    if not os.getenv("GEMINI_API_KEY"):
        print("No GEMINI_API_KEY found. Check your .env file.")
        return
    if len(sys.argv) < 2:
        print('Usage: python study_helper.py "path/to/your/folder"')
        return

    folder = Path(sys.argv[1])
    if not folder.is_dir():
        print(f"Folder not found: {folder}")
        return

    out_dir = folder / "output"
    out_dir.mkdir(exist_ok=True)

    files = [f for f in sorted(folder.iterdir()) if f.suffix.lower() in SUPPORTED]
    if not files:
        print("No .pdf / .docx / .txt / .md files found.")
        return

    for f in files:
        print(f"\nReading {f.name} ...")
        text = read_file(f).strip()

        if len(text) < 200:
            print("  Skipped: almost no text found (scanned PDF?).")
            continue
        if len(text) > MAX_CHARS:
            print(f"  Very long text, using the first {MAX_CHARS} characters.")
            text = text[:MAX_CHARS]

        try:
            data = analyse(text)
        except Exception as e:
            print(f"  Failed: {e}")
            continue

        (out_dir / f"{f.stem}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (out_dir / f"{f.stem}.md").write_text(
            to_markdown(f.stem, data), encoding="utf-8"
        )
        print(f"  Done -> output/{f.stem}.md and .json")

    print("\nAll finished.")


if __name__ == "__main__":
    main()