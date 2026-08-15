"""
AI-Assisted Resume -> Portfolio Generator
------------------------------------------
Reads resume.txt, sends it to the Gemini API with a controlled prompt,
receives structured JSON, and generates portfolio.html from a template.

Run:
    python main.py
"""

import os
import re
import sys
import json

from dotenv import load_dotenv
from google import genai

RESUME_PATH = "resume.txt"
TEMPLATE_PATH = "template.html"
OUTPUT_PATH = "portfolio.html"
MIN_RESUME_LENGTH = 50  # characters - below this we treat the resume as "too short"
GEMINI_MODEL = "gemini-flash-latest"  # alias that auto-points to Google's current stable Flash model

_client = None  # module-level Gemini client, set up in configure_gemini()


# ---------------------------------------------------------------------------
# Step 1: Read and clean resume.txt
# ---------------------------------------------------------------------------

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

    cleaned = clean_resume_text(raw_text)

    if len(cleaned) < MIN_RESUME_LENGTH:
        print(f"ERROR: '{path}' is empty or too short to process "
              f"(minimum {MIN_RESUME_LENGTH} characters after cleaning).")
        sys.exit(1)

    return cleaned


def clean_resume_text(text: str) -> str:
    """Remove extra blank lines and trailing/leading whitespace."""
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line != ""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Step 2: Configure Gemini
# ---------------------------------------------------------------------------

def configure_gemini() -> None:
    global _client

    load_dotenv()  # loads variables from a local .env file, if present
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        print("ERROR: GEMINI_API_KEY is not set. Copy .env.example to .env "
              "and add your Gemini API key.")
        sys.exit(1)

    _client = genai.Client(api_key=api_key)


# ---------------------------------------------------------------------------
# Step 3: Build the prompt
# ---------------------------------------------------------------------------

def build_prompt(resume_text: str) -> str:
    """Build a controlled prompt that forces Gemini to:
    - only use information present in the resume
    - never invent facts
    - return strict JSON matching our schema
    """
    return f"""You will receive resume text between the markers <<<RESUME>>> and <<<END>>>.

Extract information from the resume ONLY. Do not invent, assume, or add any
skill, project, company, date, achievement, or link that is not explicitly
present in the resume text. If a piece of information is missing, use an
empty string "" or an empty list [] for that field - never guess.

Return ONLY valid JSON, with no markdown code fences, no backticks, and no
explanation text before or after it. The JSON must exactly match this shape:

{{
  "name": "",
  "headline": "",
  "summary": "",
  "skills": [],
  "education": [
    {{"degree": "", "institution": "", "years": ""}}
  ],
  "experience": [
    {{"role": "", "company": "", "dates": "", "details": []}}
  ],
  "projects": [
    {{"title": "", "description": "", "technologies": []}}
  ],
  "achievements": [],
  "contact": {{"email": "", "phone": "", "linkedin": "", "github": "", "links": []}}
}}

Keep the "summary" field concise (2-4 sentences) and strictly factual,
based only on the resume content.

<<<RESUME>>>
{resume_text}
<<<END>>>
"""


# ---------------------------------------------------------------------------
# Step 4: Call Gemini
# ---------------------------------------------------------------------------

