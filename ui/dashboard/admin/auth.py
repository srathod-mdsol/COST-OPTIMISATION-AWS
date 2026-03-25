"""
Admin Authentication Module

Provides Streamlit-specific authentication UI components for the admin module.
Imports and extends functionality from utils/auth.py.
"""

import streamlit as st
from typing import Optional
from datetime import datetime, timezone

# Import the core AuthManager from utils
from utils.auth import AuthManager

# Global auth manager instance
_auth_manager: Optional[AuthManager] = None


def get_auth_manager() -> AuthManager:
    """Get or create the global auth manager instance."""
    global _auth_manager
    if _auth_manager is None:
        _auth_manager = AuthManager()
    return _auth_manager


def render_auth_section(session_state=None) -> bool:
    """Render the admin authentication section in the admin page.
    
    Args:
        session_state: Streamlit session state (defaults to st.session_state)
        
    Returns:
        True if user is authenticated as admin, False otherwise
    """
    if session_state is None:
        session_state = st.session_state
    
    auth = get_auth_manager()
    
    # Check if admin users are configured
    if not auth.has_users():
        # No admin users configured - show info message and grant access
        st.markdown('''
        <div style="
            background: rgba(255, 153, 0, 0.1); 
            padding: 1rem; 
            border-radius: 10px; 
            border: 1px solid rgba(255, 153, 0, 0.3);
            margin-bottom: 1rem;
        ">
            <p style="margin: 0; font-size: 0.85rem; color: #ff9900;">
                🔐 Admin features unlocked. Configure ADMIN_USERS in .env to enable authentication.
            </p>
        </div>
        ''', unsafe_allow_html=True)
        session_state['admin_authenticated'] = True
        session_state['is_admin'] = True
        return True
    
    # Update activity timestamp if authenticated
    if auth.is_authenticated(session_state):
        auth.update_activity(session_state)
    
    # Check current authentication status
    is_authenticated = auth.is_authenticated(session_state)
    session_state['admin_authenticated'] = is_authenticated
    session_state['is_admin'] = is_authenticated
    
    if is_authenticated:
        # Show authenticated user section
        username = session_state.get('auth_user', 'Admin')
        
        st.markdown(f'''
        <div style="
            background: linear-gradient(135deg, #232f3e 0%, #3f4a5a 100%);
            padding: 1rem;
            border-radius: 10px;
            margin-bottom: 1rem;
        ">
            <div style="display: flex; align-items: center; justify-content: space-between;">
                <div>
                    <span style="color: #ff9900; font-weight: bold;">👤</span>
                    <span style="color: white; font-weight: 600;"> {username}</span>
                </div>
                <div>
                    <span style="color: #4ade80; font-size: 0.85rem;">✓ Authenticated</span>
                </div>
            </div>
        </div>
        ''', unsafe_allow_html=True)
        
        # Logout button
        with st.form("admin_logout_form_v2"):
            submitted = st.form_submit_button("🚪 Logout", use_container_width=True)
            if submitted:
                auth.logout(session_state)
                st.rerun()
        
        # Password change section
        st.markdown("---")
        st.markdown("### 🔑 Change Password")
        
        with st.form("password_change_form_v2"):
            current_password = st.text_input("Current Password", type="password")
            new_password = st.text_input("New Password", type="password")
            confirm_password = st.text_input("Confirm New Password", type="password")
            
            change_submitted = st.form_submit_button("Update Password", use_container_width=True)
            
            if change_submitted:
                if not current_password or not new_password or not confirm_password:
                    st.error("All password fields are required.")
                elif new_password != confirm_password:
                    st.error("New passwords do not match.")
                elif len(new_password) < 6:
                    st.error("Password must be at least 6 characters.")
                else:
                    success, message = auth.change_password(
                        username, current_password, new_password, session_state
                    )
                    if success:
                        st.success(message)
                    else:
                        st.error(message)
        
        return True
    else:
        # Show login form for unauthenticated users
        st.markdown('''
        <div style="
            background: linear-gradient(135deg, #232f3e 0%, #3f4a5a 100%);
            padding: 1rem;
            border-radius: 10px;
            margin-bottom: 1rem;
        ">
            <h3 style="
                color: #ff9900;
                font-size: 1rem;
                margin: 0;
                padding-bottom: 0.5rem;
                border-bottom: 2px solid #ff9900;
            ">🔐 Admin Login</h3>
        </div>
        ''', unsafe_allow_html=True)
        
        with st.form("admin_login_form_v2"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            
            submitted = st.form_submit_button("Login", use_container_width=True)
            
            if submitted:
                if not username or not password:
                    st.error("Username and password are required.")
                else:
                    # Authenticate user
                    success, message = auth.authenticate(username, password)
                    if success:
                        # Create session
                        auth.create_session(session_state, username)
                        st.success(message)
                        st.rerun()
                    else:
                        st.error(message)
        
        return False


def render_session_info(session_state=None) -> None:
    """Display session information for authenticated admin users.
    
    Args:
        session_state: Streamlit session state
    """
    if session_state is None:
        session_state = st.session_state
    
    auth = get_auth_manager()
    
    if auth.is_authenticated(session_state):
        last_activity = session_state.get('auth_last_activity')
        if last_activity:
            try:
                last_time = datetime.fromisoformat(str(last_activity).replace('Z', '+00:00'))
                elapsed = datetime.now(timezone.utc) - last_time
                minutes = int(elapsed.total_seconds() / 60)
                
                st.caption(f"Last activity: {minutes} minutes ago")
            except (ValueError, TypeError):
                pass
        
        # Show session timeout info
        timeout = auth._session_timeout_minutes
        st.caption(f"Session timeout: {timeout} minutes of inactivity")