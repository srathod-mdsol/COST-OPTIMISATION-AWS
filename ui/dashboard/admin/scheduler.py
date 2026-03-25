"""
ETL Scheduler Module

Provides job scheduling UI for the admin module,
including schedule configuration and next run display.
"""

import streamlit as st
from typing import Optional, Dict
from datetime import datetime, timedelta

from etl.scheduler import ETLScheduler
from core.config import Config


# Global scheduler instance
_scheduler_instance: Optional[ETLScheduler] = None
_scheduler_enabled: bool = False
_schedule_time: str = "02:00"


def get_scheduler() -> ETLScheduler:
    """Get or create the ETL scheduler instance."""
    global _scheduler_instance, _schedule_time
    
    if _scheduler_instance is None:
        config = Config()
        _scheduler_instance = ETLScheduler(
            db_path=config.ETL_DB_PATH,
            schedule_time=_schedule_time
        )
    
    return _scheduler_instance


def init_scheduler_state(session_state=None) -> None:
    """Initialize scheduler state in session.
    
    Args:
        session_state: Streamlit session state
    """
    if session_state is None:
        session_state = st.session_state
    
    # Initialize scheduler config state if not present
    if 'scheduler_enabled' not in session_state:
        session_state['scheduler_enabled'] = _scheduler_enabled
    
    if 'schedule_time' not in session_state:
        session_state['schedule_time'] = _schedule_time


def get_scheduler_status() -> Dict:
    """Get current scheduler status.
    
    Returns:
        Dictionary with scheduler status information
    """
    global _scheduler_enabled, _schedule_time
    
    return {
        'enabled': _scheduler_enabled,
        'schedule_time': _schedule_time,
        'next_run': calculate_next_run(_schedule_time) if _scheduler_enabled else None
    }


def calculate_next_run(schedule_time: str) -> Optional[datetime]:
    """Calculate the next scheduled run time.
    
    Args:
        schedule_time: Schedule time in HH:MM format
        
    Returns:
        datetime of next run or None
    """
    try:
        hour, minute = map(int, schedule_time.split(':'))
        
        now = datetime.now()
        next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        # If the time has passed today, schedule for tomorrow
        if next_run <= now:
            next_run += timedelta(days=1)
        
        return next_run
    except Exception:
        return None


def render_scheduler_settings(session_state=None) -> None:
    """Render the ETL scheduler settings UI.
    
    Args:
        session_state: Streamlit session state
    """
    if session_state is None:
        session_state = st.session_state
    
    # Initialize state
    init_scheduler_state(session_state)
    
    st.markdown("### ⏰ ETL Job Scheduling")
    
    # Current status
    status = get_scheduler_status()
    
    col1, col2 = st.columns(2)
    
    with col1:
        enabled = st.toggle(
            "Enable Scheduled ETL",
            value=status['enabled'],
            help="Enable automatic daily ETL runs"
        )
    
    with col2:
        if status['enabled'] and status['next_run']:
            next_run = status['next_run']
            st.metric(
                "Next Run",
                next_run.strftime("%Y-%m-%d %H:%M"),
                f"in {(next_run - datetime.now()).total_seconds() / 3600:.1f} hours"
            )
    
    # Store enabled state
    session_state['scheduler_enabled'] = enabled
    
    # Schedule time configuration
    st.markdown("#### Schedule Time")
    
    time_input = st.text_input(
        "Daily run time (HH:MM)",
        value=session_state.get('schedule_time', '02:00'),
        help="Enter time in 24-hour format (e.g., 02:00 for 2 AM)",
        disabled=not enabled
    )
    
    # Validate time format
    if time_input:
        try:
            hour, minute = map(int, time_input.split(':'))
            if hour > 23 or minute > 59:
                st.error("Invalid time format. Use HH:MM with valid hours (0-23) and minutes (0-59).")
            else:
                session_state['schedule_time'] = time_input
                global _schedule_time
                _schedule_time = time_input
                st.success(f"Schedule updated to run daily at {time_input}")
        except ValueError:
            st.error("Invalid time format. Use HH:MM (e.g., 02:00)")
    
    # Manual trigger option
    st.markdown("---")
    st.markdown("#### Manual Trigger")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button(
            "▶️ Run ETL Now",
            use_container_width=True,
            type="primary",
            disabled=not enabled
        ):
            with st.spinner("Running ETL..."):
                try:
                    scheduler = get_scheduler()
                    result = scheduler.trigger_manual_run('manual_ui_trigger')
                    
                    if result.get('status') == 'success':
                        st.success(f"ETL completed! Loaded {result.get('records_loaded', 0)} records.")
                    else:
                        st.error(f"ETL failed: {result.get('error_message', 'Unknown error')}")
                except Exception as e:
                    st.error(f"Error running ETL: {e}")
    
    with col2:
        st.info("💡 The scheduler runs ETL automatically at the configured time each day.")


def render_scheduler_status_card(session_state=None) -> None:
    """Render a compact scheduler status card for overview.
    
    Args:
        session_state: Streamlit session state
    """
    if session_state is None:
        session_state = st.session_state
    
    status = get_scheduler_status()
    
    if status['enabled']:
        next_run = status['next_run']
        
        st.success(f"📅 Scheduled: {status['schedule_time']}")
        
        if next_run:
            time_until = next_run - datetime.now()
            hours = int(time_until.total_seconds() / 3600)
            st.caption(f"Next run in {hours} hours")
    else:
        st.info("⏸️ Scheduler is disabled")
        st.caption("Enable scheduling to run ETL automatically")