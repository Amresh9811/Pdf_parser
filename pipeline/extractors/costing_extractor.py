"""
Costing extractor for construction documents.
Extracts cost items, quantities, and unit prices.
"""

import re
from typing import List, Dict, Any, Optional
from decimal import Decimal
from loguru import logger

from pipeline.extractors.base_extractor import BaseExtractor


class CostingExtractor(BaseExtractor):
    """
    Extractor for construction costing documents.
    Focuses on Civil Works Cost Summary tables with unit prices.
    """
    
    def __init__(self, file_path: str):
        super().__init__(file_path)
        self.document_type = "costing"
    
    def extract_structured_data(self) -> List[Dict[str, Any]]:
        """
        Extract cost items from Civil Works Cost Summary tables.
        
        Returns:
            List of cost item dictionaries
        """
        logger.info(f"Extracting costing data from {self.file_path}")
        
        cost_items = []
        
        # Strategy 1: Extract from summary tables (pages 18-20)
        cost_items.extend(self._extract_from_summary_tables())
        
        # Strategy 2: Extract from unit price table (page 25)
        cost_items.extend(self._extract_from_unit_price_table())
        
        # Strategy 3: LLM extraction if insufficient data
        if len(cost_items) < 5:
            logger.warning("Insufficient cost items extracted, trying LLM extraction")
            llm_items = self._extract_with_llm()
            cost_items.extend(llm_items)
        
        # Remove duplicates
        cost_items = self._deduplicate_items(cost_items)
        
        logger.info(f"Extracted {len(cost_items)} cost items")
        return cost_items
    
    def _extract_from_summary_tables(self) -> List[Dict[str, Any]]:
        """
        Extract from Civil Works Cost Summary Tables.
        Targets pages 18-20 which contain detailed cost breakdowns.
        """
        cost_items = []
        
        # Pages with cost summary data (18-20 = indices 17-19)
        target_pages = [17, 18, 19, 20, 21, 22, 23]
        
        for page_num in target_pages:
            try:
                tables = self._extract_tables_from_page(page_num)
                
                for table in tables:
                    if len(table) < 2:
                        continue
                    
                    # Check if this is a cost table
                    header_row = ' '.join(table[0]).lower()
                    
                    if 'unit price' not in header_row and 'construction expense' not in header_row:
                        continue
                    
                    logger.info(f"Processing cost table on page {page_num + 1}")
                    
                    # Find column indices
                    col_indices = self._identify_columns(table[0])
                    
                    # Process data rows
                    for row in table[1:]:
                        item = self._parse_cost_row(row, col_indices)
                        if item:
                            cost_items.append(item)
                
            except Exception as e:
                logger.debug(f"Error on page {page_num + 1}: {e}")
                continue
        
        return cost_items
    
    def _identify_columns(self, header_row: List[str]) -> Dict[str, int]:
        """Identify which columns contain which data."""
        columns = {
            'item': -1,
            'unit': -1,
            'unit_price': -1,
            'quantity': -1
        }
        
        for idx, cell in enumerate(header_row):
            cell_lower = str(cell).lower()
            
            if 'work item' in cell_lower or 'item' in cell_lower:
                columns['item'] = idx
            elif 'unit price' in cell_lower or 'rp' in cell_lower:
                columns['unit_price'] = idx
            elif cell_lower in ['unit', 'm', 'm2', 'm3', 't', 'ton', 'km', 'no']:
                columns['unit'] = idx
            elif 'quantity' in cell_lower:
                columns['quantity'] = idx
        
        return columns
    
    def _parse_cost_row(self, row: List[str], col_indices: Dict[str, int]) -> Optional[Dict[str, Any]]:
        """Parse a single cost table row."""
        try:
            # Get item name
            item_name = None
            if col_indices['item'] >= 0 and col_indices['item'] < len(row):
                item_name = row[col_indices['item']].strip()
            else:
                # Fallback: find first non-numeric column
                for cell in row:
                    if cell and not self._is_numeric(cell):
                        item_name = cell.strip()
                        break
            
            if not item_name or len(item_name) < 2:
                return None
            
            # Skip header-like rows
            skip_keywords = ['work item', 'unit price', 'no', 'recapitulation', 'stage', 'total']
            if any(kw in item_name.lower() for kw in skip_keywords):
                return None
            
            # Get unit
            unit = 'unit'
            if col_indices['unit'] >= 0 and col_indices['unit'] < len(row):
                unit = row[col_indices['unit']].strip() or 'unit'
            
            # Get unit price and costs
            unit_price = Decimal('0')
            total_cost = Decimal('0')
            
            for cell in row:
                if not cell:
                    continue
                
                value = self._parse_currency(cell)
                if value > 0:
                    # Unit prices typically < 100M, total costs can be larger
                    if value < 100_000_000:
                        unit_price = max(unit_price, value)
                    total_cost = max(total_cost, value)
            
            # Must have at least some cost data
            if unit_price == 0 and total_cost == 0:
                return None
            
            # If only total cost, derive unit price
            if unit_price == 0:
                unit_price = total_cost
            
            # Determine cost type
            cost_type = 'other'
            item_lower = item_name.lower()
            if 'foreign' in item_lower or 'currency' in item_lower:
                cost_type = 'foreign'
            elif 'local' in item_lower:
                cost_type = 'local'
            
            return {
                'item_name': item_name,
                'quantity': 1.0,
                'unit': unit if unit else 'unit',
                'unit_price_yen': float(unit_price),
                'total_cost_yen': float(total_cost if total_cost > 0 else unit_price),
                'cost_type': cost_type
            }
            
        except Exception as e:
            logger.debug(f"Error parsing row: {e}")
            return None
    
    def _extract_from_unit_price_table(self) -> List[Dict[str, Any]]:
        """Extract from Unit Price Table (page 25)."""
        cost_items = []
        
        try:
            # Page 25 is index 24
            tables = self._extract_tables_from_page(24)
            
            for table in tables:
                if len(table) < 2:
                    continue
                
                header = ' '.join(table[0]).lower()
                if 'unit price' not in header:
                    continue
                
                logger.info("Processing unit price table")
                
                for row in table[1:]:
                    if len(row) < 3:
                        continue
                    
                    try:
                        # Format: [No, Work item, Unit, Unit price (Rp)]
                        item_name = row[1].strip() if len(row) > 1 else ""
                        unit = row[2].strip() if len(row) > 2 else "unit"
                        unit_price_str = row[3].strip() if len(row) > 3 else "0"
                        
                        if not item_name or item_name.lower() in ['work item', 'no']:
                            continue
                        
                        unit_price = self._parse_currency(unit_price_str)
                        
                        if unit_price > 0:
                            cost_items.append({
                                'item_name': item_name,
                                'quantity': 1.0,
                                'unit': unit,
                                'unit_price_yen': float(unit_price),
                                'total_cost_yen': float(unit_price),
                                'cost_type': 'unit_price'
                            })
                    
                    except Exception as e:
                        logger.debug(f"Error parsing unit price row: {e}")
                        continue
        
        except Exception as e:
            logger.error(f"Error extracting unit price table: {e}")
        
        return cost_items
    
    def _extract_with_llm(self) -> List[Dict[str, Any]]:
        """Use LLM to extract cost data from text."""
        try:
            # Extract text from cost pages (18-25)
            cost_text = ""
            for page_num in range(17, 25):
                try:
                    page_text = self._extract_text_from_page(page_num)
                    if page_text:
                        cost_text += page_text + "\n\n"
                except:
                    continue
            
            if not cost_text or len(cost_text) < 100:
                logger.error("Insufficient text for LLM extraction")
                return []
            
            # Limit context size
            cost_text = cost_text[:20000]
            
            prompt = f"""Extract construction cost items from this document.

Document text:
{cost_text}

Extract items with:
- item_name: work item description
- quantity: number (default 1)
- unit: m, m2, m3, t, ton, km, no, set
- unit_price_yen: unit price in Rupiah
- total_cost_yen: total cost in Rupiah
- cost_type: "foreign", "local", or "other"

Focus on items from EARTH WORKS, BRIDGE WORKS, and DRAIN WORKER sections.

Return a JSON array with at least 20 items. Example:
[
  {{
    "item_name": "Land preparation",
    "quantity": 1.0,
    "unit": "m2",
    "unit_price_yen": 15362,
    "total_cost_yen": 15362,
    "cost_type": "other"
  }}
]

Return ONLY the JSON array, no other text."""

            response = self._call_llm(prompt, temperature=0.1, max_tokens=3000)
            
            # Extract JSON
            json_match = re.search(r'\[.*\]', response, re.DOTALL)
            if json_match:
                import json
                items = json.loads(json_match.group())
                logger.info(f"LLM extracted {len(items)} items")
                return items
            
        except Exception as e:
            logger.error(f"LLM extraction failed: {e}")
        
        return []
    
    def _is_numeric(self, text: str) -> bool:
        """Check if text is primarily numeric."""
        if not text:
            return False
        cleaned = text.replace(',', '').replace('.', '').replace(' ', '').replace('-', '')
        return len(cleaned) > 0 and sum(c.isdigit() for c in cleaned) / len(cleaned) > 0.5
    
    def _parse_currency(self, text: str) -> Decimal:
        """Parse currency value from text."""
        if not text:
            return Decimal('0')
        
        try:
            # Clean the text
            cleaned = str(text).replace('Rp', '').replace('yen', '').replace(' ', '').strip()
            cleaned = cleaned.replace(',', '')
            
            # Handle parentheses (negatives)
            if '(' in cleaned:
                cleaned = cleaned.replace('(', '-').replace(')', '')
            
            # Extract number
            match = re.search(r'-?\d+\.?\d*', cleaned)
            if match:
                return Decimal(match.group())
            
        except Exception as e:
            logger.debug(f"Currency parse error for '{text}': {e}")
        
        return Decimal('0')
    
    def _deduplicate_items(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate cost items."""
        seen = set()
        unique_items = []
        
        for item in items:
            # Create a key from item name
            key = item['item_name'].lower().strip()
            
            if key not in seen:
                seen.add(key)
                unique_items.append(item)
        
        return unique_items
    
    def extract_for_semantic_search(self) -> List[Dict[str, Any]]:
        """Create semantic search chunks."""
        chunks = []
        
        # Extract all text
        full_text = self._extract_all_text()
        
        if not full_text:
            logger.warning("No text extracted for semantic search")
            return chunks
        
        # Create overlapping chunks
        chunk_size = 1000
        overlap = 200
        
        for i in range(0, len(full_text), chunk_size - overlap):
            chunk_text = full_text[i:i + chunk_size]
            
            if len(chunk_text) < 100:
                continue
            
            chunks.append({
                'text': chunk_text,
                'metadata': {
                    'document_type': 'costing',
                    'chunk_index': len(chunks),
                    'file_name': self.file_name
                }
            })
        
        logger.info(f"Created {len(chunks)} semantic chunks")
        return chunks
    