# app.py

import os
import tempfile
from flask import Flask, request, render_template, flash, redirect, url_for
from transformers import pipeline
import pdfplumber

app = Flask(__name__)
app.secret_key = "change_this_to_a_random_secret"  # Replace with a real secret in production

# ─── 3.1. Load the Summarization Pipeline ─────────────────────────────────
# We'll use Facebook's BART (large) for summarization. On CPU, first inference takes ~10–15s,
# subsequent inferences ~2–3s.
SUMMARIZER = pipeline("summarization", model="facebook/bart-large-cnn")

def summarize_text(text: str) -> str:
    """
    Given a (potentially long) text string, run it through the summarization pipeline.
    We chunk into ~1024-token segments if the text is very long.
    """
    max_chunk = 1000  # BART's text length limit ≈ 1024 tokens; adjust as needed.

    # If the text is short, summarize in one shot:
    if len(text.split()) <= max_chunk:
        summary = SUMMARIZER(text, max_length=120, min_length=30, do_sample=False)[0]["summary_text"]
        return summary.strip()

    # Otherwise, break the text into chunks of ~1000 words each, summarize each, then concatenate:
    sentences = text.split(". ")
    current_chunk = ""
    chunks = []
    for sent in sentences:
        # Avoid overshooting the chunk size
        if len((current_chunk + " " + sent).split()) < max_chunk:
            current_chunk += " " + sent
        else:
            chunks.append(current_chunk.strip())
            current_chunk = sent  # start new chunk
    if current_chunk:
        chunks.append(current_chunk.strip())

    summaries = []
    for chunk in chunks:
        out = SUMMARIZER(chunk, max_length=120, min_length=30, do_sample=False)[0]["summary_text"]
        summaries.append(out.strip())

    # Finally, concatenate all partial summaries and optionally summarize again to be concise:
    combined_summary = " ".join(summaries)
    if len(combined_summary.split()) > max_chunk:
        # Summarize the summary to condense further
        combined_summary = SUMMARIZER(combined_summary, max_length=150, min_length=50, do_sample=False)[0]["summary_text"].strip()

    return combined_summary

def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Use pdfplumber to extract all text from a PDF file.
    """
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text

# ─── 3.2. Routes ─────────────────────────────────────────────────────────────

@app.route("/", methods=["GET", "POST"])
def index():
    summary = None

    if request.method == "POST":
        # 1) Check if the user submitted a PDF or pasted text
        input_text = request.form.get("input_text", "").strip()
        file = request.files.get("file")

        if not input_text and (file is None or file.filename == ""):
            flash("Please either paste some text or upload a PDF.", "error")
            return redirect(request.url)

        # 2) If a PDF was uploaded, extract text
        if file and file.filename.endswith(".pdf"):
            try:
                # Save temporarily
                temp_dir = tempfile.mkdtemp()
                pdf_path = os.path.join(temp_dir, file.filename)
                file.save(pdf_path)
                input_text = extract_text_from_pdf(pdf_path)
                if not input_text:
                    flash("Could not extract any text from the uploaded PDF.", "error")
                    return redirect(request.url)
            except Exception as e:
                flash(f"Error extracting text from PDF: {e}", "error")
                return redirect(request.url)

        # 3) If the user only pasted text (or we now have extracted PDF text), summarize:
        try:
            summary = summarize_text(input_text)
        except Exception as e:
            flash(f"Error during summarization: {e}", "error")
            return redirect(request.url)

    return render_template("index.html", summary=summary)

if __name__ == "__main__":
    # Flask default port is 5000
    app.run(host="0.0.0.0", port=5000, debug=True)
