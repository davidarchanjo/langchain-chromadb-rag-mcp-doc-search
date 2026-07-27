from pydantic_settings import BaseSettings, SettingsConfigDict

# Configuration
class EnvironmentConfiguration(BaseSettings):
    DOCS_DIR: str
    CHROMA_DIR: str
    CHROMA_COLLECTION_NAME: str
    EMBEDDING_MODEL_NAME: str
    EMBEDDING_MODEL_BASE_URL: str
    CHUNK_SIZE: int
    CHUNK_OVERLAP: int
    LLM_API_KEY: str
    LLM_BASE_URL: str
    LLM_MODEL_NAME: str
    LLM_MODEL_PROVIDER: str
    LLM_TEMPERATURE: float
    MCP_SERVER_NAME: str
    MCP_SERVER_URL: str
    # Tell Pydantic to read from the `.env` file
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")