"""
Quick demo of the complete system.
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from pipeline.models import Document, ProjectTask, CostItem
from pipeline.services.vector_service import get_vector_service

print("\n" + "="*60)
print("📊 PROJECT CONTEXTUALIZER SYSTEM DEMO")
print("="*60)

# 1. Database stats
print("\n1️⃣  PostgreSQL Database:")
print(f"   Documents: {Document.objects.count()}")
print(f"   Project Tasks: {ProjectTask.objects.count()}")
print(f"   Cost Items: {CostItem.objects.count()}")

# 2. Sample tasks
print("\n2️⃣  Sample Project Tasks:")
for task in ProjectTask.objects.all()[:3]:
    print(f"   - {task.task_name} ({task.duration_days} days)")

# 3. Sample costs
print("\n3️⃣  Sample Cost Items:")
for item in CostItem.objects.all()[:3]:
    print(f"   - {item.item_name}: ¥{item.total_cost_yen:,.2f}")

# 4. Vector search
print("\n4️⃣  Semantic Search Demo:")
vector_service = get_vector_service()
stats = vector_service.get_collection_stats()
print(f"   ChromaDB documents: {stats['document_count']}")

queries = ["project schedule", "construction costs"]
for query in queries:
    results = vector_service.semantic_search(query, n_results=2)
    print(f"\n   Query: '{query}'")
    print(f"   Results: {len(results)}")
    if results:
        print(f"   Best match: {results[0]['document'][:80]}...")

print("\n" + "="*60)
print("✅ System is fully operational!")
print("="*60)
print("\n🌐 API: http://127.0.0.1:8000/api/docs")
print("📊 Admin: http://127.0.0.1:8000/admin/")
print("\n")