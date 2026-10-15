# 📚 Study Helper

A Streamlit app that turns uni readings into summaries, key points,
keywords and interactive study games (flashcards, multiple choice,
true/false, Q&A), powered by the Gemini API.

I built it because I kept pasting readings into AI chats to study faster.
This automates that and makes it interactive.

## Features
- Drag and drop PDF, DOCX, TXT or MD files
- AI-generated summary, key points, keywords and short Q&A
- Flashcards, multiple choice and true/false quizzes with scoring
- Download results as JSON and reload them later without calling the AI
- Auto-retry when the API is busy
<img width="1656" height="746" alt="image" src="https://github.com/user-attachments/assets/1ee989eb-e729-44c3-9488-b0f062b80cfe" />
<img width="1471" height="870" alt="image" src="https://github.com/user-attachments/assets/7d717634-c2a1-49ae-b2b3-3a201bd7b30c" />

## Setup
1. Install Python 3.10+
2. Install packages:
```
   pip install -r requirements.txt
```
3. Get a free API key at https://aistudio.google.com/apikey
4. Copy `.env.example` to `.env` and paste your key in it

## Run
```
python -m streamlit run app.py
```

## Known limitations
- Scanned PDFs (images of pages) don't work, there's no OCR yet
- Texts over 150,000 characters get cut off
- AI summaries can contain mistakes, always check against the source

## Built with
Python, Streamlit, Google Gemini API, pypdf, python-docx

## Roadmap
- Syllabus parsing and a week-by-week view
