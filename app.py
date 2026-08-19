"""
Optional web UI for the Resume -> Portfolio Generator.
--------------------------------------------------------
Lets a user upload a .txt or .pdf resume through a browser and get a
generated portfolio back. The Gemini API key stays on the server the
whole time (loaded from .env) and is never sent to or used by the
browser, per the project brief's Responsible AI requirements.

This is an ADDITION on top of the required CLI (main.py / resume.txt).
It reuses the exact same pipeline.py logic, so both entry points stay
in sync.

Run:
    python app.py
Then open http://127.0.0.1:5000 in a browser.
"""

import os
import uuid

from dotenv import load_dotenv
from flask import Flask, request, render_template, send_from_directory, abort
from pypdf import PdfReader

import pipeline

load_dotenv()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB upload limit

TEMPLATE_PATH = "template.html"
GENERATED_DIR = "generated"  # where finished portfolio.html files are temporarily stored for download
ALLOWED_EXTENSIONS = {"txt", "pdf"}

os.makedirs(GENERATED_DIR, exist_ok=True)


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def extract_text_from_pdf(file_storage) -> str:
    reader = PdfReader(file_storage)
    pages_text = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages_text)


@app.route("/", methods=["GET"])
def index():
    return render_template("upload.html", error=None)


@app.route("/style.css")
def serve_css():
    # Serves the same style.css used by the CLI-generated portfolio.html
    return send_from_directory(".", "style.css")


@app.route("/generate", methods=["POST"])
def generate():
    uploaded_file = request.files.get("resume_file")

    if uploaded_file is None or uploaded_file.filename == "":
        return render_template("upload.html", error="Please choose a .txt or .pdf file to upload.")

    if not allowed_file(uploaded_file.filename):
        return render_template("upload.html", error="Only .txt and .pdf files are supported.")

    extension = uploaded_file.filename.rsplit(".", 1)[1].lower()

    # --- Extract raw text depending on file type ---
    try:
        if extension == "txt":
            raw_text = uploaded_file.read().decode("utf-8", errors="ignore")
        else:  # pdf
            raw_text = extract_text_from_pdf(uploaded_file)
    except Exception as e:
        return render_template("upload.html", error=f"Could not read that file: {e}")

    cleaned_text = pipeline.clean_resume_text(raw_text)

    try:
        pipeline.validate_resume_text(cleaned_text)
    except ValueError as e:
        return render_template("upload.html", error=str(e))

    # --- Gemini call (server-side only; key never reaches the browser) ---
    api_key = os.getenv("GEMINI_API_KEY")
    try:
        client = pipeline.get_client(api_key)
    except ValueError:
        return render_template(
            "upload.html",
            error="Server is not configured with a Gemini API key. Contact the project admin.",
        )

    prompt = pipeline.build_prompt(cleaned_text)
    try:
        raw_response = pipeline.call_gemini(client, prompt)
    except RuntimeError as e:
        return render_template("upload.html", error=f"Gemini request failed: {e}")

    try:
        data = pipeline.parse_gemini_response(raw_response)
    except ValueError as e:
        return render_template("upload.html", error=f"Could not parse Gemini's response: {e}")

    data = pipeline.normalize_data(data)

    if not os.path.exists(TEMPLATE_PATH):
        return render_template("upload.html", error="Server error: template.html is missing.")

    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        template_str = f.read()

    html = pipeline.render_portfolio_html(template_str, data, css_path="/style.css")

    # Save so the user can download it, keyed by a random id (no personal
    # data in the filename/URL itself)
    file_id = uuid.uuid4().hex
    output_path = os.path.join(GENERATED_DIR, f"{file_id}.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    toolbar = f'''
    <div style="position:sticky;top:0;z-index:10;background:#0d1117;border-bottom:1px solid #30363d;
                padding:0.9rem 1.5rem;display:flex;justify-content:center;gap:1rem;">
      <a href="/download/{file_id}"
         style="font-family:'JetBrains Mono',monospace;font-size:0.82rem;font-weight:600;
                text-decoration:none;padding:0.55rem 1.1rem;border-radius:6px;
                background:#58a6ff;color:#0d1117;">⬇ Download portfolio.html</a>
      <a href="/"
         style="font-family:'JetBrains Mono',monospace;font-size:0.82rem;font-weight:600;
                text-decoration:none;padding:0.55rem 1.1rem;border-radius:6px;
                background:transparent;color:#8b949e;border:1px solid #30363d;">← Try another resume</a>
    </div>
    '''
    html_with_toolbar = html.replace("<body>", "<body>\n" + toolbar, 1)

    return html_with_toolbar


@app.route("/download/<file_id>")
def download(file_id):
    # file_id comes from uuid4().hex - alnum only, safe to use directly
    if not file_id.isalnum():
        abort(400)
    filepath = os.path.join(GENERATED_DIR, f"{file_id}.html")
    if not os.path.exists(filepath):
        abort(404)
    return send_from_directory(GENERATED_DIR, f"{file_id}.html", as_attachment=True,
                                download_name="portfolio.html")


if __name__ == "__main__":
    app.run(debug=True)