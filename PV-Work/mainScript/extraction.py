# /// script
# [tool.marimo.runtime]
# auto_instantiate = false
# ///

import marimo

__generated_with = "0.14.9"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    import pandas as pd
    import json
    from pathlib import Path
    from pydantic import BaseModel, Field, validator
    from langchain_community.document_loaders import PDFMinerLoader
    from langchain.text_splitter import RecursiveCharacterTextSplitter
    from langchain_community.chat_models import ChatOllama
    from langchain_core.prompts import PromptTemplate
    from langchain_core.output_parsers import PydanticOutputParser
    return (
        BaseModel,
        ChatOllama,
        Field,
        PDFMinerLoader,
        Path,
        PromptTemplate,
        PydanticOutputParser,
        RecursiveCharacterTextSplitter,
        json,
        pd,
        validator,
    )


@app.cell
def _():
    return


@app.cell
def _(Path):
    # Constants for readability
    PDF_FOLDER = Path("foldersam")
    MODEL_NAME = "gemma3:1b"
    OUTPUT_CSV = "pv_extraction_results_ollama.csv"
    CHUNK_SIZE = 6000
    CHUNK_OVERLAP = 200

    PROMPT_TEMPLATE = """
    You are extracting structured data from academic articles on photovoltaic cells.

    Instructions:
    - Only extract data for the **highest efficiency cell** reported.
    - Match the schema exactly as specified (see below).
    - For any field that is not available, return the value as "N/A".
    - Return a single valid **JSON object** (no markdown or code block formatting).
    - Skip the article's introduction.
    - Only one entry per article is required.

    Schema fields:
    - research_focus
    - key_findings
    - device_type
    - absorber_material
    - absorber_material_term_used
    - absorber_dopant_material
    - absorber_dopant_material_term_used
    - absorber_dopant_polarity
    - absorber_dopant_polarity_term_used
    - front_surface_morphology
    - front_surface_morphology_term_used
    - rear_surface_morphology
    - rear_surface_morphology_term_used
    - front_surface_passivation_material
    - front_surface_passivation_material_term_used
    - rear_surface_passivation_material
    - rear_surface_passivation_material_term_used
    - negative_metallization_material
    - negative_metallization_material_term_used
    - positive_metallization_material
    - positive_metallization_material_term_used
    - efficiency_percent
    - cell_area_cm2
    - short_circuit_current_a
    - short_circuit_current_density_ma_cm2
    - open_circuit_voltage_v
    - fill_factor_percent

    Article:
    {text}

    Format like:
    {format_instructions}

    """

    COLUMN_MAP = {
        "research_focus": "Research Focus", "key_findings": "Key Findings", "device_type": "Device Type",
        "absorber_material": "Absorber Material", "absorber_material_term_used": "Absorber Material Term Used",
        "absorber_dopant_material": "Absorber Dopant Material", "absorber_dopant_material_term_used": "Absorber Dopant Material Term Used",
        "absorber_dopant_polarity": "Absorber Dopant Polarity", "absorber_dopant_polarity_term_used": "Absorber Dopant Polarity Term Used",
        "front_surface_morphology": "Front Surface Morphology", "front_surface_morphology_term_used": "Front Surface Morphology Term Used",
        "rear_surface_morphology": "Rear Surface Morphology", "rear_surface_morphology_term_used": "Rear Surface Morphology Term Used",
        "front_surface_passivation_material": "Front Surface Passivation Material", "front_surface_passivation_material_term_used": "Front Surface Passivation Material Term Used",
        "rear_surface_passivation_material": "Rear Surface Passivation Material", "rear_surface_passivation_material_term_used": "Rear Surface Passivation Material Term Used",
        "negative_metallization_material": "Negative Metallization Material", "negative_metallization_material_term_used": "Negative Metallization Material Term Used",
        "positive_metallization_material": "Positive Metallization Material", "positive_metallization_material_term_used": "Positive Metallization Material Term Used",
        "efficiency_percent": "Efficiency (%)", "cell_area_cm2": "Cell Area (cm2)",
        "short_circuit_current_a": "Short-Circuit Current (A)", "short_circuit_current_density_ma_cm2": "Short-Circuit Current Density (mA/cm2)",
        "open_circuit_voltage_v": "Open-Circuit Voltage (V)", "fill_factor_percent": "Fill Factor (%)"
    }
    return (
        CHUNK_OVERLAP,
        CHUNK_SIZE,
        COLUMN_MAP,
        MODEL_NAME,
        OUTPUT_CSV,
        PDF_FOLDER,
        PROMPT_TEMPLATE,
    )


