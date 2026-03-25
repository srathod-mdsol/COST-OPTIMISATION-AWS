"""
PDF Formatter - Handles PDF export format
"""

import io
from typing import Any, List
from datetime import datetime

from ..base_formatter import BaseFormatter, FormatType


class PDFFormatter(BaseFormatter):
    """Formatter for PDF format"""
    
    def __init__(self, include_headers: bool = True, encoding: str = 'utf-8',
                 title: str = "Export Report", page_size: str = "A4"):
        """
        Initialize PDF formatter
        
        Args:
            include_headers: Whether to include column headers
            encoding: Character encoding
            title: Report title
            page_size: Page size (A4, Letter, etc.)
        """
        super().__init__(include_headers=include_headers, encoding=encoding)
        self.title = title
        self.page_size = page_size
    
    @property
    def format_type(self) -> FormatType:
        return FormatType.PDF
    
    def format(self, data: Any, **kwargs) -> bytes:
        """
        Format data as PDF bytes
        
        Args:
            data: Data to format
            **kwargs: Additional options
            
        Returns:
            PDF formatted bytes
        """
        if not self.validate_data(data):
            return self._create_empty_pdf()
        
        # Try to use reportlab for PDF creation
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4, letter
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import inch
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        except ImportError:
            self._errors.append("reportlab not installed. Install with: pip install reportlab")
            return self._create_fallback_pdf(data)
        
        # Convert data to records
        records = self._convert_to_records(data)
        
        if not records:
            return self._create_empty_pdf()
        
        # Get headers
        headers = list(records[0].keys()) if records else []
        
        # Create PDF
        output = io.BytesIO()
        
        # Set page size
        pagesize = A4 if self.page_size == "A4" else letter
        
        # Create document
        doc = SimpleDocTemplate(
            output,
            pagesize=pagesize,
            rightMargin=30,
            leftMargin=30,
            topMargin=30,
            bottomMargin=30
        )
        
        # Build story (content)
        story = []
        
        # Styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            spaceAfter=12,
            textColor=colors.HexColor("#FF9900")
        )
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=12,
            spaceAfter=6,
            textColor=colors.HexColor("#232F3E")
        )
        
        # Title
        title = kwargs.get('title', self.title)
        story.append(Paragraph(title, title_style))
        story.append(Spacer(1, 0.2 * inch))
        
        # Metadata
        story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
        story.append(Paragraph(f"Total Records: {len(records)}", styles['Normal']))
        story.append(Paragraph(f"Columns: {len(headers)}", styles['Normal']))
        story.append(Spacer(1, 0.3 * inch))
        
        # Prepare table data
        table_data = []
        
        # Headers
        if self.include_headers:
            table_data.append([self._format_cell(h) for h in headers])
        
        # Limit rows for PDF (performance)
        max_rows = kwargs.get('max_rows', 100)
        display_records = records[:max_rows]
        
        # Data rows
        for record in display_records:
            row = [self._format_cell(record.get(h, "")) for h in headers]
            table_data.append(row)
        
        if len(records) > max_rows:
            # Add note about truncated data
            story.append(Paragraph(
                f"<i>Note: Showing first {max_rows} of {len(records)} records. Export as CSV/Excel for complete data.</i>",
                styles['Normal']
            ))
            story.append(Spacer(1, 0.2 * inch))
        
        # Create table
        if table_data:
            table = Table(table_data)
            
            # Style the table
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#FF9900")),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F5F5")]),
            ]))
            
            story.append(table)
        
        # Build PDF
        doc.build(story)
        return output.getvalue()
    
    def _create_empty_pdf(self) -> bytes:
        """Create empty PDF with message"""
        return self._create_fallback_pdf(None)
    
    def _create_fallback_pdf(self, data: Any) -> bytes:
        """Create a simple text-based PDF as fallback"""
        # This creates a very basic PDF with just text
        # In production, you'd want reportlab installed
        content = "PDF export requires reportlab.\n\n"
        content += "Install with: pip install reportlab\n\n"
        content += f"Or export as CSV/Excel for full data.\n"
        
        # Return minimal PDF-like content
        # This is a placeholder - real implementation would use a PDF library
        return content.encode(self.encoding)
    
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
    
    def _format_cell(self, value: Any) -> str:
        """Format value for PDF cell"""
        if value is None:
            return ""
        if isinstance(value, datetime):
            return value.strftime('%Y-%m-%d %H:%M')
        if isinstance(value, float):
            return f"{value:.2f}"
        return str(value)[:50]  # Limit length
    
    def format_to_bytes(self, data: Any, **kwargs) -> bytes:
        """Format data as PDF bytes"""
        return self.format(data, **kwargs)
