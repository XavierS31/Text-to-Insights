# -*- coding: utf-8 -*-
"""
Created on Sun May  4 08:43:44 2025

@author: Doing


Updated Thu June 12 03:30 2025 
@aamoghS
"""
import argparse
import os
from langchain.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaLLM

#Here I added argparse so that you can drop any filepath into the script and get it running. It will still default to "folder_PV".
#To test, run from the terminal python langchain_local.py --path /full/path/to/pdf_folder
parser = argparse.ArgumentParser(description="Process PDFS using LLM")
parser.add_argument(
    "--path", "-p",
    type=str,
    required=False,
    default="folder_PV",
    help="Path to folder containing PDF files"
)

args = parser.parse_args()
pdf_folder = args.path

if not os.path.isdir(pdf_folder):
    print(f"Error: '{pdf_folder}")
chunk_size = 1000
chunk_overlap = 100

llm = OllamaLLM(model="llama3.2:1b")
text_splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

for filename in os.listdir(pdf_folder):
    if filename.endswith(".pdf"):
        pdf_path = os.path.join(pdf_folder, filename)
        print(f"Processing: {pdf_path}")

        loader = PyPDFLoader(pdf_path)
        documents = loader.load()
        chunks = text_splitter.split_documents(documents)

        for i, chunk in enumerate(chunks):
            response = llm.invoke(chunk.page_content)
            print("Response:\n", response)
