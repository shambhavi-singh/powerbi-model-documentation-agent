"""Streamlit interface for Power BI model and report documentation."""

import tempfile
from pathlib import Path

import streamlit as st

from model_doc_agent.documenter import generate_documentation_sync
from model_doc_agent.docx_exporter import render_markdown_to_docx


st.set_page_config(
    page_title="Data Model Documentation Agent",
    page_icon="📘",
    layout="wide",
)

st.title("Data Model Documentation Agent")
st.write(
    "Upload a complete Power BI Project (PBIP) ZIP to document both the "
    "report and semantic model"
)
st.info(
    "Gemini receives parsed names, descriptions, DAX, titles, and visible "
    "text-box content. The raw ZIP, report data rows, Power Query source "
    "text, images, and selected filter values are not sent to the model. "
    "The final document focuses only on the semantic model and report."
)

uploaded_file = st.file_uploader(
    "Upload PBIP project ZIP or definition.zip",
    type=["zip"],
    help="Maximum ZIP size accepted by this project: 25 MB.",
)

detail_level = st.radio(
    "Documentation detail",
    options=("Summary", "Detailed"),
    horizontal=True,
    help=(
        "Both options use the same organizational template. Summary keeps "
        "inventories compact; Detailed includes every field, measure, and "
        "visual."
    ),
)

if uploaded_file is not None and st.button(
    "Generate documentation",
    type="primary",
):
    temporary_path = None

    try:
        with tempfile.NamedTemporaryFile(
            suffix=".zip",
            delete=False,
        ) as temporary_file:
            temporary_file.write(uploaded_file.getbuffer())
            temporary_path = Path(temporary_file.name)

        with st.spinner("Gemini is creating the documentation..."):
            report = generate_documentation_sync(
                str(temporary_path),
                detail_level=detail_level.lower(),
            )
            word_document = render_markdown_to_docx(report)

        st.success("Documentation created.")
        st.markdown(report)
        st.download_button(
            "Download Markdown report",
            data=report,
            file_name="power_bi_documentation.md",
            mime="text/markdown",
        )
        st.download_button(
            "Download Word report",
            data=word_document,
            file_name="power_bi_documentation.docx",
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document"
            ),
        )
    except (RuntimeError, ValueError) as error:
        st.error(str(error))
    except Exception as error:
        st.error(
            "Documentation generation failed. Check your Gemini/Vertex "
            f"configuration and try again. Technical detail: {error}"
        )
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
