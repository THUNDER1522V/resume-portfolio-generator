"""
Shared pipeline logic for the Resume -> Portfolio Generator.

This module contains no file I/O tied to a specific entry point (no
sys.exit, no fixed file paths) so it can be reused by:
- main.py   (the required CLI tool: resume.txt -> portfolio.html)
- app.py    (the optional Flask web UI: upload a file -> view/download)

All functions here raise ordinary Python exceptions on failure; each
caller decides how to present that failure (print + exit for the CLI,
a flashed error message for the web UI).
"""

import re
import json
import time

from google import genai

GEMINI_MODEL = "gemini-flash-latest"  # alias that auto-points to Google's current stable Flash model
MIN_RESUME_LENGTH = 50  # characters - below this we treat the resume as "too short"


# ---------------------------------------------------------------------------
# Resume text cleaning + validation
# ---------------------------------------------------------------------------

def clean_resume_text(text: str) -> str:
    """Remove extra blank lines and trailing/leading whitespace."""
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line != ""]
    return "\n".join(lines)


def validate_resume_text(cleaned_text: str, min_length: int = MIN_RESUME_LENGTH) -> None:
    """Raise ValueError if the cleaned resume text is too short/empty."""
    if len(cleaned_text) < min_length:
        raise ValueError(
            f"Resume text is empty or too short to process "
            f"(minimum {min_length} characters after cleaning)."
        )


# ---------------------------------------------------------------------------
# Gemini client + prompt
# ---------------------------------------------------------------------------

def get_client(api_key: str) -> genai.Client:
    """Create a Gemini client. Raises ValueError if no key is provided."""
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set.")
    return genai.Client(api_key=api_key)


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


def call_gemini(client: genai.Client, prompt: str, model: str = GEMINI_MODEL,
                 max_retries: int = 3) -> str:
    """Send the prompt to Gemini and return the raw text response.

    Automatically retries on transient server-side errors (503 UNAVAILABLE,
    429 rate limit) with a short increasing delay, since these are usually
    temporary traffic spikes on Google's side, not real failures.

    Raises RuntimeError (with the original message) if all attempts fail.
    """
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            response = client.models.generate_content(model=model, contents=prompt)
            return response.text
        except Exception as e:
            last_error = e
            error_text = str(e)
            is_transient = "503" in error_text or "429" in error_text or "UNAVAILABLE" in error_text

            if is_transient and attempt < max_retries:
                time.sleep(2 * attempt)  # 2s, then 4s
                continue

            raise RuntimeError(f"Gemini API request failed: {e}") from e

    raise RuntimeError(f"Gemini API request failed after {max_retries} attempts: {last_error}")


# ---------------------------------------------------------------------------
# JSON parsing + normalization
# ---------------------------------------------------------------------------

def parse_gemini_response(raw_text: str) -> dict:
    """Strip accidental markdown fences and parse JSON.
    Raises ValueError if the response is not valid JSON.
    """
    text = raw_text.strip()
    text = re.sub(r"^```(json)?", "", text.strip())
    text = re.sub(r"```$", "", text.strip())
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Gemini did not return valid JSON: {e}") from e


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
# HTML rendering
# ---------------------------------------------------------------------------

def escape(text) -> str:
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


def render_portfolio_html(template_str: str, data: dict, css_path: str = "style.css") -> str:
    """Fill the HTML template with normalized portfolio data.
    css_path lets callers point at 'style.css' (CLI, same-folder file)
    or '/static/style.css' (Flask web app).
    """
    sections_html = "\n".join(filter(None, [
        render_skills(data["skills"]),
        render_education(data["education"]),
        render_experience(data["experience"]),
        render_projects(data["projects"]),
        render_achievements(data["achievements"]),
        render_contact(data["contact"]),
    ]))

    html = template_str
    html = html.replace("{{css_path}}", css_path)
    html = html.replace("{{name}}", escape(data["name"]) or "Your Name")
    html = html.replace("{{headline}}", escape(data["headline"]))
    html = html.replace("{{summary}}", escape(data["summary"]))
    html = html.replace("{{sections}}", sections_html)
    return html