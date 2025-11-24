"""
dltHub integration for data transformations and loading.
"""

from typing import List, Dict, Any, Iterator
import dlt
from dlt.sources.helpers import requests
from loguru import logger
from django.conf import settings


class DltService:
    """
    Handles data transformations and loading using dltHub.
    """
    
    def __init__(self):
        self.pipeline_name = settings.DLT_PIPELINE_NAME
        self.dataset_name = settings.DLT_DATASET_NAME
        self.destination = self._get_destination()
        
        logger.info(f"Initialized DltService for pipeline: {self.pipeline_name}")
    
    def _get_destination(self):
        """Configure PostgreSQL destination."""
        # dlt will use DATABASE_URL from environment or .dlt/secrets.toml
        return dlt.destinations.postgres(
            credentials=settings.DATABASES['default']['NAME']
        )
    
    @dlt.resource(name="project_tasks", write_disposition="append")
    def transform_tasks(self, tasks: List[Dict[str, Any]], document_id: int) -> Iterator[Dict[str, Any]]:
        """
        Transform task data for loading into PostgreSQL.
        Adds document reference and validates data.
        """
        logger.info(f"Transforming {len(tasks)} tasks for document {document_id}")
        
        for task in tasks:
            # Add document reference
            task['document_id'] = document_id
            
            # Ensure required fields
            if not all(k in task for k in ['task_id', 'task_name', 'duration_days', 'start_date', 'finish_date']):
                logger.warning(f"Skipping invalid task: {task}")
                continue
            
            # Data type conversions
            task['task_id'] = int(task['task_id'])
            task['duration_days'] = int(task['duration_days'])
            
            # Ensure dates are strings in ISO format
            if not isinstance(task['start_date'], str):
                task['start_date'] = task['start_date'].isoformat()
            if not isinstance(task['finish_date'], str):
                task['finish_date'] = task['finish_date'].isoformat()
            
            yield task
    
    @dlt.resource(name="cost_items", write_disposition="append")
    def transform_cost_items(self, cost_items: List[Dict[str, Any]], document_id: int) -> Iterator[Dict[str, Any]]:
        """
        Transform cost item data for loading into PostgreSQL.
        """
        logger.info(f"Transforming {len(cost_items)} cost items for document {document_id}")
        
        for item in cost_items:
            # Add document reference
            item['document_id'] = document_id
            
            # Ensure required fields
            if not all(k in item for k in ['item_name', 'quantity', 'unit_price_yen', 'total_cost_yen']):
                logger.warning(f"Skipping invalid cost item: {item}")
                continue
            
            # Data type conversions and validation
            try:
                item['quantity'] = float(item['quantity'])
                item['unit_price_yen'] = float(item['unit_price_yen'])
                item['total_cost_yen'] = float(item['total_cost_yen'])
                
                # Ensure non-negative values
                if item['quantity'] < 0 or item['unit_price_yen'] < 0 or item['total_cost_yen'] < 0:
                    logger.warning(f"Skipping item with negative values: {item}")
                    continue
                
                # Set defaults
                if 'unit' not in item or not item['unit']:
                    item['unit'] = 'unit'
                
                if 'cost_type' not in item:
                    item['cost_type'] = 'other'
                
                yield item
                
            except (ValueError, TypeError) as e:
                logger.error(f"Error converting cost item values: {e}")
                continue
    
    @dlt.resource(name="document_chunks", write_disposition="append")
    def transform_chunks(
        self,
        chunks: List[Dict[str, Any]],
        document_id: int,
        chunk_ids: List[str]
    ) -> Iterator[Dict[str, Any]]:
        """
        Transform document chunks for PostgreSQL tracking.
        These will be linked to ChromaDB entries.
        """
        logger.info(f"Transforming {len(chunks)} chunks for document {document_id}")
        
        for idx, (chunk, chunk_id) in enumerate(zip(chunks, chunk_ids)):
            yield {
                'document_id': document_id,
                'chunk_id': chunk_id,
                'content': chunk['content'],
                'chunk_index': idx,
                'page_number': chunk.get('metadata', {}).get('page_number'),
                'metadata': chunk.get('metadata', {})
            }
    
    def load_tasks(self, tasks: List[Dict[str, Any]], document_id: int) -> Dict[str, Any]:
        """
        Load project tasks using dlt pipeline.
        """
        try:
            # Create pipeline
            pipeline = dlt.pipeline(
                pipeline_name=f"{self.pipeline_name}_tasks",
                destination=self.destination,
                dataset_name=self.dataset_name
            )
            
            # Run pipeline
            load_info = pipeline.run(
                self.transform_tasks(tasks, document_id),
                table_name="project_tasks"
            )
            
            logger.info(f"Loaded {len(tasks)} tasks successfully")
            return {
                'success': True,
                'records_loaded': len(tasks),
                'load_info': str(load_info)
            }
            
        except Exception as e:
            logger.error(f"Failed to load tasks: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def load_cost_items(self, cost_items: List[Dict[str, Any]], document_id: int) -> Dict[str, Any]:
        """
        Load cost items using dlt pipeline.
        """
        try:
            # Create pipeline
            pipeline = dlt.pipeline(
                pipeline_name=f"{self.pipeline_name}_costs",
                destination=self.destination,
                dataset_name=self.dataset_name
            )
            
            # Run pipeline
            load_info = pipeline.run(
                self.transform_cost_items(cost_items, document_id),
                table_name="cost_items"
            )
            
            logger.info(f"Loaded {len(cost_items)} cost items successfully")
            return {
                'success': True,
                'records_loaded': len(cost_items),
                'load_info': str(load_info)
            }
            
        except Exception as e:
            logger.error(f"Failed to load cost items: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def load_chunks_metadata(
        self,
        chunks: List[Dict[str, Any]],
        document_id: int,
        chunk_ids: List[str]
    ) -> Dict[str, Any]:
        """
        Load chunk metadata to PostgreSQL for tracking.
        The actual embeddings go to ChromaDB.
        """
        try:
            # Create pipeline
            pipeline = dlt.pipeline(
                pipeline_name=f"{self.pipeline_name}_chunks",
                destination=self.destination,
                dataset_name=self.dataset_name
            )
            
            # Run pipeline
            load_info = pipeline.run(
                self.transform_chunks(chunks, document_id, chunk_ids),
                table_name="document_chunks"
            )
            
            logger.info(f"Loaded {len(chunks)} chunk records successfully")
            return {
                'success': True,
                'records_loaded': len(chunks),
                'load_info': str(load_info)
            }
            
        except Exception as e:
            logger.error(f"Failed to load chunks: {e}")
            return {
                'success': False,
                'error': str(e)
            }


# Singleton instance
_dlt_service_instance = None


def get_dlt_service() -> DltService:
    """Get or create singleton DltService instance."""
    global _dlt_service_instance
    if _dlt_service_instance is None:
        _dlt_service_instance = DltService()
    return _dlt_service_instance