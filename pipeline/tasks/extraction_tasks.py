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


@task(name="extract_schedule_data", retries=3, retry_delay_seconds=5)
def extract_schedule_data(document_id: int, file_path: str) -> Dict[str, Any]:
    """Extract schedule data from document."""
    try:
        logger.info(f"Extracting schedule data from: {file_path}")
        
        from pipeline.extractors.schedule_extractor import ProjectScheduleExtractor
        
        extractor = ProjectScheduleExtractor(file_path)
        result = extractor.extract_structured_data()
        
        # Handle both dict and list returns
        if isinstance(result, dict):
            tasks = result.get('tasks', [])
        elif isinstance(result, list):
            tasks = result  # ✅ Direct list
        else:
            tasks = []
        
        logger.info(f"Successfully extracted {len(tasks)} tasks")
        
        return {
            'success': True,
            'tasks': tasks,
            'document_id': document_id
        }
        
    except Exception as e:
        logger.error(f"Schedule extraction failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        
        return {
            'success': False,
            'tasks': [],
            'error': str(e),
            'document_id': document_id
        }
    

@task(name="extract_costing_data", retries=3, retry_delay_seconds=5)
def extract_costing_data(document_id: int, file_path: str) -> Dict[str, Any]:
    """Extract costing data from document."""
    try:
        logger.info(f"Extracting costing data from: {file_path}")
        
        from pipeline.extractors.costing_extractor import CostingExtractor
        
        extractor = CostingExtractor(file_path)
        result = extractor.extract_structured_data()
        
        # Handle both dict and list returns
        if isinstance(result, dict):
            cost_items = result.get('cost_items', [])
        elif isinstance(result, list):
            cost_items = result  # ✅ Direct list
        else:
            cost_items = []
        
        logger.info(f"Successfully extracted {len(cost_items)} cost items")
        
        return {
            'success': True,
            'cost_items': cost_items,
            'document_id': document_id
        }
        
    except Exception as e:
        logger.error(f"Costing extraction failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        
        return {
            'success': False,
            'cost_items': [],
            'error': str(e),
            'document_id': document_id
        }

@task(name="extract_semantic_chunks")
def extract_semantic_chunks(document_id: int, file_path: str, document_type: str) -> dict:
    """Extract semantic chunks from document."""
    try:
        logger.info(f"Extracting semantic chunks from: {file_path}")
        
        # Import appropriate extractor
        if document_type == 'schedule':
            from pipeline.extractors.schedule_extractor import ProjectScheduleExtractor
            extractor = ProjectScheduleExtractor(file_path)
        elif document_type == 'costing':
            from pipeline.extractors.costing_extractor import CostingExtractor
            extractor = CostingExtractor(file_path)
        else:
            raise ValueError(f"Unknown document type: {document_type}")
        
        chunks = extractor.extract_for_semantic_search()
        
        logger.info(f"Successfully extracted {len(chunks)} chunks")
        
        return {
            'success': True,
            'chunks': chunks,
            'document_id': document_id
        }
        
    except Exception as e:
        logger.error(f"Semantic chunk extraction failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        
        return {
            'success': False,
            'chunks': [],
            'error': str(e),
            'document_id': document_id
        }

@task(name="load_tasks_to_postgres")
def load_tasks_to_postgres(extraction_result: dict) -> dict:
    """Load project tasks to PostgreSQL."""
    try:
        tasks = extraction_result.get('tasks', [])
        document_id = extraction_result.get('document_id')
        
        if not tasks:
            logger.info("No tasks to load")
            return {'success': True, 'records_loaded': 0}  # ✅ Changed 'loaded' to 'records_loaded'
        
        logger.info(f"Loading {len(tasks)} tasks to PostgreSQL")
        
        from pipeline.models import ProjectTask, Document
        
        # Get document
        document = Document.objects.get(id=document_id)
        
        # Create tasks
        loaded_count = 0
        for task_data in tasks:
            try:
                # Parse dates - handle None values
                start_date = None
                if task_data.get('start_date'):
                    from datetime import datetime
                    start_date = datetime.fromisoformat(task_data['start_date']).date()
                
                finish_date = None
                if task_data.get('finish_date'):
                    from datetime import datetime
                    finish_date = datetime.fromisoformat(task_data['finish_date']).date()
                
                ProjectTask.objects.create(
                    document=document,
                    task_id=task_data['task_id'],
                    task_name=task_data['task_name'],
                    duration_days=task_data.get('duration_days', 0),
                    start_date=start_date,
                    finish_date=finish_date
                )
                loaded_count += 1
            except Exception as e:
                logger.error(f"Error creating task: {e}")
                logger.error(f"Task data: {task_data}")
                continue
        
        logger.info(f"Successfully loaded {loaded_count} tasks")
        
        return {
            'success': True,
            'records_loaded': loaded_count  # ✅ Changed 'loaded' to 'records_loaded'
        }
        
    except Exception as e:
        logger.error(f"Failed to load tasks to PostgreSQL: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            'success': False,
            'records_loaded': 0,  # ✅ Changed 'loaded' to 'records_loaded'
            'error': str(e)
        }


@task(name="load_costs_to_postgres")
@task(name="load_costs_to_postgres")
def load_costs_to_postgres(extraction_result: dict) -> dict:
    """Load cost items to PostgreSQL."""
    try:
        cost_items = extraction_result.get('cost_items', [])
        document_id = extraction_result.get('document_id')
        
        if not cost_items:
            logger.info("No cost items to load")
            return {'success': True, 'records_loaded': 0}  # ✅ Changed 'loaded' to 'records_loaded'
        
        logger.info(f"Loading {len(cost_items)} cost items to PostgreSQL")
        
        from pipeline.models import CostItem, Document
        
        # Get document
        document = Document.objects.get(id=document_id)
        
        # Create cost items
        loaded_count = 0
        for item_data in cost_items:
            try:
                CostItem.objects.create(
                    document=document,
                    item_name=item_data['item_name'],
                    quantity=item_data.get('quantity', 1.0),
                    unit=item_data.get('unit', 'unit'),
                    unit_price_yen=item_data['unit_price_yen'],
                    total_cost_yen=item_data['total_cost_yen'],
                    cost_type=item_data.get('cost_type', 'other')
                )
                loaded_count += 1
            except Exception as e:
                logger.error(f"Error creating cost item: {e}")
                logger.error(f"Item data: {item_data}")
                continue
        
        logger.info(f"Successfully loaded {loaded_count} cost items")
        
        return {
            'success': True,
            'records_loaded': loaded_count  # ✅ Changed 'loaded' to 'records_loaded'
        }
        
    except Exception as e:
        logger.error(f"Failed to load costs to PostgreSQL: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            'success': False,
            'records_loaded': 0,  # ✅ Changed 'loaded' to 'records_loaded'
            'error': str(e)
        }
        
    except Exception as e:
        logger.error(f"Failed to load costs to PostgreSQL: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            'success': False,
            'error': str(e)
        }


@task(name="load_chunks_to_chromadb")
def load_chunks_to_chromadb(chunks_result: dict) -> dict:
    """Load document chunks to ChromaDB."""
    try:
        chunks = chunks_result.get('chunks', [])
        document_id = chunks_result.get('document_id')
        
        if not chunks:
            logger.info("No chunks to load")
            return {'success': True, 'records_loaded': 0}
        
        logger.info(f"Loading {len(chunks)} chunks to ChromaDB")
        
        from pipeline.services.vector_service import get_vector_service
        from pipeline.models import DocumentChunk, Document
        
        vector_service = get_vector_service()
        
        # Get document
        document = Document.objects.get(id=document_id)
        
        # Prepare data for ChromaDB
        documents = []
        metadatas = []
        ids = []
        
        for idx, chunk in enumerate(chunks):
            chunk_id = f"{document.file_name}_{idx}"
            
            # Access the content - handle both 'content' and 'text' keys
            content = chunk.get('content') or chunk.get('text', '')
            
            if not content:
                logger.warning(f"Chunk {idx} has no content, skipping")
                continue
            
            documents.append(content)
            metadatas.append(chunk.get('metadata', {}))
            ids.append(chunk_id)
            
            # Create tracking record in PostgreSQL
            DocumentChunk.objects.create(
                document=document,
                chunk_id=chunk_id,
                content=content[:1000],  # Store first 1000 chars
                chunk_index=idx,
                metadata=chunk.get('metadata', {})
            )
        
        # Add to ChromaDB
        if documents:
            vector_service.add_documents(
                documents=documents,
                metadatas=metadatas,
                ids=ids
            )
        
        logger.info(f"Successfully loaded {len(documents)} chunks")
        
        return {
            'success': True,
            'records_loaded': len(documents)
        }
        
    except Exception as e:
        logger.error(f"Failed to load chunks: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            'success': False,
            'records_loaded': 0,
            'error': str(e)
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