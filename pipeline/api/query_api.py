"""
Django Ninja API for querying extracted data.
"""

from typing import List, Optional
from ninja import Router, Schema
from django.shortcuts import get_object_or_404
from decimal import Decimal
from datetime import date
from loguru import logger

from pipeline.models import Document, ProjectTask, CostItem, DocumentChunk
from pipeline.services.vector_service import get_vector_service


router = Router(tags=["Query"])


from pipeline.services.hybrid_rag_service import get_hybrid_rag_service


class HybridRAGRequest(Schema):
    query: str
    n_results: int = 5


class HybridRAGResponse(Schema):
    query: str
    answer: str
    sources: List[str]
    confidence: str
    data_used: dict
    classification: dict


@router.post("/hybrid-rag", response=HybridRAGResponse)
def hybrid_rag_query(request, payload: HybridRAGRequest):
    """
    Hybrid RAG that intelligently combines SQL database and vector search.
    
    This endpoint:
    1. Classifies the query to determine what data sources are needed
    2. Retrieves relevant data from SQL (tasks, costs) if needed
    3. Retrieves relevant context from vector database if needed
    4. Combines both to generate a comprehensive answer
    """
    try:
        hybrid_service = get_hybrid_rag_service()
        
        # Step 1: Classify query
        classification = hybrid_service.classify_query(payload.query)
        
        # Step 2: Get data from appropriate sources
        sql_context = {}
        vector_results = []
        
        if classification['needs_sql']:
            sql_context = hybrid_service.get_sql_data(
                payload.query,
                classification['query_type']
            )
        
        if classification['needs_vector']:
            vector_results = hybrid_service.get_vector_data(
                payload.query,
                payload.n_results
            )
        
        # Step 3: Generate answer
        result = hybrid_service.generate_answer(
            query=payload.query,
            sql_context=sql_context,
            vector_results=vector_results,
            classification=classification
        )
        
        return HybridRAGResponse(
            query=payload.query,
            answer=result['answer'],
            sources=result['sources'],
            confidence=result['confidence'],
            data_used=result['data_used'],
            classification=classification
        )
        
    except Exception as e:
        logger.error(f"Hybrid RAG query failed: {e}")
        return HybridRAGResponse(
            query=payload.query,
            answer=f"Error processing query: {str(e)}",
            sources=[],
            confidence="error",
            data_used={},
            classification={}
        )
# Schemas
class TaskSchema(Schema):
    id: int
    task_id: int
    task_name: str
    duration_days: int
    start_date: date
    finish_date: date
    document_name: str


class CostItemSchema(Schema):
    id: int
    item_name: str
    quantity: float
    unit: str
    unit_price_yen: float
    total_cost_yen: float
    cost_type: str
    document_name: str


class SemanticSearchRequest(Schema):
    query: str
    n_results: int = 5
    document_type: Optional[str] = None


class SemanticSearchResult(Schema):
    id: str
    content: str
    relevance_score: float
    metadata: dict


class CostSummarySchema(Schema):
    total_cost: float
    foreign_cost: float
    local_cost: float
    other_cost: float
    item_count: int


@router.get("/tasks", response=List[TaskSchema])
def list_tasks(
    request,
    document_id: Optional[int] = None,
    min_duration: Optional[int] = None,
    limit: int = 50
):
    """
    Query project tasks with optional filters.
    """
    queryset = ProjectTask.objects.select_related('document').all()
    
    if document_id:
        queryset = queryset.filter(document_id=document_id)
    
    if min_duration:
        queryset = queryset.filter(duration_days__gte=min_duration)
    
    queryset = queryset[:limit]
    
    return [
        TaskSchema(
            id=task.id,
            task_id=task.task_id,
            task_name=task.task_name,
            duration_days=task.duration_days,
            start_date=task.start_date,
            finish_date=task.finish_date,
            document_name=task.document.file_name
        )
        for task in queryset
    ]


@router.get("/tasks/{task_id}", response=TaskSchema)
def get_task(request, task_id: int):
    """
    Get a specific task by ID.
    """
    task = get_object_or_404(ProjectTask.objects.select_related('document'), id=task_id)
    
    return TaskSchema(
        id=task.id,
        task_id=task.task_id,
        task_name=task.task_name,
        duration_days=task.duration_days,
        start_date=task.start_date,
        finish_date=task.finish_date,
        document_name=task.document.file_name
    )


@router.get("/cost-items", response=List[CostItemSchema])
def list_cost_items(
    request,
    document_id: Optional[int] = None,
    cost_type: Optional[str] = None,
    min_total: Optional[float] = None,
    limit: int = 50
):
    """
    Query cost items with optional filters.
    """
    queryset = CostItem.objects.select_related('document').all()
    
    if document_id:
        queryset = queryset.filter(document_id=document_id)
    
    if cost_type:
        queryset = queryset.filter(cost_type=cost_type)
    
    if min_total:
        queryset = queryset.filter(total_cost_yen__gte=min_total)
    
    queryset = queryset.order_by('-total_cost_yen')[:limit]
    
    return [
        CostItemSchema(
            id=item.id,
            item_name=item.item_name,
            quantity=float(item.quantity),
            unit=item.unit,
            unit_price_yen=float(item.unit_price_yen),
            total_cost_yen=float(item.total_cost_yen),
            cost_type=item.cost_type,
            document_name=item.document.file_name
        )
        for item in queryset
    ]


