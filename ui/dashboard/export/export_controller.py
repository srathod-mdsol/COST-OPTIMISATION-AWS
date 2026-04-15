"""
Export Controller - Streamlit UI integration for export functionality

Provides a unified interface for rendering export UI components and handling
download triggers in Streamlit applications.
"""

import streamlit as st
from typing import Any, Optional, List, Dict, Callable
from datetime import datetime

from .base_formatter import (
    BaseFormatter, 
    FormatType, 
    FormatDetector, 
    get_formatter
)


class ExportController:
    """
    Controller for handling export operations in Streamlit UI.
    
    Provides methods for:
    - Rendering export UI (format selector, download buttons)
    - Processing data through formatters
    - Managing export state
    
    Usage:
        controller = ExportController()
        
        # In your Streamlit page
        controller.render_export_ui(
            data=df,
            title="Export RDS Instances",
            key="my_export"
        )
    """
    
    def __init__(self):
        """Initialize the export controller"""
        self._formatters: Dict[FormatType, BaseFormatter] = {}
    
    def get_available_formats(self) -> List[FormatType]:
        """Get list of supported export formats"""
        return [
            FormatType.CSV,
            FormatType.TSV,
            FormatType.XLSX,
            FormatType.JSON,
            FormatType.XML,
            FormatType.TXT,
            FormatType.PDF,
        ]
    
    def get_formatter(self, format_type: FormatType) -> BaseFormatter:
        """Get or create formatter for specified format type"""
        if format_type not in self._formatters:
            self._formatters[format_type] = get_formatter(format_type)
        return self._formatters[format_type]
    
    def format_data(self, data: Any, format_type: FormatType) -> Any:
        """
        Format data to specified format
        
        Args:
            data: Data to format
            format_type: Target format type
            
        Returns:
            Formatted data (string or bytes depending on format)
        """
        formatter = self.get_formatter(format_type)
        return formatter.format(data)
    
    def render_format_selector(
        self, 
        key: str = "format_selector",
        default: FormatType = FormatType.CSV,
        label: str = "Select Export Format:"
    ) -> FormatType:
        """
        Render a format selector dropdown
        
        Args:
            key: Unique key for the widget
            default: Default selected format
            label: Label for the selector
            
        Returns:
            Selected FormatType
        """
        formats = self.get_available_formats()
        
        # Create options mapping
        options = {fmt.display_name: fmt for fmt in formats}
        
        # Get default index
        default_name = default.display_name if default in options else formats[0].display_name
        
        selected_name = st.selectbox(
            label,
            options=list(options.keys()),
            index=list(options.keys()).index(default_name),
            key=key
        )
        
        return options[selected_name]
    
    def render_export_ui(
        self,
        data: Any,
        title: str = "Export Data",
        key: str = "export",
        show_title: bool = True,
        show_record_count: bool = True,
        columns: Optional[int] = None,
        data_processor: Optional[Callable[[Any], Any]] = None,
    ) -> Optional[FormatType]:
        """
        Render complete export UI with format selector and download button
        
        Args:
            data: Data to export
            title: Title for the export section
            key: Unique key for the UI components
            show_title: Whether to show section title
            show_record_count: Whether to show record count
            columns: Number of columns for layout (default: auto)
            data_processor: Optional function to process data before export
            
        Returns:
            Selected FormatType if download triggered, None otherwise
        """
        # Process data if processor provided
        export_data = data_processor(data) if data_processor else data
        
        # Count records for display
        record_count = self._get_record_count(export_data)
        
        # Render title
        if show_title:
            st.markdown(f"### 📥 {title}")
        
        # Show record count
        if show_record_count and record_count is not None:
            st.caption(f"📊 {record_count} records available for export")
        
        # Layout: format selector and download button
        if columns is None:
            # Auto-calculate columns
            col1, col2 = st.columns([1, 2])
        else:
            cols = st.columns(columns)
            col1 = cols[0] if columns > 1 else cols
            col2 = cols[1] if columns > 1 else None
        
        # Format selector
        selected_format = self.render_format_selector(
            key=f"{key}_format",
            default=FormatType.CSV
        )
        
        # Create download button
        selected = self._render_download_button(
            data=export_data,
            format_type=selected_format,
            filename=f"{title.lower().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            key=f"{key}_btn"
        )
        
        return selected
    
    def _render_download_button(
        self,
        data: Any,
        format_type: FormatType,
        filename: str,
        key: str,
    ) -> Optional[FormatType]:
        """
        Render a download button for the specified format
        
        Args:
            data: Data to export
            format_type: Format type for export
            filename: Base filename (without extension)
            key: Unique key for the button
            
        Returns:
            FormatType if button clicked, None otherwise
        """
        import io
        
        # Add extension to filename
        full_filename = f"{filename}{format_type.file_extension}"
        
        # Ensure data is a list
        if not isinstance(data, list):
            data = []
        
        # For CSV format - create manually to avoid encoding issues
        if format_type == FormatType.CSV:
            try:
                if not data:
                    st.warning("No data to export")
                    return None
                
                # Get all unique fieldnames from all rows
                fieldnames = set()
                for row in data:
                    if isinstance(row, dict):
                        fieldnames.update(row.keys())
                fieldnames = sorted(list(fieldnames))
                
                if not fieldnames:
                    st.warning("No fields found in data")
                    return None
                
                # Build CSV content manually
                lines = []
                # Header
                header = ','.join([f'"{fn}"' for fn in fieldnames])
                lines.append(header)
                
                # Data rows
                for row in data:
                    if isinstance(row, dict):
                        values = []
                        for fn in fieldnames:
                            v = row.get(fn)
                            if v is None:
                                values.append('')
                            elif isinstance(v, str):
                                # Escape quotes and wrap in quotes
                                v = v.replace('"', '""')
                                values.append(f'"{v}"')
                            elif isinstance(v, (int, float, bool)):
                                values.append(str(v))
                            elif hasattr(v, 'isoformat'):
                                values.append(f'"{v.isoformat()}"')
                            else:
                                v = str(v).replace('"', '""')
                                values.append(f'"{v}"')
                        lines.append(','.join(values))
                
                csv_content = '\n'.join(lines)
                
                # Convert to bytes for reliable download
                csv_bytes = csv_content.encode('utf-8')
                
                clicked = st.download_button(
                    label=f"⬇️ Download {format_type.display_name}",
                    data=csv_bytes,
                    file_name=full_filename,
                    mime='text/csv;charset=utf-8',
                    key=key,
                    use_container_width=True
                )
                return format_type if clicked else None
            except Exception as e:
                st.error(f"CSV Error: {str(e)}")
                import traceback
                st.code(traceback.format_exc())
                return None
        
        # For JSON format
        if format_type == FormatType.JSON:
            try:
                if not data:
                    st.warning("No data to export")
                    return None
                
                import json
                
                # Convert data to JSON-serializable format
                clean_data = []
                for row in data:
                    if isinstance(row, dict):
                        clean_row = {}
                        for k, v in row.items():
                            if v is None:
                                clean_row[k] = None
                            elif isinstance(v, (str, int, float, bool)):
                                clean_row[k] = v
                            elif hasattr(v, 'isoformat'):
                                clean_row[k] = v.isoformat()
                            else:
                                clean_row[k] = str(v)
                        clean_data.append(clean_row)
                
                json_string = json.dumps(clean_data, indent=2)
                json_bytes = json_string.encode('utf-8')
                
                clicked = st.download_button(
                    label=f"⬇️ Download {format_type.display_name}",
                    data=json_bytes,
                    file_name=full_filename,
                    mime='application/json;charset=utf-8',
                    key=key,
                    use_container_width=True
                )
                return format_type if clicked else None
            except Exception as e:
                st.error(f"JSON Error: {str(e)}")
                return None
        
        # For TSV format
        if format_type == FormatType.TSV:
            try:
                if not data:
                    st.warning("No data to export")
                    return None
                
                # Get all unique fieldnames
                fieldnames = set()
                for row in data:
                    if isinstance(row, dict):
                        fieldnames.update(row.keys())
                fieldnames = sorted(list(fieldnames))
                
                # Build TSV content
                lines = []
                header = '\t'.join([str(fn) for fn in fieldnames])
                lines.append(header)
                
                for row in data:
                    if isinstance(row, dict):
                        values = []
                        for fn in fieldnames:
                            v = row.get(fn)
                            if v is None:
                                values.append('')
                            else:
                                values.append(str(v).replace('\t', ' ').replace('\n', ' '))
                        lines.append('\t'.join(values))
                
                tsv_content = '\n'.join(lines)
                tsv_bytes = tsv_content.encode('utf-8')
                
                clicked = st.download_button(
                    label=f"⬇️ Download {format_type.display_name}",
                    data=tsv_bytes,
                    file_name=full_filename,
                    mime='text/tab-separated-values;charset=utf-8',
                    key=key,
                    use_container_width=True
                )
                return format_type if clicked else None
            except Exception as e:
                st.error(f"TSV Error: {str(e)}")
                return None
        
        # For TXT format
        if format_type == FormatType.TXT:
            try:
                if not data:
                    st.warning("No data to export")
                    return None
                
                # Get all unique fieldnames
                fieldnames = set()
                for row in data:
                    if isinstance(row, dict):
                        fieldnames.update(row.keys())
                fieldnames = sorted(list(fieldnames))
                
                # Build TXT content
                lines = []
                header = ' | '.join([str(fn) for fn in fieldnames])
                lines.append(header)
                lines.append('=' * len(header))
                
                for row in data:
                    if isinstance(row, dict):
                        values = []
                        for fn in fieldnames:
                            v = row.get(fn)
                            values.append(str(v) if v is not None else '')
                        lines.append(' | '.join(values))
                
                txt_content = '\n'.join(lines)
                txt_bytes = txt_content.encode('utf-8')
                
                clicked = st.download_button(
                    label=f"⬇️ Download {format_type.display_name}",
                    data=txt_bytes,
                    file_name=full_filename,
                    mime='text/plain;charset=utf-8',
                    key=key,
                    use_container_width=True
                )
                return format_type if clicked else None
            except Exception as e:
                st.error(f"TXT Error: {str(e)}")
                return None
        
        # For XML format
        if format_type == FormatType.XML:
            try:
                if not data:
                    st.warning("No data to export")
                    return None
                
                import xml.etree.ElementTree as ET
                
                root = ET.Element('data')
                for row in data:
                    if isinstance(row, dict):
                        item = ET.SubElement(root, 'item')
                        for k, v in row.items():
                            child = ET.SubElement(item, str(k))
                            if v is not None:
                                child.text = str(v)
                
                xml_string = ET.tostring(root, encoding='unicode')
                xml_bytes = xml_string.encode('utf-8')
                
                clicked = st.download_button(
                    label=f"⬇️ Download {format_type.display_name}",
                    data=xml_bytes,
                    file_name=full_filename,
                    mime='application/xml;charset=utf-8',
                    key=key,
                    use_container_width=True
                )
                return format_type if clicked else None
            except Exception as e:
                st.error(f"XML Error: {str(e)}")
                return None
        
        # For XLSX and PDF, try using formatter
        try:
            formatter = self.get_formatter(format_type)
            formatted_data = formatter.format(data)
            
            # Ensure bytes
            if isinstance(formatted_data, str):
                formatted_data = formatted_data.encode('utf-8')
            
            clicked = st.download_button(
                label=f"⬇️ Download {format_type.display_name}",
                data=formatted_data,
                file_name=full_filename,
                mime=format_type.mime_type,
                key=key,
                use_container_width=True
            )
            return format_type if clicked else None
        except Exception as e:
            st.error(f"Error creating download: {str(e)}")
            return None
    
    def _get_record_count(self, data: Any) -> Optional[int]:
        """Get record count from data"""
        if data is None:
            return 0
        
        # Handle pandas DataFrame
        try:
            import pandas as pd
            if isinstance(data, pd.DataFrame):
                return len(data)
        except ImportError:
            pass
        
        # Handle list
        if isinstance(data, list):
            return len(data)
        
        # Handle dict
        if isinstance(data, dict):
            return 1
        
        return None
    
    def create_export_section(
        self,
        data: Any,
        title: str = "Export",
        key: str = "export",
    ) -> Dict[str, Any]:
        """
        Create a complete export section with all options
        
        Returns a dictionary with:
        - format: Selected format type
        - data: Processed data
        - triggered: Whether export was triggered
        
        Args:
            data: Data to export
            title: Section title
            key: Unique key
            
        Returns:
            Dictionary with export results
        """
        with st.expander(f"📥 {title}", expanded=False):
            result = self.render_export_ui(
                data=data,
                title=title,
                key=key,
                show_title=False,
            )
            
            return {
                'format': result,
                'data': data,
                'triggered': result is not None
            }
    
    def render_batch_export(
        self,
        datasets: Dict[str, Any],
        key: str = "batch_export",
    ) -> None:
        """
        Render export UI for multiple datasets
        
        Args:
            datasets: Dictionary of {name: data} pairs
            key: Unique key for the UI
        """
        st.markdown("### 📥 Batch Export")
        
        for name, data in datasets.items():
            with st.expander(f"📦 {name}", expanded=False):
                self.render_export_ui(
                    data=data,
                    title=name,
                    key=f"{key}_{name}",
                )


def render_quick_export(
    data: Any,
    key: str = "quick_export",
    formats: Optional[List[FormatType]] = None,
) -> None:
    """
    Quick render of multiple export format buttons
    
    Args:
        data: Data to export
        key: Unique key
        formats: List of formats to offer (default: all)
    """
    if formats is None:
        formats = [
            FormatType.CSV,
            FormatType.XLSX,
            FormatType.JSON,
        ]
    
    controller = ExportController()
    
    st.markdown("### 📥 Quick Export")
    
    cols = st.columns(len(formats))
    
    for idx, fmt in enumerate(formats):
        with cols[idx]:
            formatter = controller.get_formatter(fmt)
            try:
                formatted_data = formatter.format(data)
            except:
                continue
            
            filename = f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}{fmt.file_extension}"
            
            st.download_button(
                label=fmt.display_name,
                data=formatted_data,
                file_name=filename,
                mime=fmt.mime_type,
                key=f"{key}_{fmt.value}",
                use_container_width=True,
            )
