import json
import random
import tempfile
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Study Helper", page_icon="📚", layout="centered")
st.title("📚 Study Helper")

# reuse the functions from study_helper.py (keep both files in the same folder)
try:
    from study_helper import MAX_CHARS, analyse, read_file
except Exception as e:
    st.error(f"Couldn't load study_helper.py: {e}")
    st.stop()


# ---------- analysis (cached so clicks don't re-call the AI) ----------
@st.cache_data(show_spinner=False)
def process(name: str, content: bytes) -> dict:
    ext = Path(name).suffix.lower()
    if ext == ".json":
        return json.loads(content.decode("utf-8"))

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"upload{ext}"
        path.write_bytes(content)
        text = read_file(path).strip()
    print(f"{name}: {len(text)} characters")
    if len(text) < 200:
        raise ValueError("almost no text found (scanned PDF?)")
    return analyse(text[:MAX_CHARS])


# ---------- flashcard helpers ----------
def go(key, step, n):
    st.session_state[f"{key}_idx"] = (st.session_state[f"{key}_idx"] + step) % n
    st.session_state[f"{key}_flip"] = False


def flip(key):
    st.session_state[f"{key}_flip"] = not st.session_state[f"{key}_flip"]


def shuffle(key, n):
    order = list(range(n))
    random.shuffle(order)
    st.session_state[f"{key}_order"] = order
    st.session_state[f"{key}_idx"] = 0
    st.session_state[f"{key}_flip"] = False


# ---------- drag & drop ----------
uploaded = st.file_uploader(
    "Drop your readings here (tip: open the folder, Ctrl+A, drag all files in)",
    type=["pdf", "docx", "txt", "md", "json"],
    accept_multiple_files=True,
)
if not uploaded:
    st.info("Drop one or more files to start.")
    st.stop()

docs = {}
for f in uploaded:
    with st.spinner(f"Working on {f.name} ..."):
        try:
            docs[f.name] = process(f.name, f.getvalue())
        except Exception as e:
            st.error(f"{f.name}: {e}")

if not docs:
    st.stop()

key = st.selectbox("Pick a document", list(docs.keys()))
data = docs[key]

tab_notes, tab_cards, tab_mcq, tab_tf, tab_qa = st.tabs(
    ["📝 Notes", "🃏 Flashcards", "✅ Multiple choice", "⚖️ True / False", "❓ Q&A"]
)

# ---------- notes ----------
with tab_notes:
    if "overview" in data:
        st.subheader("Overview")
        st.write(data["overview"])
        st.subheader("⭐ Must know")
        for m in data.get("must_know", []):
            st.markdown(f"- {m}")
        st.subheader("Notes by section")
        for s in data.get("sections", []):
            with st.expander(s["title"], expanded=True):
                for n in s["notes"]:
                    st.markdown(f"- {n}")
    else:  # old v1 files
        st.subheader("Summary")
        st.write(data.get("summary", ""))
        st.subheader("Key points")
        for b in data.get("bullet_points", []):
            st.markdown(f"- {b}")

    st.subheader("Keywords")
    for k in data.get("keywords", []):
        st.markdown(f"- **{k['term']}**: {k['definition']}")
    st.download_button(
        "💾 Download .json (drop it next time, no AI needed)",
        json.dumps(data, ensure_ascii=False, indent=2),
        file_name=f"{Path(key).stem}.json",
        mime="application/json",
    )

# ---------- flashcards ----------
with tab_cards:
    cards = data.get("flashcards", [])
    if not cards:
        st.write("No flashcards for this document.")
    else:
        st.session_state.setdefault(f"{key}_order", list(range(len(cards))))
        st.session_state.setdefault(f"{key}_idx", 0)
        st.session_state.setdefault(f"{key}_flip", False)

        order = st.session_state[f"{key}_order"]
        idx = st.session_state[f"{key}_idx"]
        flipped = st.session_state[f"{key}_flip"]
        card = cards[order[idx]]

        st.caption(f"Card {idx + 1} / {len(cards)}")
        if flipped:
            st.success(f"**Answer:** {card['back']}")
        else:
            st.info(f"**Question:** {card['front']}")

        c1, c2, c3, c4 = st.columns(4)
        c1.button("⬅️ Prev", on_click=go, args=(key, -1, len(cards)), key=f"{key}_prev")
        c2.button("🔄 Flip", on_click=flip, args=(key,), key=f"{key}_flipbtn")
        c3.button("Next ➡️", on_click=go, args=(key, 1, len(cards)), key=f"{key}_next")
        c4.button("🔀 Shuffle", on_click=shuffle, args=(key, len(cards)), key=f"{key}_shuf")

# ---------- multiple choice ----------
with tab_mcq:
    mcq = data.get("multiple_choice", [])
    if not mcq:
        st.write("No multiple choice questions for this document.")
    else:
        with st.form(f"{key}_mcq_form"):
            picks = []
            for i, q in enumerate(mcq):
                st.markdown(f"**{i + 1}. {q['question']}**")
                picks.append(
                    st.radio(
                        "Choose",
                        q["options"],
                        index=None,
                        key=f"{key}_mcq_{i}",
                        label_visibility="collapsed",
                    )
                )
            submitted = st.form_submit_button("Check answers")

        if submitted:
            score = 0
            for i, q in enumerate(mcq):
                correct = q["options"][q.get("answer_index", 0)]
                if picks[i] == correct:
                    score += 1
                    st.success(f"{i + 1}. Correct ✅")
                else:
                    st.error(f"{i + 1}. Wrong ❌ Correct answer: {correct}")
                if q.get("explanation"):
                    st.caption(q["explanation"])
            st.subheader(f"Score: {score} / {len(mcq)}")

# ---------- true / false ----------
with tab_tf:
    tf = data.get("true_false", [])
    if not tf:
        st.write("No true/false questions for this document.")
    else:
        with st.form(f"{key}_tf_form"):
            tf_picks = []
            for i, q in enumerate(tf):
                st.markdown(f"**{i + 1}. {q['statement']}**")
                tf_picks.append(
                    st.radio(
                        "Choose",
                        ["True", "False"],
                        index=None,
                        horizontal=True,
                        key=f"{key}_tf_{i}",
                        label_visibility="collapsed",
                    )
                )
            tf_submitted = st.form_submit_button("Check answers")

        if tf_submitted:
            score = 0
            for i, q in enumerate(tf):
                correct = "True" if q["answer"] else "False"
                if tf_picks[i] == correct:
                    score += 1
                    st.success(f"{i + 1}. Correct ✅")
                else:
                    st.error(f"{i + 1}. Wrong ❌ It's {correct}")
                if q.get("explanation"):
                    st.caption(q["explanation"])
            st.subheader(f"Score: {score} / {len(tf)}")

# ---------- Q&A ----------
with tab_qa:
    st.caption("Answer in your head (or out loud) first, then open it.")
    for i, item in enumerate(data.get("questions", [])):
        with st.expander(f"{i + 1}. {item['q']}"):
            st.write(item["a"])