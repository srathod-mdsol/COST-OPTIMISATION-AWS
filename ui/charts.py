import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from typing import Dict, List, Any

class ChartBuilder:
    """Helper to build consistent Plotly charts for the dashboard"""
    
    @staticmethod
    def build_line_chart(df: pd.DataFrame, x: str, y: str, title: str, labels: Dict = None, color: str = '#00d2ff'):
        """Build a futuristic line chart"""
        if df.empty:
            return ChartBuilder.build_empty_chart(title)
            
        fig = px.line(df, x=x, y=y, title=title, labels=labels or {})
        fig.update_traces(line_color=color, line_width=3)
        ChartBuilder._apply_futuristic_layout(fig)
        return fig

    @staticmethod
    def build_metric_comparison(metrics_data: List[Dict], title: str):
        """Build a bar chart comparing metrics"""
        df = pd.DataFrame(metrics_data)
        if df.empty:
            return ChartBuilder.build_empty_chart(title)
            
        fig = px.bar(df, x='name', y='value', title=title, color='name')
        ChartBuilder._apply_futuristic_layout(fig)
        return fig

    @staticmethod
    def build_empty_chart(title: str):
        """Return a placeholder chart for no data"""
        fig = go.Figure()
        fig.add_annotation(text="No data available for this period", showarrow=False, font_size=20)
        fig.update_layout(title=title)
        ChartBuilder._apply_futuristic_layout(fig)
        return fig

    @staticmethod
    def _apply_futuristic_layout(fig):
        """Apply shared styling for all charts"""
        fig.update_layout(
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font_color='#ffffff',
            title_font_size=24,
            hovermode="x unified",
            margin=dict(l=20, r=20, t=60, b=20),
            xaxis=dict(gridcolor='rgba(255,255,255,0.1)'),
            yaxis=dict(gridcolor='rgba(255,255,255,0.1)')
        )
