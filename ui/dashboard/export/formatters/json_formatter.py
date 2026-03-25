"""
JSON Formatter - Handles JSON export format
"""

import json
import io
from typing import Any, List
from datetime import datetime

from ..base_formatter import BaseFormatter, FormatType


class JSONFormatter(BaseFormatter):
    """Formatter for JSON format"""
    
    def __init__(self, include_headers: bool = True, encoding: str = 'utf-8',
                 indent: int = 2, sort_keys: bool = False):
        """
        Initialize JSON formatter
        
        Args:
            include_headers: Whether to include headers (for JSON, always true)
            encoding: Character encoding
            indent: JSON indentation spaces
            sort_keys: Whether to sort dictionary keys
        """
        super().__init__(include_headers=True, encoding=encoding)
        self.indent = indent
        self.sort_keys = sort_keys
    
    @property
    def format_type(self) -> FormatType:
        return FormatType.JSON
    
    def format(self, data: Any, **kwargs) -> str:
        """
        Format data as JSON string
        
        Args:
            data: Data to format
            **kwargs: Additional options (indent, sort_keys)
            
        Returns:
            JSON formatted string
        """
        if not self.validate_data(data):
            return "{}"
        
        # Override settings if provided
        indent = kwargs.get('indent', self.indent)
        sort_keys = kwargs.get('sort_keys', self.sort_keys)
        
        # Convert data to serializable format
        serializable_data = self._make_serializable(data)
        
        # Format as JSON
        try:
            return json.dumps(
                serializable_data,
                indent=indent,
                sort_keys=sort_keys,
                default=str,
                ensure_ascii=False
            )
        except Exception as e:
            self._errors.append(f"JSON formatting error: {str(e)}")
            return "{}"
    
    def _make_serializable(self, data: Any) -> Any:
        """Convert data to JSON-serializable format"""
        # Handle pandas DataFrame
        try:
            import pandas as pd
            if isinstance(data, pd.DataFrame):
                return self._dataframe_to_json_structure(data)
        except ImportError:
            pass
        
        # Handle list
        if isinstance(data, list):
            # Handle SQLAlchemy Row objects
            if data and hasattr(data[0], '_mapping'):
                return [self._make_serializable(dict(row._mapping)) for row in data]
            return [self._make_serializable(item) for item in data]
        
        # Handle dictionary
        if isinstance(data, dict):
            return {k: self._make_serializable(v) for k, v in data.items()}
        
        # Handle datetime
        if isinstance(data, datetime):
            return data.isoformat()
        
        # Handle bytes
        if isinstance(data, bytes):
            return data.decode(self.encoding, errors='replace')
        
        # Return as-is if already serializable
        try:
            json.dumps(data)
            return data
        except:
            return str(data)
    
    def _dataframe_to_json_structure(self, df) -> dict:
        """Convert DataFrame to JSON-serializable structure"""
        # Convert to records
        records = df.to_dict('records')
        
        # Process each record
        result = []
        for record in records:
            processed = {}
            for key, value in record.items():
                if isinstance(value, datetime):
                    processed[key] = value.isoformat()
                elif hasattr(value, 'item'):  # numpy types
                    processed[key] = value.item()
                else:
                    processed[key] = value
            result.append(processed)
        
        return {
            "data": result,
            "metadata": {
                "total_records": len(result),
                "columns": list(df.columns),
                "export_timestamp": datetime.now().isoformat()
            }
        }
    
    def format_to_bytes(self, data: Any, **kwargs) -> bytes:
        """Format data as JSON bytes"""
        return self.format(data, **kwargs).encode(self.encoding)