def call_gemini(prompt: str) -> str:
    """Send the prompt to Gemini and return the raw text response.
    Handles API errors without crashing the program.
    """
    try:
        response = _client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )
        return response.text
    except Exception as e:
        print(f"ERROR: Gemini API request failed: {e}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Step 5: Parse the JSON response safely
# ---------------------------------------------------------------------------

def parse_gemini_response(raw_text: str) -> dict:
    """Strip accidental markdown fences and parse JSON.
    Exits cleanly if the response is not valid JSON.
    """
    text = raw_text.strip()

    # Defensive cleanup in case Gemini wraps the JSON in ```json ... ```
    text = re.sub(r"^```(json)?", "", text.strip())
    text = re.sub(r"```$", "", text.strip())
    text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        print("ERROR: Gemini did not return valid JSON. Raw response was:")
        print(raw_text)
        sys.exit(1)

    return data


# ---------------------------------------------------------------------------
# Step 6: Fill in any missing fields with safe defaults
# ---------------------------------------------------------------------------

def normalize_data(data: dict) -> dict:
    defaults = {
        "name": "",
        "headline": "",
        "summary": "",
        "skills": [],
        "education": [],
        "experience": [],
        "projects": [],
        "achievements": [],
        "contact": {"email": "", "phone": "", "linkedin": "", "github": "", "links": []},
    }
    for key, default_value in defaults.items():
        data.setdefault(key, default_value)
    return data


# ---------------------------------------------------------------------------
# Step 7: Generate HTML sections from data
# ---------------------------------------------------------------------------

def escape(text: str) -> str:
    """Minimal HTML escaping for text pulled from JSON."""
    if not isinstance(text, str):
        return ""
    return (text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;"))


def render_skills(skills: list) -> str:
    if not skills:
        return ""
    items = ", ".join(f'<span class="str">"{escape(s)}"</span>' for s in skills)
    return f'''<section class="file-card" id="skills">
      <div class="file-tab"><span class="tab-dot dot-json"></span>skills.json</div>
      <div class="file-body"><pre class="code-array"><span class="punct">[</span>{items}<span class="punct">]</span></pre></div>
    </section>'''


def render_education(education: list) -> str:
    if not education:
        return ""
    items = ""
    for edu in education:
        items += f"""
        <div class="entry">
          <p class="entry-title">{escape(edu.get("degree", ""))}</p>
          <p class="entry-meta">{escape(edu.get("institution", ""))} · {escape(edu.get("years", ""))}</p>
        </div>"""
    return f'''<section class="file-card" id="education">
      <div class="file-tab"><span class="tab-dot dot-log"></span>education.log</div>
      <div class="file-body">{items}</div>
    </section>'''


def render_experience(experience: list) -> str:
    if not experience:
        return ""
    items = ""
    for exp in experience:
        details = "".join(f"<li>{escape(d)}</li>" for d in exp.get("details", []))
        details_html = f"<ul>{details}</ul>" if details else ""
        items += f"""
        <div class="entry">
          <p class="entry-title">{escape(exp.get("role", ""))}</p>
          <p class="entry-meta">{escape(exp.get("company", ""))} · {escape(exp.get("dates", ""))}</p>
          {details_html}
        </div>"""
    return f'''<section class="file-card" id="experience">
      <div class="file-tab"><span class="tab-dot dot-log"></span>experience.log</div>
      <div class="file-body">{items}</div>
    </section>'''


def render_projects(projects: list) -> str:
    if not projects:
        return ""
    items = ""
    for proj in projects:
        tech = ", ".join(proj.get("technologies", []))
        tech_html = f'<p class="entry-tech">// {escape(tech)}</p>' if tech else ""
        items += f"""
        <div class="entry">
          <p class="entry-title">{escape(proj.get("title", ""))}</p>
          <p>{escape(proj.get("description", ""))}</p>
          {tech_html}
        </div>"""
    return f'''<section class="file-card" id="projects">
      <div class="file-tab"><span class="tab-dot dot-folder"></span>projects/</div>
      <div class="file-body">{items}</div>
    </section>'''


def render_achievements(achievements: list) -> str:
    if not achievements:
        return ""
    items = "".join(f"<li>{escape(a)}</li>" for a in achievements)
    return f'''<section class="file-card" id="achievements">
      <div class="file-tab"><span class="tab-dot dot-txt"></span>achievements.txt</div>
      <div class="file-body"><ul class="plain-list">{items}</ul></div>
    </section>'''


def render_contact(contact: dict) -> str:
    rows = []
    if contact.get("email"):
        rows.append(f'<div class="contact-row"><span class="contact-key">email:</span><a href="mailto:{escape(contact["email"])}">{escape(contact["email"])}</a></div>')
    if contact.get("phone"):
        rows.append(f'<div class="contact-row"><span class="contact-key">phone:</span><span class="plain-value">{escape(contact["phone"])}</span></div>')
    if contact.get("linkedin"):
        rows.append(f'<div class="contact-row"><span class="contact-key">linkedin:</span><a href="{escape(contact["linkedin"])}" target="_blank" rel="noopener">{escape(contact["linkedin"])}</a></div>')
    if contact.get("github"):
        rows.append(f'<div class="contact-row"><span class="contact-key">github:</span><a href="{escape(contact["github"])}" target="_blank" rel="noopener">{escape(contact["github"])}</a></div>')
    for link in contact.get("links", []):
        rows.append(f'<div class="contact-row"><span class="contact-key">link:</span><a href="{escape(link)}" target="_blank" rel="noopener">{escape(link)}</a></div>')

    if not rows:
        return ""
    return f'''<section class="file-card" id="contact">
      <div class="file-tab"><span class="tab-dot dot-md"></span>README.md</div>
      <div class="file-body"><div class="contact-rows">{"".join(rows)}</div></div>
    </section>'''


# ---------------------------------------------------------------------------
# Step 8: Fill the HTML template and save portfolio.html
# ---------------------------------------------------------------------------

def generate_portfolio(data: dict) -> None:
    if not os.path.exists(TEMPLATE_PATH):
        print(f"ERROR: '{TEMPLATE_PATH}' was not found.")
        sys.exit(1)

    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        template = f.read()

    sections_html = "\n".join(filter(None, [
        render_skills(data["skills"]),
        render_education(data["education"]),
        render_experience(data["experience"]),
        render_projects(data["projects"]),
        render_achievements(data["achievements"]),
        render_contact(data["contact"]),
    ]))

    html = template
    html = html.replace("{{name}}", escape(data["name"]) or "Your Name")
    html = html.replace("{{headline}}", escape(data["headline"]))
    html = html.replace("{{summary}}", escape(data["summary"]))
    html = html.replace("{{sections}}", sections_html)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Portfolio generated successfully: {OUTPUT_PATH}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Reading and validating resume.txt ...")
    resume_text = read_resume(RESUME_PATH)

    print("Configuring Gemini ...")
    configure_gemini()

    print("Sending resume to Gemini ...")
    prompt = build_prompt(resume_text)
    raw_response = call_gemini(prompt)

    print("Parsing JSON response ...")
    data = parse_gemini_response(raw_response)
    data = normalize_data(data)

    print("Generating portfolio.html ...")
    generate_portfolio(data)


if __name__ == "__main__":
    main()
