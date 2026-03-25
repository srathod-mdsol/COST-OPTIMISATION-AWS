"""
Admin Module - Centralized Admin Functionality

This module provides a centralized admin interface for the AWS Cost Optimizer,
including authentication, access control, ETL management, and scheduling.
"""

from ui.dashboard.admin.auth import render_auth_section, get_auth_manager
from ui.dashboard.admin.access_control import check_admin_access, require_admin, is_admin_user
from ui.dashboard.admin.etl_controls import render_etl_controls, render_etl_lock_status
from ui.dashboard.admin.etl_status import render_etl_history, render_etl_metrics, get_etl_runs
from ui.dashboard.admin.scheduler import render_scheduler_settings, get_scheduler_status

__all__ = [
    # Auth
    'render_auth_section',
    'get_auth_manager',
    # Access Control
    'check_admin_access',
    'require_admin',
    'is_admin_user',
    # ETL Controls
    'render_etl_controls',
    'render_etl_lock_status',
    # ETL Status
    'render_etl_history',
    'render_etl_metrics',
    'get_etl_runs',
    # Scheduler
    'render_scheduler_settings',
    'get_scheduler_status',
]