@router.get("/cost-summary", response=CostSummarySchema)
def get_cost_summary(request, document_id: Optional[int] = None):
    """
    Get cost summary statistics.
    """
    queryset = CostItem.objects.all()
    
    if document_id:
        queryset = queryset.filter(document_id=document_id)
    
    from django.db.models import Sum
    
    summary = queryset.aggregate(
        total=Sum('total_cost_yen'),
        foreign=Sum('total_cost_yen', filter=queryset.filter(cost_type='foreign').query),
        local=Sum('total_cost_yen', filter=queryset.filter(cost_type='local').query),
        other=Sum('total_cost_yen', filter=queryset.filter(cost_type='other').query)
    )
    
    return CostSummarySchema(
        total_cost=float(summary['total'] or 0),
        foreign_cost=float(summary['foreign'] or 0),
        local_cost=float(summary['local'] or 0),
        other_cost=float(summary['other'] or 0),
        item_count=queryset.count()
    )


@router.post("/semantic-search", response=List[SemanticSearchResult])
def semantic_search(request, payload: SemanticSearchRequest):
    """
    Perform semantic search across all processed documents.
    
    This enables AI agents to retrieve relevant context based on
    natural language queries.
    """
    try:
        vector_service = get_vector_service()
        
        # Prepare metadata filter if document type specified
        filter_metadata = None
        if payload.document_type:
            filter_metadata = {'document_type': payload.document_type}
        
        # Perform search
        results = vector_service.semantic_search(
            query=payload.query,
            n_results=payload.n_results,
            filter_metadata=filter_metadata
        )
        
        return [
            SemanticSearchResult(
                id=result['id'],
                content=result['document'],
                relevance_score=result['relevance_score'],
                metadata=result['metadata']
            )
            for result in results
        ]
        
    except Exception as e:
        logger.error(f"Semantic search failed: {e}")
        return []


@router.get("/semantic-search/examples")
def get_search_examples(request):
    """
    Get example semantic search queries to demonstrate the system.
    """
    return {
        "examples": [
            {
                "query": "What are the foundation requirements?",
                "description": "Find information about foundation specifications"
            },
            {
                "query": "Show me all tasks related to concrete work",
                "description": "Find schedule tasks for concrete activities"
            },
            {
                "query": "What are the most expensive cost items?",
                "description": "Identify high-cost construction items"
            },
            {
                "query": "What is the timeline for site preparation?",
                "description": "Find schedule information for site prep phase"
            },
            {
                "query": "Tell me about pile foundation costs",
                "description": "Find cost details for pile foundations"
            }
        ]
    }


@router.get("/statistics")
def get_statistics(request):
    """
    Get overall pipeline statistics.
    """
    from django.db.models import Sum, Count, Avg
    
    document_stats = Document.objects.aggregate(
        total=Count('id'),
        completed=Count('id', filter=Document.objects.filter(status='completed').query),
        failed=Count('id', filter=Document.objects.filter(status='failed').query)
    )
    
    task_stats = ProjectTask.objects.aggregate(
        total=Count('id'),
        avg_duration=Avg('duration_days')
    )
    
    cost_stats = CostItem.objects.aggregate(
        total_items=Count('id'),
        total_cost=Sum('total_cost_yen')
    )
    
    chunk_stats = DocumentChunk.objects.aggregate(
        total=Count('id')
    )
    
    # Get vector store stats
    try:
        vector_service = get_vector_service()
        vector_stats = vector_service.get_collection_stats()
    except:
        vector_stats = {'document_count': 0}
    
    return {
        "documents": {
            "total": document_stats['total'],
            "completed": document_stats['completed'],
            "failed": document_stats['failed']
        },
        "tasks": {
            "total": task_stats['total'],
            "average_duration_days": float(task_stats['avg_duration'] or 0)
        },
        "cost_items": {
            "total": cost_stats['total_items'],
            "total_cost_yen": float(cost_stats['total_cost'] or 0)
        },
        "semantic_chunks": {
            "postgres": chunk_stats['total'],
            "chromadb": vector_stats['document_count']
        }
    }


@router.get("/export/tasks")
def export_tasks_csv(request, document_id: Optional[int] = None):
    """
    Export tasks to CSV format.
    """
    import csv
    from django.http import HttpResponse
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="tasks.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Task ID', 'Task Name', 'Duration (days)', 'Start Date', 'Finish Date', 'Document'])
    
    queryset = ProjectTask.objects.select_related('document').all()
    if document_id:
        queryset = queryset.filter(document_id=document_id)
    
    for task in queryset:
        writer.writerow([
            task.task_id,
            task.task_name,
            task.duration_days,
            task.start_date,
            task.finish_date,
            task.document.file_name
        ])
    
    return response
