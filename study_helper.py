import time
import json
import os
import sys
from pathlib import Path

from docx import Document
from dotenv import load_dotenv
from google import genai
from pypdf import PdfReader

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

MODEL = "gemini-3.8-flash"
MAX_CHARS = 150_000  # safety limit for very long texts
SUPPORTED = {".pdf", ".docx", ".txt", ".md"}

PROMPT = """You are a study assistant for a university student.
Read the text below and reply with ONLY valid JSON.
Write everything in the same language as the text.

JSON structure:
{
  "summary": "short summary, 5-8 sentences",
  "bullet_points": ["key point", "..."],
  "keywords": [{"term": "...", "definition": "one short line"}],
  "questions": [{"q": "...", "a": "short answer"}],
  "flashcards": [{"front": "...", "back": "..."}],
  "multiple_choice": [{"question": "...", "options": ["A", "B", "C", "D"], "answer_index": 0, "explanation": "..."}],
  "true_false": [{"statement": "...", "answer": true, "explanation": "..."}]
}

Give about: 8 bullet points, 8 keywords, 6 questions, 10 flashcards,
6 multiple choice, 6 true/false. Only use info from the text.
If the text contains several separate works (e.g. multiple poems or
chapters), cover ALL of them and name each one by title in the summary.

TEXT:
"""


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


def analyse(text: str, retries: int = 5) -> dict:
    for attempt in range(retries):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=PROMPT + text,
                config={"response_mime_type": "application/json"},
            )
            return clean_json(response.text)
        except Exception as e:
            msg = str(e)
            temporary = "503" in msg or "429" in msg or "UNAVAILABLE" in msg
            if temporary and attempt < retries - 1:
                wait = 10 * 2**attempt  # 10s, 20s, 40s, 80s
                print(f"  Busy, retrying in {wait}s ...")
                time.sleep(wait)
            else:
                raise


def to_markdown(name: str, data: dict) -> str:
    lines = [f"# {name}", "", "## Summary", data["summary"], "", "## Key points"]
    lines += [f"- {b}" for b in data["bullet_points"]]
    lines += ["", "## Keywords"]
    lines += [f"- **{k['term']}**: {k['definition']}" for k in data["keywords"]]
    lines += ["", "## Questions"]
    for item in data["questions"]:
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
            print(f"  Text is very long, using the first {MAX_CHARS} characters.")
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