"""Knowledge base API endpoints for ingestion, search, and management."""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status
from pydantic import BaseModel, Field

from ..core.tasks import search_knowledge_base
from ..pipelines.orchestrator import PipelineOrchestrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])

# Global job tracking
_active_jobs: Dict[str, Dict] = {}


class SearchRequest(BaseModel):
    """Request model for knowledge base search."""

    query: str = Field(..., description="Search query")
    category: Optional[str] = Field(None, description="Filter by category")
    limit: int = Field(5, ge=1, le=50, description="Number of results to return")


class SearchResponse(BaseModel):
    """Response model for knowledge base search."""

    query: str
    category_filter: Optional[str]
    results_count: int
    results: List[Dict]
    formatted_output: str


class IngestionRequest(BaseModel):
    """Request model for ingestion operations."""

    batch_date: Optional[str] = Field(
        None, description="Batch date (YYYY-MM-DD), defaults to today"
    )
    artifacts_path: str = Field("./artifacts", description="Path to artifacts directory")
    scrapers: Optional[List[str]] = Field(None, description="List of scrapers to run")
    operation: str = Field("ingest", description="Operation type: 'scrape', 'ingest', or 'full'")


class JobStatus(BaseModel):
    """Job status model."""

    job_id: str
    operation: str
    status: str  # queued, running, completed, failed
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    progress: Dict = Field(default_factory=dict)
    results: Optional[Dict] = None
    error: Optional[str] = None


class DocumentIngestionRequest(BaseModel):
    """Request model for single document ingestion."""

    title: str = Field(..., description="Document title")
    content: str = Field(..., description="Document content")
    source: str = Field(..., description="Source system or file")
    category: str = Field("general", description="Document category")
    severity: str = Field("info", description="Severity level")


class KnowledgeSettings(BaseModel):
    """Knowledge base ingestion settings."""

    chunk_size: int = Field(1000, ge=100, le=4000, description="Size of text chunks for processing")
    chunk_overlap: int = Field(200, ge=0, le=1000, description="Overlap between consecutive chunks")
    splitting_strategy: str = Field(
        "recursive", description="Text splitting strategy: recursive, semantic, or fixed"
    )
    embedding_model: str = Field(
        "sentence-transformers/all-MiniLM-L6-v2", description="Embedding model to use"
    )
    max_documents_per_batch: int = Field(
        100, ge=1, le=1000, description="Maximum documents to process in one batch"
    )
    enable_metadata_extraction: bool = Field(True, description="Extract metadata from documents")
    enable_semantic_chunking: bool = Field(
        False, description="Use semantic chunking instead of fixed-size"
    )
    similarity_threshold: float = Field(
        0.7, ge=0.0, le=1.0, description="Similarity threshold for semantic chunking"
    )
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def get_defaults(cls) -> "KnowledgeSettings":
        """Get default settings."""
        return cls()


class UpdateKnowledgeSettingsRequest(BaseModel):
    """Request model for updating knowledge settings."""

    chunk_size: Optional[int] = Field(
        None, ge=100, le=4000, description="Size of text chunks for processing"
    )
    chunk_overlap: Optional[int] = Field(
        None, ge=0, le=1000, description="Overlap between consecutive chunks"
    )
    splitting_strategy: Optional[str] = Field(
        None, description="Text splitting strategy: recursive, semantic, or fixed"
    )
    embedding_model: Optional[str] = Field(None, description="Embedding model to use")
    max_documents_per_batch: Optional[int] = Field(
        None, ge=1, le=1000, description="Maximum documents to process in one batch"
    )
    enable_metadata_extraction: Optional[bool] = Field(
        None, description="Extract metadata from documents"
    )
    enable_semantic_chunking: Optional[bool] = Field(
        None, description="Use semantic chunking instead of fixed-size"
    )
    similarity_threshold: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Similarity threshold for semantic chunking"
    )


# Using existing DocumentIngestionRequest model for real ingestion


