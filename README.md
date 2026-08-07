# Data Model Documentation Agent

This beginner-friendly project creates Power BI semantic-model documentation
from a zipped TMDL `definition` folder. Python reads the model structure, and a
Gemini model running through Google Agent Development Kit (ADK) writes the final
Markdown report.

## Why each part exists

- `tmdl_parser.py` reads trusted structure from the ZIP without needing a PBIX
  parser or Power BI Desktop automation.
- `agent.py` defines the Gemini model, its role, and its safety/documentation
  instructions using Google ADK.
- `documenter.py` sends metadata to the agent and receives Markdown.
- `app.py` gives users a simple upload, preview, and download screen.
- `.env` stores local configuration and is excluded from Git.

The raw ZIP and report data rows are not sent to Gemini. The model receives the
parsed semantic metadata needed for documentation: table/column names,
descriptions, DAX measures, relationships, roles, perspectives, and cultures.
Shared Power Query expression names are included, but their M source text is
not sent because it may contain internal URLs or connection information.

## 1. Activate the Python 3.11 environment

```bash
source .venv/bin/activate
python --version
```

Google ADK requires a newer Python than the original Python 3.9 environment, so
this project now uses Python 3.11.

## 2. Install the packages

```bash
python -m pip install -r requirements.txt
```

## 3. Configure Gemini authentication

Do not paste a real API key into source code or commit it to Git.

For local learning with Google AI Studio:

```bash
cp .env.example .env
```

Open `.env`, replace `replace-with-your-key`, and leave the Vertex AI lines
commented.

For organizational use, ask your cloud/security team for an approved Vertex AI
project and authentication. Then configure Application Default Credentials and
use these `.env` values instead of an API key:

```bash
gcloud auth application-default login
```

```text
GOOGLE_GENAI_USE_VERTEXAI=TRUE
GOOGLE_CLOUD_PROJECT=your-approved-project-id
GOOGLE_CLOUD_LOCATION=your-approved-location
GEMINI_MODEL=gemini-flash-latest
```

## 4. Start the user interface

```bash
streamlit run app.py
```

Upload `definition.zip`, select **Generate documentation**, review the report,
and download the Markdown file.

## Command-line option

```bash
python -m model_doc_agent.documenter sample_data/definition.zip \
  --output output/model_documentation.md
```

## Run tests

The tests validate parsing and the LLM handoff without spending Gemini tokens:

```bash
python -m unittest discover -s tests -v
```

## Current limits

- Input must be a ZIP of the semantic model's `definition` folder.
- ZIP size is limited to 25 MB and uncompressed content to 100 MB.
- Parsed metadata is limited to 800,000 characters per Gemini request.
- AI-written descriptions are suggestions and must be reviewed by a model
  owner before publication.
- Use only a Gemini/Vertex AI environment approved by your organization.
