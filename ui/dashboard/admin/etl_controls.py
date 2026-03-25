"""
ETL Controls Module

Provides ETL management controls for the admin module,
including data refresh, pricing reload, and lock management.
"""

import streamlit as st
from typing import Optional

from core.config import Config
from etl.orchestrator import ETLOrchestrator
from etl.pricing_loader import PricingLoader
from etl.data_provider import ETLDataProvider
from ui.dashboard.admin.access_control import check_admin_access
from ui.dashboard.admin.async_etl import (
    run_etl_refresh,
    run_pricing_reload,
    get_active_tasks,
    get_recent_tasks,
    render_task_status,
)


def get_etl_orchestrator() -> ETLOrchestrator:
    """Get an ETLOrchestrator instance."""
    config = Config()
    return ETLOrchestrator(database_url=config.DATABASE_URL)


def get_etl_provider(aws_environment: str = 'Default') -> ETLDataProvider:
    """Get an ETLDataProvider instance for the given environment."""
    config = Config()
    return ETLDataProvider(db_path=config.ETL_DB_PATH, database_url=config.DATABASE_URL)


def render_etl_lock_status(session_state=None) -> None:
    """Render ETL lock status and provide force unlock option for admins.
    
    Args:
        session_state: Streamlit session state
    """
    if session_state is None:
        session_state = st.session_state
    
    is_admin = check_admin_access(session_state)
    
    orchestrator = get_etl_orchestrator()
    is_locked = orchestrator.is_etl_locked()
    
    if is_locked:
        st.markdown('''
        <div style="
            background: rgba(239, 68, 68, 0.1);
            border: 1px solid rgba(239, 68, 68, 0.3);
            border-radius: 8px;
            padding: 1rem;
            margin-bottom: 1rem;
        ">
            <p style="margin: 0; color: #ef4444; font-size: 0.9rem;">
                ⚠️ <strong>ETL Process Locked</strong><br>
                A previous ETL run may have been interrupted.
            </p>
        </div>
        ''', unsafe_allow_html=True)
        
        if is_admin:
            if st.button("🔓 Force Unlock ETL", use_container_width=True, type="secondary"):
                try:
                    orchestrator.force_unlock()
                    st.success("ETL lock released successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to release lock: {e}")
        else:
            st.warning("🔐 Login as admin to unlock.")
    else:
        st.markdown('''
        <div style="
            background: rgba(34, 197, 94, 0.1);
            border: 1px solid rgba(34, 197, 94, 0.3);
            border-radius: 8px;
            padding: 1rem;
            margin-bottom: 1rem;
        ">
            <p style="margin: 0; color: #22c55e; font-size: 0.9rem;">
                ✅ <strong>ETL Ready</strong><br>
                No active ETL processes. Ready to run.
            </p>
        </div>
        ''', unsafe_allow_html=True)


def render_etl_controls(
    aws_environment: Optional[str] = None,
    session_state=None
) -> None:
    """Render the ETL control buttons (Refresh Data, Reload Pricing).
    
    Args:
        aws_environment: AWS environment name (defaults to session state)
        session_state: Streamlit session state
    """
    if session_state is None:
        session_state = st.session_state
    
    if aws_environment is None:
        aws_environment = session_state.get('aws_environment', 'Default')
    
    is_admin = check_admin_access(session_state)
    
    # Get orchestrator for lock status
    orchestrator = get_etl_orchestrator()
    is_locked = orchestrator.is_etl_locked()
    
    # Section header
    st.markdown('''
    <div style="
        background: rgba(255,255,255,0.05); 
        padding: 0.75rem; 
        border-radius: 8px; 
        border: 1px solid rgba(255,255,255,0.1);
        margin-bottom: 1rem;
    ">
        <h3 style="
            color: #ff9900 !important; 
            font-size: 0.9rem !important; 
            text-transform: uppercase; 
            letter-spacing: 1px;
            font-weight: 600 !important;
            margin: 0;
        ">📥 Data Management</h3>
    </div>
    ''', unsafe_allow_html=True)
    
    # Render lock status
    render_etl_lock_status(session_state)
    
    # Show active background tasks if any
    active_tasks = get_active_tasks()
    if active_tasks:
        st.markdown("### 🔄 Background Tasks Running")
        for task_id, task in active_tasks.items():
            render_task_status(task)
        st.markdown("---")
    
    if is_admin:
        # Show active admin controls
        col1, col2 = st.columns(2)
        
        with col1:
            refresh_disabled = is_locked or bool(active_tasks)
            if st.button(
                "🔄 Refresh Data",
                help="Fetches fresh data from AWS and reloads database" if not refresh_disabled else "ETL is currently locked or running",
                use_container_width=True,
                type="primary",
                disabled=refresh_disabled
            ):
                # Launch async ETL refresh - doesn't block UI
                task = run_etl_refresh(aws_environment=aws_environment)
                st.session_state['last_etl_task_id'] = task.task_id
                st.success("🚀 ETL refresh started in background! You can continue using the app.")
                st.rerun()
        
        with col2:
            if st.button(
                "💲 Reload Pricing",
                help="Update pricing cache from AWS",
                use_container_width=True,
                type="primary"
            ):
                # Launch async pricing reload - doesn't block UI
                task = run_pricing_reload()
                st.session_state['last_pricing_task_id'] = task.task_id
                st.success("🚀 Pricing reload started in background!")
                st.rerun()
        
        # Additional info
        st.caption(f"Environment: {aws_environment}")
        
    else:
        # Show disabled buttons for non-admin users
        col1, col2 = st.columns(2)
        
        with col1:
            st.button(
                "🔄 Refresh Data",
                help="Admin login required",
                use_container_width=True,
                type="secondary",
                disabled=True
            )
        
        with col2:
            st.button(
                "💲 Reload Pricing",
                help="Admin login required",
                use_container_width=True,
                type="secondary",
                disabled=True
            )
        
        st.info("🔐 Login as admin to access data management features.")


def trigger_etl_refresh(aws_environment: str = 'Default') -> dict:
    """Programmatically trigger an ETL data refresh.
    
    Args:
        aws_environment: AWS environment name
        
    Returns:
        Dictionary with status and message
    """
    try:
        provider = get_etl_provider(aws_environment)
        provider.truncate_and_reload(aws_environment=aws_environment)
        st.cache_data.clear()
        return {'status': 'success', 'message': 'Data refreshed successfully'}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}


def trigger_pricing_reload(regions: list = None) -> dict:
    """Programmatically trigger a pricing data reload.
    
    Args:
        regions: List of AWS regions to load pricing for
        
    Returns:
        Dictionary with status and message
    """
    if regions is None:
        regions = ['us-east-1']
    
    try:
        config = Config()
        PricingLoader.run_etl(
            config.PRICING_DB_PATH,
            regions=regions,
            ec2_json_path=config.PRICING_JSON_PATHS['ec2'],
            rds_json_path=config.PRICING_JSON_PATHS['rds']
        )
        return {'status': 'success', 'message': 'Pricing updated successfully'}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}