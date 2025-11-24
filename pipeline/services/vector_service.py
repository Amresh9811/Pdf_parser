"""
ChromaDB service for vector storage and semantic search.
"""

from typing import List, Dict, Any, Optional
import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions
from loguru import logger
from django.conf import settings as django_settings
import uuid
import os


class VectorService:
    """
    Manages ChromaDB collection for semantic search.
    """
    
    def __init__(self):
        self.collection_name = django_settings.CHROMA_COLLECTION_NAME
        
        # Check if using ChromaDB Cloud or local
        chroma_api_key = os.getenv('CHROMA_API_KEY')
        chroma_tenant = os.getenv('CHROMA_TENANT')
        chroma_database = os.getenv('CHROMA_DATABASE')
        
        if chroma_api_key and chroma_tenant and chroma_database:
            # Use ChromaDB Cloud
            logger.info("Connecting to ChromaDB Cloud...")
            self.client = chromadb.CloudClient(
                api_key=chroma_api_key,
                tenant=chroma_tenant,
                database=chroma_database
            )
            logger.info(f"Connected to ChromaDB Cloud - Tenant: {chroma_tenant}, Database: {chroma_database}")
        else:
            # Use local persistent client
            logger.info("Using local ChromaDB...")
            self.persist_directory = django_settings.CHROMA_PERSIST_DIRECTORY
            self.client = chromadb.PersistentClient(
                path=self.persist_directory,
                settings=Settings(anonymized_telemetry=False)
            )
            logger.info(f"Connected to local ChromaDB at: {self.persist_directory}")
        
        # Use OpenAI embeddings
        openai_api_key = os.getenv('OPENAI_API_KEY')
        if openai_api_key:
            logger.info("Using OpenAI embeddings")
            self.embedding_function = embedding_functions.OpenAIEmbeddingFunction(
                api_key=openai_api_key,
                model_name="text-embedding-3-small"
            )
        else:
            logger.info("Using default embeddings")
            self.embedding_function = embedding_functions.DefaultEmbeddingFunction()
        
        # Try to get collection, if it has wrong embeddings, delete and recreate
        try:
            # First try to get existing collection
            self.collection = self.client.get_collection(name=self.collection_name)
            logger.info(f"Found existing collection: {self.collection_name}")
            
            # Try to set embedding function
            try:
                self.collection._embedding_function = self.embedding_function
                # Test if it works
                self.collection.count()
                logger.info("Successfully using existing collection with OpenAI embeddings")
            except Exception as embed_error:
                # If embedding function conflicts, delete and recreate
                logger.warning(f"Embedding conflict detected: {embed_error}")
                logger.info("Deleting and recreating collection with OpenAI embeddings...")
                self.client.delete_collection(name=self.collection_name)
                self.collection = self.client.create_collection(
                    name=self.collection_name,
                    embedding_function=self.embedding_function,
                    metadata={"description": "Construction documents for AI context"}
                )
                logger.info(f"Created fresh collection: {self.collection_name}")
                
        except ValueError:
            # Collection doesn't exist, create it
            self.collection = self.client.create_collection(
                name=self.collection_name,
                embedding_function=self.embedding_function,
                metadata={"description": "Construction documents for AI context"}
            )
            logger.info(f"Created new collection: {self.collection_name}")
    
    def add_documents(
        self,
        documents: List[str],
        metadatas: List[Dict[str, Any]],
        ids: Optional[List[str]] = None
    ) -> List[str]:
        """
        Add documents to ChromaDB with automatic embedding.
        
        Args:
            documents: List of text documents to add
            metadatas: List of metadata dicts for each document
            ids: Optional list of IDs (will generate if not provided)
        
        Returns:
            List of document IDs
        """
        if ids is None:
            ids = [str(uuid.uuid4()) for _ in documents]
        
        try:
            self.collection.add(
                documents=documents,
                metadatas=metadatas,
                ids=ids
            )
            logger.info(f"Added {len(documents)} documents to ChromaDB")
            return ids
            
        except Exception as e:
            logger.error(f"Failed to add documents to ChromaDB: {e}")
            raise
    
    def semantic_search(
        self,
        query: str,
        n_results: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Perform semantic search on the collection.
        
        Args:
            query: Search query string
            n_results: Number of results to return
            filter_metadata: Optional metadata filter
        
        Returns:
            List of search results with documents, metadata, and distances
        """
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results,
                where=filter_metadata
            )
            
            # Format results
            formatted_results = []
            if results['ids'] and len(results['ids'][0]) > 0:
                for idx in range(len(results['ids'][0])):
                    formatted_results.append({
                        'id': results['ids'][0][idx],
                        'document': results['documents'][0][idx],
                        'metadata': results['metadatas'][0][idx],
                        'relevance_score': 1 - results['distances'][0][idx]  # Convert distance to similarity
                    })
            
            logger.info(f"Found {len(formatted_results)} results for query: {query[:50]}...")
            return formatted_results
            
        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            return []
    
    def delete_documents(self, ids: List[str]) -> bool:
        """Delete documents by IDs."""
        try:
            self.collection.delete(ids=ids)
            logger.info(f"Deleted {len(ids)} documents from ChromaDB")
            return True
        except Exception as e:
            logger.error(f"Failed to delete documents: {e}")
            return False
    
    def get_collection_stats(self) -> Dict[str, Any]:
        """Get collection statistics."""
        try:
            count = self.collection.count()
            return {
                'collection_name': self.collection_name,
                'document_count': count,
                'embedding_model': 'OpenAI text-embedding-3-small'
            }
        except Exception as e:
            logger.error(f"Failed to get collection stats: {e}")
            return {'document_count': 0}
    
    def clear_collection(self) -> bool:
        """Clear all documents from collection."""
        try:
            # Delete the collection
            self.client.delete_collection(name=self.collection_name)
            # Recreate it
            self.collection = self.client.create_collection(
                name=self.collection_name,
                embedding_function=self.embedding_function,
                metadata={"description": "Construction documents for AI context"}
            )
            logger.info(f"Cleared collection: {self.collection_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to clear collection: {e}")
            return False


# Singleton instance
_vector_service_instance = None


def get_vector_service() -> VectorService:
    """Get or create singleton VectorService instance."""
    global _vector_service_instance
    if _vector_service_instance is None:
        _vector_service_instance = VectorService()
    return _vector_service_instance