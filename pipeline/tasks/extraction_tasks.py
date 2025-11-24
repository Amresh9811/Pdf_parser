"""
Prefect tasks for the data pipeline.
Each task represents a discrete unit of work with retry logic and logging.
"""

from typing import Dict, List, Any, Tuple
from pathlib import Path
from prefect import task
from prefect.tasks import task_input_hash
from datetime import timedelta
from loguru import logger
import django

# Setup Django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from pipeline.models import Document, ProjectTask, CostItem, DocumentChunk
from pipeline.extractors.schedule_extractor import ProjectScheduleExtractor
from pipeline.extractors.costing_extractor import CostingExtractor
from pipeline.services.vector_service import get_vector_service
from pipeline.services.dlt_service import get_dlt_service
from django.conf import settings


@task(
    name="validate_document",
    description="Validate that document exists and is accessible",
    retries=2,
    retry_delay_seconds=5,
    tags=["validation"]
)
def validate_document(file_path: str) -> Dict[str, Any]:
    """
    Validate document exists and get basic info.
    
    Returns:
        Dict with file_path, file_name, and exists status
    """
    logger.info(f"Validating document: {file_path}")
    
    path = Path(file_path)
    
    if not path.exists():
        raise FileNotFoundError(f"Document not found: {file_path}")
    
    if not path.suffix.lower() == '.pdf':
        raise ValueError(f"Only PDF files are supported: {file_path}")
    
    file_size = path.stat().st_size
    
    logger.info(f"Document validated: {path.name} ({file_size} bytes)")
    
    return {
        'file_path': str(path.absolute()),
        'file_name': path.name,
        'file_size': file_size,
        'exists': True
    }


@task(
    name="create_document_record",
    description="Create database record for document",
    retries=2,
    retry_delay_seconds=5,
    tags=["database"]
)
def create_document_record(file_info: Dict[str, Any], document_type: str) -> int:
    """
    Create Document record in database.
    
    Args:
        file_info: Dict with file_path and file_name
        document_type: Type of document (schedule, costing, etc.)
    
    Returns:
        Document ID
    """
    logger.info(f"Creating document record for {file_info['file_name']}")
    
    document = Document.objects.create(
        file_name=file_info['file_name'],
        file_path=file_info['file_path'],
        document_type=document_type,
        status='processing'
    )
    
    logger.info(f"Created document record with ID: {document.id}")
    return document.id


@task(
    name="extract_schedule_data",
    description="Extract structured data from project schedule document",
    retries=settings.MAX_RETRIES,
    retry_delay_seconds=settings.RETRY_DELAY_SECONDS,
    tags=["extraction", "schedule"],
    # cache_key_fn=task_input_hash,
    # cache_expiration=timedelta(hours=24)
)
def extract_schedule_data(file_path: str) -> Dict[str, Any]:
    """
    Extract tasks from project schedule PDF.
    
    Returns:
        Dict with 'tasks' list and extraction metadata
    """
    logger.info(f"Extracting schedule data from: {file_path}")
    
    try:
        extractor = ProjectScheduleExtractor(file_path)
        structured_data = extractor.extract_structured_data()
        
        logger.info(f"Extracted {len(structured_data['tasks'])} tasks")
        
        return {
            'success': True,
            'data': structured_data,
            'task_count': len(structured_data['tasks'])
        }
        
    except Exception as e:
        logger.error(f"Schedule extraction failed: {e}")
        return {
            'success': False,
            'error': str(e),
            'task_count': 0
        }


@task(
    name="extract_costing_data",
    description="Extract structured data from costing document",
    retries=settings.MAX_RETRIES,
    retry_delay_seconds=settings.RETRY_DELAY_SECONDS,
    tags=["extraction", "costing"],
    # cache_key_fn=task_input_hash,
    # cache_expiration=timedelta(hours=24)
)
def extract_costing_data(file_path: str) -> Dict[str, Any]:
    """
    Extract cost items from costing PDF.
    
    Returns:
        Dict with 'cost_items' list and extraction metadata
    """
    logger.info(f"Extracting costing data from: {file_path}")
    
    try:
        extractor = CostingExtractor(file_path)
        structured_data = extractor.extract_structured_data()
        
        logger.info(f"Extracted {len(structured_data['cost_items'])} cost items")
        
        return {
            'success': True,
            'data': structured_data,
            'cost_item_count': len(structured_data['cost_items'])
        }
        
    except Exception as e:
        logger.error(f"Costing extraction failed: {e}")
        return {
            'success': False,
            'error': str(e),
            'cost_item_count': 0
        }


