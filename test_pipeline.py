"""
Test script to run the pipeline manually.
"""
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from pipeline.flows.main_flow import process_single_document
from pathlib import Path
from loguru import logger

# Configure logging
logger.add("logs/test_pipeline.log", rotation="10 MB")

def main():
    # Path to your documents
    docs_path = Path("data/documents")
    
    # Find PDF files
    pdf_files = list(docs_path.glob("*.pdf"))
    
    if not pdf_files:
        print("❌ No PDF files found in data/documents/")
        print("Please add PDF files to data/documents/ directory")
        return
    
    print(f"Found {len(pdf_files)} PDF files")
    
    # Process first two documents (as per requirements)
    for pdf_file in pdf_files[:2]:
        print(f"\n{'='*60}")
        print(f"Processing: {pdf_file.name}")
        print(f"{'='*60}")
        
        # Determine document type from filename
        filename_lower = pdf_file.name.lower()
        if 'schedule' in filename_lower:
            doc_type = 'schedule'
        elif 'cost' in filename_lower or 'planning' in filename_lower:
            doc_type = 'costing'
        else:
            # Default to costing if unsure
            doc_type = 'costing'
            print(f"⚠️  Could not determine type, using: {doc_type}")
        
        try:
            # Run pipeline
            result = process_single_document(
                file_path=str(pdf_file.absolute()),
                document_type=doc_type
            )
            
            if result.get('success'):
                print(f"\n✅ SUCCESS!")
                print(f"   - Tasks extracted: {result.get('tasks', 0)}")
                print(f"   - Cost items extracted: {result.get('cost_items', 0)}")
                print(f"   - Chunks created: {result.get('chunks', 0)}")
            else:
                print(f"\n❌ FAILED: {result.get('error', 'Unknown error')}")
                
        except Exception as e:
            print(f"\n❌ ERROR: {e}")
            logger.error(f"Pipeline failed for {pdf_file.name}: {e}")
    
    print(f"\n{'='*60}")
    print("Pipeline execution completed!")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()