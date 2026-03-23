from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 8765
    debug: bool = False
    chroma_path: str = "./data/chroma_db"
    meilisearch_host: str = "http://localhost:7700"
    meilisearch_api_key: str = ""
    meilisearch_index: str = "form"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-haiku-latest"

    class Config:
        env_file = ".env"


settings = Settings()

