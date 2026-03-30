import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import router, router_v2
from src.api.template_routes import router as template_router
from src.config.settings import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Push updated filterable/sortable settings to Meilisearch on every startup.
    # This is a fire-and-forget task (Meilisearch processes it async).
    try:
        from src.services.template_search import TemplateSearchService
        svc = TemplateSearchService()
        svc.configure_index()
        svc.setup_embedder_if_needed()
    except Exception as e:
        logger.warning("Meilisearch setup skipped: %s", e)
    yield


app = FastAPI(
    title="PDF Prompt Agent",
    description="AI-powered prompt template generator based on PDF content",
    version="1.0.0",
    lifespan=lifespan,
)

# Allow all CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")
app.include_router(router_v2, prefix="/api/v2")
app.include_router(template_router, prefix="/form-templates/api")


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
