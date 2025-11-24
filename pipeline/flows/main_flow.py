"""
Main Prefect flow orchestrating the document processing pipeline.
"""

from typing import List, Dict, Any
from prefect import flow, get_run_logger
from prefect.task_runners import ConcurrentTaskRunner
from loguru import logger
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Import tasks
from pipeline.tasks.extraction_tasks import (
    validate_document,
    create_document_record,
    extract_schedule_data,
    extract_costing_data,
    extract_semantic_chunks,
    load_tasks_to_postgres,
    load_costs_to_postgres,
    load_chunks_to_chromadb,
    update_document_status,
    notify_completion,
    notify_failure
)


@flow(
    name="process_single_document",
    description="Process a single document through the entire pipeline",
    task_runner=ConcurrentTaskRunner(),
    retries=0,  # Handle retries at task level
    log_prints=True
)
def process_single_document(
    file_path: str,
    document_type: str
) -> Dict[str, Any]:
    """
    Process a single document through extraction, transformation, and loading.
    
    Args:
        file_path: Path to the PDF document
        document_type: Type of document ('schedule' or 'costing')
    
    Returns:
        Dict with processing results and statistics
    """
    run_logger = get_run_logger()
    run_logger.info(f"Starting pipeline for {file_path} (type: {document_type})")
    
    stats = {
        'tasks': 0,
        'cost_items': 0,
        'chunks': 0,
        'success': False
    }
    
    document_id = None
    
    try:
        # Step 1: Validate document
        file_info = validate_document(file_path)
        run_logger.info(f"✓ Validated document: {file_info['file_name']}")
        
        # Step 2: Create document record
        document_id = create_document_record(file_info, document_type)
        run_logger.info(f"✓ Created document record (ID: {document_id})")
        
        # Step 3: Extract structured data based on document type
        # Step 3: Extract structured data based on document type
        if document_type == 'schedule':
            extraction_result = extract_schedule_data(document_id, file_path)  # ✅ Pass document_id
            
            if extraction_result['success']:
                tasks = extraction_result['tasks']  # ✅ Changed from ['data']['tasks']
                stats['tasks'] = len(tasks)
                run_logger.info(f"✓ Extracted {len(tasks)} tasks")
                
                # Load to PostgreSQL
                # For schedule:
            if extraction_result['success']:
                tasks = extraction_result['tasks']
                stats['tasks'] = len(tasks)
                run_logger.info(f"✓ Extracted {len(tasks)} tasks")
                
                # Load to PostgreSQL - pass the whole extraction_result
                load_result = load_tasks_to_postgres(extraction_result)  # ✅ Pass entire dict
                if load_result['success']:
                    run_logger.info(f"✓ Loaded {load_result['records_loaded']} tasks to PostgreSQL")

        elif document_type == 'costing':
            extraction_result = extract_costing_data(document_id, file_path)  # ✅ Pass document_id
            
            if extraction_result['success']:
                cost_items = extraction_result['cost_items']  # ✅ Changed from ['data']['cost_items']
                stats['cost_items'] = len(cost_items)
                run_logger.info(f"✓ Extracted {len(cost_items)} cost items")
                
                # Load to PostgreSQL
                # For costing:
            elif document_type == 'costing':
                extraction_result = extract_costing_data(document_id, file_path)
                
                if extraction_result['success']:
                    cost_items = extraction_result['cost_items']
                    stats['cost_items'] = len(cost_items)
                    run_logger.info(f"✓ Extracted {len(cost_items)} cost items")
                    
                    # Load to PostgreSQL - pass the whole extraction_result
            load_result = load_costs_to_postgres(extraction_result)  # ✅ Pass entire dict
            if load_result['success']:
                run_logger.info(f"✓ Loaded {load_result['records_loaded']} cost items to PostgreSQL")
        # Step 4: Extract semantic chunks
        chunks_result = extract_semantic_chunks(document_id, file_path, document_type)
        
        if chunks_result['success']:
            chunks = chunks_result['chunks']
            stats['chunks'] = len(chunks)
            run_logger.info(f"✓ Extracted {len(chunks)} semantic chunks")
            
            # Load to ChromaDB
            vector_result = load_chunks_to_chromadb(chunks_result)  # Pass the whole result
            if vector_result['success']:
                run_logger.info(f"✓ Loaded {vector_result['records_loaded']} chunks to ChromaDB")
            else:
                raise Exception(f"Failed to load chunks: {vector_result.get('error')}")
        else:
            run_logger.warning(f"Semantic extraction had issues: {chunks_result.get('error')}")
        
        # Step 5: Update document status to completed
        update_document_status(document_id, 'completed')
        run_logger.info("✓ Updated document status to completed")
        
        # Step 6: Notify completion
        notify_completion(file_info['file_name'], stats)
        
        stats['success'] = True
        stats['document_id'] = document_id
        
        return stats
        
    except Exception as e:
        error_msg = str(e)
        run_logger.error(f"Pipeline failed: {error_msg}")
        
        # Update document status to failed
        if document_id:
            update_document_status(document_id, 'failed', error_msg)
        
        # Notify failure
        notify_failure(file_path, error_msg)
        
        stats['success'] = False
        stats['error'] = error_msg
        
        # Re-raise to mark flow as failed
        raise


