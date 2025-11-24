"""
Base extractor class for document processing.
"""
"""
Base extractor class for document processing.
"""

import pdfplumber
import PyPDF2
from typing import List, Dict, Any, Optional
from pathlib import Path
from loguru import logger
import os
from openai import OpenAI
from anthropic import Anthropic
from django.conf import settings


class ExtractionError(Exception):
    """Custom exception for extraction errors."""
    pass


class BaseExtractor:
    """
    Base class for document extractors.
    Provides common functionality for PDF processing.
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
    
    def _extract_text_from_page(self, page_number: int) -> str:
        """Extract text from a specific page using pdfplumber."""
        try:
            with pdfplumber.open(self.file_path) as pdf:
                if 0 <= page_number < len(pdf.pages):
                    page = pdf.pages[page_number]
                    return page.extract_text() or ""
        except Exception as e:
            logger.error(f"Error extracting text from page {page_number + 1}: {e}")
        return ""
    
    def _extract_all_text(self) -> str:
        """Extract all text from the PDF."""
        full_text = ""
        try:
            with pdfplumber.open(self.file_path) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        full_text += text + "\n"
        except Exception as e:
            logger.error(f"Error extracting all text: {e}")
        return full_text
    
    def _extract_tables_from_page(self, page_number: int) -> List[List[List[Any]]]:
        """
        Extract all tables from a specific page.
        
        Args:
            page_number: Zero-indexed page number
            
        Returns:
            List of tables, where each table is a list of rows
        """
        tables = []
        try:
            with pdfplumber.open(self.file_path) as pdf:
                if 0 <= page_number < len(pdf.pages):
                    page = pdf.pages[page_number]
                    page_tables = page.extract_tables()
                    
                    if page_tables:
                        # Clean the tables
                        for table in page_tables:
                            if table:
                                # Remove None values and clean cells
                                cleaned_table = []
                                for row in table:
                                    if row:
                                        cleaned_row = [str(cell).strip() if cell else "" for cell in row]
                                        cleaned_table.append(cleaned_row)
                                
                                if cleaned_table:
                                    tables.append(cleaned_table)
        
        except Exception as e:
            logger.error(f"Error extracting tables from page {page_number + 1}: {e}")
        
        return tables
    
    def _extract_all_tables(self) -> List[Dict[str, Any]]:
        """Extract all tables from the PDF with page information."""
        all_tables = []
        try:
            with pdfplumber.open(self.file_path) as pdf:
                for page_num, page in enumerate(pdf.pages):
                    tables = page.extract_tables()
                    if tables:
                        for table_idx, table in enumerate(tables):
                            if table:
                                all_tables.append({
                                    'page': page_num + 1,
                                    'table_index': table_idx,
                                    'data': table
                                })
        except Exception as e:
            logger.error(f"Error extracting all tables: {e}")
        return all_tables
    
    def _call_llm(self, prompt: str, temperature: float = 0.1, max_tokens: int = 4000) -> str:
        """
        Call LLM (OpenAI or Anthropic) with fallback.
        
        Args:
            prompt: The prompt to send
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response
            
        Returns:
            LLM response text
        """
        # Try OpenAI first
        if self.openai_client:
            try:
                response = self.openai_client.chat.completions.create(
                    model=os.getenv('DEFAULT_LLM_MODEL', 'gpt-4o-mini'),
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant that extracts structured data from documents."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                return response.choices[0].message.content
            except Exception as e:
                logger.error(f"OpenAI API error: {e}")
        
        # Fallback to Anthropic
        if self.anthropic_client:
            try:
                response = self.anthropic_client.messages.create(
                    model=os.getenv('DEFAULT_LLM_MODEL', 'claude-3-5-sonnet-20241022'),
                    max_tokens=max_tokens,
                    temperature=temperature,
                    messages=[
                        {"role": "user", "content": prompt}
                    ]
                )
                return response.content[0].text
            except Exception as e:
                logger.error(f"Anthropic API error: {e}")
        
        raise Exception("No LLM provider available")
    
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
    
    def extract_structured_data(self) -> List[Dict[str, Any]]:
        """Extract structured data. To be implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement extract_structured_data")
    
    def extract_for_semantic_search(self) -> List[Dict[str, Any]]:
        """Extract and chunk text for semantic search. To be implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement extract_for_semantic_search")
    
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