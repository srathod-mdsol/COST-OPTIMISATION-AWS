"""
Base Formatter Module - Core export format handling

Provides the base class for all formatters and format type enumeration
with proper MIME type detection and file extension handling.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from datetime import datetime
import json
import io


class FormatType(Enum):
    """Supported export format types"""
    CSV = "csv"
    TSV = "tsv"
    XLSX = "xlsx"
    TXT = "txt"
    JSON = "json"
    XML = "xml"
    PDF = "pdf"
    
    @property
    def mime_type(self) -> str:
        """Return MIME type for each format"""
        mime_types = {
            FormatType.CSV: "text/csv",
            FormatType.TSV: "text/tab-separated-values",
            FormatType.XLSX: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            FormatType.TXT: "text/plain",
            FormatType.JSON: "application/json",
            FormatType.XML: "application/xml",
            FormatType.PDF: "application/pdf",
        }
        return mime_types.get(self, "application/octet-stream")
    
    @property
    def file_extension(self) -> str:
        """Return file extension for each format"""
        return f".{self.value}"
    
    @property
    def display_name(self) -> str:
        """Return human-readable format name"""
        names = {
            FormatType.CSV: "CSV (Comma Separated)",
            FormatType.TSV: "TSV (Tab Separated)",
            FormatType.XLSX: "Excel (XLSX)",
            FormatType.TXT: "Plain Text",
            FormatType.JSON: "JSON",
            FormatType.XML: "XML",
            FormatType.PDF: "PDF Document",
        }
        return names.get(self, self.value.upper())


class FormatDetector:
    """Detects format from file extension or MIME type"""
    
    EXTENSION_MAP = {
        '.csv': FormatType.CSV,
        '.tsv': FormatType.TSV,
        '.xlsx': FormatType.XLSX,
        '.xls': FormatType.XLSX,
        '.txt': FormatType.TXT,
        '.json': FormatType.JSON,
        '.xml': FormatType.XML,
        '.pdf': FormatType.PDF,
    }
    
    MIME_MAP = {
        'text/csv': FormatType.CSV,
        'text/tab-separated-values': FormatType.TSV,
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': FormatType.XLSX,
        'application/vnd.ms-excel': FormatType.XLSX,
        'text/plain': FormatType.TXT,
        'application/json': FormatType.JSON,
        'application/xml': FormatType.XML,
        'application/pdf': FormatType.PDF,
    }
    
    @classmethod
    def detect_from_extension(cls, extension: str) -> Optional[FormatType]:
        """Detect format from file extension"""
        ext = extension.lower().strip()
        if not ext.startswith('.'):
            ext = '.' + ext
        return cls.EXTENSION_MAP.get(ext)
    
    @classmethod
    def detect_from_mime(cls, mime_type: str) -> Optional[FormatType]:
        """Detect format from MIME type"""
        return cls.MIME_MAP.get(mime_type.lower().strip())
    
    @classmethod
    def detect_from_filename(cls, filename: str) -> Optional[FormatType]:
        """Detect format from filename"""
        if '.' in filename:
            ext = filename.rsplit('.', 1)[-1]
            return cls.detect_from_extension(ext)
        return None


class BaseFormatter(ABC):
    """Base class for all data formatters"""
    
    def __init__(self, include_headers: bool = True, encoding: str = 'utf-8'):
        """
        Initialize formatter
        
        Args:
            include_headers: Whether to include column headers
            encoding: Character encoding for text formats
        """
        self.include_headers = include_headers
        self.encoding = encoding
        self._errors: List[str] = []
        self._warnings: List[str] = []
    
    @property
    @abstractmethod
    def format_type(self) -> FormatType:
        """Return the format type this formatter handles"""
        pass
    
    @property
    def mime_type(self) -> str:
        """Return MIME type for this format"""
        return self.format_type.mime_type
    
    @property
    def file_extension(self) -> str:
        """Return file extension for this format"""
        return self.format_type.file_extension
    
    @abstractmethod
    def format(self, data: Any, **kwargs) -> Union[str, bytes]:
        """
        Format data to the target format
        
        Args:
            data: Data to format (DataFrame, list, dict, etc.)
            **kwargs: Additional format-specific options
            
        Returns:
            Formatted data as string or bytes
        """
        pass
    
    def get_errors(self) -> List[str]:
        """Get list of errors encountered during formatting"""
        return self._errors.copy()
    
    def get_warnings(self) -> List[str]:
        """Get list of warnings encountered during formatting"""
        return self._warnings.copy()
    
    def clear_messages(self):
        """Clear errors and warnings"""
        self._errors.clear()
        self._warnings.clear()
    
    def validate_data(self, data: Any) -> bool:
        """
        Validate data before formatting
        
        Args:
            data: Data to validate
            
        Returns:
            True if data is valid, False otherwise
        """
        if data is None:
            self._errors.append("Data is None")
            return False
        
        if isinstance(data, (list, dict)) and len(data) == 0:
            self._warnings.append("Data is empty")
        
        return True
    
    def sanitize_value(self, value: Any) -> str:
        """Sanitize a value for safe inclusion in output"""
        if value is None:
            return ""
        if isinstance(value, (datetime,)):
            return value.isoformat()
        if isinstance(value, bytes):
            return value.decode(self.encoding, errors='replace')
        return str(value)
    
    def create_download_response(self, data: Any, filename: str) -> Dict:
        """
        Create a download response dictionary for Streamlit
        
        Args:
            data: Data to create download for
            filename: Base filename without extension
            
        Returns:
            Dictionary with data, filename, and mime_type
        """
        formatted_data = self.format(data)
        
        # Ensure filename has correct extension
        if not filename.endswith(self.file_extension):
            filename = filename + self.file_extension
        
        return {
            'data': formatted_data,
            'filename': filename,
            'mime_type': self.mime_type,
            'format': self.format_type,
            'errors': self.get_errors(),
            'warnings': self.get_warnings(),
        }


def get_formatter(format_type: FormatType, **kwargs) -> BaseFormatter:
    """
    Factory function to get formatter for specified format type
    
    Args:
        format_type: The format type to format data as
        **kwargs: Additional arguments passed to formatter
        
    Returns:
        Formatter instance for the specified format
    """
    # Import formatters lazily to avoid circular imports
    from .formatters.csv_formatter import CSVFormatter
    from .formatters.xlsx_formatter import XLSXFormatter
    from .formatters.json_formatter import JSONFormatter
    from .formatters.xml_formatter import XMLFormatter
    from .formatters.txt_formatter import TXTFormatter
    from .formatters.pdf_formatter import PDFFormatter
    
    formatters = {
        FormatType.CSV: CSVFormatter,
        FormatType.TSV: CSVFormatter,  # TSV uses CSV with tab separator
        FormatType.XLSX: XLSXFormatter,
        FormatType.JSON: JSONFormatter,
        FormatType.XML: XMLFormatter,
        FormatType.TXT: TXTFormatter,
        FormatType.PDF: PDFFormatter,
    }
    
    formatter_class = formatters.get(format_type)
    if not formatter_class:
        raise ValueError(f"Unsupported format type: {format_type}")
    
    return formatter_class(**kwargs)