@router.get("/search", response_model=SearchResponse)
async def search_knowledge(
    query: str = Query(..., description="Search query"),
    category: Optional[str] = Query(None, description="Filter by category"),
    product_labels: Optional[str] = Query(
        None, description="Comma-separated list of product labels to filter by"
    ),
    limit: int = Query(5, ge=1, le=50, description="Number of results to return"),
):
    """Search the knowledge base for relevant documents."""
    try:
        logger.info(f"Knowledge base search: {query}")

        # Validate query is not empty
        if not query or not query.strip():
            raise HTTPException(status_code=400, detail="Query parameter cannot be empty")

        # Parse product labels if provided
        parsed_product_labels = None
        if product_labels:
            parsed_product_labels = [
                label.strip() for label in product_labels.split(",") if label.strip()
            ]

        result = await search_knowledge_base(
            query, category=category, product_labels=parsed_product_labels, limit=limit
        )

        # Handle string, list, and dict responses
        if isinstance(result, str):
            # Parse the formatted output to extract results
            return SearchResponse(
                query=query,
                category_filter=category,
                results_count=0,  # Would need to parse from string
                results=[],
                formatted_output=result,
            )
        elif isinstance(result, list):
            # List format (direct results)
            return SearchResponse(
                query=query,
                category_filter=category,
                results_count=len(result),
                results=result,
                formatted_output="",
            )
        else:
            # Dict format
            return SearchResponse(
                query=result.get("query", query),
                category_filter=result.get("category_filter"),
                results_count=result.get("results_count", 0),
                results=result.get("results", []),
                formatted_output=result.get("formatted_output", ""),
            )

    except HTTPException:
        # Re-raise HTTP exceptions (like 400 validation errors)
        raise
    except Exception as e:
        logger.error(f"Knowledge search failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Search failed: {str(e)}"
        )


@router.post("/search", response_model=SearchResponse)
async def search_knowledge_post(request: SearchRequest):
    """Search the knowledge base using POST request."""
    return await search_knowledge(
        query=request.query, category=request.category, limit=request.limit
    )


@router.post("/ingest/document")
async def ingest_single_document(request: DocumentIngestionRequest):
    """Ingest a single document into the knowledge base."""
    try:
        from ..core.tasks import ingest_sre_document

        logger.info(f"Ingesting single document: {request.title}")

        result = await ingest_sre_document(
            title=request.title,
            content=request.content,
            source=request.source,
            category=request.category,
            severity=request.severity,
        )

        return {
            "success": True,
            "document_id": result.get("document_id"),
            "message": f"Document '{request.title}' ingested successfully",
        }

    except Exception as e:
        logger.error(f"Single document ingestion failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Document ingestion failed: {str(e)}",
        )


@router.post("/ingest/pipeline")
async def start_ingestion_pipeline(request: IngestionRequest, background_tasks: BackgroundTasks):
    """Start an ingestion pipeline job."""
    try:
        job_id = f"job_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')}"

        # Create job record
        job = {
            "job_id": job_id,
            "operation": request.operation,
            "status": "queued",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "started_at": None,
            "completed_at": None,
            "progress": {},
            "results": None,
            "error": None,
            "request": request.dict(),
        }

        _active_jobs[job_id] = job

        # Start background task
        background_tasks.add_task(
            _run_pipeline_job,
            job_id,
            request.operation,
            request.batch_date,
            request.artifacts_path,
            request.scrapers,
        )

        logger.info(f"Started ingestion job {job_id}")

        return {
            "job_id": job_id,
            "status": "queued",
            "message": f"Ingestion job started. Use GET /knowledge/jobs/{job_id} to check status.",
        }

    except Exception as e:
        logger.error(f"Failed to start ingestion job: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start ingestion job: {str(e)}",
        )


@router.get("/jobs", response_model=List[JobStatus])
async def list_jobs():
    """List all ingestion jobs."""
    jobs = []
    for job_data in _active_jobs.values():
        jobs.append(JobStatus(**job_data))

    # Sort by created_at descending
    jobs.sort(key=lambda x: x.created_at, reverse=True)
    return jobs


@router.get("/jobs/{job_id}", response_model=JobStatus)
async def get_job_status(job_id: str):
    """Get status of a specific ingestion job."""
    if job_id not in _active_jobs:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job {job_id} not found")

    job_data = _active_jobs[job_id]
    return JobStatus(**job_data)


@router.delete("/jobs/{job_id}")
async def cancel_job(job_id: str):
    """Cancel a running job (if possible) or remove from job list."""
    if job_id not in _active_jobs:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job {job_id} not found")

    job = _active_jobs[job_id]

    if job["status"] == "running":
        # For now, we can't actually cancel running jobs, but mark as cancelled
        job["status"] = "cancelled"
        job["completed_at"] = datetime.now(timezone.utc).isoformat()
        job["error"] = "Job cancelled by user"

    # Remove from active jobs
    del _active_jobs[job_id]

    return {"message": f"Job {job_id} cancelled/removed"}


