"""
TXT Formatter - Handles plain text export format
"""

import io
from typing import Any, List
from datetime import datetime

from ..base_formatter import BaseFormatter, FormatType


class TXTFormatter(BaseFormatter):
    """Formatter for plain text format"""
    
    def __init__(self, include_headers: bool = True, encoding: str = 'utf-8',
                 column_width: int = 20, separator: str = " | "):
        """
        Initialize TXT formatter
        
        Args:
            include_headers: Whether to include column headers
            encoding: Character encoding
            column_width: Width for each column
            separator: Separator between columns
        """
        super().__init__(include_headers=include_headers, encoding=encoding)
        self.column_width = column_width
        self.separator = separator
    
    @property
    def format_type(self) -> FormatType:
        return FormatType.TXT
    
    def format(self, data: Any, **kwargs) -> str:
        """
        Format data as plain text string
        
        Args:
            data: Data to format
            **kwargs: Additional options
            
        Returns:
            Plain text formatted string
        """
        if not self.validate_data(data):
            return "No data available.\n"
        
        # Override settings if provided
        column_width = kwargs.get('column_width', self.column_width)
        separator = kwargs.get('separator', self.separator)
        include_headers = kwargs.get('include_headers', self.include_headers)
        
        # Convert data to records
        records = self._convert_to_records(data)
        
        if not records:
            return "No records to export.\n"
        
        # Get headers
        headers = list(records[0].keys()) if records else []
        
        # Build output
        output = io.StringIO()
        
        # Add title
        output.write("=" * (len(headers) * (column_width + len(separator)) - len(separator)) + "\n")
        output.write(f"Export Report - Generated {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        output.write(f"Total Records: {len(records)}\n")
        output.write("=" * (len(headers) * (column_width + len(separator)) - len(separator)) + "\n\n")
        
        # Write headers
        if include_headers and headers:
            header_line = separator.join(
                str(h).center(column_width) for h in headers
            )
            output.write(header_line + "\n")
            output.write("-" * len(header_line) + "\n")
        
        # Write data rows
        for record in records:
            row_line = separator.join(
                self._truncate(str(record.get(h, "")), column_width).ljust(column_width)
                for h in headers
            )
            output.write(row_line + "\n")
        
        # Add summary
        output.write("\n" + "=" * (len(headers) * (column_width + len(separator)) - len(separator)) + "\n")
        output.write("End of Report\n")
        
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
                        data[col] = data[col].dt.strftime('%Y-%m-%d %H:%M:%S')
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
        
        # Handle single dictionary
        if isinstance(data, dict):
            return [data]
        
        # Handle other iterables
        try:
            return list(data)
        except:
            self._errors.append(f"Unsupported data type: {type(data)}")
            return []
    
    def _truncate(self, text: str, width: int) -> str:
        """Truncate text to fit column width"""
        text = str(text)
        if len(text) <= width:
            return text
        return text[:width-3] + "..."
    
    def format_to_bytes(self, data: Any, **kwargs) -> bytes:
        """Format data as TXT bytes"""
        return self.format(data, **kwargs).encode(self.encoding)
