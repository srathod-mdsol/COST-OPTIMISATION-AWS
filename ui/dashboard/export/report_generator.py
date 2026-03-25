"""
Report Generator - Business report generation functionality

Provides methods for generating formatted reports from data
with analysis summaries suitable for business reporting.
"""

import streamlit as st
from typing import Any, Dict, List, Optional, Callable
from datetime import datetime
import json

from .base_formatter import FormatType
from .export_controller import ExportController


class ReportGenerator:
    """
    Generates formatted business reports from data.
    
    Provides:
    - Summary statistics
    - Data analysis
    - Formatted output suitable for business use
    
    Usage:
        generator = ReportGenerator()
        
        # Generate report from data
        report = generator.generate_report(
            data=df,
            report_type="summary",
            title="Monthly RDS Usage Report"
        )
        
        # Render in Streamlit
        generator.render_report_ui(report)
    """
    
    def __init__(self):
        """Initialize the report generator"""
        self.export_controller = ExportController()
    
    def generate_report(
        self,
        data: Any,
        report_type: str = "summary",
        title: str = "Data Report",
        include_stats: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate a report from data
        
        Args:
            data: Input data
            report_type: Type of report (summary, detailed, analysis)
            title: Report title
            include_stats: Whether to include summary statistics
            **kwargs: Additional report options
            
        Returns:
            Dictionary containing report data and metadata
        """
        report = {
            'title': title,
            'type': report_type,
            'generated_at': datetime.now().isoformat(),
            'data': data,
            'metadata': {},
        }
        
        # Add summary statistics
        if include_stats:
            report['summary'] = self._generate_summary(data)
        
        # Add report-type specific content
        if report_type == "summary":
            report['content'] = self._generate_summary_content(data)
        elif report_type == "detailed":
            report['content'] = self._generate_detailed_content(data)
        elif report_type == "analysis":
            report['content'] = self._generate_analysis_content(data)
        
        return report
    
    def _generate_summary(self, data: Any) -> Dict[str, Any]:
        """Generate summary statistics from data"""
        summary = {
            'total_records': 0,
            'columns': [],
            'data_types': {},
        }
        
        # Handle pandas DataFrame
        try:
            import pandas as pd
            if isinstance(data, pd.DataFrame):
                summary['total_records'] = len(data)
                summary['columns'] = list(data.columns)
                summary['data_types'] = {
                    col: str(dtype) for col, dtype in data.dtypes.items()
                }
                
                # Numeric columns stats
                numeric_cols = data.select_dtypes(include=['number']).columns
                if len(numeric_cols) > 0:
                    summary['numeric_summary'] = {
                        col: {
                            'min': float(data[col].min()),
                            'max': float(data[col].max()),
                            'mean': float(data[col].mean()),
                            'median': float(data[col].median()),
                        }
                        for col in numeric_cols
                    }
                
                return summary
        except ImportError:
            pass
        
        # Handle list of dicts
        if isinstance(data, list) and data and isinstance(data[0], dict):
            summary['total_records'] = len(data)
            summary['columns'] = list(data[0].keys()) if data else []
            return summary
        
        # Handle dict
        if isinstance(data, dict):
            summary['total_records'] = 1
            summary['columns'] = list(data.keys())
            return summary
        
        return summary
    
    def _generate_summary_content(self, data: Any) -> str:
        """Generate summary text content"""
        lines = []
        lines.append("=" * 50)
        lines.append("REPORT SUMMARY")
        lines.append("=" * 50)
        lines.append("")
        
        # Record count
        try:
            import pandas as pd
            if isinstance(data, pd.DataFrame):
                lines.append(f"Total Records: {len(data)}")
                lines.append(f"Columns: {len(data.columns)}")
                lines.append("")
                
                # Column info
                lines.append("Column Information:")
                for col in data.columns:
                    lines.append(f"  - {col}: {data[col].dtype}")
                
                return "\n".join(lines)
        except ImportError:
            pass
        
        if isinstance(data, list):
            lines.append(f"Total Records: {len(data)}")
        
        lines.append("")
        return "\n".join(lines)
    
    def _generate_detailed_content(self, data: Any) -> str:
        """Generate detailed content"""
        return self._generate_summary_content(data)
    
    def _generate_analysis_content(self, data: Any) -> str:
        """Generate analysis content"""
        return self._generate_summary_content(data)
    
    def render_report_ui(
        self,
        report: Dict[str, Any],
        show_data: bool = False,
        key: str = "report"
    ) -> None:
        """
        Render report in Streamlit UI
        
        Args:
            report: Report dictionary from generate_report
            show_data: Whether to show raw data table
            key: Unique key for UI components
        """
        # Report header
        st.markdown(f"## 📋 {report.get('title', 'Report')}")
        
        # Metadata
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Generated", datetime.now().strftime("%Y-%m-%d %H:%M"))
        with col2:
            st.metric("Type", report.get('type', 'Summary').title())
        with col3:
            total = report.get('summary', {}).get('total_records', 0)
            st.metric("Records", total)
        
        # Summary statistics
        if 'summary' in report:
            with st.expander("📊 Summary Statistics", expanded=True):
                summary = report['summary']
                
                # Columns
                if 'columns' in summary:
                    st.write("**Columns:**")
                    cols = summary['columns']
                    st.write(", ".join(str(c) for c in cols))
                
                # Numeric summary
                if 'numeric_summary' in summary:
                    st.write("**Numeric Columns:**")
                    for col, stats in summary['numeric_summary'].items():
                        st.write(f"  {col}:")
                        for stat_name, stat_value in stats.items():
                            st.write(f"    {stat_name}: {stat_value:.2f}")
        
        # Export report
        st.markdown("### 📥 Export Report")
        
        self.export_controller.render_export_ui(
            data=report.get('data', []),
            title="Export Report Data",
            key=f"{key}_export",
        )
    
    def render_report_section(
        self,
        data: Any,
        title: str = "Report",
        report_type: str = "summary",
        key: str = "report"
    ) -> None:
        """
        Render complete report section with generation and export
        
        Args:
            data: Input data
            title: Report title
            report_type: Type of report
            key: Unique key
        """
        # Generate report
        report = self.generate_report(
            data=data,
            report_type=report_type,
            title=title
        )
        
        # Render in UI
        self.render_report_ui(report, key=key)
    
    def create_idle_report(
        self,
        instances: List[Dict],
        region: str,
        environment: str,
    ) -> Dict[str, Any]:
        """
        Create a specialized idle instance report
        
        Args:
            instances: List of idle instance data
            region: AWS region
            environment: Environment name
            
        Returns:
            Report dictionary
        """
        # Calculate savings
        total_potential_savings = sum(
            inst.get('potential_monthly_savings', 0) 
            for inst in instances
        )
        
        # Group by instance type
        by_type = {}
        for inst in instances:
            inst_type = inst.get('instance_type', 'unknown')
            if inst_type not in by_type:
                by_type[inst_type] = {
                    'count': 0,
                    'potential_savings': 0,
                }
            by_type[inst_type]['count'] += 1
            by_type[inst_type]['potential_savings'] += inst.get('potential_monthly_savings', 0)
        
        report = {
            'title': f'Idle Instance Report - {environment} ({region})',
            'generated_at': datetime.now().isoformat(),
            'environment': environment,
            'region': region,
            'summary': {
                'total_idle_instances': len(instances),
                'total_potential_monthly_savings': total_potential_savings,
                'total_potential_yearly_savings': total_potential_savings * 12,
                'by_instance_type': by_type,
            },
            'data': instances,
        }
        
        return report


def render_report_summary(data: Any, key: str = "summary") -> None:
    """
    Quick render of data summary in Streamlit
    
    Args:
        data: Data to summarize
        key: Unique key
    """
    generator = ReportGenerator()
    summary = generator._generate_summary(data)
    
    st.markdown("### 📊 Data Summary")
    
    # Metrics
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Records", summary.get('total_records', 0))
    with col2:
        st.metric("Columns", len(summary.get('columns', [])))
    with col3:
        st.metric("Types", len(summary.get('data_types', {})))
    
    # Quick export
    if summary.get('total_records', 0) > 0:
        controller = ExportController()
        st.markdown("#### 📥 Quick Export")
        controller.render_export_ui(
            data=data,
            title="Export Data",
            key=f"{key}_export",
        )
