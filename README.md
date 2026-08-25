# AI-Assisted Resume → Portfolio Generator

Converts a plain-text resume into a styled HTML portfolio page using the
Gemini API.

## How it works

1. `resume.txt` is read and cleaned (extra blank lines / whitespace removed).
2. The cleaned text is sent to Gemini with a controlled prompt that asks for
   strict JSON, built only from information present in the resume.
3. The JSON response is parsed and normalized (missing fields default to
   empty values — nothing is invented).
4. The data is inserted into `template.html` / `style.css` to produce
   `portfolio.html`.

## Setup

1. Clone this repository.
2. Create a virtual environment and install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate   # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and add your own Gemini API key:
   ```bash
   cp .env.example .env
   ```
4. Get a free API key from [Google AI Studio](https://aistudio.google.com/apikey).

## Run

1. Put your resume content in `resume.txt`.
2. Run:
   ```bash
   python main.py
   ```
3. Open `portfolio.html` in your browser.

## Prompt design

_(Fill in: paste your final prompt and explain the choices you made —
why you require JSON-only output, why empty values are used for missing
info, how you prevent invented content, etc.)_

## Limitations & hallucination risks

_(Fill in: Gemini output is a draft. Document any cases where it
paraphrased, summarized, or subtly altered facts, and how you verified
content against the original resume before submission.)_

## Testing results

| Test case | Expected behavior | Result |
|---|---|---|
| Missing resume.txt | Clear error, safe stop |Passed |
| Empty/very short resume | Rejected with message | Passed|
| Valid resume | portfolio.html generated |Passed |
| Resume with missing sections | No invented content | Passed|
| Missing API key | Configuration error |Passed |
| API failure | Handled without crashing |Passed |
| Invalid JSON response | Clear error, safe stop | Passed|

## AI usage log

| Tool | Prompt/request | What it generated | What we changed |
|---|---|---|---|
| | | | |

## Screenshots

_(Add screenshots of the running program and the generated portfolio here.)_
