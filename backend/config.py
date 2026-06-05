from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    # ── MySQL ──────────────────────────────────────────────
    MYSQL_URL: str = "mysql+aiomysql://aries_user:aries_pass@localhost:3306/aries_db"

    # ── ArangoDB ──────────────────────────────────────────
    ARANGO_URL: str = "http://localhost:8529"
    ARANGO_DB: str = "aries_graph"
    ARANGO_USER: str = "root"
    ARANGO_PASSWORD: str = "arangoroot"

    # ── ChromaDB ──────────────────────────────────────────
    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8001
    CHROMA_POLICY_COLLECTION: str = "policy_documents"
    CHROMA_PROSPECT_COLLECTION: str = "prospect_contexts"
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"

    # ── Mistral LLM ────────────────────────────────────────
    MISTRAL_API_KEY: str = ""
    MISTRAL_MODEL: str = "mistral-small-latest"
    MISTRAL_MAX_TOKENS: int = 1024
    MISTRAL_TEMPERATURE: float = 0.3

    # ── App ────────────────────────────────────────────────
    APP_TITLE: str = "ARIES API"
    APP_VERSION: str = "2.1.0"
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"
    UPLOAD_DIR: str = "./uploads"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",")]


@lru_cache
def get_settings() -> Settings:
    return Settings()
