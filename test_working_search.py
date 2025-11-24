"""
Test semantic search after fresh ChromaDB setup.
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from pipeline.services.vector_service import get_vector_service

print("🔍 Testing Semantic Search\n")
print("="*60)

vector_service = get_vector_service()

# Check collection stats
stats = vector_service.get_collection_stats()
print(f"\n📊 ChromaDB Stats:")
print(f"   Collection: {stats['collection_name']}")
print(f"   Document count: {stats['document_count']}")
print(f"   Embedding model: {stats.get('embedding_model', 'default')}")

if stats['document_count'] == 0:
    print("\n❌ ERROR: ChromaDB is empty!")
    print("   Run: python test_pipeline.py")
    exit(1)

print(f"\n{'='*60}")

# Test queries
test_queries = [
    "Urban Redevelopment Authority",
    "What is the GFA definition?",
    "construction schedule",
    "project tasks",
    "When does the new definition take effect?",
]

for query in test_queries:
    print(f"\n🔎 Query: '{query}'")
    print("-" * 60)
    
    results = vector_service.semantic_search(
        query=query,
        n_results=3
    )
    
    if results:
        print(f"✅ Found {len(results)} results:")
        for idx, result in enumerate(results, 1):
            print(f"\n   Result {idx}:")
            print(f"   Score: {result['relevance_score']:.4f}")
            print(f"   Content: {result['document'][:150]}...")
            print(f"   Source: {result['metadata'].get('file_name', 'Unknown')}")
    else:
        print("❌ No results found")

print(f"\n{'='*60}")
print("\n✅ If you see results above, semantic search is working!")
print("❌ If all queries return 0 results, there's still an issue.")