@task(
    name="extract_semantic_chunks",
    description="Extract and chunk content for semantic search",
    retries=settings.MAX_RETRIES,
    retry_delay_seconds=settings.RETRY_DELAY_SECONDS,
    tags=["extraction", "semantic"],
    # cache_key_fn=task_input_hash,
    # cache_expiration=timedelta(hours=24)
)
def extract_semantic_chunks(file_path: str, document_type: str) -> Dict[str, Any]:
    """
    Extract content chunks for vector embedding.
    
    Args:
        file_path: Path to PDF
        document_type: Type of document (schedule or costing)
    
    Returns:
        Dict with chunks list
    """
    logger.info(f"Extracting semantic chunks from: {file_path}")
    
    try:
        # Select appropriate extractor
        if document_type == 'schedule':
            extractor = ProjectScheduleExtractor(file_path)
        elif document_type == 'costing':
            extractor = CostingExtractor(file_path)
        else:
            raise ValueError(f"Unknown document type: {document_type}")
        
        chunks = extractor.extract_for_semantic_search()
        
        logger.info(f"Extracted {len(chunks)} chunks")
        
        return {
            'success': True,
            'chunks': chunks,
            'chunk_count': len(chunks)
        }
        
    except Exception as e:
        logger.error(f"Semantic extraction failed: {e}")
        return {
            'success': False,
            'error': str(e),
            'chunk_count': 0
        }


@task(
    name="load_tasks_to_postgres",
    description="Load project tasks to PostgreSQL using dltHub",
    retries=2,
    retry_delay_seconds=10,
    tags=["loading", "postgres"]
)
def load_tasks_to_postgres(tasks: List[Dict[str, Any]], document_id: int) -> Dict[str, Any]:
    """
    Load tasks to PostgreSQL.
    
    Returns:
        Load statistics
    """
    logger.info(f"Loading {len(tasks)} tasks to PostgreSQL for document {document_id}")
    
    try:
        # Use Django ORM directly for reliability
        task_objects = []
        for task_data in tasks:
            # CHANGED: Handle None dates properly
            start_date = task_data.get('start_date')
            finish_date = task_data.get('finish_date')
            
            # Convert ISO string to date object if needed
            if start_date and isinstance(start_date, str):
                from datetime import datetime
                start_date = datetime.fromisoformat(start_date).date()
            
            if finish_date and isinstance(finish_date, str):
                from datetime import datetime
                finish_date = datetime.fromisoformat(finish_date).date()
            
            task_obj = ProjectTask(
                document_id=document_id,
                task_id=task_data['task_id'],
                task_name=task_data['task_name'],
                duration_days=task_data['duration_days'],
                start_date=start_date,  # Can be None now
                finish_date=finish_date  # Can be None now
            )
            task_objects.append(task_obj)
        
        # Bulk create
        ProjectTask.objects.bulk_create(task_objects)
        
        logger.info(f"Successfully loaded {len(task_objects)} tasks")
        
        return {
            'success': True,
            'records_loaded': len(task_objects)
        }
        
    except Exception as e:
        logger.error(f"Failed to load tasks: {e}")
        return {
            'success': False,
            'error': str(e),
            'records_loaded': 0
        }


@task(
    name="load_costs_to_postgres",
    description="Load cost items to PostgreSQL using dltHub",
    retries=2,
    retry_delay_seconds=10,
    tags=["loading", "postgres"]
)
def load_costs_to_postgres(cost_items: List[Dict[str, Any]], document_id: int) -> Dict[str, Any]:
    """
    Load cost items to PostgreSQL.
    
    Returns:
        Load statistics
    """
    logger.info(f"Loading {len(cost_items)} cost items to PostgreSQL for document {document_id}")
    
    try:
        # Use Django ORM
        cost_objects = []
        for item_data in cost_items:
            cost_obj = CostItem(
                document_id=document_id,
                item_name=item_data['item_name'],
                quantity=item_data['quantity'],
                unit=item_data.get('unit', 'unit'),
                unit_price_yen=item_data['unit_price_yen'],
                total_cost_yen=item_data['total_cost_yen'],
                cost_type=item_data.get('cost_type', 'other')
            )
            cost_objects.append(cost_obj)
        
        # Bulk create
        CostItem.objects.bulk_create(cost_objects)
        
        logger.info(f"Successfully loaded {len(cost_objects)} cost items")
        
        return {
            'success': True,
            'records_loaded': len(cost_objects)
        }
        
    except Exception as e:
        logger.error(f"Failed to load cost items: {e}")
        return {
            'success': False,
            'error': str(e),
            'records_loaded': 0
        }


