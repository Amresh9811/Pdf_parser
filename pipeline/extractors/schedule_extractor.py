"""
Extractor for Project Schedule Documents.
"""

import re
import json
from typing import Dict, List, Any
from datetime import datetime, date
from loguru import logger
import pandas as pd

from .base_extractor import BaseExtractor, ExtractionError


class ProjectScheduleExtractor(BaseExtractor):
    """
    Extracts task schedule data from Gantt-like project schedules.
    """
    
    def extract_structured_data(self) -> Dict[str, Any]:
        """
        Extract project tasks with IDs, names, durations, and dates.
        Returns: Dict with 'tasks' list.
        """
        logger.info(f"Starting schedule extraction for {self.file_name}")
        
        # Try table extraction first
        tasks = self._extract_from_tables()
        
        # If table extraction fails, try LLM
        if len(tasks) < 5:
            logger.info("Supplementing table extraction with LLM")
            llm_tasks = self._extract_with_llm()
            tasks.extend(llm_tasks)
        
        # Deduplicate by task_id
        tasks = self._deduplicate_tasks(tasks)
        
        if not tasks:
            raise ExtractionError("Failed to extract any tasks")
        
        logger.info(f"Successfully extracted {len(tasks)} tasks")
        return {"tasks": tasks}
    
    def _extract_from_tables(self) -> List[Dict[str, Any]]:
        """Extract tasks from schedule tables."""
        tables = self.extract_tables_pdfplumber()
        if not tables:
            return []
        
        tasks = []
        
        for table_idx, table in enumerate(tables):
            try:
                if not table or len(table) < 2:
                    continue
                
                # Convert to DataFrame
                df = pd.DataFrame(table[1:], columns=table[0])
                
                # Clean column names
                df.columns = [str(col).strip().lower() if col else f'col_{i}' 
                             for i, col in enumerate(df.columns)]
                
                # Identify columns
                id_col = self._find_column(df, ['id', 'task id', 'task_id', 'no'])
                name_col = self._find_column(df, ['task name', 'task', 'activity', 'description'])
                duration_col = self._find_column(df, ['duration', 'dur', 'days'])
                start_col = self._find_column(df, ['start', 'start date', 'begin'])
                finish_col = self._find_column(df, ['finish', 'end', 'end date', 'completion'])
                
                if not (id_col and name_col):
                    continue
                
                for _, row in df.iterrows():
                    try:
                        task = self._parse_task_row(
                            row, id_col, name_col, duration_col, 
                            start_col, finish_col
                        )
                        if task:
                            tasks.append(task)
                    except Exception as e:
                        logger.debug(f"Skipped row: {e}")
                        continue
                        
            except Exception as e:
                logger.error(f"Error processing table {table_idx}: {e}")
                continue
        
        return tasks
    
    def _find_column(self, df: pd.DataFrame, possible_names: List[str]) -> str:
        """Find column name from possibilities."""
        for col in df.columns:
            for name in possible_names:
                if name in str(col).lower():
                    return col
        return None
    
    def _parse_task_row(
    self,
    row: pd.Series,
    id_col: str,
    name_col: str,
    duration_col: str,
    start_col: str,
    finish_col: str
) -> Dict[str, Any]:
        """Parse a single task row."""
        
        # Extract task ID
        task_id = str(row[id_col]).strip()
        if not task_id or task_id.lower() in ['nan', 'none', '']:
            return None
        
        try:
            task_id = int(float(task_id))
        except:
            return None
        
        # Extract task name
        task_name = str(row[name_col]).strip()
        if not task_name or task_name.lower() in ['nan', 'none', '']:
            return None
        
        # Extract duration
        duration = 0
        if duration_col and pd.notna(row.get(duration_col)):
            duration = self._parse_duration(row[duration_col])
        
        # Extract dates
        start_date = None
        if start_col and pd.notna(row.get(start_col)):
            start_date = self._parse_date(row[start_col])
        
        finish_date = None
        if finish_col and pd.notna(row.get(finish_col)):
            finish_date = self._parse_date(row[finish_col])
        
        # Calculate missing values if possible
        if start_date and finish_date and duration == 0:
            duration = (finish_date - start_date).days
        
        return {
            "task_id": task_id,
            "task_name": task_name,
            "duration_days": duration,
            "start_date": start_date.isoformat() if start_date else None,  # CHANGED: Allow None
            "finish_date": finish_date.isoformat() if finish_date else None  # CHANGED: Allow None
        }
    
    def _parse_duration(self, value: Any) -> int:
        """Parse duration value."""
        if pd.isna(value):
            return 0
        
        value_str = str(value).strip()
        
        # Extract number
        match = re.search(r'(\d+)', value_str)
        if match:
            return int(match.group(1))
        
        return 0
    
    def _parse_date(self, value: Any) -> date:
        """Parse date value."""
        if pd.isna(value):
            return None
        
        value_str = str(value).strip()
        
        # Try common date formats
        date_formats = [
            '%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y',
            '%Y/%m/%d', '%m-%d-%Y', '%d-%m-%Y'
        ]
        
        for fmt in date_formats:
            try:
                return datetime.strptime(value_str, fmt).date()
            except:
                continue
        
        return None
    
    def _extract_with_llm(self) -> List[Dict[str, Any]]:
        """Use LLM to extract tasks."""
        text = self.extract_text_pdfplumber()
        
        system_prompt = """You are a project management expert. Extract task information from project schedules.
Return a JSON array with this structure:
{
  "tasks": [
    {
      "task_id": number,
      "task_name": "string",
      "duration_days": number,
      "start_date": "YYYY-MM-DD",
      "finish_date": "YYYY-MM-DD"
    }
  ]
}

Extract all tasks with their IDs, names, durations, and dates."""

        user_prompt = f"""Extract all tasks from this project schedule:

{text[:8000]}

Return valid JSON only."""

        try:
            response = self.call_llm(
                prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=0.1,
                max_tokens=4000
            )
            
            # Parse JSON
            json_str = response.strip()
            if json_str.startswith('```'):
                json_str = re.sub(r'```json\s*', '', json_str)
                json_str = re.sub(r'```\s*$', '', json_str)
            
            data = json.loads(json_str)
            return data.get('tasks', [])
            
        except Exception as e:
            logger.error(f"LLM extraction failed: {e}")
            return []
    
    def _deduplicate_tasks(self, tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate tasks."""
        seen = set()
        unique_tasks = []
        
        for task in tasks:
            key = task['task_id']
            if key not in seen:
                seen.add(key)
                unique_tasks.append(task)
        
        return unique_tasks
    
    def extract_for_semantic_search(self) -> List[Dict[str, Any]]:
        """Extract and chunk content for semantic search."""
        text = self.extract_text_pdfplumber()
        
        chunks = []
        
        # Chunk the full text
        text_chunks = self._chunk_text(text, chunk_size=1000, overlap=200)
        
        for idx, chunk in enumerate(text_chunks):
            chunks.append({
                "content": chunk,
                "metadata": {
                    "document_type": "schedule",
                    "file_name": self.file_name,
                    "chunk_index": idx,
                    "content_type": "text"
                }
            })
        
        return chunks
    
    def _chunk_text(self, text: str, chunk_size: int, overlap: int) -> List[str]:
        """Split text into overlapping chunks."""
        chunks = []
        start = 0
        text_length = len(text)
        
        while start < text_length:
            end = start + chunk_size
            chunk = text[start:end]
            
            if end < text_length:
                last_period = chunk.rfind('.')
                last_newline = chunk.rfind('\n')
                break_point = max(last_period, last_newline)
                
                if break_point > chunk_size // 2:
                    chunk = chunk[:break_point + 1]
                    end = start + len(chunk)
            
            chunks.append(chunk.strip())
            start = end - overlap
        
        return chunks