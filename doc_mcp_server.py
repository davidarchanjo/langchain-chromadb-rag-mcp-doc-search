"""
FastMCP ASGI server exposing a local document search service.

Start the server:
    uvicorn doc_mcp_server:app --host 0.0.0.0 --port 3001
"""
import warnings
warnings.filterwarnings("ignore")

import logging
from config import EnvironmentConfiguration
from pathlib import Path
from fastmcp import FastMCP
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from typing import Any

# Create environment configuration reference
config = EnvironmentConfiguration() # type: ignore

# Load Uvicorn logger reference
logger = logging.getLogger("uvicorn.error")

def create_app():
    """
    Application factory used to create the FastMCP app reference
    """
    
    embeddings = OpenAIEmbeddings(
        model=config.EMBEDDING_MODEL_NAME,
        base_url=config.EMBEDDING_MODEL_BASE_URL,
        check_embedding_ctx_length=False,
    )

    vector_store = Chroma(
        host="127.0.0.1",
        port=5000,
        collection_name=config.CHROMA_COLLECTION_NAME,
        embedding_function=embeddings,
    )    

    mcp = FastMCP(config.MCP_SERVER_NAME)

    @mcp.tool
    def search_documents(query: str) -> list[dict[str, Any]]:
        """
        Search the indexed knowledge base using semantic similarity.

        Use this tool whenever the user asks questions about documents,
        manuals, notes, Markdown files, text files, PDF files, CSV files,
        Microsoft Word files or any information contained in the indexed
        knowledge base.

        The returned content contains the most relevant document chunks
        found in the vector database.

        Args:
            query: The semantic search text or question.
        """

        logger.info("Executing tool: search_documents ['%s']", query)

        try:
            retriever = vector_store.as_retriever(search_kwargs={"k": 3})

            documents = retriever.invoke(query)

            return [
                {"metadata": doc.metadata, "content": doc.page_content}
                for doc in documents
            ] if documents else []
        except Exception as ex:
          logger.error("search_documents failed: %s", ex)
          return []

    @mcp.tool
    def list_documents() -> list[str]:
        """
        Return the names of every indexed document.

        Use this tool when the user asks which documents are available,
        what files have been indexed, or what knowledge sources exist.
        """

        logger.info("Executing tool: list_documents")

        data = vector_store.get(include=["metadatas"])

        sources = set()
        metadatas = data.get("metadatas") or []

        for metadata in metadatas:
            if metadata and "source" in metadata:
                source_name = Path(metadata["source"]).name
                sources.add(source_name)

        return sorted(sources)

    return mcp.http_app()

app = create_app()

# --- Entry Point ---
if __name__ == "__main__":
    print("🚀 starting Document MCP Server...")
    print("Access the documentation at: https://127.0.0.1:8000/docs")
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3001)