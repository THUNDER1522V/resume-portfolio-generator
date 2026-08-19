"""
AI-Assisted Resume -> Portfolio Generator (CLI)
------------------------------------------------
Reads resume.txt, sends it to the Gemini API with a controlled prompt,
receives structured JSON, and generates portfolio.html from template.html.

This is the required command-line workflow for the project brief.
Core logic lives in pipeline.py so it's shared with the optional web
UI in app.py.

Run:
    python main.py
"""

import os
import sys

from dotenv import load_dotenv

import pipeline

RESUME_PATH = "resume.txt"
TEMPLATE_PATH = "template.html"
OUTPUT_PATH = "portfolio.html"


def read_resume(path: str) -> str:
    """Read resume.txt, validate it, and return cleaned text.
    Exits the program with a clear message on any failure.
    """
    if not os.path.exists(path):
        print(f"ERROR: '{path}' was not found. Create a resume.txt file "
              f"in the project folder and try again.")
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        raw_text = f.read()

    cleaned = pipeline.clean_resume_text(raw_text)

    try:
        pipeline.validate_resume_text(cleaned)
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    return cleaned


def load_api_key() -> str:
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY is not set. Copy .env.example to .env "
              "and add your Gemini API key.")
        sys.exit(1)
    return api_key


def main():
    print("Reading and validating resume.txt ...")
    resume_text = read_resume(RESUME_PATH)

    print("Configuring Gemini ...")
    api_key = load_api_key()
    try:
        client = pipeline.get_client(api_key)
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    print("Sending resume to Gemini ...")
    prompt = pipeline.build_prompt(resume_text)
    try:
        raw_response = pipeline.call_gemini(client, prompt)
    except RuntimeError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    print("Parsing JSON response ...")
    try:
        data = pipeline.parse_gemini_response(raw_response)
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)
    data = pipeline.normalize_data(data)

    print("Generating portfolio.html ...")
    if not os.path.exists(TEMPLATE_PATH):
        print(f"ERROR: '{TEMPLATE_PATH}' was not found.")
        sys.exit(1)

    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        template_str = f.read()

    html = pipeline.render_portfolio_html(template_str, data, css_path="style.css")

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Portfolio generated successfully: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()