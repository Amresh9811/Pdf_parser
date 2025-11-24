"""
Base extractor class with common PDF processing functionality.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from pathlib import Path
import pdfplumber
import PyPDF2
from loguru import logger
from openai import OpenAI
from anthropic import Anthropic
from django.conf import settings


class BaseExtractor(ABC):
    """
    Abstract base class for document extractors.
    Provides common functionality for PDF processing and LLM integration.
    """
    
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self.file_name = self.file_path.name
        
        # Initialize LLM clients
        self.llm_provider = settings.DEFAULT_LLM_PROVIDER
        
        if settings.OPENAI_API_KEY:
            self.openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
        else:
            self.openai_client = None
            
        if settings.ANTHROPIC_API_KEY:
            self.anthropic_client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        else:
            self.anthropic_client = None
            
        logger.info(f"Initialized {self.__class__.__name__} for {self.file_name}")
    
    def extract_text_pdfplumber(self) -> str:
        """Extract text using pdfplumber - good for tables and structured content."""
        try:
            text_content = []
            with pdfplumber.open(self.file_path) as pdf:
                for page_num, page in enumerate(pdf.pages, 1):
                    text = page.extract_text()
                    if text:
                        text_content.append(f"--- Page {page_num} ---\n{text}")
            
            full_text = "\n\n".join(text_content)
            logger.info(f"Extracted {len(full_text)} characters using pdfplumber")
            return full_text
        except Exception as e:
            logger.error(f"pdfplumber extraction failed: {e}")
            return ""
    
    def extract_text_pypdf2(self) -> str:
        """Extract text using PyPDF2 - backup method."""
        try:
            text_content = []
            with open(self.file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                for page_num, page in enumerate(pdf_reader.pages, 1):
                    text = page.extract_text()
                    if text:
                        text_content.append(f"--- Page {page_num} ---\n{text}")
            
            full_text = "\n\n".join(text_content)
            logger.info(f"Extracted {len(full_text)} characters using PyPDF2")
            return full_text
        except Exception as e:
            logger.error(f"PyPDF2 extraction failed: {e}")
            return ""
    
    def extract_tables_pdfplumber(self) -> List[List[List[Any]]]:
        """Extract all tables from PDF using pdfplumber."""
        try:
            all_tables = []
            with pdfplumber.open(self.file_path) as pdf:
                for page_num, page in enumerate(pdf.pages, 1):
                    tables = page.extract_tables()
                    if tables:
                        logger.info(f"Found {len(tables)} tables on page {page_num}")
                        all_tables.extend(tables)
            return all_tables
        except Exception as e:
            logger.error(f"Table extraction failed: {e}")
            return []
    
    def call_llm(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 4000
    ) -> str:
        """
        Call LLM with fallback between providers.
        """
        try:
            if self.llm_provider == 'openai' and self.openai_client:
                return self._call_openai(prompt, system_prompt, temperature, max_tokens)
            elif self.llm_provider == 'anthropic' and self.anthropic_client:
                return self._call_anthropic(prompt, system_prompt, temperature, max_tokens)
            else:
                # Fallback to available provider
                if self.openai_client:
                    return self._call_openai(prompt, system_prompt, temperature, max_tokens)
                elif self.anthropic_client:
                    return self._call_anthropic(prompt, system_prompt, temperature, max_tokens)
                else:
                    raise ValueError("No LLM provider configured")
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise
    
    def _call_openai(
        self,
        prompt: str,
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: int
    ) -> str:
        """Call OpenAI API."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        response = self.openai_client.chat.completions.create(
            model=settings.DEFAULT_LLM_MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        return response.choices[0].message.content
    
    def _call_anthropic(
        self,
        prompt: str,
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: int
    ) -> str:
        """Call Anthropic API."""
        message = self.anthropic_client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt or "",
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text
    
    def get_page_count(self) -> int:
        """Get number of pages in PDF."""
        try:
            with open(self.file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                return len(pdf_reader.pages)
        except Exception as e:
            logger.error(f"Failed to get page count: {e}")
            return 0
    
    @abstractmethod
    def extract_structured_data(self) -> Dict[str, Any]:
        """
        Extract structured data specific to document type.
        Must be implemented by subclasses.
        """
        pass
    
    @abstractmethod
    def extract_for_semantic_search(self) -> List[Dict[str, Any]]:
        """
        Extract and chunk content for semantic search.
        Must be implemented by subclasses.
        """
        pass
    
    def validate_extraction(self, data: Dict[str, Any]) -> bool:
        """
        Validate extracted data.
        Can be overridden by subclasses for custom validation.
        """
        return bool(data)


class ExtractionError(Exception):
    """Custom exception for extraction errors."""
    pass