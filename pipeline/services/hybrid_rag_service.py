"""
Hybrid RAG service that combines SQL queries and vector search.
"""

from typing import Dict, List, Any, Tuple
from loguru import logger
from django.db.models import Q, Sum, Count, Avg
from openai import OpenAI
import os
import json

from pipeline.models import ProjectTask, CostItem, Document
from pipeline.services.vector_service import get_vector_service


class HybridRAGService:
    """
    Intelligent service that routes queries to appropriate data sources.
    """
    
    def __init__(self):
        self.openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.vector_service = get_vector_service()
    
    def classify_query(self, query: str) -> Dict[str, Any]:
        """
        Classify what type of data the query needs.
        
        Returns:
            {
                'needs_sql': bool,
                'needs_vector': bool,
                'query_type': 'tasks' | 'costs' | 'general' | 'hybrid',
                'sql_intent': description of what SQL data is needed
            }
        """
        
        classification_prompt = f"""Analyze this user query and determine what data sources it needs.

Query: "{query}"

Available data sources:
1. SQL Database with:
   - project_tasks: Contains task_id, task_name, duration_days, start_date, finish_date
   - cost_items: Contains item_name, quantity, unit, unit_price_yen, total_cost_yen, cost_type

2. Vector Database with:
   - Full document text chunks from construction and regulatory documents

Determine:
- Does this query need structured data from SQL tables? (yes/no)
- Does this query need document context from vector database? (yes/no)
- What type of query is this? (tasks/costs/general/hybrid)

Respond with ONLY valid JSON:
{{
    "needs_sql": true/false,
    "needs_vector": true/false,
    "query_type": "tasks|costs|general|hybrid",
    "sql_intent": "brief description of what SQL data is needed",
    "reasoning": "brief explanation"
}}"""

        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a query classifier. Respond only with valid JSON."},
                    {"role": "user", "content": classification_prompt}
                ],
                temperature=0,
                max_tokens=200
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # Clean up JSON if wrapped in markdown
            if result_text.startswith('```'):
                result_text = result_text.split('```')[1]
                if result_text.startswith('json'):
                    result_text = result_text[4:]
                result_text = result_text.strip()
            
            classification = json.loads(result_text)
            logger.info(f"Query classification: {classification}")
            return classification
            
        except Exception as e:
            logger.error(f"Query classification failed: {e}")
            # Default to hybrid approach
            return {
                'needs_sql': True,
                'needs_vector': True,
                'query_type': 'hybrid',
                'sql_intent': 'Unknown',
                'reasoning': f'Classification failed: {e}'
            }
    
    def get_sql_data(self, query: str, query_type: str) -> Dict[str, Any]:
        """
        Retrieve relevant structured data from SQL.
        """
        sql_context = {
            'tasks': [],
            'costs': [],
            'summary': {}
        }
        
        try:
            # Search tasks
            if query_type in ['tasks', 'hybrid', 'general']:
                tasks = ProjectTask.objects.all()
                
                # Try to filter by keywords
                query_lower = query.lower()
                keywords = query_lower.split()
                
                for keyword in keywords:
                    if len(keyword) > 3:  # Skip short words
                        tasks = tasks.filter(
                            Q(task_name__icontains=keyword)
                        )
                
                tasks_data = []
                for task in tasks[:20]:  # Limit to 20 tasks
                    tasks_data.append({
                        'task_id': task.task_id,
                        'task_name': task.task_name,
                        'duration_days': task.duration_days,
                        'start_date': str(task.start_date) if task.start_date else None,
                        'finish_date': str(task.finish_date) if task.finish_date else None
                    })
                
                sql_context['tasks'] = tasks_data
                
                # Add task summary
                if tasks.exists():
                    sql_context['summary']['total_tasks'] = tasks.count()
                    sql_context['summary']['total_duration'] = tasks.aggregate(
                        total=Sum('duration_days')
                    )['total'] or 0
            
            # Search costs
            if query_type in ['costs', 'hybrid', 'general']:
                costs = CostItem.objects.all()
                
                # Try to filter by keywords
                query_lower = query.lower()
                keywords = query_lower.split()
                
                for keyword in keywords:
                    if len(keyword) > 3:
                        costs = costs.filter(
                            Q(item_name__icontains=keyword)
                        )
                
                costs_data = []
                for item in costs[:20]:  # Limit to 20 items
                    costs_data.append({
                        'item_name': item.item_name,
                        'quantity': float(item.quantity),
                        'unit': item.unit,
                        'unit_price_yen': float(item.unit_price_yen),
                        'total_cost_yen': float(item.total_cost_yen),
                        'cost_type': item.cost_type
                    })
                
                sql_context['costs'] = costs_data
                
                # Add cost summary
                if costs.exists():
                    sql_context['summary']['total_cost_items'] = costs.count()
                    sql_context['summary']['total_cost'] = float(
                        costs.aggregate(total=Sum('total_cost_yen'))['total'] or 0
                    )
                    
                    # Breakdown by type
                    by_type = costs.values('cost_type').annotate(
                        total=Sum('total_cost_yen'),
                        count=Count('id')
                    )
                    sql_context['summary']['cost_breakdown'] = {
                        item['cost_type']: {
                            'total': float(item['total'] or 0),
                            'count': item['count']
                        }
                        for item in by_type
                    }
            
            logger.info(f"Retrieved SQL data: {len(sql_context['tasks'])} tasks, {len(sql_context['costs'])} costs")
            return sql_context
            
        except Exception as e:
            logger.error(f"SQL data retrieval failed: {e}")
            return sql_context
    
    def get_vector_data(self, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """
        Retrieve relevant document chunks from vector database.
        """
        try:
            results = self.vector_service.semantic_search(
                query=query,
                n_results=n_results
            )
            logger.info(f"Retrieved {len(results)} vector results")
            return results
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []
    
    def generate_answer(
        self,
        query: str,
        sql_context: Dict[str, Any],
        vector_results: List[Dict[str, Any]],
        classification: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Generate final answer using both SQL and vector context.
        """
        
        # Build context sections
        context_parts = []
        sources = []
        
        # Add SQL context
        if sql_context['tasks'] or sql_context['costs']:
            sql_section = "=== STRUCTURED DATA FROM DATABASE ===\n\n"
            
            if sql_context['summary']:
                sql_section += f"Summary:\n{json.dumps(sql_context['summary'], indent=2)}\n\n"
            
            if sql_context['tasks']:
                sql_section += f"Project Tasks ({len(sql_context['tasks'])} found):\n"
                for task in sql_context['tasks'][:10]:  # Show top 10
                    sql_section += f"- {task['task_name']}: {task['duration_days']} days"
                    if task['start_date']:
                        sql_section += f" (Start: {task['start_date']})"
                    sql_section += "\n"
                sql_section += "\n"
            
            if sql_context['costs']:
                sql_section += f"Cost Items ({len(sql_context['costs'])} found):\n"
                for item in sql_context['costs'][:10]:  # Show top 10
                    sql_section += f"- {item['item_name']}: ¥{item['total_cost_yen']:,.2f} ({item['quantity']} {item['unit']})\n"
                sql_section += "\n"
            
            context_parts.append(sql_section)
            sources.append("SQL Database")
        
        # Add vector context
        if vector_results:
            vector_section = "=== DOCUMENT CONTEXT ===\n\n"
            for idx, result in enumerate(vector_results, 1):
                vector_section += f"[Document {idx} - {result['metadata'].get('file_name', 'Unknown')}]:\n"
                vector_section += f"{result['document']}\n\n"
                
                source = result['metadata'].get('file_name', 'Unknown')
                if source not in sources:
                    sources.append(source)
            
            context_parts.append(vector_section)
        
        full_context = "\n".join(context_parts)
        
        # Generate answer
        system_prompt = """You are a helpful assistant that answers questions using provided structured data and document context.

CRITICAL RULES:
1. Use BOTH the structured SQL data AND document context when available
2. For questions about specific tasks, costs, or numbers, prioritize the SQL data
3. For questions about definitions, processes, or explanations, use document context
4. ONLY answer based on the provided information
5. If information is not in the provided context, say "This information is not available"
6. Cite your sources clearly (e.g., "According to the database..." or "According to the document...")
7. Be specific with numbers and data from the SQL database
8. Format your answer clearly with proper structure

Your goal is to provide accurate, well-sourced answers by intelligently combining both data sources."""

        user_prompt = f"""Context:

{full_context}

---

Question: {query}

Provide a comprehensive answer using the information above. Combine insights from both the structured database and documents where relevant.

Answer:"""

        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,
                max_tokens=1500
            )
            
            answer = response.choices[0].message.content.strip()
            
            # Determine confidence
            has_sql = bool(sql_context['tasks'] or sql_context['costs'])
            has_vector = bool(vector_results)
            
            if has_sql and has_vector:
                confidence = "high"
            elif has_sql or has_vector:
                confidence = "medium"
            else:
                confidence = "low"
            
            return {
                'success': True,
                'answer': answer,
                'sources': sources,
                'confidence': confidence,
                'data_used': {
                    'sql_data': has_sql,
                    'vector_data': has_vector,
                    'tasks_count': len(sql_context['tasks']),
                    'costs_count': len(sql_context['costs']),
                    'documents_count': len(vector_results)
                },
                'classification': classification,
                'sql_context': sql_context,
                'vector_results': vector_results
            }
            
        except Exception as e:
            logger.error(f"Answer generation failed: {e}")
            return {
                'success': False,
                'answer': f"Error generating answer: {str(e)}",
                'sources': [],
                'confidence': 'error',
                'data_used': {},
                'classification': classification,
                'sql_context': {},
                'vector_results': []
            }


# Singleton
_hybrid_rag_service = None

def get_hybrid_rag_service() -> HybridRAGService:
    """Get or create singleton instance."""
    global _hybrid_rag_service
    if _hybrid_rag_service is None:
        _hybrid_rag_service = HybridRAGService()
    return _hybrid_rag_service