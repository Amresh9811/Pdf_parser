"""
Management command to reset ChromaDB collection.
"""

from django.core.management.base import BaseCommand
from pipeline.services.vector_service import get_vector_service
from loguru import logger
import os


class Command(BaseCommand):
    help = 'Reset ChromaDB collection'

    def handle(self, *args, **options):
        self.stdout.write('Resetting ChromaDB collection...')
        
        try:
            # Force new instance
            import pipeline.services.vector_service as vs
            vs._vector_service_instance = None
            
            vector_service = get_vector_service()
            
            # Delete collection
            try:
                vector_service.client.delete_collection(
                    name=vector_service.collection_name
                )
                self.stdout.write(self.style.SUCCESS(f'Deleted collection: {vector_service.collection_name}'))
            except:
                self.stdout.write('No existing collection to delete')
            
            # Recreate collection
            from chromadb.utils import embedding_functions
            openai_api_key = os.getenv('OPENAI_API_KEY')
            
            if openai_api_key:
                embedding_function = embedding_functions.OpenAIEmbeddingFunction(
                    api_key=openai_api_key,
                    model_name="text-embedding-3-small"
                )
            else:
                embedding_function = embedding_functions.DefaultEmbeddingFunction()
            
            vector_service.collection = vector_service.client.create_collection(
                name=vector_service.collection_name,
                embedding_function=embedding_function,
                metadata={"description": "Construction documents for AI context"}
            )
            
            self.stdout.write(self.style.SUCCESS(f'Created fresh collection: {vector_service.collection_name}'))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Failed to reset collection: {e}'))