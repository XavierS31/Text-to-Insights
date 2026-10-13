#small script to extract chunks, and create a csv and small pandas dataframe.

import os
import re
import json
import pandas as pd
from langchain_ollama import OllamaLLM
from langchain.output_parsers import StructuredOutputParser, ResponseSchema
from langchain.prompts import PromptTemplate

chunk_root = "chunks"

# Start the LLM
llm = OllamaLLM(model="llama3.2:1b")

# Create a sample schema for inital testing with structured output
response_schemas = [
    ResponseSchema(name="author", description="The primary author or list of authors of the paper"),
    ResponseSchema(name="publication_date", description="The date that the paper was published"),
    ResponseSchema(name="doi", description="The DOI (Digital Object Identifier) of the article"),
    ResponseSchema(name="material", description="The absorber or emitter material studied in the paper"),
    ResponseSchema(name="crystallinity", description="Whether the material is crystalline, amorphous, or another form"),
]

# Set up parser and format instructions 
parser = StructuredOutputParser.from_response_schemas(response_schemas)
format_instructions = parser.get_format_instructions()

# Sample prompt templete to see how model performs
# (This could be improved with possible results from team 1)
prompt= PromptTemplate(
    template=("Extract the following information from the scientific text: \n"
    "Author or Authors, Publication Date, Article DOI,  Absorber or Emitter Material, and Material Crystallinity.\n\n "
    "{format_instructions}\n\n"
    "Text:\n{chunk}"
    ),
    input_variables = ['chunk'],
    partial_variables={"format_instructions" : format_instructions},
    )      

results = []

# Go through all text chunks in subfolders
for dirpath, _, filenames in os.walk(chunk_root):
    for filename in filenames:
        if filename.endswith('.txt'):
            file_path = os.path.join(dirpath, filename)
            with open(file_path, "r", encoding="utf-8") as f:
                chunk_text = f.read()
            
            form_prompt = prompt.format(chunk=chunk_text)
            raw_output = llm.invoke(form_prompt)

            try:
                structured_data = parser.parse(raw_output)
            except Exception:
                try:
                    # Fallback: extract JSON block manually and strip comments
                    json_start = raw_output.find("{")
                    json_end = raw_output.rfind("}") + 1
                    json_str = raw_output[json_start:json_end]
                    json_str = re.sub(r"//.*", "", json_str)  # remove JS-style comments
                    structured_data = json.loads(json_str)
                except Exception as e:
                    print(f"\nFailed to parse {file_path}")
                    print(f"Raw Output:\n{raw_output}")
                    print(f"Error:\n{e}")
                    continue

if results:
    df = pd.DataFrame(results)
    print(df.head(20))

else:
    print("No data was extracted from the chunks")