@app.cell
def _(BaseModel, Field, validator):
    # Specific schema written by Rhea for PV articles

    class PVArticleData(BaseModel):
        research_focus: str = Field("N/A")
        key_findings: str = Field("N/A")
        device_type: str = Field("N/A")
        absorber_material: str = Field("N/A")
        absorber_material_term_used: str = Field("N/A")
        absorber_dopant_material: str = Field("N/A")
        absorber_dopant_material_term_used: str = Field("N/A")
        absorber_dopant_polarity: str = Field("N/A")
        absorber_dopant_polarity_term_used: str = Field("N/A")
        front_surface_morphology: str = Field("N/A")
        front_surface_morphology_term_used: str = Field("N/A")
        rear_surface_morphology: str = Field("N/A")
        rear_surface_morphology_term_used: str = Field("N/A")
        front_surface_passivation_material: str = Field("N/A")
        front_surface_passivation_material_term_used: str = Field("N/A")
        rear_surface_passivation_material: str = Field("N/A")
        rear_surface_passivation_material_term_used: str = Field("N/A")
        negative_metallization_material: str = Field("N/A")
        negative_metallization_material_term_used: str = Field("N/A")
        positive_metallization_material: str = Field("N/A")
        positive_metallization_material_term_used: str = Field("N/A")
        efficiency_percent: str = Field("N/A")
        cell_area_cm2: str = Field("N/A")
        short_circuit_current_a: str = Field("N/A")
        short_circuit_current_density_ma_cm2: str = Field("N/A")
        open_circuit_voltage_v: str = Field("N/A")
        fill_factor_percent: str = Field("N/A")

        @validator("*", pre=True)
        def convert_to_string(cls, v):
            return "N/A" if v is None else str(v)
    return (PVArticleData,)


@app.cell
def _(PVArticleData, json):
    # Parser made to handle the response from the model and clean it up
    def clean_response_data(response_data):
        if isinstance(response_data, list):
            response_data = response_data[0] if response_data else {}
        if isinstance(response_data, PVArticleData):
            return response_data.model_dump()
        if isinstance(response_data, str):
            cleaned = response_data.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            try:
                parsed = json.loads(cleaned)
                return parsed[0] if isinstance(parsed, list) else parsed
            except json.JSONDecodeError:
                return {}
        if isinstance(response_data, dict):
            return response_data
        return {}
    return (clean_response_data,)


@app.function
def count_filled_fields(data: dict) -> int:
    return sum(1 for v in data.values() if v != "N/A")


@app.cell
def _(
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    COLUMN_MAP,
    ChatOllama,
    MODEL_NAME,
    OUTPUT_CSV,
    PDFMinerLoader,
    PDF_FOLDER,
    PROMPT_TEMPLATE,
    PVArticleData,
    PromptTemplate,
    PydanticOutputParser,
    RecursiveCharacterTextSplitter,
    clean_response_data,
    pd,
):
    from tqdm import tqdm

    def main():
        model = ChatOllama(model=MODEL_NAME)
        parser = PydanticOutputParser(pydantic_object=PVArticleData)
        prompt = PromptTemplate.from_template(PROMPT_TEMPLATE)
        chain = prompt | model | parser

        pdf_files = list(PDF_FOLDER.rglob("*.pdf"))
        results = []

        for pdf_file in tqdm(pdf_files, desc="Processing PDFs"):
            try:
                loader = PDFMinerLoader(str(pdf_file))
                docs = loader.load()
                full_text = "\n\n".join([doc.page_content for doc in docs])
                splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
                chunks = splitter.split_text(full_text)

                best_data = None
                highest_filled_count = 0
                for chunk in chunks:
                    try:
                        response = chain.invoke({
                            "text": chunk,
                            "format_instructions": parser.get_format_instructions()
                        })
                        cleaned_data = clean_response_data(response)
                        if cleaned_data:
                            filled_count = count_filled_fields(cleaned_data)
                            if filled_count > highest_filled_count:
                                highest_filled_count = filled_count
                                best_data = cleaned_data
                    except Exception:
                        continue

                if best_data:
                    article_data = PVArticleData(**best_data)
                    results.append(article_data.model_dump())
            except Exception:
                continue

        if results:
            df = pd.DataFrame(results)
            df = df.rename(columns=COLUMN_MAP)
            df = df[list(COLUMN_MAP.values())]
            df.to_csv(OUTPUT_CSV, index=False)
            print(f"\nSaved the CSV to {OUTPUT_CSV}")
        else:
            print("\nNo results to save.")

    return (main,)


@app.cell
def _(main):
    if __name__ == "__main__":
        main()
    return


if __name__ == "__main__":
    app.run()