class RAGQueryRequest(Schema):
    query: str
    n_results: int = 5
    temperature: float = 0.1


class RAGQueryResponse(Schema):
    query: str
    answer: str
    sources_used: List[str]
    confidence: str
    search_results: List[SemanticSearchResult]


@router.post("/rag-query", response=RAGQueryResponse)
def rag_query(request, payload: RAGQueryRequest):
    """
    RAG-based Question Answering using semantic search + OpenAI.
    
    This endpoint:
    1. Performs semantic search to find relevant context
    2. Uses OpenAI to generate an answer ONLY from the retrieved context
    3. Includes strong guardrails to prevent hallucination
    """
    try:
        import os
        from openai import OpenAI
        
        # Check if OpenAI is configured
        openai_key = os.getenv('OPENAI_API_KEY')
        if not openai_key:
            logger.error("OpenAI API key not configured")
            return RAGQueryResponse(
                query=payload.query,
                answer="Error: OpenAI API key not configured. Please add OPENAI_API_KEY to .env file.",
                sources_used=[],
                confidence="error",
                search_results=[]
            )
        
        # Step 1: Perform semantic search
        vector_service = get_vector_service()
        search_results = vector_service.semantic_search(
            query=payload.query,
            n_results=payload.n_results
        )
        
        if not search_results:
            return RAGQueryResponse(
                query=payload.query,
                answer="I couldn't find any relevant information in the documents to answer your question. Please try rephrasing or asking about topics covered in the construction and regulatory documents.",
                sources_used=[],
                confidence="no_results",
                search_results=[]
            )
        
        # Step 2: Prepare context from search results
        context_parts = []
        sources = []
        
        for idx, result in enumerate(search_results, 1):
            context_parts.append(f"[Source {idx}]:\n{result['document']}\n")
            source = result['metadata'].get('file_name', 'Unknown')
            if source not in sources:
                sources.append(source)
        
        context = "\n".join(context_parts)
        
        # Step 3: Create prompt with strong guardrails
        system_prompt = """You are a helpful assistant that answers questions based STRICTLY on the provided context documents.

CRITICAL RULES:
1. You MUST ONLY use information from the provided context to answer questions
2. If the context doesn't contain enough information to answer the question, you MUST say "I cannot answer this question based on the available documents"
3. DO NOT use your general knowledge or training data to supplement the answer
4. DO NOT make assumptions or inferences beyond what's explicitly stated in the context
5. Always cite which source number you're using (e.g., "According to Source 1...")
6. If asked about something not in the context, clearly state: "This information is not available in the provided documents"

Your role is to be a faithful intermediary between the documents and the user - nothing more, nothing less."""

        user_prompt = f"""Context from relevant documents:

{context}

---

Question: {payload.query}

Instructions:
- Answer the question using ONLY the information provided in the context above
- Cite which source(s) you're using (Source 1, Source 2, etc.)
- If the context doesn't contain the answer, say so clearly
- Do not add information from your training data
- Keep your answer concise and factual

Answer:"""

        # Step 4: Call OpenAI
        client = OpenAI(api_key=openai_key)
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # or "gpt-4" for better quality
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=payload.temperature,
            max_tokens=1000
        )
        
        answer = response.choices[0].message.content.strip()
        
        # Step 5: Determine confidence based on search scores
        avg_score = sum(r['relevance_score'] for r in search_results) / len(search_results)
        if avg_score > 0.3:
            confidence = "high"
        elif avg_score > 0.0:
            confidence = "medium"
        else:
            confidence = "low"
        
        # Format search results for response
        formatted_results = [
            SemanticSearchResult(
                id=result['id'],
                content=result['document'],
                relevance_score=result['relevance_score'],
                metadata=result['metadata']
            )
            for result in search_results
        ]
        
        return RAGQueryResponse(
            query=payload.query,
            answer=answer,
            sources_used=sources,
            confidence=confidence,
            search_results=formatted_results
        )
        
    except Exception as e:
        logger.error(f"RAG query failed: {e}")
        return RAGQueryResponse(
            query=payload.query,
            answer=f"Error processing query: {str(e)}",
            sources_used=[],
            confidence="error",
            search_results=[]
        )

@router.get("/export/costs")
def export_costs_csv(request, document_id: Optional[int] = None):
    """
    Export cost items to CSV format.
    """
    import csv
    from django.http import HttpResponse
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="cost_items.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Item Name', 'Quantity', 'Unit', 'Unit Price (¥)', 'Total Cost (¥)', 'Cost Type', 'Document'])
    
    queryset = CostItem.objects.select_related('document').all()
    if document_id:
        queryset = queryset.filter(document_id=document_id)
    
    for item in queryset:
        writer.writerow([
            item.item_name,
            item.quantity,
            item.unit,
            item.unit_price_yen,
            item.total_cost_yen,
            item.cost_type,
            item.document.file_name
        ])
    
    return response