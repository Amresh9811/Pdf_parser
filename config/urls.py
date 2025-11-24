"""
URL configuration for project_contextualizer.
"""

from django.contrib import admin
from django.urls import path
from django.http import JsonResponse
from django.shortcuts import render
from ninja_extra import NinjaExtraAPI
from pipeline.api.pipeline_api import router as pipeline_router
from pipeline.api.query_api import router as query_router


def root_view(request):
    """Root endpoint showing available API routes."""
    return JsonResponse({
        "message": "Project Contextualizer API",
        "version": "1.0.0",
        "endpoints": {
            "search_ui": "/search/",  # NEW
            "api_docs": "/api/docs",
            "admin": "/admin/",
            "health": "/api/pipeline/health",
            "trigger_pipeline": "/api/pipeline/trigger",
            "pipeline_status": "/api/pipeline/status/{run_id}",
            "query_tasks": "/api/query/tasks",
            "query_costs": "/api/query/cost-items",
            "semantic_search": "/api/query/semantic-search",
            "statistics": "/api/query/statistics"
        },
        "documentation": "Visit /api/docs for interactive API documentation"
    })


def search_ui(request):
    """Render search interface."""
    return render(request, 'search.html')


# Create API instance
api = NinjaExtraAPI(
    title="Project Contextualizer API",
    version="1.0.0",
    description="Data pipeline for extracting structured and unstructured information from construction documents"
)

# Register routers
api.add_router("/pipeline", pipeline_router)
api.add_router("/query", query_router)

urlpatterns = [
    path('', root_view, name='root'),
    path('search/', search_ui, name='search'),  # NEW
    path('admin/', admin.site.urls),
    path('api/', api.urls),
]