"""
ETL Status Module

Provides ETL execution status monitoring and history display
for the admin module.
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timezone
from typing import List, Dict, Optional

from etl.orchestrator import ETLOrchestrator
from core.config import Config


def row_to_dict(row) -> Dict:
    """Convert SQLAlchemy row to dictionary for consistent access."""
    if hasattr(row, '_mapping'):
        return dict(row._mapping)
    return dict(row)


def get_etl_runs(limit: int = 20) -> List[Dict]:
    """Get ETL run history from the database.
    
    Args:
        limit: Maximum number of runs to return
        
    Returns:
        List of ETL run dictionaries
    """
    config = Config()
    orchestrator = ETLOrchestrator(database_url=config.DATABASE_URL)
    
    try:
        results = orchestrator.fetch_all(f"""
            SELECT 
                run_id, run_type, status, start_time, end_time,
                duration_seconds, records_extracted, records_loaded,
                error_message, triggered_by, service_flags
            FROM etl_runs
            ORDER BY start_time DESC
            LIMIT {limit}
        """)
        # Convert SQLAlchemy rows to dictionaries
        return [row_to_dict(row) for row in results] if results else []
    except Exception as e:
        st.error(f"Failed to fetch ETL history: {e}")
        return []


def render_etl_history(limit: int = 20, session_state=None) -> None:
    """Render the ETL execution history table.
    
    Args:
        limit: Number of recent runs to display
        session_state: Streamlit session state
    """
    st.markdown("### 📋 ETL Execution History")
    
    runs = get_etl_runs(limit)
    
    if not runs:
        st.info("No ETL runs recorded yet.")
        return
    
    # Convert to DataFrame for display
    df = pd.DataFrame(runs)
    
    # Format the data for display
    display_cols = ['run_id', 'run_type', 'status', 'start_time', 'duration_seconds', 'records_loaded', 'triggered_by']
    
    # Filter columns that exist
    available_cols = [col for col in display_cols if col in df.columns]
    if 'error_message' in df.columns:
        available_cols.append('error_message')
    
    df_display = df[available_cols].copy()
    
    # Format datetime
    if 'start_time' in df_display.columns:
        # Handle different datetime formats
        try:
            df_display['start_time'] = pd.to_datetime(df_display['start_time'], format='mixed', utc=True).dt.strftime('%Y-%m-%d %H:%M')
        except:
            df_display['start_time'] = pd.to_datetime(df_display['start_time'], errors='coerce').dt.strftime('%Y-%m-%d %H:%M')
    
    # Format duration
    if 'duration_seconds' in df_display.columns:
        df_display['duration_seconds'] = df_display['duration_seconds'].apply(
            lambda x: f"{x}s" if pd.notna(x) else "-"
        )
    
    # Format status with color
    if 'status' in df_display.columns:
        def format_status(status):
            if status == 'success':
                return "✅ Success"
            elif status == 'failed':
                return "❌ Failed"
            elif status == 'running':
                return "🔄 Running"
            else:
                return status
        df_display['status'] = df_display['status'].apply(format_status)
    
    # Display as table
    st.dataframe(
        df_display,
        use_container_width=True,
        hide_index=True
    )


def render_etl_metrics(session_state=None) -> None:
    """Render ETL metrics summary cards.
    
    Args:
        session_state: Streamlit session state
    """
    st.markdown("### 📊 ETL Performance Metrics")
    
    runs = get_etl_runs(100)  # Get more runs for metrics
    
    if not runs:
        st.info("No ETL metrics available yet.")
        return
    
    # Calculate metrics
    total_runs = len(runs)
    successful_runs = len([r for r in runs if r.get('status') == 'success'])
    failed_runs = len([r for r in runs if r.get('status') == 'failed'])
    
    success_rate = (successful_runs / total_runs * 100) if total_runs > 0 else 0
    
    # Average duration
    durations = [r.get('duration_seconds', 0) for r in runs if r.get('duration_seconds')]
    avg_duration = sum(durations) / len(durations) if durations else 0
    
    # Total records loaded
    total_records = sum(r.get('records_loaded', 0) for r in runs if r.get('records_loaded'))
    
    # Display metrics in columns
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Runs", total_runs)
    
    with col2:
        st.metric("Success Rate", f"{success_rate:.1f}%", 
                  delta=f"{successful_runs} successful" if successful_runs else None,
                  delta_color="normal" if success_rate > 80 else "inverse")
    
    with col3:
        st.metric("Avg Duration", f"{avg_duration:.0f}s")
    
    with col4:
        st.metric("Total Records", f"{total_records:,}")
    
    # Show recent failures if any
    if failed_runs > 0:
        st.markdown("#### Recent Failures")
        failures = [r for r in runs if r.get('status') == 'failed'][:5]
        
        for run in failures:
            start_time = run.get('start_time', 'Unknown')
            error = run.get('error_message', 'Unknown error')
            triggered_by = run.get('triggered_by', 'Unknown')
            
            st.markdown(f'''
            <div style="
                background: rgba(239, 68, 68, 0.1);
                border-left: 3px solid #ef4444;
                padding: 0.75rem;
                margin-bottom: 0.5rem;
            ">
                <p style="margin: 0; font-size: 0.85rem;">
                    <strong>Run ID:</strong> {run.get('run_id', 'N/A')}<br>
                    <strong>Time:</strong> {start_time}<br>
                    <strong>Triggered by:</strong> {triggered_by}<br>
                    <strong>Error:</strong> {error}
                </p>
            </div>
            ''', unsafe_allow_html=True)


def render_etl_status_summary(session_state=None) -> None:
    """Render a summary of ETL status for the overview tab.
    
    Args:
        session_state: Streamlit session state
    """
    config = Config()
    orchestrator = ETLOrchestrator(database_url=config.DATABASE_URL)
    
    # Check lock status
    is_locked = orchestrator.is_etl_locked()
    
    # Get last run info
    runs = get_etl_runs(1)
    
    col1, col2 = st.columns(2)
    
    with col1:
        if is_locked:
            st.error("🔒 ETL is currently locked")
        else:
            st.success("✅ ETL is idle")
    
    with col2:
        if runs:
            last_run = runs[0]
            # Convert SQLAlchemy row to dict for compatibility
            run_dict = dict(last_run._mapping) if hasattr(last_run, '_mapping') else dict(last_run)
            status = run_dict.get('status', 'unknown')
            start_time = run_dict.get('start_time', 'N/A')
            
            if start_time != 'N/A':
                try:
                    dt = datetime.fromisoformat(str(start_time).replace('Z', '+00:00'))
                    formatted_time = dt.strftime('%Y-%m-%d %H:%M')
                except:
                    formatted_time = str(start_time)
            else:
                formatted_time = 'N/A'
            
            if status == 'success':
                st.info(f"Last run: {formatted_time}")
            else:
                st.warning(f"Last run: {formatted_time} ({status})")
        else:
            st.info("No ETL runs yet")


def get_data_freshness(service_type: str = 'RDS') -> Optional[Dict]:
    """Get data freshness for a service type.
    
    Args:
        service_type: Service type (RDS, EC2, EBS)
        
    Returns:
        Dictionary with freshness info or None
    """
    config = Config()
    orchestrator = ETLOrchestrator(database_url=config.DATABASE_URL)
    
    try:
        result = orchestrator.fetch_one("""
            SELECT service_type, last_updated, records_count
            FROM data_freshness
            WHERE service_type = :service_type
        """, {'service_type': service_type})
        
        if result:
            # Convert to dict
            result_dict = row_to_dict(result)
            return {
                'service_type': result_dict.get('service_type'),
                'last_updated': result_dict.get('last_updated'),
                'records_count': result_dict.get('records_count')
            }
    except Exception as e:
        pass
    
    return None