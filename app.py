"""Streamlit interface for the Power BI data-model documentation agent."""

import tempfile
from pathlib import Path

import streamlit as st

from model_doc_agent.documenter import generate_documentation_sync


st.set_page_config(
    page_title="Data Model Documentation Agent",
    page_icon="📘",
    layout="wide",
)

st.title("Data Model Documentation Agent")
st.write(
    "Upload the ZIP made from a Power BI semantic model's `definition` "
    "folder. The app parses TMDL metadata and asks Gemini to create a "
    "Markdown report."
)
st.info(
    "Only parsed model metadata is sent to Gemini. The application does "
    "not read report data rows and does not send the raw ZIP to the model."
)

uploaded_file = st.file_uploader(
    "Upload definition.zip",
    type=["zip"],
    help="Maximum ZIP size accepted by this project: 25 MB.",
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
                str(temporary_path)
            )

        st.success("Documentation created.")
        st.markdown(report)
        st.download_button(
            "Download Markdown report",
            data=report,
            file_name="model_documentation.md",
            mime="text/markdown",
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
