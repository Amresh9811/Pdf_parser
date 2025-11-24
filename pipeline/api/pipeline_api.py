"""
Django Ninja API for pipeline control and management.
"""

from typing import List, Optional
from ninja import Router, Schema
from ninja_extra import NinjaExtraAPI
from django.shortcuts import get_object_or_404
from loguru import logger
import asyncio
from pathlib import Path

from pipeline.models import Document, PipelineRun, ProjectTask, CostItem, DocumentChunk
from pipeline.flows.main_flow import main_pipeline, process_single_document
from django.utils import timezone


router = Router(tags=["Pipeline"])


# Schemas
class DocumentInput(Schema):
    file_path: str
    document_type: str  # 'schedule' or 'costing'


class PipelineTriggerRequest(Schema):
    document_paths: List[str]
    document_types: Optional[List[str]] = None


class PipelineTriggerResponse(Schema):
    run_id: str
    status: str
    message: str


class PipelineStatusResponse(Schema):
    run_id: str
    status: str
    documents_processed: int
    tasks_extracted: int
    cost_items_extracted: int
    chunks_created: int
    started_at: str
    completed_at: Optional[str]
    duration_seconds: Optional[float]
    error_log: Optional[str]


class DocumentResponse(Schema):
    id: int
    file_name: str
    document_type: str
    status: str
    created_at: str
    processed_at: Optional[str]
    task_count: int
    cost_item_count: int
    chunk_count: int


@router.post("/trigger", response=PipelineTriggerResponse)
def trigger_pipeline(request, payload: PipelineTriggerRequest):
    """
    Trigger the data pipeline for document processing.
    
    This endpoint accepts a list of document paths and triggers
    the Prefect flow for processing them.
    """
    try:
        logger.info(f"API: Triggering pipeline for {len(payload.document_paths)} documents")
        
        # Create pipeline run record
        run = PipelineRun.objects.create(
            run_id=f"run_{timezone.now().strftime('%Y%m%d_%H%M%S')}",
            status='started'
        )
        
        # Trigger the Prefect flow asynchronously
        # In production, this would be submitted to a Prefect deployment
        try:
            result = main_pipeline(
                document_paths=payload.document_paths,
                document_types=payload.document_types
            )
            
            # Update run record
            run.status = 'completed' if result.get('success', False) else 'failed'
            run.completed_at = timezone.now()
            run.documents_processed = len(payload.document_paths)
            
            if 'tasks' in result:
                run.tasks_extracted = result['tasks']
            if 'cost_items' in result:
                run.cost_items_extracted = result['cost_items']
            if 'chunks' in result:
                run.chunks_created = result['chunks']
            
            if 'error' in result:
                run.error_log = result['error']
            
            run.save()
            
            return PipelineTriggerResponse(
                run_id=run.run_id,
                status=run.status,
                message="Pipeline executed successfully" if result.get('success') else "Pipeline failed"
            )
            
        except Exception as e:
            logger.error(f"Pipeline execution failed: {e}")
            run.status = 'failed'
            run.error_log = str(e)
            run.completed_at = timezone.now()
            run.save()
            
            return PipelineTriggerResponse(
                run_id=run.run_id,
                status='failed',
                message=f"Pipeline failed: {str(e)}"
            )
            
    except Exception as e:
        logger.error(f"Failed to trigger pipeline: {e}")
        return PipelineTriggerResponse(
            run_id="",
            status="error",
            message=f"Failed to trigger pipeline: {str(e)}"
        )


@router.get("/status/{run_id}", response=PipelineStatusResponse)
def get_pipeline_status(request, run_id: str):
    """
    Get the status of a pipeline run.
    """
    run = get_object_or_404(PipelineRun, run_id=run_id)
    
    return PipelineStatusResponse(
        run_id=run.run_id,
        status=run.status,
        documents_processed=run.documents_processed,
        tasks_extracted=run.tasks_extracted,
        cost_items_extracted=run.cost_items_extracted,
        chunks_created=run.chunks_created,
        started_at=run.started_at.isoformat(),
        completed_at=run.completed_at.isoformat() if run.completed_at else None,
        duration_seconds=run.duration_seconds,
        error_log=run.error_log
    )


@router.get("/runs", response=List[PipelineStatusResponse])
def list_pipeline_runs(request, limit: int = 10):
    """
    List recent pipeline runs.
    """
    runs = PipelineRun.objects.all()[:limit]
    
    return [
        PipelineStatusResponse(
            run_id=run.run_id,
            status=run.status,
            documents_processed=run.documents_processed,
            tasks_extracted=run.tasks_extracted,
            cost_items_extracted=run.cost_items_extracted,
            chunks_created=run.chunks_created,
            started_at=run.started_at.isoformat(),
            completed_at=run.completed_at.isoformat() if run.completed_at else None,
            duration_seconds=run.duration_seconds,
            error_log=run.error_log
        )
        for run in runs
    ]


@router.get("/documents", response=List[DocumentResponse])
def list_documents(request, status: Optional[str] = None, limit: int = 20):
    """
    List processed documents with statistics.
    """
    queryset = Document.objects.all()
    
    if status:
        queryset = queryset.filter(status=status)
    
    queryset = queryset[:limit]
    
    return [
        DocumentResponse(
            id=doc.id,
            file_name=doc.file_name,
            document_type=doc.document_type,
            status=doc.status,
            created_at=doc.created_at.isoformat(),
            processed_at=doc.processed_at.isoformat() if doc.processed_at else None,
            task_count=doc.tasks.count(),
            cost_item_count=doc.cost_items.count(),
            chunk_count=doc.chunks.count()
        )
        for doc in queryset
    ]


@router.get("/documents/{document_id}", response=DocumentResponse)
def get_document_details(request, document_id: int):
    """
    Get detailed information about a processed document.
    """
    doc = get_object_or_404(Document, id=document_id)
    
    return DocumentResponse(
        id=doc.id,
        file_name=doc.file_name,
        document_type=doc.document_type,
        status=doc.status,
        created_at=doc.created_at.isoformat(),
        processed_at=doc.processed_at.isoformat() if doc.processed_at else None,
        task_count=doc.tasks.count(),
        cost_item_count=doc.cost_items.count(),
        chunk_count=doc.chunks.count()
    )


@router.post("/reprocess/{document_id}")
def reprocess_document(request, document_id: int):
    """
    Reprocess a specific document.
    """
    doc = get_object_or_404(Document, id=document_id)
    
    try:
        # Trigger reprocessing
        result = process_single_document(
            file_path=doc.file_path,
            document_type=doc.document_type
        )
        
        return {
            "success": True,
            "message": f"Document {doc.file_name} reprocessed successfully",
            "result": result
        }
        
    except Exception as e:
        logger.error(f"Reprocessing failed: {e}")
        return {
            "success": False,
            "message": f"Reprocessing failed: {str(e)}"
        }


@router.get("/health")
def health_check(request):
    """
    Health check endpoint.
    """
    try:
        # Check database connection
        Document.objects.count()
        
        # Check ChromaDB
        from pipeline.services.vector_service import get_vector_service
        vector_service = get_vector_service()
        stats = vector_service.get_collection_stats()
        
        return {
            "status": "healthy",
            "database": "connected",
            "chromadb": "connected",
            "vector_documents": stats.get('document_count', 0)
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }