"""
Async ETL Module

Provides asynchronous ETL execution using Python's threading module.
Allows ETL processes to run in the background without blocking the Streamlit UI.
"""

import threading
import time
from typing import Dict, Any, Optional, Callable
from datetime import datetime
import streamlit as st

from core.config import Config
from etl.orchestrator import ETLOrchestrator
from etl.pricing_loader import PricingLoader
from etl.data_provider import ETLDataProvider


class AsyncETLTask:
    """Manages an asynchronous ETL task running in the background."""
    
    def __init__(self, task_id: str):
        self.task_id = task_id
        self.status = "pending"  # pending, running, completed, failed
        self.start_time = None
        self.end_time = None
        self.error = None
        self.result = None
        self._thread = None
        self._lock = threading.Lock()
    
    def is_running(self) -> bool:
        return self.status == "running"
    
    def is_complete(self) -> bool:
        return self.status in ["completed", "failed"]


# Global task registry
_etl_tasks: Dict[str, AsyncETLTask] = {}
_tasks_lock = threading.Lock()


def get_task(task_id: str) -> Optional[AsyncETLTask]:
    """Get a task by ID."""
    with _tasks_lock:
        return _etl_tasks.get(task_id)


def create_task(task_id: str) -> AsyncETLTask:
    """Create a new task."""
    with _tasks_lock:
        task = AsyncETLTask(task_id)
        _etl_tasks[task_id] = task
        return task


def run_etl_refresh(
    aws_environment: str = 'Default',
    on_complete: Optional[Callable] = None
) -> AsyncETLTask:
    """Run ETL refresh in a background thread.
    
    Args:
        aws_environment: AWS environment name
        on_complete: Optional callback function to run when complete
        
    Returns:
        AsyncETLTask object with task ID
    """
    task_id = f"etl_refresh_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    task = create_task(task_id)
    
    def _run_task():
        task.status = "running"
        task.start_time = datetime.now()
        
        try:
            config = Config()
            provider = ETLDataProvider(
                db_path=config.ETL_DB_PATH,
                database_url=config.DATABASE_URL
            )
            
            # Run the ETL refresh
            result = provider.truncate_and_reload(aws_environment=aws_environment)
            
            task.status = "completed"
            task.result = result
            task.end_time = datetime.now()
            
        except Exception as e:
            task.status = "failed"
            task.error = str(e)
            task.end_time = datetime.now()
        
        # Call completion callback if provided
        if on_complete:
            try:
                on_complete(task)
            except Exception:
                pass
    
    # Start the background thread
    task._thread = threading.Thread(target=_run_task, daemon=True)
    task._thread.start()
    
    return task


def run_pricing_reload(
    on_complete: Optional[Callable] = None
) -> AsyncETLTask:
    """Run pricing reload in a background thread.
    
    Args:
        on_complete: Optional callback function to run when complete
        
    Returns:
        AsyncETLTask object with task ID
    """
    task_id = f"pricing_reload_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    task = create_task(task_id)
    
    def _run_task():
        task.status = "running"
        task.start_time = datetime.now()
        
        try:
            config = Config()
            loader = PricingLoader(database_url=config.DATABASE_URL)
            
            # Reload pricing data
            result = loader.load_pricing()
            
            task.status = "completed"
            task.result = result
            task.end_time = datetime.now()
            
        except Exception as e:
            task.status = "failed"
            task.error = str(e)
            task.end_time = datetime.now()
        
        # Call completion callback if provided
        if on_complete:
            try:
                on_complete(task)
            except Exception:
                pass
    
    # Start the background thread
    task._thread = threading.Thread(target=_run_task, daemon=True)
    task._thread.start()
    
    return task


def get_active_tasks() -> Dict[str, AsyncETLTask]:
    """Get all active (running) tasks."""
    with _tasks_lock:
        return {
            task_id: task 
            for task_id, task in _etl_tasks.items() 
            if task.is_running()
        }


def get_recent_tasks(limit: int = 5) -> list:
    """Get recent tasks sorted by start time."""
    with _tasks_lock:
        tasks = sorted(
            _etl_tasks.values(),
            key=lambda t: t.start_time or datetime.min,
            reverse=True
        )
        return tasks[:limit]


def render_task_status(task: AsyncETLTask) -> None:
    """Render the status of an async task in Streamlit."""
    if task.status == "pending":
        st.info("⏳ Task pending...")
    elif task.status == "running":
        elapsed = ""
        if task.start_time:
            elapsed = f" (running for {(datetime.now() - task.start_time).seconds}s)"
        st.info(f"🔄 Task in progress{elapsed}")
    elif task.status == "completed":
        st.success("✅ Task completed successfully!")
    elif task.status == "failed":
        st.error(f"❌ Task failed: {task.error}")


def render_active_tasks_status() -> None:
    """Render status of all active background tasks."""
    active = get_active_tasks()
    
    if active:
        st.markdown("### 🔄 Active Background Tasks")
        for task_id, task in active.items():
            with st.expander(f"Task: {task_id}"):
                render_task_status(task)