@task(
    name="load_chunks_to_chromadb",
    description="Load document chunks to ChromaDB for semantic search",
    retries=2,
    retry_delay_seconds=10,
    tags=["loading", "chromadb"]
)
def load_chunks_to_chromadb(
    chunks: List[Dict[str, Any]],
    document_id: int
) -> Dict[str, Any]:
    """
    Load chunks to ChromaDB and create tracking records in PostgreSQL.
    
    Returns:
        Load statistics including chunk IDs
    """
    logger.info(f"Loading {len(chunks)} chunks to ChromaDB for document {document_id}")
    
    try:
        vector_service = get_vector_service()
        
        # Prepare data for ChromaDB
        documents = [chunk['content'] for chunk in chunks]
        metadatas = [chunk.get('metadata', {}) for chunk in chunks]
        
        # Add to ChromaDB (returns generated IDs)
        chunk_ids = vector_service.add_documents(documents, metadatas)
        
        # Create tracking records in PostgreSQL
        chunk_objects = []
        for idx, (chunk, chunk_id) in enumerate(zip(chunks, chunk_ids)):
            chunk_obj = DocumentChunk(
                document_id=document_id,
                chunk_id=chunk_id,
                content=chunk['content'],
                chunk_index=idx,
                metadata=chunk.get('metadata', {})
            )
            chunk_objects.append(chunk_obj)
        
        DocumentChunk.objects.bulk_create(chunk_objects)
        
        logger.info(f"Successfully loaded {len(chunk_ids)} chunks")
        
        return {
            'success': True,
            'records_loaded': len(chunk_ids),
            'chunk_ids': chunk_ids
        }
        
    except Exception as e:
        logger.error(f"Failed to load chunks: {e}")
        return {
            'success': False,
            'error': str(e),
            'records_loaded': 0
        }


@task(
    name="update_document_status",
    description="Update document processing status",
    retries=2,
    retry_delay_seconds=5,
    tags=["database"]
)
def update_document_status(
    document_id: int,
    status: str,
    error_message: str = None
) -> bool:
    """
    Update document status in database.
    
    Args:
        document_id: Document ID
        status: New status (completed, failed)
        error_message: Optional error message if failed
    
    Returns:
        Success boolean
    """
    try:
        from django.utils import timezone
        
        document = Document.objects.get(id=document_id)
        document.status = status
        
        if status == 'completed':
            document.processed_at = timezone.now()
        
        if error_message:
            document.error_message = error_message
        
        document.save()
        
        logger.info(f"Updated document {document_id} status to {status}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to update document status: {e}")
        return False


@task(
    name="notify_completion",
    description="Send notification on pipeline completion",
    tags=["notification"]
)
def notify_completion(document_name: str, stats: Dict[str, Any]) -> None:
    """
    Log completion notification.
    In production, this could send emails, Slack messages, etc.
    """
    logger.success(f"""
    ╔═══════════════════════════════════════╗
    ║   Pipeline Completed Successfully!   ║
    ╚═══════════════════════════════════════╝
    
    Document: {document_name}
    Tasks Extracted: {stats.get('tasks', 0)}
    Cost Items Extracted: {stats.get('cost_items', 0)}
    Chunks Created: {stats.get('chunks', 0)}
    """)


@task(
    name="notify_failure",
    description="Send notification on pipeline failure",
    tags=["notification"]
)
def notify_failure(document_name: str, error: str) -> None:
    """
    Log failure notification.
    """
    logger.error(f"""
    ╔═══════════════════════════════════════╗
    ║     Pipeline Failed!                  ║
    ╚═══════════════════════════════════════╝
    
    Document: {document_name}
    Error: {error}
    """)