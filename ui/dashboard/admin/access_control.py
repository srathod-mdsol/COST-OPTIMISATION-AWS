"""
Admin Access Control Module

Provides access control functions for the admin module,
including session validation and admin-only action gates.
"""

import streamlit as st
from typing import Optional, Callable, Any
from functools import wraps

from ui.dashboard.admin.auth import get_auth_manager


def check_admin_access(session_state=None) -> bool:
    """Check if the current user has admin access.
    
    Args:
        session_state: Streamlit session state (defaults to st.session_state)
        
    Returns:
        True if user has admin access, False otherwise
    """
    if session_state is None:
        session_state = st.session_state
    
    # First check session state (set by render_auth_section)
    if session_state.get('admin_authenticated', False):
        return True
    
    # Also check is_admin for backward compatibility
    if session_state.get('is_admin', False):
        return True
    
    # Check if auth manager considers user authenticated
    auth = get_auth_manager()
    return auth.is_authenticated(session_state)


def is_admin_user(session_state=None) -> bool:
    """Check if current user is an admin (alias for check_admin_access).
    
    Args:
        session_state: Streamlit session state
        
    Returns:
        True if user is admin, False otherwise
    """
    return check_admin_access(session_state)


def require_admin(session_state=None) -> bool:
    """Require admin access - returns True if admin, False if not.
    Use this to gate admin-only functionality.
    
    Args:
        session_state: Streamlit session state
        
    Returns:
        True if user has admin access, False otherwise
    """
    if session_state is None:
        session_state = st.session_state
    
    return check_admin_access(session_state)


def admin_action_guard(session_state=None):
    """Decorator to guard a function/button behind admin authentication.
    
    Usage:
        @admin_action_guard()
        def my_admin_function():
            # Only admins can reach here
            ...
    
    Or use directly in render logic:
        if admin_action_guard():
            # Show admin-only UI
    """
    return check_admin_access(session_state)


def render_access_warning() -> None:
    """Render an access warning message for non-admin users."""
    st.markdown('''
    <div style="
        background: rgba(255, 153, 0, 0.1);
        border: 1px solid rgba(255, 153, 0, 0.3);
        border-radius: 8px;
        padding: 1rem;
        margin: 1rem 0;
    ">
        <p style="margin: 0; color: #ff9900; font-size: 0.9rem;">
            🔐 <strong>Admin Access Required</strong><br>
            Please log in as an admin to access this feature.
        </p>
    </div>
    ''', unsafe_allow_html=True)


def render_admin_required_button(
    label: str,
    help_text: str = "Admin login required",
    button_type: str = "secondary",
    disabled: bool = True,
    use_container_width: bool = True,
    session_state=None
) -> None:
    """Render a disabled admin-required button.
    
    Args:
        label: Button label
        help_text: Tooltip help text
        button_type: Button type (primary, secondary, tertiary)
        disabled: Whether button is disabled
        use_container_width: Use full container width
        session_state: Streamlit session state
    """
    if session_state is None:
        session_state = st.session_state
    
    # Check if user is admin - if so, button should be enabled
    is_admin = check_admin_access(session_state)
    
    st.button(
        label,
        help=help_text if not is_admin else None,
        type=button_type,
        disabled=(disabled and not is_admin),
        use_container_width=use_container_width
    )


def with_admin_access(func: Callable) -> Callable:
    """Decorator to wrap a Streamlit function with admin access check.
    
    Usage:
        @with_admin_access
        def render_admin_section():
            st.write("This is only visible to admins")
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        session_state = kwargs.get('session_state') or st.session_state
        
        if not check_admin_access(session_state):
            render_access_warning()
            return None
        
        return func(*args, **kwargs)
    
    return wrapper


def get_admin_users_list() -> list:
    """Get a list of configured admin usernames.
    
    Returns:
        List of admin usernames
    """
    auth = get_auth_manager()
    return list(auth.users().keys())


def has_admin_users_configured() -> bool:
    """Check if any admin users are configured in the system.
    
    Returns:
        True if admin users are configured, False otherwise
    """
    auth = get_auth_manager()
    return auth.has_users()