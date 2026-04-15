"""
CSV/TSV Formatter - Handles CSV and TSV export formats
"""

import csv
import io
from typing import Any, List, Union
from datetime import datetime

from ..base_formatter import BaseFormatter, FormatType


class CSVFormatter(BaseFormatter):
    """Formatter for CSV and TSV (tab-separated) formats"""
    
    def __init__(self, include_headers: bool = True, encoding: str = 'utf-8',
                 delimiter: str = ',', quotechar: str = '"',
                 quoting: int = csv.QUOTE_MINIMAL):
        """
        Initialize CSV/TSV formatter
        
        Args:
            include_headers: Whether to include column headers
            encoding: Character encoding
            delimiter: Field delimiter (',' for CSV, '\\t' for TSV)
            quotechar: Quote character
            quoting: CSV quoting mode
        """
        super().__init__(include_headers=include_headers, encoding=encoding)
        self.delimiter = delimiter
        self.quotechar = quotechar
        self.quoting = quoting
        
        # Determine format type based on delimiter
        self._format_type = FormatType.TSV if delimiter == '\t' else FormatType.CSV
    
    @property
    def format_type(self) -> FormatType:
        return self._format_type
    
    def format(self, data: Any, **kwargs) -> str:
        """
        Format data as CSV/TSV string
        
        Args:
            data: Data to format (DataFrame, list of dicts, list of lists)
            **kwargs: Additional options (override constructor settings)
            
        Returns:
            CSV/TSV formatted string
        """
        # Override settings if provided
        delimiter = kwargs.get('delimiter', self.delimiter)
        include_headers = kwargs.get('include_headers', self.include_headers)
        
        # Validate data
        if not self.validate_data(data):
            return ""
        
        # Convert data to list of records
        records = self._convert_to_records(data)
        
        if not records:
            self._warnings.append("No records to export")
            return ""
        
        # Get headers from first record
        headers = list(records[0].keys()) if isinstance(records[0], dict) else None
        
        # Create output buffer
        output = io.StringIO()
        
        # Create writer
        writer = csv.DictWriter(
            output,
            fieldnames=headers,
            delimiter=delimiter,
            quotechar=self.quotechar,
            quoting=self.quoting,
            extrasaction='ignore'
        )
        
        # Write headers
        if include_headers and headers:
            writer.writeheader()
        
        # Write data
        for record in records:
            # Sanitize values
            sanitized = {k: self.sanitize_value(v) for k, v in record.items()}
            writer.writerow(sanitized)
        
        return output.getvalue()
    
    def _convert_to_records(self, data: Any) -> List[dict]:
        """Convert various data types to list of dictionaries"""
        # Handle pandas DataFrame
        try:
            import pandas as pd
            if isinstance(data, pd.DataFrame):
                # Convert datetime columns to strings
                for col in data.columns:
                    if pd.api.types.is_datetime64_any_dtype(data[col]):
                        data[col] = data[col].dt.isoformat()
                return data.to_dict('records')
        except ImportError:
            pass
        
        # Handle list of dictionaries
        if isinstance(data, list) and data and isinstance(data[0], dict):
            return data
        
        # Handle SQLAlchemy Row objects - convert to dict
        if isinstance(data, list) and data:
            first_item = data[0]
            # Check if it's a Row-like object
            if hasattr(first_item, '_mapping'):
                return [dict(row._mapping) for row in data]
            elif hasattr(first_item, 'keys'):
                return [dict(row) for row in data]
            elif hasattr(first_item, '__dict__'):
                # It's an object, convert attributes to dict
                return [{k: v for k, v in vars(row).items() if not k.startswith('_')} for row in data]
        
        # Handle list of lists
        if isinstance(data, list) and data and isinstance(data[0], list):
            # Assume first row is headers
            if self.include_headers and len(data) > 1:
                headers = data[0]
                return [dict(zip(headers, row)) for row in data[1:]]
            else:
                headers = [f"Column_{i}" for i in range(len(data[0]))]
                return [dict(zip(headers, row)) for row in data]
        
        # Handle single dictionary
        if isinstance(data, dict):
            return [data]
        
        # Handle other iterables
        try:
            return list(data)
        except:
            self._errors.append(f"Unsupported data type: {type(data)}")
            return []
    
    def format_to_bytes(self, data: Any, **kwargs) -> bytes:
        """Format data as CSV/TSV bytes"""
        return self.format(data, **kwargs).encode(self.encoding)


class TSVFormatter(CSVFormatter):
    """Formatter specifically for TSV (tab-separated values)"""
    
    def __init__(self, include_headers: bool = True, encoding: str = 'utf-8'):
        super().__init__(
            include_headers=include_headers,
            encoding=encoding,
            delimiter='\t'
        )
    
    @property
    def format_type(self) -> FormatType:
        return FormatType.TSV
