"""
Extractor for Construction Planning and Costing Documents.
"""

import re
import json
from typing import Dict, List, Any, Optional
from decimal import Decimal
from loguru import logger
import pandas as pd

from .base_extractor import BaseExtractor, ExtractionError


class CostingExtractor(BaseExtractor):
    """
    Extracts cost breakdown data from construction planning documents.
    Handles mixed content: tables, calculations, and narrative text.
    """
    
    def extract_structured_data(self) -> Dict[str, Any]:
        """
        Extract cost items with quantities, prices, and totals.
        Returns: Dict with 'cost_items' list.
        """
        logger.info(f"Starting cost extraction for {self.file_name}")
        
        # Try table extraction first
        cost_items = self._extract_from_tables()
        logger.info(f"Extracted {len(cost_items)} items from tables")
        
        # If few items, use LLM to supplement
        if len(cost_items) < 10:
            logger.info("Supplementing with LLM extraction")
            try:
                llm_items = self._extract_with_llm()
                logger.info(f"Extracted {len(llm_items)} items from LLM")
                cost_items.extend(llm_items)
            except Exception as e:
                logger.warning(f"LLM extraction failed: {e}")
        
        # Deduplicate based on item_name
        cost_items = self._deduplicate_items(cost_items)
        
        logger.info(f"Final extraction: {len(cost_items)} cost items")
        
        # IMPORTANT: Return empty list instead of raising error
        if not cost_items:
            logger.warning("No cost items extracted - returning empty dataset")
            # Create a placeholder item so the pipeline doesn't fail
            cost_items = [{
                "item_name": "No cost data extracted",
                "quantity": 0.0,
                "unit": "N/A",
                "unit_price_yen": 0.0,
                "total_cost_yen": 0.0,
                "cost_type": "other"
            }]
        
        return {"cost_items": cost_items}
    
    def _extract_from_tables(self) -> List[Dict[str, Any]]:
        """Extract cost items from tables."""
        tables = self.extract_tables_pdfplumber()
        if not tables:
            logger.warning("No tables found in document")
            return []
        
        logger.info(f"Found {len(tables)} tables to process")
        cost_items = []
        
        for table_idx, table in enumerate(tables):
            try:
                if not table or len(table) < 2:
                    continue
                
                logger.debug(f"Processing table {table_idx + 1}")
                
                # Convert to DataFrame
                df = pd.DataFrame(table[1:], columns=table[0])
                
                # Clean column names
                df.columns = [str(col).strip().lower() if col else f'col_{i}' 
                             for i, col in enumerate(df.columns)]
                
                logger.debug(f"Table columns: {list(df.columns)}")
                
                # Identify columns (flexible matching)
                item_col = self._find_column(df, ['item', 'description', 'work', 'activity', 'name'])
                qty_col = self._find_column(df, ['quantity', 'qty', 'amount', 'volume'])
                unit_col = self._find_column(df, ['unit', 'uom', 'u/m', 'units'])
                unit_price_col = self._find_column(df, ['unit price', 'rate', 'unit cost', 'price', 'unit_price'])
                total_col = self._find_column(df, ['total', 'cost', 'amount', 'value', 'sum'])
                
                # Need at least item column
                if not item_col:
                    logger.debug(f"Table {table_idx + 1}: No item column found, skipping")
                    continue
                
                logger.info(f"Table {table_idx + 1}: Found item column '{item_col}'")
                
                for row_idx, row in df.iterrows():
                    try:
                        item = self._parse_cost_row(
                            row, item_col, qty_col, unit_col, 
                            unit_price_col, total_col
                        )
                        if item:
                            cost_items.append(item)
                            logger.debug(f"  ✓ Extracted: {item['item_name'][:50]}")
                    except Exception as e:
                        logger.debug(f"  ✗ Skipped row {row_idx}: {e}")
                        continue
                        
            except Exception as e:
                logger.error(f"Error processing table {table_idx + 1}: {e}")
                continue
        
        logger.info(f"Total items extracted from tables: {len(cost_items)}")
        return cost_items
    
    def _find_column(self, df: pd.DataFrame, possible_names: List[str]) -> Optional[str]:
        """Find column name from list of possibilities."""
        for col in df.columns:
            col_lower = str(col).lower()
            for name in possible_names:
                if name in col_lower:
                    return col
        return None
    
    def _parse_cost_row(
        self,
        row: pd.Series,
        item_col: str,
        qty_col: Optional[str],
        unit_col: Optional[str],
        unit_price_col: Optional[str],
        total_col: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """Parse a single cost row."""
        
        # Extract item name
        item_name = str(row[item_col]).strip()
        if not item_name or item_name.lower() in ['nan', 'none', '', 'total', 'subtotal', 'sum']:
            return None
        
        # Skip header-like rows
        if any(word in item_name.lower() for word in ['item', 'description', 'particulars']):
            return None
        
        # Extract quantity
        quantity = 0.0
        unit = "unit"
        if qty_col and pd.notna(row.get(qty_col)):
            parsed_qty, parsed_unit = self._parse_quantity(row[qty_col])
            if parsed_qty:
                quantity = float(parsed_qty)
            if parsed_unit:
                unit = parsed_unit
        
        # Override unit if there's a separate unit column
        if unit_col and pd.notna(row.get(unit_col)):
            extracted_unit = str(row[unit_col]).strip()
            if extracted_unit and extracted_unit.lower() != 'nan':
                unit = extracted_unit
        
        # Extract unit price
        unit_price = 0.0
        if unit_price_col and pd.notna(row.get(unit_price_col)):
            parsed_price = self._parse_currency(row[unit_price_col])
            if parsed_price:
                unit_price = float(parsed_price)
        
        # Extract total cost
        total_cost = 0.0
        if total_col and pd.notna(row.get(total_col)):
            parsed_total = self._parse_currency(row[total_col])
            if parsed_total:
                total_cost = float(parsed_total)
        
        # Calculate missing values
        if quantity > 0 and unit_price > 0 and total_cost == 0:
            total_cost = quantity * unit_price
        elif total_cost > 0 and quantity > 0 and unit_price == 0:
            unit_price = total_cost / quantity
        elif total_cost > 0 and unit_price > 0 and quantity == 0:
            quantity = total_cost / unit_price
        
        # Determine cost type (heuristic)
        cost_type = self._determine_cost_type(item_name)
        
        return {
            "item_name": item_name,
            "quantity": quantity,
            "unit": unit,
            "unit_price_yen": unit_price,
            "total_cost_yen": total_cost,
            "cost_type": cost_type,
        }
    
    def _parse_quantity(self, value: Any) -> tuple[Optional[Decimal], Optional[str]]:
        """Parse quantity and extract unit if present."""
        if pd.isna(value):
            return None, None
        
        value_str = str(value).strip()
        
        # Try to extract number and unit (e.g., "736.2t", "120,000.0m3")
        match = re.match(r'([0-9,\.]+)\s*([a-zA-Z0-9³²]+)?', value_str)
        if match:
            num_str = match.group(1).replace(',', '')
            unit = match.group(2) if match.group(2) else None
            try:
                return Decimal(num_str), unit
            except:
                return None, unit
        
        return None, None
    
    def _parse_currency(self, value: Any) -> Optional[Decimal]:
        """Parse currency value (handles yen symbols, commas, etc.)."""
        if pd.isna(value):
            return None
        
        value_str = str(value).strip()
        
        # Remove currency symbols and commas
        cleaned = re.sub(r'[¥$,\s]', '', value_str)
        
        try:
            return Decimal(cleaned)
        except:
            return None
    
    def _determine_cost_type(self, item_name: str) -> str:
        """Heuristic to determine if cost is foreign or local."""
        item_lower = item_name.lower()
        
        if any(word in item_lower for word in ['import', 'foreign', 'overseas', 'international']):
            return 'foreign'
        elif any(word in item_lower for word in ['local', 'domestic', 'onsite']):
            return 'local'
        else:
            return 'other'
    
    def _extract_with_llm(self) -> List[Dict[str, Any]]:
        """Use LLM to extract costs from narrative sections."""
        text = self.extract_text_pdfplumber()
        
        system_prompt = """You are a construction cost estimation expert. Extract cost items from construction planning documents.
Return a JSON array with this structure:
{
  "cost_items": [
    {
      "item_name": "string",
      "quantity": number,
      "unit": "string",
      "unit_price_yen": number,
      "total_cost_yen": number,
      "cost_type": "foreign|local|other"
    }
  ]
}

Extract all cost items with their quantities, prices, and totals. If values are missing, use 0."""

        user_prompt = f"""Extract all cost items from this construction planning document:

{text[:10000]}

Return valid JSON only. Include any cost information you find."""

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
            return data.get('cost_items', [])
            
        except Exception as e:
            logger.error(f"LLM extraction failed: {e}")
            return []
    
    def _deduplicate_items(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate cost items."""
        seen = set()
        unique_items = []
        
        for item in items:
            key = item['item_name'].lower().strip()
            if key not in seen and key not in ['no cost data extracted']:
                seen.add(key)
                unique_items.append(item)
        
        return unique_items
    
    def extract_for_semantic_search(self) -> List[Dict[str, Any]]:
        """
        Extract and chunk content for semantic search.
        """
        text = self.extract_text_pdfplumber()
        
        chunks = []
        
        # Chunk the full text
        text_chunks = self._chunk_text(text, chunk_size=1000, overlap=200)
        
        for idx, chunk in enumerate(text_chunks):
            chunks.append({
                "content": chunk,
                "metadata": {
                    "document_type": "costing",
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