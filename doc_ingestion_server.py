"""
Document ingestion pipeline & server.

Start the server:
    uvicorn doc_ingestion_server:app --host 0.0.0.0 --port 3002

The ingestion pipeline is automatically executed once during server startup.

Upload new documents through:
    POST /documents
"""

import sys
import logging
import shutil
from config import EnvironmentConfiguration
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, UploadFile
from langchain_chroma import Chroma
from langchain_community.document_loaders import (
    CSVLoader,
    DirectoryLoader,
    TextLoader,
    PyPDFLoader
)
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pathlib import Path


# Allowed file extensions for ingestion
ALLOWED_FILE_EXTENSIONS = {".csv", ".txt", ".md", ".pdf"}


# Create environment configuration reference
config = EnvironmentConfiguration() # type: ignore


# Load Uvicorn logger reference
logger = logging.getLogger("uvicorn.error")


# Define global embeddings to be used to embed document chunks
embeddings = OpenAIEmbeddings(
    model=config.EMBEDDING_MODEL_NAME,
    base_url=config.EMBEDDING_MODEL_BASE_URL,
    check_embedding_ctx_length=False
)


def split_documents(loader: CSVLoader | TextLoader | PyPDFLoader | DirectoryLoader):
    """
    Load documents from the given loader and split them into overlapping chunks
    suitable for embedding.

    Returns an empty list if no documents are loaded.
    """
    documents = loader.load()
    if not documents:
        extensions = loader.glob if isinstance(loader.glob, str) else ', '.join(loader.glob) # type: ignore
        extensions = extensions.replace('**/*', '')
        logger.warning("No '%s' files found in '%s'.", extensions, loader.path) # type: ignore
        return []

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.CHUNK_SIZE,
        chunk_overlap=config.CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunks = text_splitter.split_documents(documents)
    logger.info("Loaded %d document(s) → %d chunk(s).", len(documents), len(chunks))
    return chunks


def embed_and_write(chunks):
    """
    Embed document chunks into embeddings and write them to ChromaDB
    """
    if len(chunks) == 0:
        logger.warning("Empty document chunks. Initializing empty ChromaDB collection.")
        Chroma(
            collection_name=config.CHROMA_COLLECTION_NAME,
            persist_directory=config.CHROMA_DIR,
            embedding_function=embeddings
        )
        return

    Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        collection_name=config.CHROMA_COLLECTION_NAME,
        persist_directory=config.CHROMA_DIR,
    )
    logger.info("Ingestion complete. %d chunks indexed into ChromaDB.", len(chunks))


def ingest():
    """
    Full ingestion pipeline: load → split → embed → store.
    ChromaDB persists the vector store to CHROMA_DIR so the server
    can load it on startup without re-indexing every time.
    """
    logger.info("Starting ingestion pipeline.")

    # Load and process text/markdown files
    loader = DirectoryLoader(
        config.DOCS_DIR,
        glob=["**/*.txt", "**/*.md"],
        loader_cls=TextLoader,
        loader_kwargs={"encoding": "utf-8"}
    )
    chunks = split_documents(loader)

    # Load and process CSV spreadsheets
    csv_loader = DirectoryLoader(
        config.DOCS_DIR,
        glob="**/*.csv",
        loader_cls=CSVLoader,
        loader_kwargs={"encoding": "utf-8"}
    )
    csv_chunks = split_documents(csv_loader)
    chunks.extend(csv_chunks)

    # Load and process PDF files
    pdf_loader = DirectoryLoader(
        config.DOCS_DIR,
        glob="**/*.pdf",
        loader_cls=PyPDFLoader # type: ignore
    )
    pdf_chunks = split_documents(pdf_loader)
    chunks.extend(pdf_chunks)

    # Write all gathered chunks at once
    embed_and_write(chunks)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Execute the ingestion pipeline once during application startup.
    """
    try:
        # ensures document directory exists before running the pipeline
        docs_dir = Path(config.DOCS_DIR)
        docs_dir.mkdir(parents=True, exist_ok=True)

        ingest()
        yield
    except Exception as e:
        logger.critical("Failed to initialize storage directory '%s': %s", config.DOCS_DIR, e)
        sys.exit(1)


# Define FastAPI app
app = FastAPI(
    title="Document Ingestion Server",
    lifespan=lifespan,
)


@app.post("/documents")
async def upload_document(file: UploadFile):
    """
    Process file upload, storage, and ingestion
    """

    logger.info("New document upload: '%s'.", file.filename)

    # Verify file eligibility for ingestion
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required.")
    extension = Path(file.filename).suffix.lower()
    if extension not in ALLOWED_FILE_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Only '{ALLOWED_FILE_EXTENSIONS}' files are supported.")    

    # Save file to DOCS_DIR
    destination = Path(config.DOCS_DIR) / file.filename
    with destination.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # Convert document in chunks and write them to ChromaDB
    try:
        if extension == ".csv":
          loader = CSVLoader(str(destination), encoding="utf-8")
        elif extension == ".pdf":
            loader = PyPDFLoader(str(destination))
        else:
            loader = TextLoader(str(destination), encoding="utf-8")
        chunks = split_documents(loader)
        embed_and_write(chunks)
    except Exception as e:
        logger.exception("Failed to process uploaded file '%s'.", file.filename)
        raise HTTPException(status_code=500, detail=f"File saved but ingestion failed: {e}")
    
    logger.info("Success document upload: '%s'.", destination.name)

    return {
        "message": "Document uploaded and ingested successfully.",
        "filename": file.filename,
    }