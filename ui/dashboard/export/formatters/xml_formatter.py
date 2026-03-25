"""
XML Formatter - Handles XML export format
"""

import xml.etree.ElementTree as ET
from typing import Any, List
from datetime import datetime
import html

from ..base_formatter import BaseFormatter, FormatType


class XMLFormatter(BaseFormatter):
    """Formatter for XML format"""
    
    def __init__(self, include_headers: bool = True, encoding: str = 'utf-8',
                 root_element: str = "data", record_element: str = "record"):
        """
        Initialize XML formatter
        
        Args:
            include_headers: Whether to include headers (for XML, always true)
            encoding: Character encoding
            root_element: Name of root XML element
            record_element: Name of each record element
        """
        super().__init__(include_headers=True, encoding=encoding)
        self.root_element = root_element
        self.record_element = record_element
    
    @property
    def format_type(self) -> FormatType:
        return FormatType.XML
    
    def format(self, data: Any, **kwargs) -> str:
        """
        Format data as XML string
        
        Args:
            data: Data to format
            **kwargs: Additional options
            
        Returns:
            XML formatted string
        """
        if not self.validate_data(data):
            return self._create_empty_xml()
        
        # Override settings if provided
        root_element = kwargs.get('root_element', self.root_element)
        record_element = kwargs.get('record_element', self.record_element)
        
        # Create root
        root = ET.Element(root_element)
        
        # Add metadata
        metadata = ET.SubElement(root, "metadata")
        ET.SubElement(metadata, "export_timestamp").text = datetime.now().isoformat()
        
        # Convert data to records
        records = self._convert_to_records(data)
        
        if records:
            ET.SubElement(metadata, "total_records").text = str(len(records))
            ET.SubElement(metadata, "columns").text = ",".join(records[0].keys()) if records else ""
            
            # Add records
            records_elem = ET.SubElement(root, "records")
            for record in records:
                record_elem = ET.SubElement(records_elem, record_element)
                for key, value in record.items():
                    # Sanitize key for XML tag
                    safe_key = self._sanitize_xml_tag(key)
                    if safe_key:
                        field_elem = ET.SubElement(record_elem, safe_key)
                        field_elem.text = self._format_xml_value(value)
        
        # Generate XML string
        try:
            xml_str = ET.tostring(root, encoding='unicode', method='xml')
            # Add XML declaration
            return f'<?xml version="1.0" encoding="{self.encoding}"?>\n{xml_str}'
        except Exception as e:
            self._errors.append(f"XML formatting error: {str(e)}")
            return self._create_empty_xml()
    
    def _create_empty_xml(self) -> str:
        """Create empty XML structure"""
        root = ET.Element(self.root_element)
        metadata = ET.SubElement(root, "metadata")
        ET.SubElement(metadata, "export_timestamp").text = datetime.now().isoformat()
        ET.SubElement(metadata, "total_records").text = "0"
        return f'<?xml version="1.0" encoding="{self.encoding}"?>\n{ET.tostring(root, encoding="unicode")}'
    
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
        
        # Handle single dictionary
        if isinstance(data, dict):
            return [data]
        
        # Handle other iterables
        try:
            return list(data)
        except:
            self._errors.append(f"Unsupported data type: {type(data)}")
            return []
    
    def _sanitize_xml_tag(self, name: str) -> str:
        """Sanitize string to be valid XML tag name"""
        # Replace invalid characters with underscores
        safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in str(name))
        # Ensure it doesn't start with a number
        if safe and safe[0].isdigit():
            safe = "_" + safe
        return safe[:50]  # Limit length
    
    def _format_xml_value(self, value: Any) -> str:
        """Format value for XML, escaping special characters"""
        if value is None:
            return ""
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, bytes):
            value = value.decode(self.encoding, errors='replace')
        # Escape HTML entities
        return html.escape(str(value))
    
    def format_to_bytes(self, data: Any, **kwargs) -> bytes:
        """Format data as XML bytes"""
        return self.format(data, **kwargs).encode(self.encoding)
