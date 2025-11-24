# Project Contextualizer Pipeline

![Python](https://img.shields.io/badge/Python-3.12-blue)
![Django](https://img.shields.io/badge/Django-5.0-green)
![Prefect](https://img.shields.io/badge/Prefect-3.0-purple)
![License](https://img.shields.io/badge/License-MIT-yellow)

An intelligent data pipeline for extracting structured and unstructured information from construction and regulatory documents, providing high-quality context for AI agents through semantic search and RAG (Retrieval-Augmented Generation).

---

## 📋 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [API Documentation](#api-documentation)
- [Testing](#testing)
- [Deployment](#deployment)
- [Project Structure](#project-structure)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

---

## 🎯 Overview

The Project Contextualizer Pipeline is a comprehensive data extraction and retrieval system designed for construction and real estate documents. It combines traditional structured data extraction with modern AI-powered semantic search to provide intelligent question-answering capabilities.

### Key Capabilities

- **Document Processing**: Automatically extract data from PDF documents (schedules, costing reports, regulatory circulars)
- **Structured Extraction**: Parse tables and extract project tasks, cost items, and regulatory rules
- **Semantic Search**: Find relevant information using natural language queries
- **Hybrid RAG**: Intelligently combines SQL database queries with vector search for comprehensive answers
- **REST API**: Full-featured API for integration with other systems

---

## ✨ Features

### Core Features

- ✅ **Multi-Source Data Extraction**
  - Project schedules (Gantt-like tables)
  - Construction costing documents
  - Regulatory circulars and guidelines
  
- ✅ **Dual Storage Strategy**
  - **PostgreSQL**: Structured data (tasks, costs, rules)
  - **ChromaDB**: Vector embeddings for semantic search

- ✅ **Intelligent Query System**
  - Automatic query classification
  - SQL queries for structured data
  - Vector search for document context
  - Hybrid approach combining both

- ✅ **Production-Ready Pipeline**
  - Prefect orchestration with error handling
  - dltHub for data transformation
  - Comprehensive logging with Loguru
  - Retry logic and failure notifications

- ✅ **Multiple Extraction Methods**
  - Table parsing (pdfplumber, PyPDF2)
  - LLM-based extraction (OpenAI, Anthropic)
  - Hybrid approach for maximum accuracy

### Advanced Features

- 🔍 **Semantic Search**: Find relevant content using natural language
- 🤖 **RAG Q&A**: Get AI-powered answers with source attribution
- 🧠 **Hybrid RAG**: Combines SQL + Vector search intelligently
- 📊 **Statistics API**: Query structured data with filters
- 🌐 **Web Interface**: Beautiful search UI for non-technical users
- 📈 **Pipeline Monitoring**: Track execution history and statistics

---

## 🏗️ Architecture
```
┌─────────────────────────────────────────────────────────────┐
│                     Document Sources                         │
│              (PDF: Schedules, Costs, Circulars)             │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                  Prefect Orchestration                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Validate   │→│   Extract    │→│   Transform  │      │
│  │  Document    │  │     Data     │  │   & Load     │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└────────────────────┬────────────────────────────────────────┘
                     │
            ┌────────┴────────┐
            ▼                 ▼
┌──────────────────┐  ┌──────────────────┐
│   PostgreSQL     │  │    ChromaDB      │
│  (Structured)    │  │   (Vectors)      │
│                  │  │                  │
│ • project_tasks  │  │ • Embeddings     │
│ • cost_items     │  │ • Metadata       │
│ • documents      │  │ • Chunks         │
└────────┬─────────┘  └────────┬─────────┘
         │                     │
         └──────────┬──────────┘
                    ▼
         ┌─────────────────────┐
         │   Hybrid RAG Layer  │
         │                     │
         │  • Query Classifier │
         │  • SQL Generator    │
         │  • Vector Search    │
         │  • Answer Synthesis │
         └──────────┬──────────┘
                    ▼
         ┌─────────────────────┐
         │   Django REST API   │
         │   (Django Ninja)    │
         └─────────────────────┘
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
    Web UI      API Docs    External Apps
```

---

## 🛠️ Tech Stack

### Core Framework
- **Django 5.0**: Web framework and ORM
- **Django Ninja**: Modern REST API framework
- **Prefect 3.0**: Workflow orchestration

### Data Processing
- **pdfplumber**: PDF table extraction
- **PyPDF2**: PDF text extraction
- **pandas**: Data manipulation
- **dltHub**: ETL transformations

### AI & Search
- **OpenAI GPT-4**: LLM for extraction and RAG
- **Anthropic Claude**: Alternative LLM provider
- **ChromaDB**: Vector database for semantic search
- **OpenAI Embeddings**: Text embeddings (text-embedding-3-small)

### Database
- **PostgreSQL**: Structured data storage
- **ChromaDB Cloud**: Vector storage (cloud or local)

### Utilities
- **Loguru**: Enhanced logging
- **python-dotenv**: Environment management
- **psycopg2**: PostgreSQL adapter

---

## 📋 Prerequisites

- Python 3.12+
- PostgreSQL 14+
- OpenAI API key
- ChromaDB Cloud account (optional, can use local)
- 4GB RAM minimum
- 10GB disk space

---

## 🚀 Installation

### 1. Clone Repository
```bash
git clone https://github.com/yourusername/project-contextualizer.git
cd project-contextualizer
```

### 2. Create Virtual Environment
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Set Up Project Structure
```bash
# Create necessary directories
mkdir -p data/documents data/chroma data/processed logs
mkdir -p pipeline/extractors pipeline/services pipeline/tasks pipeline/flows pipeline/api
mkdir -p templates config

# Create __init__.py files
New-Item -ItemType File -Path "config/__init__.py"
New-Item -ItemType File -Path "pipeline/__init__.py"
New-Item -ItemType File -Path "pipeline/extractors/__init__.py"
New-Item -ItemType File -Path "pipeline/services/__init__.py"
New-Item -ItemType File -Path "pipeline/tasks/__init__.py"
New-Item -ItemType File -Path "pipeline/flows/__init__.py"
New-Item -ItemType File -Path "pipeline/api/__init__.py"
New-Item -ItemType File -Path "pipeline/management/__init__.py"
New-Item -ItemType File -Path "pipeline/management/commands/__init__.py"
```

### 5. Configure Environment

Create `.env` file:
```env
# Django Settings
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Database
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/contextualizer

# AI Services
OPENAI_API_KEY=your-openai-api-key
ANTHROPIC_API_KEY=your-anthropic-api-key
DEFAULT_LLM_PROVIDER=openai
DEFAULT_LLM_MODEL=gpt-4o-mini

# ChromaDB Cloud (or use local)
CHROMA_API_KEY=your-chroma-api-key
CHROMA_TENANT=your-tenant-id
CHROMA_DATABASE=your-database-name
CHROMA_COLLECTION_NAME=construction_docs

# ChromaDB Local (alternative)
# CHROMA_PERSIST_DIRECTORY=./data/chroma
# CHROMA_COLLECTION_NAME=construction_docs

# Embedding Model
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2

# Pipeline Settings
MAX_RETRIES=3
RETRY_DELAY_SECONDS=5
CHUNK_SIZE=1000
CHUNK_OVERLAP=200

# Prefect
PREFECT_API_URL=http://localhost:4200/api
PREFECT_LOGGING_LEVEL=INFO

# Paths
DOCUMENTS_PATH=./data/documents
PROCESSED_PATH=./data/processed
LOG_LEVEL=INFO
LOG_FILE=logs/pipeline.log

# dltHub
DLT_PIPELINE_NAME=construction_pipeline
DLT_DATASET_NAME=construction_data
```

### 6. Set Up Database
```bash
# Create PostgreSQL database
createdb contextualizer

# Run migrations
python manage.py makemigrations
python manage.py migrate
```

### 7. Add Sample Documents

Place your PDF documents in `data/documents/`:
```bash
data/documents/
├── schedule.pdf              # Project schedule
├── costing.pdf              # Construction costing
└── URA-Circular.pdf         # Regulatory circular
```

---

## ⚙️ Configuration

### Database Configuration

**PostgreSQL:**
```python
# config/settings.py
DATABASES = {
    'default': dj_database_url.parse(
        os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/contextualizer')
    )
}
```

### ChromaDB Configuration

**Cloud Setup:**
```python
CHROMA_API_KEY=ck-xxx
CHROMA_TENANT=xxx
CHROMA_DATABASE=xxx
```

**Local Setup:**
```python
CHROMA_PERSIST_DIRECTORY=./data/chroma
```

### LLM Configuration

**OpenAI:**
```python
OPENAI_API_KEY=sk-xxx
DEFAULT_LLM_MODEL=gpt-4o-mini
```

**Anthropic:**
```python
ANTHROPIC_API_KEY=sk-ant-xxx
DEFAULT_LLM_MODEL=claude-3-5-sonnet-20241022
```

---

## 📖 Usage

### Running the Pipeline

**Method 1: Direct Execution (Recommended for Testing)**
```bash
python run_pipeline_direct.py
```

**Method 2: Via Prefect (Production)**
```bash
# Terminal 1: Start Prefect server
prefect server start

# Terminal 2: Run pipeline
python test_pipeline.py
```

**Method 3: Via API**
```bash
# Start Django server
python manage.py runserver

# Trigger via API
curl -X POST http://localhost:8000/api/pipeline/trigger \
  -H "Content-Type: application/json" \
  -d '{
    "document_paths": ["./data/documents/schedule.pdf"],
    "document_types": ["schedule"]
  }'
```

### Starting the Web Server
```bash
python manage.py runserver
```

Access:
- **Web UI**: http://127.0.0.1:8000/search/
- **API Docs**: http://127.0.0.1:8000/api/docs
- **Admin**: http://127.0.0.1:8000/admin/

### Using the Search Interface

1. Open http://127.0.0.1:8000/search/
2. Choose mode:
   - **🧠 Smart AI (Hybrid)**: Combines SQL + Vector search
   - **🤖 Document AI**: Vector search only
   - **🔍 Raw Search**: Semantic search results
3. Enter your question
4. View AI-generated answer with sources

### Example Queries

**Structured Data Queries:**
```
- How many project tasks are there?
- What is the total construction cost?
- List all tasks with duration over 30 days
- Show me cost items related to piling
```

**Document Context Queries:**
```
- When does the new GFA definition take effect?
- What is the Urban Redevelopment Authority?
- Explain the harmonisation of floor area definitions
- What are the regulatory requirements?
```

**Hybrid Queries:**
```
- What construction tasks are related to the GFA definition?
- Compare project costs with regulatory requirements
- Which tasks need to comply with URA regulations?
```

---

## 🔌 API Documentation

### Base URL
```
http://127.0.0.1:8000/api
```

### Endpoints

#### 1. Hybrid RAG Query (Recommended)
```http
POST /query/hybrid-rag
Content-Type: application/json

{
  "query": "How many project tasks are there?",
  "n_results": 5
}
```

**Response:**
```json
{
  "query": "How many project tasks are there?",
  "answer": "There are 32 project tasks in the database...",
  "sources": ["SQL Database", "schedule.pdf"],
  "confidence": "high",
  "data_used": {
    "sql_data": true,
    "vector_data": true,
    "tasks_count": 32,
    "costs_count": 0,
    "documents_count": 3
  },
  "classification": {
    "needs_sql": true,
    "needs_vector": false,
    "query_type": "tasks"
  }
}
```

#### 2. Semantic Search
```http
POST /query/semantic-search
Content-Type: application/json

{
  "query": "Urban Redevelopment Authority",
  "n_results": 5
}
```

#### 3. Get Tasks
```http
GET /query/tasks?limit=10&min_duration=30
```

#### 4. Get Cost Items
```http
GET /query/cost-items?limit=20&cost_type=foreign
```

#### 5. Get Cost Summary
```http
GET /query/cost-summary?document_id=1
```

#### 6. Get Statistics
```http
GET /query/statistics
```

**Response:**
```json
{
  "documents": {
    "total": 2,
    "completed": 2,
    "failed": 0
  },
  "tasks": {
    "total": 32,
    "average_duration_days": 45.5
  },
  "cost_items": {
    "total": 10,
    "total_cost_yen": 1500000.00
  },
  "semantic_chunks": {
    "postgres": 102,
    "chromadb": 102
  }
}
```

#### 7. Trigger Pipeline
```http
POST /pipeline/trigger
Content-Type: application/json

{
  "document_paths": [
    "D:\\Pdf_parser\\data\\documents\\schedule.pdf"
  ],
  "document_types": ["schedule"]
}
```

#### 8. Health Check
```http
GET /pipeline/health
```

### Interactive API Documentation

Visit http://127.0.0.1:8000/api/docs for interactive Swagger UI.

---

## 🧪 Testing

### Run All Tests
```bash
pytest
```

### Run Specific Tests
```bash
# Test extractors
pytest tests/test_extractors.py

# Test services
pytest tests/test_services.py

# Test API
pytest tests/test_api.py
```

### Test Scripts

**Test ChromaDB:**
```bash
python test_chromadb.py
```

**Test Search:**
```bash
python test_search.py
```

**Test Pipeline:**
```bash
python test_pipeline.py
```

**Demo System:**
```bash
python demo.py
```

### Manual Testing

**Query via PowerShell:**
```powershell
$body = @{
    query = "How many tasks are there?"
    n_results = 5
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/query/hybrid-rag" `
  -Method POST `
  -Body $body `
  -ContentType "application/json"
```

---

## 🚢 Deployment

### Production Checklist

- [ ] Set `DEBUG=False` in `.env`
- [ ] Use production PostgreSQL database
- [ ] Set strong `SECRET_KEY`
- [ ] Configure ALLOWED_HOSTS
- [ ] Set up SSL/TLS
- [ ] Configure production logging
- [ ] Set up monitoring (Sentry, DataDog)
- [ ] Configure backup strategy
- [ ] Set up CI/CD pipeline

### Deploy to Render

1. Create `render.yaml`:
```yaml
services:
  - type: web
    name: contextualizer-api
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: gunicorn config.wsgi:application
    envVars:
      - key: PYTHON_VERSION
        value: 3.12.0
      - key: DATABASE_URL
        fromDatabase:
          name: contextualizer-db
          property: connectionString
```

2. Push to GitHub
3. Connect to Render
4. Deploy

### Docker Deployment
```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
```
```bash
docker build -t contextualizer .
docker run -p 8000:8000 --env-file .env contextualizer
```

---

## 📁 Project Structure
```
project-contextualizer/
│
├── config/                          # Django configuration
│   ├── __init__.py
│   ├── settings.py                  # Django settings
│   ├── urls.py                      # URL routing
│   └── wsgi.py                      # WSGI application
│
├── pipeline/                        # Main application
│   ├── __init__.py
│   ├── models.py                    # Database models
│   │
│   ├── extractors/                  # Document extractors
│   │   ├── __init__.py
│   │   ├── base_extractor.py       # Base extractor class
│   │   ├── schedule_extractor.py   # Schedule document extractor
│   │   └── costing_extractor.py    # Costing document extractor
│   │
│   ├── services/                    # Business logic services
│   │   ├── __init__.py
│   │   ├── vector_service.py       # ChromaDB service
│   │   ├── dlt_service.py          # dltHub service
│   │   └── hybrid_rag_service.py   # Hybrid RAG service
│   │
│   ├── tasks/                       # Prefect tasks
│   │   ├── __init__.py
│   │   └── extraction_tasks.py     # Pipeline tasks
│   │
│   ├── flows/                       # Prefect flows
│   │   ├── __init__.py
│   │   └── main_flow.py            # Main pipeline flow
│   │
│   ├── api/                         # API endpoints
│   │   ├── __init__.py
│   │   ├── pipeline_api.py         # Pipeline control API
│   │   └── query_api.py            # Query API
│   │
│   ├── management/                  # Django management commands
│   │   ├── __init__.py
│   │   └── commands/
│   │       ├── __init__.py
│   │       └── reset_chromadb.py
│   │
│   └── migrations/                  # Database migrations
│
├── templates/                       # HTML templates
│   └── search.html                  # Search interface
│
├── data/                            # Data directory
│   ├── documents/                   # Input PDFs
│   ├── chroma/                      # ChromaDB local storage
│   └── processed/                   # Processed files
│
├── logs/                            # Application logs
│
├── tests/                           # Test suite
│   ├── test_extractors.py
│   ├── test_services.py
│   └── test_api.py
│
├── manage.py                        # Django management
├── requirements.txt                 # Python dependencies
├── .env                             # Environment variables
├── .gitignore                       # Git ignore file
│
├── test_pipeline.py                 # Pipeline test script
├── test_chromadb.py                 # ChromaDB test script
├── test_search.py                   # Search test script
├── run_pipeline_direct.py           # Direct pipeline runner
├── demo.py                          # System demo script
├── fix_chromadb.py                  # ChromaDB fix script
└── README.md                        # This file
```

---

## 🐛 Troubleshooting

### Common Issues

#### 1. ChromaDB Returns 0 Results

**Problem**: Semantic search returns no results despite having documents.

**Solution**:
```bash
# Delete and recreate collection
python fix_chromadb.py

# Clear PostgreSQL
python manage.py shell
>>> from pipeline.models import *
>>> Document.objects.all().delete()
>>> exit()

# Re-run pipeline
python test_pipeline.py
```

**Cause**: Embedding function mismatch (default vs OpenAI embeddings).

#### 2. Prefect Cache Issues

**Problem**: Pipeline uses cached failed results.

**Solution**:
```python
# In extraction_tasks.py, remove these lines:
# cache_key_fn=task_input_hash,
# cache_expiration=timedelta(hours=24)
```

#### 3. Database Connection Error

**Problem**: `psycopg2.OperationalError: could not connect to server`

**Solution**:
```bash
# Check PostgreSQL is running
pg_ctl status

# Verify DATABASE_URL in .env
DATABASE_URL=postgresql://user:pass@localhost:5432/dbname
```

#### 4. OpenAI API Key Error

**Problem**: `openai.error.AuthenticationError: Incorrect API key`

**Solution**:
- Check OPENAI_API_KEY in `.env`
- Verify key is valid at https://platform.openai.com/api-keys
- Ensure no extra spaces or quotes

#### 5. Module Import Errors

**Problem**: `ModuleNotFoundError: No module named 'config'`

**Solution**:
```bash
# Ensure __init__.py files exist
touch config/__init__.py
touch pipeline/__init__.py

# Check PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:${PWD}"
```

### Debug Commands
```bash
# Check database tables
python manage.py dbshell
\dt

# View logs
cat logs/pipeline.log

# Test ChromaDB connection
python verify_chromadb.py

# Check API health
curl http://localhost:8000/api/pipeline/health
```

---

## 🤝 Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Setup
```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run tests before committing
pytest

# Format code
black .
isort .

# Lint
flake8 .
```

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 👥 Authors

- **Your Name** - *Initial work* - [YourGithub](https://github.com/yourusername)

---

## 🙏 Acknowledgments

- Prefect for workflow orchestration
- OpenAI for embeddings and LLM capabilities
- ChromaDB for vector storage
- Django community for the excellent framework

---

## 📞 Support

For issues, questions, or contributions:

- **Issues**: Your Issues you can mail me.
- **Email**: amresh.kumar90150@gmail.com

---

## 🔄 Changelog

### Version 1.0.0 (2024-11-24)

- ✨ Initial release
- ✅ Document extraction pipeline
- ✅ Semantic search with ChromaDB
- ✅ Hybrid RAG system
- ✅ REST API with Django Ninja
- ✅ Web search interface
- ✅ Prefect orchestration
- ✅ Comprehensive documentation

---

**Made with ❤️ for the construction and real estate industry**
