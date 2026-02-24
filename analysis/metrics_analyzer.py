from typing import Dict, List, Any
import pandas as pd

class MetricsAnalyzer:
    """Processes and aggregates CloudWatch metrics"""
    
    @staticmethod
    def aggregate_metrics(metrics: Dict) -> Dict:
        """Calculate basic aggregates for metrics if not already present"""
        # This is a placeholder for more complex logic if needed
        # The ETL provider already calculates most aggregates
        return metrics

    @staticmethod
    def format_for_plotly(datapoints: List[Dict], metric_name: str) -> pd.DataFrame:
        """Convert CW datapoints to a Pandas DataFrame suitable for Plotly"""
        if not datapoints:
            return pd.DataFrame()
            
        df = pd.DataFrame(datapoints)
        # Handle different CW stat names (Average, Sum, etc.)
        stat_cols = ['Average', 'Sum', 'Maximum', 'Minimum']
        actual_stat = next((col for col in stat_cols if col in df.columns), 'Value')
        
        if 'Timestamp' in df.columns:
            df['Timestamp'] = pd.to_datetime(df['Timestamp'])
            df = df.sort_values('Timestamp')
            
        return df
