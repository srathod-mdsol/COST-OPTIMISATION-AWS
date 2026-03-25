"""
Export Module - Modular Export Service for Streamlit Dashboard

This module provides comprehensive export functionality supporting multiple file formats:
- CSV, TSV, XLSX, TXT, JSON, XML, PDF

Architecture:
- base_formatter.py: Base formatter class and interface
- formatters/: Individual format implementations
- export_controller.py: Streamlit UI integration
- report_generator.py: Business report generation

Usage:
    from ui.dashboard.export import ExportController, ReportGenerator
    
    # Create export controller
    exporter = ExportController()
    exporter.render_export_ui(data, title="My Report")
"""

from .base_formatter import BaseFormatter, FormatType
from .export_controller import ExportController
from .report_generator import ReportGenerator

__all__ = [
    'BaseFormatter',
    'FormatType', 
    'ExportController',
    'ReportGenerator',
]

__version__ = "1.0.0"
