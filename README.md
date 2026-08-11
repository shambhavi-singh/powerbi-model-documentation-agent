# Data Model Documentation Agent

This beginner-friendly project creates documentation for Power BI reports and
semantic models. Upload a complete Power BI Project (PBIP) ZIP for page and
visual explanations, or upload a zipped TMDL `definition` folder for model-only
documentation. Python reads the structure, and a Gemini model running through
Google Agent Development Kit (ADK) writes the report. Users can download both
Markdown and a styled Word document based on the supplied organizational
template.

## Why each part exists

- `tmdl_parser.py` reads trusted structure from the ZIP without needing a PBIX
  parser or Power BI Desktop automation.
- `report_parser.py` reads PBIR pages, visuals, data roles, filters,
  drill-through configuration, sorting, bookmarks, and visible report text.
- `agent.py` defines the Gemini model, its role, and its safety/documentation
  instructions using Google ADK.
- `documenter.py` sends metadata to the agent and receives Markdown.
- `docx_exporter.py` converts that Markdown into the branded Word layout while
  preserving the template's theme, styles, page setup, header, footer, and page
  number field.
- `templates/Power_BI_Report_Documentation_Template.docx` is the unchanged Word
  template used as the visual authority.
- `app.py` gives users a simple upload, preview, and download screen.
- `.env` stores local configuration and is excluded from Git.

The raw ZIP and report data rows are not sent to Gemini. The model receives
parsed semantic metadata plus sanitized report metadata such as page names,
visual types, titles, fields, measures, filter fields, sorting, drill-through,
and bookmarks. Report filter-selection expressions, bookmark exploration state,
images, resource content, and Power Query M source text are excluded.

## Prepare the input ZIP

For complete report and model documentation:

1. Open the PBIX file in Power BI Desktop.
2. Save it as a Power BI Project (`.pbip`).
3. Keep the related `.Report` and `.SemanticModel` folders together.
4. ZIP the project folder.

Example:

```text
SalesProject.zip
├── Sales.pbip
├── Sales.Report/
│   ├── definition.pbir
│   └── definition/
│       ├── report.json
│       ├── pages/
│       └── bookmarks/
└── Sales.SemanticModel/
    └── definition/
        ├── model.tmdl
        ├── relationships.tmdl
        └── tables/
```

For model-only documentation, the existing `definition.zip` format is still
supported.

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

Upload the complete PBIP ZIP or `definition.zip`. Choose **Summary** for a short
business-friendly document or **Detailed** for every visual and a technical
model inventory. Select **Generate documentation**, review the result, and
download either the Markdown or Word file.

## Generated document format

The Word document uses the supplied template's visual design and a concise,
developer-oriented structure:

1. Report Overview (or Semantic Model Overview for a model-only ZIP)
2. Report Pages, only when PBIR report files are present
3. Semantic Model, including tables, relationships, and a model diagram
4. Measures and Business Logic
5. Model-to-Report Lineage, when direct report references are parsed
6. Developer Insights, limited to evidence-backed observations
7. Security and Developer Handover
8. Technical Appendix

The overview includes the generation date, artifact source, counts, and
important measures. Report sections connect pages and visuals to semantic-model
fields. The appendix keeps the main document short while retaining the measure
catalog and, in Detailed mode, the complete column inventory.

The document uses compact tables and Mermaid definitions. Mermaid blocks are
normalized after Gemini responds: the application emits only simple
`flowchart LR` nodes and `-->` edges, while relationship details remain in the
adjacent table. This prevents malformed ER-cardinality syntax from breaking the
document renderer. Summary mode explains every table and report page while
keeping columns, calculations, and visual inventories compact. Detailed mode
includes every parsed column, measure, relationship, page, filter field, and
visual. Unsupported sections are removed completely; the agent does not fill
the report with `[Enter details]` or missing-input messages.

PBIP metadata cannot prove owners, contacts, revision history, refresh and
gateway settings, workspace permissions, or deployment paths. These unsupported
administrative sections are intentionally excluded from the generated document.

## Command-line option

```bash
python -m model_doc_agent.documenter path/to/SalesProject.zip \
  --detail summary \
  --output output/model_documentation.md
```

Use `--detail detailed` when every parsed field, measure, relationship, filter,
and visual should be included.

## Run tests

The tests validate parsing and the LLM handoff without spending Gemini tokens:

```bash
python -m unittest discover -s tests -v
```

## Current limits

- Input must be a complete PBIP project ZIP containing one semantic model, or a
  ZIP of one semantic model's `definition` folder.
- Complete project ZIPs currently support the modern PBIR `definition` folder.
- A ZIP containing multiple semantic models is rejected to prevent incorrect
  visual-to-model matching.
- ZIP size is limited to 25 MB and uncompressed content to 100 MB.
- Parsed metadata is limited to 800,000 characters per Gemini request.
- Selected filter expressions and bookmark state are intentionally excluded;
  visible page titles, visual titles, text boxes, and bookmark names are sent as
  documentation metadata.
- AI-written descriptions are suggestions and must be reviewed by a model
  owner before publication.
- Use only a Gemini/Vertex AI environment approved by your organization.