@flow(
    name="process_multiple_documents",
    description="Process multiple documents in parallel",
    task_runner=ConcurrentTaskRunner(),
    log_prints=True
)
def process_multiple_documents(
    documents: List[Dict[str, str]]
) -> Dict[str, Any]:
    """
    Process multiple documents in parallel.
    
    Args:
        documents: List of dicts with 'file_path' and 'document_type'
    
    Returns:
        Dict with overall statistics
    """
    run_logger = get_run_logger()
    run_logger.info(f"Starting batch processing of {len(documents)} documents")
    
    results = []
    overall_stats = {
        'total_documents': len(documents),
        'successful': 0,
        'failed': 0,
        'total_tasks': 0,
        'total_cost_items': 0,
        'total_chunks': 0
    }
    
    # Process documents (Prefect will handle parallelization based on task runner)
    for doc in documents:
        try:
            result = process_single_document(
                file_path=doc['file_path'],
                document_type=doc['document_type']
            )
            
            results.append(result)
            
            if result['success']:
                overall_stats['successful'] += 1
                overall_stats['total_tasks'] += result.get('tasks', 0)
                overall_stats['total_cost_items'] += result.get('cost_items', 0)
                overall_stats['total_chunks'] += result.get('chunks', 0)
            else:
                overall_stats['failed'] += 1
                
        except Exception as e:
            run_logger.error(f"Failed to process {doc['file_path']}: {e}")
            overall_stats['failed'] += 1
    
    run_logger.info(f"""
    ╔═══════════════════════════════════════════════╗
    ║   Batch Processing Complete                   ║
    ╚═══════════════════════════════════════════════╝
    
    Total Documents: {overall_stats['total_documents']}
    Successful: {overall_stats['successful']}
    Failed: {overall_stats['failed']}
    
    Total Tasks Extracted: {overall_stats['total_tasks']}
    Total Cost Items Extracted: {overall_stats['total_cost_items']}
    Total Chunks Created: {overall_stats['total_chunks']}
    """)
    
    return overall_stats


@flow(
    name="main_pipeline",
    description="Main entry point for the contextualizer pipeline",
    log_prints=True
)
def main_pipeline(
    document_paths: List[str] = None,
    document_types: List[str] = None
) -> Dict[str, Any]:
    """
    Main pipeline entry point.
    
    Args:
        document_paths: List of paths to documents
        document_types: List of document types corresponding to paths
    
    Returns:
        Processing results
    """
    run_logger = get_run_logger()
    
    if not document_paths:
        # Use default sample documents for testing
        from django.conf import settings
        docs_path = Path(settings.DOCUMENTS_PATH)
        
        document_paths = [
            str(docs_path / "schedule.pdf"),
            str(docs_path / "costing.pdf")
        ]
        document_types = ['schedule', 'costing']
        
        run_logger.info("Using default sample documents")
    
    if not document_types:
        # Infer types from filenames if not provided
        document_types = []
        for path in document_paths:
            if 'schedule' in path.lower():
                document_types.append('schedule')
            elif 'cost' in path.lower():
                document_types.append('costing')
            else:
                document_types.append('schedule')  # default
    
    # Prepare documents list
    documents = [
        {'file_path': path, 'document_type': doc_type}
        for path, doc_type in zip(document_paths, document_types)
    ]
    
    run_logger.info(f"Processing {len(documents)} documents")
    
    # Process documents
    if len(documents) == 1:
        # Single document flow
        return process_single_document(
            file_path=documents[0]['file_path'],
            document_type=documents[0]['document_type']
        )
    else:
        # Batch processing flow
        return process_multiple_documents(documents)


if __name__ == "__main__":
    """
    Run the pipeline directly for testing.
    """
    import os
    import django
    
    # Setup Django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    django.setup()
    
    # Configure logging
    from loguru import logger
    logger.add(
        "logs/pipeline_{time}.log",
        rotation="500 MB",
        retention="10 days",
        level="INFO"
    )
    
    # Run pipeline
    result = main_pipeline()
    
    if result.get('success', False):
        logger.success("Pipeline completed successfully!")
    else:
        logger.error("Pipeline failed!")