async def _run_pipeline_job(
    job_id: str,
    operation: str,
    batch_date: Optional[str],
    artifacts_path: str,
    scrapers: Optional[List[str]],
):
    """Run a pipeline job in the background."""
    job = _active_jobs[job_id]

    try:
        job["status"] = "running"
        job["started_at"] = datetime.now(timezone.utc).isoformat()

        # Get current knowledge settings
        global _knowledge_settings
        if _knowledge_settings is None:
            _knowledge_settings = KnowledgeSettings.get_defaults()

        orchestrator = PipelineOrchestrator(artifacts_path, knowledge_settings=_knowledge_settings)

        if operation == "scrape":
            job["progress"]["stage"] = "scraping"
            results = await orchestrator.run_scraping_pipeline(scrapers)
        elif operation == "ingest":
            job["progress"]["stage"] = "ingesting"
            results = await orchestrator.run_ingestion_pipeline(batch_date)
        elif operation == "full":
            job["progress"]["stage"] = "full_pipeline"
            results = await orchestrator.run_full_pipeline(scrapers)
        else:
            raise ValueError(f"Unknown operation: {operation}")

        job["status"] = "completed"
        job["completed_at"] = datetime.now(timezone.utc).isoformat()
        job["results"] = results

        logger.info(f"Job {job_id} completed successfully")

    except Exception as e:
        job["status"] = "failed"
        job["completed_at"] = datetime.now(timezone.utc).isoformat()
        job["error"] = str(e)

        logger.error(f"Job {job_id} failed: {e}")


@router.post("/ingest/source-documents")
async def ingest_source_documents(background_tasks: BackgroundTasks):
    """Ingest documents from the source_documents directory."""
    try:
        job_id = f"source_docs_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')}"

        # Create job record
        job = {
            "job_id": job_id,
            "operation": "ingest_source_documents",
            "status": "queued",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "started_at": None,
            "completed_at": None,
            "progress": {},
            "results": None,
            "error": None,
            "request": {"source": "source_documents"},
        }

        _active_jobs[job_id] = job

        # Start background task
        background_tasks.add_task(_run_source_documents_ingestion, job_id)

        logger.info(f"Started source documents ingestion job {job_id}")

        return {
            "job_id": job_id,
            "status": "queued",
            "message": f"Source documents ingestion started. Use GET /knowledge/jobs/{job_id} to check status.",
        }

    except Exception as e:
        logger.error(f"Failed to start source documents ingestion: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start source documents ingestion: {str(e)}",
        )


async def _run_source_documents_ingestion(job_id: str):
    """Run source documents ingestion in the background."""
    job = _active_jobs[job_id]

    try:
        job["status"] = "running"
        job["started_at"] = datetime.now(timezone.utc).isoformat()
        job["progress"]["stage"] = "ingesting_source_documents"

        from ..pipelines.ingestion.processor import IngestionPipeline
        from ..pipelines.scraper.base import ArtifactStorage

        storage = ArtifactStorage("./artifacts")
        pipeline = IngestionPipeline(storage)

        results = await pipeline.ingest_source_documents(Path("source_documents"))

        job["status"] = "completed"
        job["completed_at"] = datetime.now(timezone.utc).isoformat()
        job["results"] = {
            "successful": [r for r in results if r["status"] == "success"],
            "failed": [r for r in results if r["status"] == "error"],
            "total_processed": len(results),
        }

        logger.info(f"Source documents ingestion job {job_id} completed successfully")

    except Exception as e:
        job["status"] = "failed"
        job["completed_at"] = datetime.now(timezone.utc).isoformat()
        job["error"] = str(e)

        logger.error(f"Source documents ingestion job {job_id} failed: {e}")


# Advanced ingestion endpoints removed - using existing real ingestion endpoint


