import httpx
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from typing import List
from src.services.pdf_processor import PDFProcessor
from src.services.vector_store import VectorStore
from src.services.prompt_generator import PromptGenerator
from src.services.followup_generator import FollowUpGenerator
from src.services.meilisearch_client import MeilisearchClient
from src.services.claude_prompt_generator import ClaudePromptGenerator
from src.models.schemas import (
    IngestResponse, 
    PromptResponse,
    SearchRequest, 
    SearchResponse,
    EmbedderSetupResponse,
    FollowUpRequest,
    FollowUpResponse,
    V2PromptRequest,
    V2PromptResponse,
)

router = APIRouter()
router_v2 = APIRouter()
pdf_processor = PDFProcessor()
vector_store = VectorStore()
prompt_generator = PromptGenerator()
followup_generator = FollowUpGenerator()
meilisearch_client = MeilisearchClient()
claude_prompt_generator = None


@router.post("/ingest", response_model=IngestResponse)
async def ingest_pdfs(files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
    
    for file in files:
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(
                status_code=400,
                detail=f"File {file.filename} is not a PDF"
            )
    
    total_chunks = 0
    for file in files:
        content = await file.read()
        text = pdf_processor.extract_text(content)
        chunks = pdf_processor.chunk_text(text, file.filename)
        vector_store.add_documents(chunks)
        total_chunks += len(chunks)
    
    return IngestResponse(
        status="success",
        documents_processed=len(files),
        total_chunks=total_chunks
    )


@router.post("/prompts", response_model=PromptResponse)
async def generate_prompts():
    context = vector_store.get_context_summary()
    
    if not context:
        raise HTTPException(
            status_code=400,
            detail="No documents ingested. Please upload PDFs first."
        )
    
    result = prompt_generator.generate_templates(context)
    
    return PromptResponse(
        prompt=result["prompt"],
        placeholders=result["placeholders"],
        context_summary=context[:500]
    )


@router_v2.post("/prompts", response_model=V2PromptResponse)
async def generate_prompts_v2(request: V2PromptRequest):
    global claude_prompt_generator

    try:
        if claude_prompt_generator is None:
            claude_prompt_generator = ClaudePromptGenerator()
        prompts = claude_prompt_generator.generate(
            query=request.query,
            context=request.context,
            count=request.count,
        )
        return V2PromptResponse(prompt=prompts)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/prompts/follow-up", response_model=FollowUpResponse)
async def generate_follow_up_prompts(request: FollowUpRequest):
    if not request.prompt or not request.prompt.strip():
        raise HTTPException(
            status_code=400,
            detail="Prompt cannot be empty"
        )
    
    follow_up_queries = followup_generator.generate(request.prompt)
    
    return FollowUpResponse(
        original_prompt=request.prompt,
        follow_up_queries=follow_up_queries
    )


@router.post("/search", response_model=SearchResponse)
async def search_forms(request: SearchRequest):
    try:
        results = meilisearch_client.search(
            query=request.query,
            use_hybrid=request.use_hybrid,
            limit=request.limit,
            filters=request.filters
        )
        return SearchResponse(**results)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search/semantic", response_model=SearchResponse)
async def semantic_search_forms(request: SearchRequest):
    try:
        results = meilisearch_client.semantic_search(
            query=request.query,
            limit=request.limit,
            filters=request.filters
        )
        return SearchResponse(
            query=results["query"],
            hits=results["hits"],
            total_hits=results["total_hits"],
            processing_time_ms=results["processing_time_ms"],
            hybrid_enabled=True
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/embedder/setup", response_model=EmbedderSetupResponse)
async def setup_embedder():
    try:
        result = meilisearch_client.setup_embedder()
        return EmbedderSetupResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/embedder/status")
async def get_embedder_status():
    try:
        status = meilisearch_client.get_embedder_status()
        return {"embedders": status, "configured": len(status) > 0}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/embedder/task/{task_uid}")
async def check_task_status(task_uid: int):
    try:
        task = meilisearch_client.get_task(task_uid)
        return task
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class PdfFetchRequest(BaseModel):
    url: str
    filename: str = "document.pdf"


@router.post("/pdf/fetch")
async def fetch_pdf(request: PdfFetchRequest):
    """Server-side proxy to fetch a PDF from a remote URL, bypassing browser CORS."""
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            resp = await client.get(request.url)
            if resp.status_code != 200:
                raise HTTPException(
                    status_code=resp.status_code,
                    detail=f"Failed to fetch PDF from remote URL: {resp.status_code}",
                )
        return Response(
            content=resp.content,
            media_type=resp.headers.get("content-type", "application/pdf"),
            headers={"Content-Disposition": f'attachment; filename="{request.filename}"'},
        )
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Could not reach remote URL: {e}")