@router.get("/stats")
async def get_knowledge_base_stats():
    """Get detailed knowledge base statistics from the real vector index."""
    try:
        from ..core.redis import get_knowledge_index

        # Get the real vector index
        index = get_knowledge_index()

        # Get accurate document and chunk counts
        try:
            from ..core.redis import get_redis_client

            # Get Redis client directly instead of relying on index.client
            redis_client = await get_redis_client()

            # Count total chunks (all entries in the index)
            chunks_result = await redis_client.execute_command(
                "FT.SEARCH",
                index.name,
                "*",  # Match all entries
                "LIMIT",
                "0",
                "0",  # Return 0 results, just get the total count
            )
            total_chunks = int(chunks_result[0]) if chunks_result else 0

            # Count unique documents using FT.AGGREGATE to count distinct document_hash values
            # This gives us the actual number of unique documents
            try:
                agg_result = await redis_client.execute_command(
                    "FT.AGGREGATE",
                    index.name,
                    "*",  # Match all entries
                    "GROUPBY",
                    "1",
                    "@document_hash",  # Group by document_hash field
                    "REDUCE",
                    "COUNT",
                    "0",
                    "AS",
                    "count",  # Count entries per group
                )

                # FT.AGGREGATE returns [total_groups, group1_data, group2_data, ...]
                # The first element is the number of unique document_hash values
                total_documents = int(agg_result[0]) if agg_result else 0

            except Exception as agg_error:
                logger.warning(f"Could not count unique documents via aggregation: {agg_error}")
                # Fallback: estimate documents from chunks (assuming 4 chunks per document)
                total_documents = max(1, total_chunks // 4) if total_chunks > 0 else 0

            # Calculate storage size based on actual chunk count
            storage_size_mb = total_chunks * 0.002  # ~2KB per chunk average

        except Exception as e:
            logger.warning(f"Could not get index info: {e}")
            total_documents = 0
            total_chunks = 0
            storage_size_mb = 0.0

        # Check ingestion status
        running_jobs = [j for j in _active_jobs.values() if j["status"] == "running"]
        ingestion_status = "running" if running_jobs else "idle"

        # Get last ingestion time
        last_ingestion = None
        completed_jobs = [j for j in _active_jobs.values() if j["status"] == "completed"]
        if completed_jobs:
            last_job = max(completed_jobs, key=lambda x: x.get("completed_at", ""))
            last_ingestion = last_job.get("completed_at")

        return {
            "total_documents": total_documents,
            "total_chunks": total_chunks,
            "last_ingestion": last_ingestion,
            "ingestion_status": ingestion_status,
            "document_types": {
                "general": total_documents  # Simplified - could be enhanced to track actual types
            },
            "storage_size_mb": storage_size_mb,
        }

    except Exception as e:
        logger.error(f"Failed to get knowledge base stats: {e}")
        return {
            "total_documents": 0,
            "total_chunks": 0,
            "last_ingestion": None,
            "ingestion_status": "error",
            "document_types": {},
            "storage_size_mb": 0.0,
        }


# Document management endpoints removed - using real search-based approach instead


# Global settings storage (in production, this would be in a database)
_knowledge_settings: Optional[KnowledgeSettings] = None


@router.get("/settings", response_model=KnowledgeSettings)
async def get_knowledge_settings():
    """Get current knowledge base settings."""
    global _knowledge_settings
    if _knowledge_settings is None:
        _knowledge_settings = KnowledgeSettings.get_defaults()
    return _knowledge_settings


@router.put("/settings", response_model=KnowledgeSettings)
async def update_knowledge_settings(
    settings: UpdateKnowledgeSettingsRequest, background_tasks: BackgroundTasks
):
    """Update knowledge base settings and optionally trigger re-ingestion."""
    global _knowledge_settings

    # Get current settings or defaults
    if _knowledge_settings is None:
        _knowledge_settings = KnowledgeSettings.get_defaults()

    # Update only provided fields
    update_data = settings.dict(exclude_unset=True)
    if update_data:
        # Create new settings with updated values
        current_data = _knowledge_settings.dict()
        current_data.update(update_data)
        current_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        _knowledge_settings = KnowledgeSettings(**current_data)

        logger.info(f"Knowledge settings updated: {update_data}")

        # Note: In a real implementation, you would:
        # 1. Save settings to database
        # 2. Trigger re-ingestion job with new settings
        # 3. Update any running processes

    return _knowledge_settings


@router.post("/settings/reset", response_model=KnowledgeSettings)
async def reset_knowledge_settings():
    """Reset knowledge base settings to defaults."""
    global _knowledge_settings
    _knowledge_settings = KnowledgeSettings.get_defaults()
    logger.info("Knowledge settings reset to defaults")
    return _knowledge_settings
