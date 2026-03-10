"""
AWS Idle Identifier Dashboard

This module provides the main Streamlit dashboard interface.
For cached functions, import from ui.dashboard.cache instead.

Backward compatibility is maintained - all exports are available here.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
import traceback
import re
import os

from core.config import Config
from core.logger import setup_logger
from core.constants import HOURS_PER_MONTH, DAYS_PER_MONTH, DAYS_PER_YEAR, HOURS_PER_DAY
from services.rds_manager import RDSManager
from services.ec2_manager import EC2Manager
from services.ebs_manager import EBSManager
from etl.data_provider import ETLDataProvider
from etl.pricing_loader import PricingLoader
from etl.orchestrator import ETLOrchestrator
from analysis.idle_analyzer import IdleAnalyzer
from utils.auth import get_auth_manager

# Import cached functions from the modular cache module
# This reduces code duplication and centralizes caching logic
from ui.dashboard.cache import (
    get_ec2_detailed_breakdown_cached,
    get_rds_detailed_breakdown_cached,
    get_ebs_detailed_breakdown_cached,
    get_etl_provider_cached,
    get_instances_cached,
    get_data_freshness_cached,
    get_pricing_cached,
    get_instance_tags_cached,
    get_manager_cached,
    load_css_cached,
)

# Import UI components for modular design
from ui.dashboard.components import (
    render_auth_section as _render_auth_section,
    render_tags_display as _render_tags_display,
    render_instance_selector as _render_instance_selector,
    render_freshness_info as _render_freshness_info,
    render_header as _render_header,
    render_parameters as _render_parameters,
    get_manager as _get_manager,
)

logger = setup_logger(__name__)


class DashboardUI:
    """Streamlit-based presentation layer - EXACT REPLICA of original main.py UI"""
    
    def __init__(self):
        self.config = Config()
        self._initialize_session_state()
        # Use cached provider instead of creating new one each time
        self._etl_provider = None
        # Initialize data provider and database URL
        self.data_provider = ETLDataProvider(db_path=self.config.ETL_DB_PATH, database_url=self.config.DATABASE_URL)
        self.database_url = self.config.DATABASE_URL

    @property
    def etl_provider(self):
        """Get environment-specific ETL provider using cached instance."""
        if self._etl_provider is None:
            env = st.session_state.get('aws_environment', 'Default')
            self._etl_provider = get_etl_provider_cached(env)
        return self._etl_provider
        
    def _initialize_session_state(self):
        """Initialize Streamlit session state variables"""
        if 'scan_results' not in st.session_state:
            st.session_state.scan_results = None
        if 'scanning' not in st.session_state:
            st.session_state.scanning = False
        if 'instance_analysis_active' not in st.session_state:
            st.session_state.instance_analysis_active = False
        if 'analyzing_instance' not in st.session_state:
            st.session_state.analyzing_instance = None
        if 'selected_service' not in st.session_state:
            st.session_state.selected_service = 'RDS'
        # Pagination state
        if 'current_page' not in st.session_state:
            st.session_state.current_page = 1
        if 'page_size' not in st.session_state:
            st.session_state.page_size = 25

    def apply_custom_css(self):
        """Apply CSS from external file for better performance.
        
        Loads CSS from ui/styles.css file which can be cached by the browser.
        Falls back to minimal inline CSS if file not found.
        """
        css_content = load_css_cached()
        if css_content:
            st.markdown(f'<style>{css_content}</style>', unsafe_allow_html=True)
        else:
            # Minimal fallback CSS
            st.markdown("""
            <style>
                .main { background: #ffffff; color: #16191f; }
                .stApp { background: #ffffff; }
                h1 { color: #ff9900; }
            </style>
            """, unsafe_allow_html=True)

    def _render_auth_section(self, auth) -> None:
        """Render authentication section in sidebar.
        
        Shows login form for unauthenticated users, and user info/logout
        for authenticated users. Also provides password change functionality.
        
        Args:
            auth: AuthManager instance
        """
        # Check if admin users are configured
        if not auth.has_users():
            # No admin users configured - show info message
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
            # Set admin access to True when no users configured
            st.session_state['admin_authenticated'] = True
            return
        
        # Update activity timestamp if authenticated
        if auth.is_authenticated(st.session_state):
            auth.update_activity(st.session_state)
        
        if auth.is_authenticated(st.session_state):
            # Authenticated user info
            username = auth.get_current_user(st.session_state)
            remaining_time = auth.get_remaining_session_time(st.session_state)
            
            st.markdown('''
            <div style="
                background: rgba(0, 200, 83, 0.1); 
                padding: 1rem; 
                border-radius: 10px; 
                border: 1px solid rgba(0, 200, 83, 0.3);
                margin-bottom: 1rem;
            ">
                <h3 style="
                    color: #00c853 !important; 
                    font-size: 0.7rem !important; 
                    text-transform: uppercase; 
                    letter-spacing: 1.5px;
                    font-weight: 600 !important;
                    margin-bottom: 0.5rem;
                ">🔐 Admin Session</h3>
            </div>
            ''', unsafe_allow_html=True)
            
            st.markdown(f"**User:** {username}")
            if remaining_time is not None:
                st.markdown(f"**Session:** {remaining_time} min remaining")
            
            # Password change section
            with st.expander("🔑 Change Password"):
                with st.form("password_change_form"):
                    current_pwd = st.text_input("Current Password", type="password")
                    new_pwd = st.text_input("New Password", type="password")
                    confirm_pwd = st.text_input("Confirm New Password", type="password")
                    submit = st.form_submit_button("Update Password", use_container_width=True)
                    
                    if submit:
                        if not current_pwd or not new_pwd or not confirm_pwd:
                            st.error("Please fill in all fields")
                        elif new_pwd != confirm_pwd:
                            st.error("New passwords do not match")
                        elif len(new_pwd) < 8:
                            st.error("Password must be at least 8 characters")
                        else:
                            success, message = auth.change_password(username, current_pwd, new_pwd)
                            if success:
                                st.success(message)
                            else:
                                st.error(message)
            
            # Logout button
            if st.button("🚪 Logout", use_container_width=True, type="secondary"):
                auth.logout(st.session_state)
                st.rerun()
            
            st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
        else:
            # Login form
            st.markdown('''
            <div style="
                background: rgba(255, 255, 255, 0.05); 
                padding: 0.5rem; 
                border-radius: 8px; 
                border: 1px solid rgba(255, 255, 255, 0.1);
                margin-bottom: 0.5rem;
            ">
                <h3 style="
                    color: #ff9900 !important; 
                    font-size: 0.7rem !important; 
                    text-transform: uppercase; 
                    letter-spacing: 1.5px;
                    font-weight: 600 !important;
                    margin-bottom: 0.5rem;
                ">🔐 Admin Login</h3>
            </div>
            ''', unsafe_allow_html=True)
            
            with st.form("admin_login_form"):
                username = st.text_input("Username")
                password = st.text_input("Password", type="password")
                submit = st.form_submit_button("Login", use_container_width=True, type="primary")
                
                if submit:
                    if not username or not password:
                        st.error("Please enter username and password")
                    else:
                        success, message = auth.authenticate(username, password)
                        if success:
                            auth.create_session(st.session_state, username)
                            st.success("Login successful!")
                            st.rerun()
                        else:
                            st.error(message)
            
            st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
        
        # Store authentication status for use in other methods
        st.session_state['admin_authenticated'] = auth.is_authenticated(st.session_state)

    def render_sidebar(self, manager=None) -> tuple:
        """Render sidebar configuration with improved organization and accessibility"""
        with st.sidebar:
            # Header with icon
            st.markdown('''
            <div style="text-align: center; padding: 1rem 0; border-bottom: 1px solid var(--glass-border); margin-bottom: 1rem;">
                <h2 style="font-size: 1.5rem; margin: 0;">⚙️ Configuration</h2>
            </div>
            ''', unsafe_allow_html=True)
            
            # AWS Environment Selection
            st.markdown('''
            <div style="
                background: rgba(255,255,255,0.05); 
                padding: 0.5rem; 
                border-radius: 8px; 
                border: 1px solid rgba(255,255,255,0.1);
                margin-bottom: 0.5rem;
            ">
                <h3 style="
                    color: #ff9900 !important; 
                    font-size: 0.7rem !important; 
                    text-transform: uppercase; 
                    letter-spacing: 1.5px;
                    font-weight: 600 !important;
                    margin-bottom: 0.5rem;
                ">☁️ AWS Environment</h3>
            </div>
            ''', unsafe_allow_html=True)
            
            available_envs = Config.get_available_environments()
            if 'aws_environment' not in st.session_state:
                st.session_state.aws_environment = available_envs[0]
                
            selected_env = st.selectbox(
                "Select Account:",
                options=available_envs,
                index=available_envs.index(st.session_state.aws_environment) if st.session_state.aws_environment in available_envs else 0,
                key="env_selector_ui"
            )
            
            if selected_env != st.session_state.aws_environment:
                st.session_state.aws_environment = selected_env
                st.session_state.scan_results = None
                st.session_state.scanning = False
                st.session_state.instance_analysis_active = False
                st.rerun()

            # Service Selection with styled header
            st.markdown('''
            <div style="
                background: rgba(255,255,255,0.05); 
                padding: 0.5rem; 
                border-radius: 8px; 
                border: 1px solid rgba(255,255,255,0.1);
                margin-bottom: 0.5rem;
            ">
                <h3 style="
                    color: #ff9900 !important; 
                    font-size: 0.7rem !important; 
                    text-transform: uppercase; 
                    letter-spacing: 1.5px;
                    font-weight: 600 !important;
                    margin-bottom: 0.5rem;
                ">🖥️ Service Type</h3>
            </div>
            ''', unsafe_allow_html=True)
            
            # Use simple radio buttons instead of segmented control for plain buttons
            service_type = st.radio(
                "Select Service",
                options=['RDS', 'EC2'],
                horizontal=True,
                index=0 if st.session_state.selected_service == 'RDS' else (1 if st.session_state.selected_service == 'EC2' else 0),
                key="service_selector"
            )
            
            if service_type != st.session_state.selected_service:
                st.session_state.selected_service = service_type
                st.session_state.scan_results = None
                st.session_state.scanning = False
                st.session_state.instance_analysis_active = False
            
            # Region Selection with styled header
            st.markdown('''
            <div style="
                background: rgba(255,255,255,0.05); 
                padding: 0.5rem; 
                border-radius: 8px; 
                border: 1px solid rgba(255,255,255,0.1);
                margin-bottom: 0.5rem;
            ">
                <h3 style="
                    color: #ff9900 !important; 
                    font-size: 0.7rem !important; 
                    text-transform: uppercase; 
                    letter-spacing: 1.5px;
                    font-weight: 600 !important;
                    margin-bottom: 0.5rem;
                ">🌍 Region</h3>
            </div>
            ''', unsafe_allow_html=True)
            
            # Get regions from aws_regions table (cached discovered regions)
            # Fall back to all available AWS regions if no data exists
            try:
                db_regions = self.data_provider.fetch_all(
                    "SELECT region_name FROM aws_regions WHERE is_enabled = TRUE ORDER BY region_name"
                )
                if db_regions:
                    all_regions = [r['region_name'] for r in db_regions]
                else:
                    # No cached regions yet - discover from AWS
                    orchestrator = ETLOrchestrator(database_url=self.database_url)
                    all_regions = orchestrator.get_all_aws_regions(st.session_state.get('aws_environment', 'Default'))
            except Exception as e:
                # Log the exception for debugging
                logger.warning(f"Could not fetch regions from database: {e}")
                # Discover from AWS using orchestrator (which has proper error handling)
                try:
                    orchestrator = ETLOrchestrator(database_url=self.database_url)
                    all_regions = orchestrator.get_all_aws_regions(st.session_state.get('aws_environment', 'Default'))
                except Exception as e2:
                    logger.error(f"Could not discover regions from AWS: {e2}")
                    # Final fallback to all known AWS regions from constants
                    from core.constants import AWS_REGIONS
                    all_regions = AWS_REGIONS
            
            region = st.selectbox(
                "Select Region:",
                options=all_regions,
                index=0,
                format_func=lambda x: x.replace('-', ' ').title(),
                help="AWS region to scan for resources"
            )

            st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
            
            # Analysis Mode Section with styled header
            st.markdown('''
            <div style="
                background: rgba(255,255,255,0.05); 
                padding: 0.5rem; 
                border-radius: 8px; 
                border: 1px solid rgba(255,255,255,0.1);
                margin-bottom: 0.5rem;
            ">
                <h3 style="
                    color: #ff9900 !important; 
                    font-size: 0.7rem !important; 
                    text-transform: uppercase; 
                    letter-spacing: 1.5px;
                    font-weight: 600 !important;
                    margin-bottom: 0.5rem;
                ">📊 Analysis Mode</h3>
            </div>
            ''', unsafe_allow_html=True)
            
            analysis_mode = st.radio(
                "Choose mode:",
                ["Scan All Instances", "Analyze Single Instance"],
                captions=["Scan all resources at once", "Deep dive into specific resource"]
            )

            selected_instance = None
            
            # Initialize manager first for use in instance selector
            manager = self._get_manager(service_type, region)
            
            if analysis_mode == "Analyze Single Instance":
                selected_instance = self._render_instance_selector(manager, service_type)

            st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
            
            # Action Buttons with styled header
            st.markdown('''
            <div style="
                background: rgba(255,255,255,0.05); 
                padding: 0.5rem; 
                border-radius: 8px; 
                border: 1px solid rgba(255,255,255,0.1);
                margin-bottom: 0.5rem;
            ">
                <h3 style="
                    color: #ff9900 !important; 
                    font-size: 0.7rem !important; 
                    text-transform: uppercase; 
                    letter-spacing: 1.5px;
                    font-weight: 600 !important;
                    margin-bottom: 0.5rem;
                ">🎯 Actions</h3>
            </div>
            ''', unsafe_allow_html=True)
            
            scan_button = False
            analyze_button = False
            
            if analysis_mode == "Scan All Instances":
                scan_button = st.button(
                    "🚀 Scan All Resources", 
                    type="primary", 
                    use_container_width=True,
                    help="Scan all instances/buckets in the selected region"
                )
            else:
                analyze_button = st.button(
                    "🔍 Analyze Resource", 
                    type="primary", 
                    use_container_width=True,
                    help="Analyze the selected resource in detail"
                )

            # Data Freshness Info
            self._render_freshness_info(service_type)
            
            # Authentication Section - at bottom
            auth = get_auth_manager()
            self._render_auth_section(auth)
            
            # Data Management Section - below Admin Login
            st.markdown('''
            <div style="
                background: rgba(255,255,255,0.05); 
                padding: 0.5rem; 
                border-radius: 8px; 
                border: 1px solid rgba(255,255,255,0.1);
                margin-bottom: 0.5rem;
            ">
                <h3 style="
                    color: #ff9900 !important; 
                    font-size: 0.7rem !important; 
                    text-transform: uppercase; 
                    letter-spacing: 1.5px;
                    font-weight: 600 !important;
                    margin-bottom: 0.5rem;
                ">📥 Data Management</h3>
            </div>
            ''', unsafe_allow_html=True)
            
            # Check authentication for admin actions
            admin_authenticated = st.session_state.get('admin_authenticated', False)
            
            # Check ETL lock status for conditional UI
            orchestrator = ETLOrchestrator(database_url=self.config.DATABASE_URL)
            is_locked = orchestrator.is_etl_locked()
            
            # Show lock warning if ETL is locked (admin only)
            if is_locked:
                if admin_authenticated:
                    st.warning("⚠️ ETL process is currently locked. A previous ETL run may have been interrupted.")
                    if st.button("🔓 Force Unlock ETL", 
                                 help="Release the ETL lock if a previous run was interrupted",
                                 use_container_width=True,
                                 type="secondary"):
                        try:
                            orchestrator.force_unlock()
                            st.success("ETL lock released successfully!")
                            st.rerun()
                        except Exception as e:
                            logger.error(f"Failed to release ETL lock: {e}", exc_info=True)
                            st.error(f"Failed to release lock: {e}")
                    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
                else:
                    st.warning("⚠️ ETL process is locked. Login as admin to unlock.")
            
            # Admin-only buttons: Refresh Data and Reload Pricing
            if admin_authenticated:
                # Add some spacing for buttons
                col_etl1, col_etl2 = st.columns([1, 1])
                with col_etl1:
                    if st.button("🔄 Refresh Data", 
                                 help="Fetches fresh data from AWS and reloads database",
                                 use_container_width=True,
                                 type="primary",
                                 disabled=is_locked):
                        with st.spinner("Executing ETL process..."):
                            try:
                                self.etl_provider.truncate_and_reload(aws_environment=st.session_state.aws_environment)
                                st.success("Data refreshed successfully!")
                                # Clear Streamlit cache after data refresh
                                st.cache_data.clear()
                                st.rerun()
                            except Exception as e:
                                logger.error(f"ETL refresh failed: {e}", exc_info=True)
                                st.error("ETL refresh failed. Check application logs.")
                
                with col_etl2:
                    if st.button("💲 Reload Pricing", 
                                 help="Update pricing cache from AWS",
                                 use_container_width=True,
                                 type="primary"):
                        with st.spinner("Updating pricing cache..."):
                            try:
                                PricingLoader.run_etl(
                                    self.config.PRICING_DB_PATH,
                                    regions=['us-east-1'],  # Default region for pricing
                                    ec2_json_path=self.config.PRICING_JSON_PATHS['ec2'],
                                    rds_json_path=self.config.PRICING_JSON_PATHS['rds']
                                )
                                st.success(f"Pricing updated!")
                            except Exception as e:
                                logger.error(f"Pricing ETL failed: {e}", exc_info=True)
                                st.error("Pricing ETL failed. Check logs.")
                                logger.error(f"Pricing ETL error: {e}")
            else:
                # Show disabled buttons with lock icon for non-admin users
                col_etl1, col_etl2 = st.columns([1, 1])
                with col_etl1:
                    st.button("🔄 Refresh Data", 
                             help="Admin login required",
                             use_container_width=True,
                             type="secondary",
                             disabled=True)
                with col_etl2:
                    st.button("💲 Reload Pricing", 
                             help="Admin login required",
                             use_container_width=True,
                             type="secondary",
                             disabled=True)
                st.info("🔐 Login as admin to access data management features.")
            
            return manager, service_type, region, scan_button, analyze_button, selected_instance

    def _get_manager(self, service_type: str, region: str):
        """Get appropriate service manager with environment awareness using cached instance."""
        env = st.session_state.get('aws_environment', 'Default')
        return get_manager_cached(service_type, region, env)

    def _render_tags_display(self, instance_id: str):
        """Render tags for an instance from the separate tags table using cached lookup."""
        env = st.session_state.get('aws_environment', 'Default')
        tags = get_instance_tags_cached(instance_id, env)
        
        if tags:
            st.markdown("### 🏷️ Tags")
            # Create a nice visual display of tags with AWS-style coloring
            # Use a single string without leading whitespace to prevent markdown code block detection
            tag_html = '<div style="display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; margin-bottom: 20px;">'
            for key, value in tags.items():
                tag_html += (
                    f'<div style="background: linear-gradient(135deg, #232f3e 0%, #3f4a5a 100%); '
                    f'color: white; padding: 5px 12px; border-radius: 4px; font-size: 0.85rem; '
                    f'border: 1px solid rgba(255,255,255,0.1); display: flex; align-items: center; gap: 6px;">'
                    f'<span style="color: #ff9900; font-weight: bold;">{key}:</span> '
                    f'<span style="color: #ffffff;">{value}</span></div>'
                )
            tag_html += '</div>'
            st.markdown(tag_html, unsafe_allow_html=True)
        else:
            st.markdown("### 🏷️ Tags")
            st.info("ℹ️ No tags found for this resource in the database.")
            st.caption("💡 Run a fresh ETL scan to capture and store tags in the new tags table.")

    def _render_instance_selector(self, manager, service_type: str):
        """Render instance/bucket selector with improved UX"""
        try:
            with st.container():
                st.markdown('**Select a resource to analyze:**')
                
                # Get instances
                if service_type == 'RDS':
                    instances = manager.list_instances()
                    ids = [i['instance_id'] for i in instances]
                elif service_type == 'EC2':
                    instances = manager.list_instances()
                    ids = [f"{i['instance_id']} ({i.get('name', 'N/A')})" for i in instances]
                elif service_type == 'EBS':
                    instances = manager.list_instances()
                    ids = [f"{i['volume_id']} ({i.get('name', 'N/A')})" for i in instances]

                if not ids:
                    st.warning(f"⚠️ No {service_type} resources found")
                    st.caption("Try refreshing the data or selecting a different region.")
                    return None
                
                # Search input
                search = st.text_input(
                    "🔍 Search", 
                    placeholder="Filter resources...", 
                    key=f"{service_type}_search",
                    help="Type to filter the list below"
                )
                
                if search:
                    # Security: Sanitize search input to prevent injection/path concerns
                    search = re.sub(r'[^a-zA-Z0-9\-_./\s]', '', search)
                    
                    ids = [i for i in ids if search.lower() in i.lower()]
                    if not ids:
                        st.warning(f"No resources match '{search}'")
                        return None
                
                # Selection
                selected = st.selectbox(
                    "Select Resource:",
                    options=ids,
                    help="Choose a resource to analyze"
                )
                
                # Show count
                st.caption(f"Showing {len(ids)} of {len(instances)} resources")
                
                # Extract instance ID from formatted string for EC2
                return selected.split(' (')[0] if service_type == 'EC2' else selected
                
        except Exception as e:
            logger.error(f"Error listing resources: {e}", exc_info=True)
            st.error("Error listing resources. Please ensure AWS credentials are valid and region is accessible.")
            logger.error(f"Instance selector error: {e}")
        return None

    def _render_freshness_info(self, service_type: str):
        """Display data freshness info with proper sidebar styling using cached lookup."""
        st.markdown('### 📊 Data Status')
        
        env = st.session_state.get('aws_environment', 'Default')
        freshness = get_data_freshness_cached(service_type, env)
        
        if freshness:
            # Status indicator
            last_updated = freshness.get('last_updated')
            record_count = freshness.get('record_count', 0)
            status = freshness.get('status', 'unknown')
            
            # Determine status color for dark sidebar
            if status == 'fresh':
                status_icon = "🟢"
                status_color = "#00d8ff"
                status_text = "Fresh"
            elif status == 'stale':
                status_icon = "🟡"
                status_color = "#ffbf00"
                status_text = "Stale"
            else:
                status_icon = "⚪"
                status_color = "#aab7c4"
                status_text = "Unknown"
            
            # Display with dark sidebar-friendly styling
            st.markdown(f"""
            <div style="
                background: rgba(255,255,255,0.08); 
                padding: 1rem; 
                border-radius: 8px; 
                border: 1px solid rgba(255,255,255,0.1);
                margin-top: 0.5rem;
            ">
                <div style="
                    display: flex; 
                    align-items: center; 
                    gap: 8px; 
                    margin-bottom: 0.75rem;
                    color: #ffffff;
                ">
                    <span style="font-size: 1.2rem;">{status_icon}</span>
                    <strong style="color: {status_color};">Status: {status_text}</strong>
                </div>
                <p style="
                    margin: 0.5rem 0; 
                    color: #aab7c4; 
                    font-size: 0.85rem;
                    line-height: 1.4;
                ">
                    <span style="color: #ffffff;">Last Updated:</span> {last_updated or 'Never'}
                </p>
                <p style="
                    margin: 0.5rem 0; 
                    color: #aab7c4; 
                    font-size: 0.85rem;
                    line-height: 1.4;
                ">
                    <span style="color: #ffffff;">Records:</span> {record_count:,}
                </p>
            </div>
            """, unsafe_allow_html=True)
        else:
            # Warning for dark sidebar
            st.markdown("""
            <div style="
                background: rgba(255,191,0,0.15); 
                padding: 0.75rem; 
                border-radius: 6px; 
                border-left: 3px solid #ffbf00;
                margin-top: 0.5rem;
            ">
                <p style="margin: 0; color: #ffbf00; font-size: 0.85rem;">
                    <strong>⚠️ No data available</strong>
                </p>
            </div>
            """, unsafe_allow_html=True)
            st.caption("Click 'Refresh Data' to load AWS resources.")

    def render_header(self):
        """Render main header with AWS Console styling and animations"""
        st.markdown("""
        <!-- AWS Console Style Header with Animations -->
        <div class="aws-header">
            <div class="aws-header-left">
                <div class="aws-logo-container">
                    <svg class="aws-logo" width="48" height="48" viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <defs>
                            <linearGradient id="awsGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                                <stop offset="0%" style="stop-color:#FF9900;stop-opacity:1" />
                                <stop offset="100%" style="stop-color:#FF6600;stop-opacity:1" />
                            </linearGradient>
                        </defs>
                        <path d="M32 4L4 22V50L32 62L60 50V22L32 4Z" stroke="url(#awsGrad)" stroke-width="2" fill="rgba(255,153,0,0.1)"/>
                        <path d="M32 14L14 25V43L32 52L50 43V25L32 14Z" fill="url(#awsGrad)"/>
                    </svg>
                </div>
                <div class="aws-header-text">
                    <h1>AWS Idle Instance Monitor</h1>
                    <p class="aws-subtitle">Intelligent Cost Optimization & Resource Management</p>
                </div>
            </div>
            <div class="aws-header-right">
                <div class="aws-status-indicator">
                    <span class="status-pulse"></span>
                    <span>System Online</span>
                </div>
                <div class="aws-version-badge">v2.0</div>
            </div>
        </div>
        
        <style>
        .aws-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 1.5rem 2rem;
            background: linear-gradient(135deg, #232f3e 0%, #1a2332 100%);
            border-radius: 12px;
            margin-bottom: 1.5rem;
            box-shadow: 0 4px 20px rgba(0,0,0,0.15);
        }
        
        .aws-header-left {
            display: flex;
            align-items: center;
            gap: 1.5rem;
        }
        
        .aws-logo-container {
            position: relative;
        }
        
        .aws-logo {
            animation: float 3s ease-in-out infinite;
        }
        
        @keyframes float {
            0%, 100% { transform: translateY(0); }
            50% { transform: translateY(-5px); }
        }
        
        .aws-header-text h1 {
            margin: 0;
            font-size: 1.75rem;
            font-weight: 700;
            color: #ffffff;
            letter-spacing: -0.5px;
        }
        
        .aws-subtitle {
            margin: 0.25rem 0 0 0;
            color: #aab7c4;
            font-size: 0.9rem;
        }
        
        .aws-header-right {
            display: flex;
            align-items: center;
            gap: 1rem;
        }
        
        .aws-status-indicator {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.5rem 1rem;
            background: rgba(0,113,133,0.2);
            border-radius: 20px;
            color: #00d8ff;
            font-size: 0.85rem;
            font-weight: 500;
        }
        
        .status-pulse {
            width: 8px;
            height: 8px;
            background: #00d8ff;
            border-radius: 50%;
            animation: pulse 2s ease-in-out infinite;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.5; transform: scale(1.2); }
        }
        
        .aws-version-badge {
            padding: 0.35rem 0.75rem;
            background: #ff9900;
            color: #232f3e;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 600;
        }
        
        .aws-header-divider {
            border: none;
            height: 2px;
            background: linear-gradient(90deg, transparent, #ff9900, transparent);
            margin: 0 0 1.5rem 0;
        }
        </style>
        """, unsafe_allow_html=True)

    def render_parameters(self) -> tuple:
        """Render parameter controls with improved spacing"""
        st.markdown('''
        <div style="
            background: #ffffff; 
            border: 1px solid #dfe3e8; 
            border-radius: 10px; 
            padding: 1.5rem; 
            margin: 1rem 0 2rem 0;
        ">
            <h3 style="
                color: #232f3e; 
                font-size: 1.1rem; 
                margin: 0 0 1.5rem 0;
                padding-bottom: 0.75rem;
                border-bottom: 2px solid #ff9900;
            ">⚡ Mission Parameters</h3>
        </div>
        ''', unsafe_allow_html=True)
        
        # Create three columns with helpful tooltips
        col1, col2, col3 = st.columns(3)
        
        with col1:
            cw_hours = st.slider(
                "CloudWatch Lookback", 
                min_value=1, 
                max_value=2160, 
                value=2160,
                help="How far back to look for CloudWatch metrics (in hours). Higher values = more historical data but slower queries."
            )
            st.caption(f"📊 Viewing {cw_hours // 24} day(s) of metrics")
            
        with col2:
            act_days = st.slider(
                "Activity Detection Window", 
                min_value=1, 
                max_value=90, 
                value=30,
                help="Days of inactivity before marking a resource as potentially idle. Longer windows = fewer false positives."
            )
            st.caption(f"🔍 {act_days} day activity window")
            
        with col3:
            threshold = st.slider(
                "Idle Score Threshold", 
                min_value=0, 
                max_value=100, 
                value=70,
                help="Minimum idle score (0-100) to classify as idle. Higher = more strict classification."
            )
            st.caption(f"🎯 Threshold: {threshold}+")
        
        # Pricing Model Settings Section
        st.markdown('''
        <div style="
            background: #ffffff; 
            border: 1px solid #dfe3e8; 
            border-radius: 10px; 
            padding: 1.5rem; 
            margin: 1rem 0 2rem 0;
        ">
            <h3 style="
                color: #232f3e; 
                font-size: 1.1rem; 
                margin: 0 0 1.5rem 0;
                padding-bottom: 0.75rem;
                border-bottom: 2px solid #ff9900;
            ">💰 Pricing Model Settings</h3>
        </div>
        ''', unsafe_allow_html=True)
        
        # Pricing model selection
        pricing_col1, pricing_col2, pricing_col3 = st.columns(3)
        
        with pricing_col1:
            pricing_model = st.selectbox(
                "Pricing Model",
                options=["On-Demand", "Reserved Instances", "Savings Plans"],
                index=0,
                help="Select your pricing model to calculate accurate potential savings."
            )
        
        # Initialize pricing settings dictionary
        pricing_settings = {
            'pricing_model': pricing_model,
            'ri_coverage': 0,
            'sp_coverage': 0,
            'use_actual_runtime': False,
            'actual_hours': None
        }
        
        if pricing_model == "Reserved Instances":
            with pricing_col2:
                ri_coverage = st.slider(
                    "RI Coverage", 
                    min_value=0, 
                    max_value=100, 
                    value=0,
                    help="Percentage of instances covered by Reserved Instances (0-100%). This reduces the calculated savings."
                )
                pricing_settings['ri_coverage'] = ri_coverage / 100.0
            st.caption(f"🔒 {ri_coverage}% covered by RI")
        elif pricing_model == "Savings Plans":
            with pricing_col2:
                sp_coverage = st.slider(
                    "Savings Plans Coverage", 
                    min_value=0, 
                    max_value=100, 
                    value=0,
                    help="Percentage of instances covered by Savings Plans (0-100%). This reduces the calculated savings."
                )
                pricing_settings['sp_coverage'] = sp_coverage / 100.0
            st.caption(f"💎 {sp_coverage}% covered by Savings Plans")
        
        with pricing_col3:
            use_actual_runtime = st.checkbox(
                "Use Actual Runtime",
                value=False,
                help="Use actual instance runtime hours instead of fixed 730 hours/month for more accurate savings."
            )
            pricing_settings['use_actual_runtime'] = use_actual_runtime
        
        if use_actual_runtime:
            st.caption("📈 Using actual runtime hours for cost calculation")
        else:
            st.caption("📅 Using fixed 730 hours/month (average)")
        
        return cw_hours, act_days, threshold, pricing_settings

    def display_single_analysis(self, manager, service_type, instance_id, cloudwatch_hours, activity_days, pricing_settings=None):
        """Display single instance analysis with improved visual hierarchy"""
        
        # Default pricing settings if not provided
        if pricing_settings is None:
            pricing_settings = {
                'pricing_model': 'On-Demand',
                'ri_coverage': 0,
                'sp_coverage': 0,
                'use_actual_runtime': False,
                'actual_hours': None
            }
        
        with st.spinner(f"🔍 Analyzing {instance_id}..."):
            try:
                # Fetch metrics
                metrics = manager.get_cloudwatch_metrics(instance_id, cloudwatch_hours)
                last_activity = manager.detect_last_activity(instance_id, activity_days)
                
                # Get instance info
                attached_volumes = []
                if service_type == 'RDS':
                    instances = manager.list_instances()
                    instance_info = next((i for i in instances if i.get('instance_id') == instance_id), None)
                elif service_type == 'EC2':
                    instances = manager.list_instances()
                    instance_info = next((i for i in instances if i.get('instance_id') == instance_id), None)
                    attached_volumes = manager.get_attached_volumes(instance_id)
                elif service_type == 'EBS':
                    instances = manager.list_instances()
                    instance_info = next((i for i in instances if i.get('volume_id') == instance_id), None)

                if not instance_info:
                    st.error("Resource information not found")
                    return

                # Run analysis
                if service_type == 'RDS':
                    analysis = IdleAnalyzer.analyze_rds(metrics, last_activity, activity_days)
                elif service_type == 'EC2':
                    analysis = IdleAnalyzer.analyze_ec2(metrics, last_activity, activity_days)
                elif service_type == 'EBS':
                    analysis = IdleAnalyzer.analyze_ebs(metrics, last_activity, activity_days)

                # Header
                st.markdown(f'## 🔍 {service_type} Analysis: {instance_info.get("instance_id", instance_info.get("name"))}')
                
                # Severity badge
                severity = analysis['severity']
                badge_class = "idle-badge" if severity in ['CRITICAL', 'HIGH'] else "active-badge"
                if severity == 'MEDIUM':
                    badge_class = "warning-badge"
                
                # Top-level metrics row
                metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
                
                with metric_col1:
                    if service_type == 'RDS':
                        st.metric("Instance Identifier", instance_info.get('instance_id', instance_info.get('db_instance_identifier', 'N/A')))
                        st.metric("Instance Class", instance_info.get('instance_class', 'N/A'))
                        st.metric("Engine", instance_info.get('engine', 'N/A'))
                    elif service_type == 'EC2':
                        st.metric("Instance ID", instance_info.get('instance_id', 'N/A'))
                        st.metric("Instance Type", instance_info.get('instance_type', 'N/A'))
                        st.metric("Platform", instance_info.get('platform', 'N/A'))
                    elif service_type == 'EBS':
                        st.metric("Volume Type", instance_info.get('volume_type', 'N/A'))
                        st.metric("Size", f"{instance_info.get('size_gb', 0)} GB")
                
                with metric_col2:
                    if service_type == 'EBS':
                        st.metric("Attached To", instance_info.get('attached_instance_id', 'Unattached'))
                        st.metric("Status", instance_info.get('status', 'unknown'))
                    else:
                        st.metric("Status", instance_info.get('status', instance_info.get('state', 'N/A')))
                    
                    # Display last activity with exact timestamp
                    days_idle = last_activity.get('days_since_activity')
                    last_time = last_activity.get('last_activity_time')
                    activity_details = last_activity.get('activity_details', {})
                    
                    if last_time:
                        if isinstance(last_time, str):
                            from datetime import datetime
                            last_time = datetime.fromisoformat(last_time.replace('Z', '+00:00'))
                        st.metric("Last Activity", f"{days_idle:.1f} days ago")
                        st.caption(f"📅 {last_time.strftime('%Y-%m-%d %H:%M UTC')}")
                        if activity_details.get('metric_name'):
                            st.caption(f"📊 {activity_details['metric_name']} = {activity_details.get('metric_value', 0):.2f}")
                    elif days_idle is not None and days_idle != float('inf'):
                        if days_idle < 1:
                            st.metric("Last Activity", "<1 day ago")
                        else:
                            st.metric("Last Activity", f"{days_idle:.1f} days ago")
                    else:
                        st.metric("Last Activity", "No data")
                        st.caption("⚠️ Run ETL to collect metrics")
                
                with metric_col3:
                    st.metric("Idle Score", f"{analysis['idle_score']:.0f}%")
                    st.metric("Severity", severity, delta_color="inverse")
                
                with metric_col4:
                    st.markdown(f'<div class="{badge_class}" style="text-align: center; margin-top: 1rem;">{severity} - Score: {analysis["idle_score"]:.0f}%</div>', unsafe_allow_html=True)
                    st.markdown(f"**{analysis['recommendation']}**")

                # Tags Section - NEW
                st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
                self._render_tags_display(instance_id)

                # Cost Savings Section
                if severity in ['CRITICAL', 'HIGH', 'MEDIUM']:
                    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
                    st.markdown('### 💰 Potential Cost Savings (Considering only Idle Instances)')
                    region = instance_info.get('region', 'us-east-1')
                    
                    # Get actual hours based on pricing settings
                    if pricing_settings.get('use_actual_runtime', False):
                        try:
                            from analysis.cost_calculator import CostCalculator
                            actual_hours = CostCalculator.get_actual_runtime_hours(instance_id)
                        except:
                            actual_hours = HOURS_PER_MONTH
                    else:
                        actual_hours = HOURS_PER_MONTH
                    
                    # Calculate discount factor based on pricing model
                    ri_coverage = pricing_settings.get('ri_coverage', 0)
                    sp_coverage = pricing_settings.get('sp_coverage', 0)
                    discount_factor = 1.0 - max(ri_coverage, sp_coverage)
                    
                    if service_type == 'RDS':
                        sku = instance_info.get('instance_class', '').replace('db.', '')
                        # Pass additional parameters for accurate pricing
                        database_engine = instance_info.get('engine', '')
                        deployment_option = 'Multi-AZ' if instance_info.get('multi_az') in [True, 'true', 'True', 'yes', 'Yes'] else 'Single-AZ'
                        license_model = instance_info.get('license_model', '')
                        hourly_cost = self.etl_provider.get_pricing(
                            sku, region, service='RDS',
                            database_engine=database_engine,
                            deployment_option=deployment_option,
                            license_model=license_model
                        )
                        if not hourly_cost:
                            st.warning(f"Pricing data not available for {sku} ({database_engine}) in {region}")
                            return
                        
                        # Add RDS storage costs - use RDS-specific pricing (DIFFERENT from EBS!)
                        from analysis.cost_calculator import CostCalculator
                        storage_type = instance_info.get('storage_type', 'gp2')
                        allocated_storage = instance_info.get('allocated_storage', 0)
                        iops = instance_info.get('iops', 0)
                        multi_az = instance_info.get('multi_az', False)
                        
                        if allocated_storage and allocated_storage > 0:
                            storage_cost = CostCalculator.calculate_rds_storage_cost(
                                int(allocated_storage), storage_type, 
                                iops=int(iops) if iops else None,
                                multi_az=multi_az,
                                region=region
                            )
                            monthly_storage_cost = storage_cost.get('monthly', 0)
                            # Also get IOPS monthly cost if applicable
                            iops_monthly_cost = storage_cost.get('iops_monthly', 0)
                        else:
                            monthly_storage_cost = 0
                            iops_monthly_cost = 0
                        
                        # Apply discount factor and use actual hours
                        monthly_savings = ((hourly_cost * actual_hours) + monthly_storage_cost + iops_monthly_cost) * discount_factor
                    elif service_type == 'EC2':
                        sku = instance_info.get('instance_type', '')
                        # Pass additional parameters for accurate pricing
                        operating_system = instance_info.get('platform', 'Linux/UNIX')
                        tenancy = instance_info.get('tenancy', 'shared')
                        hourly_cost = self.etl_provider.get_pricing(
                            sku, region, service='EC2',
                            operating_system=operating_system,
                            tenancy=tenancy
                        )
                        if not hourly_cost:
                            st.warning(f"Pricing data not available for {sku} ({operating_system}) in {region}")
                            return
                        # Apply discount factor and use actual hours
                        monthly_savings = (hourly_cost * actual_hours) * discount_factor
                    elif service_type == 'EBS':
                        monthly_savings = instance_info.get('monthly_cost', 0) * discount_factor
                        hourly_cost = monthly_savings / actual_hours if actual_hours > 0 else 0
                    
                    savings_col1, savings_col2, savings_col3 = st.columns(3)
                    with savings_col1:
                        st.metric("Hourly Cost", f"${hourly_cost:.4f}")
                    with savings_col2:
                        # Include EBS in savings for EC2 if applicable
                        if service_type == 'EC2' and attached_volumes:
                            total_ebs_cost = sum(v.get('monthly_cost', 0) for v in attached_volumes) * discount_factor
                            total_monthly = monthly_savings + total_ebs_cost
                            st.metric("Monthly Savings", f"${total_monthly:.2f}", delta=f"Incl. ${total_ebs_cost:.2f} EBS")
                            monthly_savings = total_monthly # For annual calculation
                        else:
                            st.metric("Monthly Savings", f"${monthly_savings:.2f}")
                    with savings_col3:
                        st.metric("Annual Savings", f"${monthly_savings * 12:.2f}")
                    
                    # Show pricing model info if not On-Demand
                    pricing_model = pricing_settings.get('pricing_model', 'On-Demand')
                    if pricing_model != 'On-Demand':
                        coverage = int(max(ri_coverage, sp_coverage) * 100)
                        st.caption(f"📊 {pricing_model} coverage applied: {coverage}% discount")

                    # =============================================================
                    # ITEMIZED COST BREAKDOWN SECTION
                    # =============================================================
                    
                    # Get environment for ETL provider calls
                    env = st.session_state.get('aws_environment', 'Default')
                    
                    with st.expander("📋 View Detailed Cost Breakdown", expanded=False):
                        if service_type == 'EC2':
                            # EC2 Detailed Cost Breakdown
                            st.markdown("### 💻 EC2 Instance Cost Breakdown")
                            
                            # Get detailed cost breakdown using cached function
                            try:
                                import json
                                # Build EBS volumes list from attached_volumes for cost calculation
                                ebs_volumes_for_calc = []
                                if attached_volumes:
                                    for vol in attached_volumes:
                                        ebs_volumes_for_calc.append({
                                            'volume_id': vol.get('volume_id', 'unknown'),
                                            'size_gb': vol.get('size_gb', 0),
                                            'volume_type': vol.get('volume_type', 'gp2'),
                                            'iops': vol.get('iops', 0),
                                            'throughput': vol.get('throughput_mbps', 0)
                                        })
                                
                                ebs_volumes_json = json.dumps(ebs_volumes_for_calc) if ebs_volumes_for_calc else '[]'
                                detailed_cost = get_ec2_detailed_breakdown_cached(
                                    instance_type=sku,
                                    region=region,
                                    operating_system=operating_system,
                                    tenancy=tenancy,
                                    hourly_price=hourly_cost,
                                    env=env,
                                    ebs_volumes_json=ebs_volumes_json
                                )
                                
                                # Display Compute Costs
                                compute = detailed_cost.get('compute', {})
                                st.markdown("**COMPUTE COSTS**")
                                col1, col2, col3, col4 = st.columns(4)
                                with col1:
                                    st.metric("Instance Type", detailed_cost.get('instance_type', sku))
                                with col2:
                                    st.metric("Operating System", operating_system)
                                with col3:
                                    st.metric("Unit Price", f"${compute.get('unit_price', 0):.4f}/hr")
                                with col4:
                                    st.metric("Hours/Month", f"{compute.get('hours', HOURS_PER_MONTH)}")
                                
                                st.markdown(f"""
                                <div style="background: rgba(0,100,0,0.1); padding: 10px; border-radius: 5px; margin: 10px 0;">
                                    <strong>Compute Subtotal:</strong> ${compute.get('monthly', 0):.2f}/month
                                </div>
                                """, unsafe_allow_html=True)
                                
                                # Display Storage Costs
                                storage = detailed_cost.get('storage', {})
                                volumes = storage.get('volumes', [])
                                if volumes:
                                    st.markdown("**STORAGE COSTS (EBS)**")
                                    for vol in volumes:
                                        st.markdown(f"""
                                        <div style="background: rgba(255,150,0,0.1); padding: 10px; border-radius: 5px; border-left: 3px solid #ff9900; margin: 5px 0;">
                                            <strong>Volume: {vol.get('volume_id', 'unknown')}</strong><br/>
                                            <small>Type: {vol.get('volume_type')} | Size: {vol.get('size_gb')} GB</small><br/>
                                            Storage: ${vol.get('storage_monthly', 0):.2f}/mo | IOPS: ${vol.get('iops_monthly', 0):.2f}/mo<br/>
                                            <strong>Total: ${vol.get('total_monthly', 0):.2f}/mo</strong>
                                        </div>
                                        """, unsafe_allow_html=True)
                                    
                                    st.markdown(f"""
                                    <div style="background: rgba(0,100,0,0.1); padding: 10px; border-radius: 5px; margin: 10px 0;">
                                        <strong>Storage Subtotal:</strong> ${storage.get('monthly', 0):.2f}/month
                                    </div>
                                    """, unsafe_allow_html=True)
                                
                                # Display Data Transfer
                                data_transfer = detailed_cost.get('data_transfer', {})
                                if data_transfer.get('gb_out', 0) > 0 or data_transfer.get('gb_in', 0) > 0:
                                    st.markdown("**DATA TRANSFER**")
                                    st.markdown(f"""
                                    <div style="background: rgba(0,0,100,0.1); padding: 10px; border-radius: 5px; margin: 10px 0;">
                                        Transfer OUT: {data_transfer.get('gb_out', 0)} GB @ ${data_transfer.get('rate_out', 0):.2f}/GB = ${data_transfer.get('cost_out', 0):.2f}<br/>
                                        <strong>Transfer Subtotal:</strong> ${data_transfer.get('monthly', 0):.2f}/month
                                    </div>
                                    """, unsafe_allow_html=True)
                                
                                # Total
                                st.markdown(f"""
                                <div style="background: rgba(0,150,0,0.2); padding: 15px; border-radius: 5px; margin: 15px 0; border: 2px solid #00aa00;">
                                    <strong style="font-size: 1.2em;">TOTAL MONTHLY COST: ${detailed_cost.get('monthly', 0):.2f}</strong><br/>
                                    <strong style="font-size: 1.2em;">TOTAL ANNUAL COST: ${detailed_cost.get('annual', 0):.2f}</strong>
                                </div>
                                """, unsafe_allow_html=True)
                                
                            except Exception as e:
                                st.warning(f"Could not generate detailed breakdown: {e}")
                                
                        elif service_type == 'RDS':
                            # RDS Detailed Cost Breakdown
                            st.markdown("### 🗄️ RDS Instance Cost Breakdown")
                            
                            try:
                                detailed_cost = get_rds_detailed_breakdown_cached(
                                    instance_type=sku,
                                    region=region,
                                    database_engine=database_engine,
                                    license_model=license_model,
                                    deployment_option=deployment_option,
                                    instance_hourly_price=hourly_cost,
                                    allocated_storage=allocated_storage,
                                    storage_type=storage_type,
                                    iops=int(iops) if iops else 0,
                                    multi_az=multi_az,
                                    env=env,
                                    backup_storage_gb=instance_info.get('backup_storage_gb', 0),
                                    backup_retention_days=instance_info.get('backup_retention_days', 7)
                                )
                                
                                # Display Compute Costs
                                compute = detailed_cost.get('compute', {})
                                st.markdown("**COMPUTE COSTS**")
                                col1, col2 = st.columns(2)
                                with col1:
                                    st.metric("Instance Type", detailed_cost.get('instance_type', sku))
                                with col2:
                                    st.metric("Database Engine", detailed_cost.get('database_engine', database_engine))
                                
                                col3, col4 = st.columns(2)
                                with col3:
                                    st.metric("Deployment", detailed_cost.get('deployment_option', deployment_option))
                                with col4:
                                    st.metric("Unit Price", f"${compute.get('unit_price', 0):.4f}/hr")
                                
                                st.markdown(f"""
                                <div style="background: rgba(0,100,0,0.1); padding: 10px; border-radius: 5px; margin: 10px 0;">
                                    <strong>Compute Subtotal:</strong> ${compute.get('monthly', 0):.2f}/month
                                </div>
                                """, unsafe_allow_html=True)
                                
                                # Display Storage Costs
                                storage = detailed_cost.get('storage', {})
                                st.markdown("**STORAGE COSTS**")
                                col1, col2, col3 = st.columns(3)
                                with col1:
                                    st.metric("Storage Type", storage.get('storage_type', storage_type))
                                with col2:
                                    st.metric("Allocated", f"{storage.get('allocated_storage_gb', 0)} GB")
                                with col3:
                                    st.metric("Multi-AZ Factor", f"{storage.get('multi_az_factor', 1)}x")
                                
                                st.markdown(f"""
                                <div style="background: rgba(255,150,0,0.1); padding: 10px; border-radius: 5px; border-left: 3px solid #ff9900; margin: 10px 0;">
                                    Effective Storage: {storage.get('effective_storage_gb', 0)} GB @ ${storage.get('rate_per_gb', 0):.3f}/GB/mo<br/>
                                    <strong>Storage Subtotal:</strong> ${storage.get('monthly', 0):.2f}/month
                                </div>
                                """, unsafe_allow_html=True)
                                
                                # Display IOPS Costs
                                iops_data = detailed_cost.get('iops', {})
                                if iops_data.get('provisioned'):
                                    st.markdown("**IOPS COSTS**")
                                    st.markdown(f"""
                                    <div style="background: rgba(100,100,0,0.1); padding: 10px; border-radius: 5px; margin: 10px 0;">
                                        Provisioned: {iops_data.get('provisioned', 0)} IOPS<br/>
                                        Base Included: {iops_data.get('base_included', 0)} IOPS<br/>
                                        Extra IOPS: {iops_data.get('extra_iops', 0)} @ ${iops_data.get('rate_per_iops', 0):.4f}/IOPS/mo<br/>
                                        <strong>IOPS Subtotal:</strong> ${iops_data.get('monthly', 0):.2f}/month
                                    </div>
                                    """, unsafe_allow_html=True)
                                
                                # Display Backup Storage Costs
                                backup_data = detailed_cost.get('backup', {})
                                if backup_data.get('storage_gb', 0) > 0:
                                    st.markdown("**BACKUP STORAGE COSTS**")
                                    st.markdown(f"""
                                    <div style="background: rgba(0,100,150,0.1); padding: 10px; border-radius: 5px; margin: 10px 0;">
                                        Backup Storage: {backup_data.get('storage_gb', 0)} GB<br/>
                                        Retention: {backup_data.get('retention_days', 7)} days<br/>
                                        Rate: ${backup_data.get('rate_per_gb', 0):.3f}/GB/mo<br/>
                                        <strong>Backup Subtotal:</strong> ${backup_data.get('monthly', 0):.2f}/month
                                    </div>
                                    """, unsafe_allow_html=True)
                                
                                # Total
                                st.markdown(f"""
                                <div style="background: rgba(0,150,0,0.2); padding: 15px; border-radius: 5px; margin: 15px 0; border: 2px solid #00aa00;">
                                    <strong style="font-size: 1.2em;">TOTAL MONTHLY COST: ${detailed_cost.get('monthly', 0):.2f}</strong><br/>
                                    <strong style="font-size: 1.2em;">TOTAL ANNUAL COST: ${detailed_cost.get('annual', 0):.2f}</strong>
                                </div>
                                """, unsafe_allow_html=True)
                                
                            except Exception as e:
                                st.warning(f"Could not generate detailed breakdown: {e}")
                                
                        elif service_type == 'EBS':
                            # EBS Detailed Cost Breakdown
                            st.markdown("### 💿 EBS Volume Cost Breakdown")
                            
                            try:
                                vol_size = instance_info.get('size_gb', 0)
                                vol_type = instance_info.get('volume_type', 'gp2')
                                vol_iops = instance_info.get('iops')
                                vol_throughput = instance_info.get('throughput_mbps')
                                
                                detailed_cost = get_ebs_detailed_breakdown_cached(
                                    volume_id=instance_info.get('volume_id', 'unknown'),
                                    size_gb=vol_size,
                                    volume_type=vol_type,
                                    region=region,
                                    iops=vol_iops if vol_iops else 0,
                                    throughput_mbps=vol_throughput if vol_throughput else 0,
                                    env=env
                                )
                                
                                # Display Storage Cost
                                col1, col2, col3 = st.columns(3)
                                with col1:
                                    st.metric("Volume Type", detailed_cost.get('volume_type', vol_type))
                                with col2:
                                    st.metric("Size", f"{detailed_cost.get('size_gb', vol_size)} GB")
                                with col3:
                                    st.metric("Storage Rate", f"${detailed_cost.get('storage_rate', 0):.3f}/GB/mo")
                                
                                st.markdown(f"""
                                <div style="background: rgba(255,150,0,0.1); padding: 10px; border-radius: 5px; border-left: 3px solid #ff9900; margin: 10px 0;">
                                    <strong>Storage Cost:</strong> ${detailed_cost.get('storage_monthly', 0):.2f}/month
                                </div>
                                """, unsafe_allow_html=True)
                                
                                # Display IOPS Cost if applicable
                                if detailed_cost.get('iops_provisioned'):
                                    st.markdown(f"""
                                    <div style="background: rgba(100,100,0,0.1); padding: 10px; border-radius: 5px; margin: 10px 0;">
                                        Provisioned IOPS: {detailed_cost.get('iops_provisioned', 0)}<br/>
                                        Extra IOPS: {detailed_cost.get('iops_extra', 0)} @ ${detailed_cost.get('iops_rate', 0):.4f}/IOPS/mo<br/>
                                        <strong>IOPS Cost:</strong> ${detailed_cost.get('iops_monthly', 0):.2f}/month
                                    </div>
                                    """, unsafe_allow_html=True)
                                
                                # Display Throughput Cost if applicable
                                if detailed_cost.get('throughput_provisioned'):
                                    st.markdown(f"""
                                    <div style="background: rgba(0,100,100,0.1); padding: 10px; border-radius: 5px; margin: 10px 0;">
                                        Provisioned Throughput: {detailed_cost.get('throughput_provisioned', 0)} MB/s<br/>
                                        Extra Throughput: {detailed_cost.get('throughput_extra', 0)} MB/s @ ${detailed_cost.get('throughput_rate', 0):.2f}/MB/s/mo<br/>
                                        <strong>Throughput Cost:</strong> ${detailed_cost.get('throughput_monthly', 0):.2f}/month
                                    </div>
                                    """, unsafe_allow_html=True)
                                
                                # Total
                                st.markdown(f"""
                                <div style="background: rgba(0,150,0,0.2); padding: 15px; border-radius: 5px; margin: 15px 0; border: 2px solid #00aa00;">
                                    <strong style="font-size: 1.2em;">TOTAL MONTHLY COST: ${detailed_cost.get('monthly', 0):.2f}</strong><br/>
                                    <strong style="font-size: 1.2em;">TOTAL ANNUAL COST: ${detailed_cost.get('annual', 0):.2f}</strong>
                                </div>
                                """, unsafe_allow_html=True)
                                
                            except Exception as e:
                                st.warning(f"Could not generate detailed breakdown: {e}")

                # Attached EBS Volumes Section (for EC2)
                if service_type == 'EC2' and attached_volumes:
                    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
                    st.markdown('### 💾 Attached EBS Volumes')
                    
                    vol_cols = st.columns(len(attached_volumes) if len(attached_volumes) <= 3 else 3)
                    total_ebs_cost = 0
                    
                    for idx, vol in enumerate(attached_volumes):
                        col_idx = idx % 3
                        with vol_cols[col_idx]:
                            vol_id = vol.get('volume_id', 'Unknown')
                            vol_size = vol.get('size_gb', 0)
                            vol_type = vol.get('volume_type', 'Unknown')
                            vol_cost = vol.get('monthly_cost', 0)
                            total_ebs_cost += vol_cost
                            
                            st.markdown(f"""
                            <div style="background: rgba(255,255,255,0.05); padding: 10px; border-radius: 5px; border-left: 3px solid #ff9900; margin-bottom: 10px;">
                                <strong style="color: #ff9900;">{vol_id}</strong><br/>
                                <small>Type: {vol_type} | Size: {vol_size} GB</small><br/>
                                <strong>Cost: ${vol_cost:.2f}/mo</strong>
                            </div>
                            """, unsafe_allow_html=True)
                    
                    if total_ebs_cost > 0:
                        st.info(f"💡 Total monthly EBS cost for this instance: **${total_ebs_cost:.2f}**")

                # Activity Timeline Charts with slider
                st.markdown("### 📈 Activity History")
                
                # Slider for chart period
                col_slider, col_refresh = st.columns([4, 1])
                with col_slider:
                    activity_days_chart = st.slider(
                        "Chart period (days):",
                        min_value=7,
                        max_value=90,
                        value=activity_days,
                        key="activity_days_chart"
                    )
                with col_refresh:
                    if st.button("🔄 Refresh", key="refresh_charts"):
                        st.rerun()

                # Fetch historical metrics for charts
                historical_metrics = manager.get_cloudwatch_metrics(instance_id, activity_days_chart * 24)

                # INLINE HELPER FUNCTION - PRESERVED FROM ORIGINAL
                def create_empty_chart(title, y_label, chart_type='line', color='#00d2ff'):
                    """Create empty chart with 'No Activity Detected' message"""
                    
                    if chart_type == 'area':
                        fig = go.Figure()
                        fig.add_trace(go.Scatter(
                            x=[],
                            y=[],
                            fill='tozeroy',
                            fillcolor=f'rgba({int(color[1:3], 16)}, {int(color[3:5], 16)}, {int(color[5:7], 16)}, 0.1)',
                            line=dict(color=color),
                            mode='lines'
                        ))
                        fig.update_layout(
                            title=title,
                            xaxis_title='Time',
                            yaxis_title=y_label,
                            template="plotly_dark"
                        )
                    else:
                        fig = px.line(
                            pd.DataFrame(),
                            title=title,
                            labels={'y': y_label, 'x': 'Time'},
                            template="plotly_dark"
                        )
                        fig.update_traces(line_color=color)
                    
                    fig.update_layout(
                        hovermode='x',
                        height=300,
                        annotations=[{
                            'text': 'No Activity Detected',
                            'xref': 'paper',
                            'yref': 'paper',
                            'x': 0.5,
                            'y': 0.5,
                            'showarrow': False,
                            'font': {'size': 16, 'color': 'gray'},
                            'opacity': 0.5
                        }]
                    )
                    return fig

                # ========== RDS CHARTS ==========
                if service_type == 'RDS':
                    chart_tabs = st.tabs(["📊 Overview", "💻 CPU & Connections", "💾 IOPS", "🌐 Network"])
                    
                    # Overview Tab
                    with chart_tabs[0]:
                        st.markdown("**Activity Overview - Multiple Metrics**")
                        has_data = False
                        for metric_name in ['CPUUtilization', 'DatabaseConnections', 'ReadIOPS', 'WriteIOPS']:
                            metric = historical_metrics.get(metric_name)
                            if metric and isinstance(metric, dict) and metric.get('datapoints'):
                                has_data = True
                                break
                        
                        if has_data:
                            activity_scores = []
                            
                            cpu_metric = historical_metrics.get('CPUUtilization', {})
                            if cpu_metric and cpu_metric.get('datapoints'):
                                df_cpu = pd.DataFrame(cpu_metric['datapoints'])
                                df_cpu['Metric'] = 'CPU %'
                                df_cpu['Value'] = df_cpu['Average']
                                activity_scores.append(df_cpu[['Timestamp', 'Metric', 'Value']])
                            
                            conn_metric = historical_metrics.get('DatabaseConnections', {})
                            if conn_metric and conn_metric.get('datapoints'):
                                df_conn = pd.DataFrame(conn_metric['datapoints'])
                                df_conn['Metric'] = 'Connections'
                                df_conn['Value'] = df_conn['Average']
                                activity_scores.append(df_conn[['Timestamp', 'Metric', 'Value']])
                            
                            if activity_scores:
                                combined_df = pd.concat(activity_scores, ignore_index=True)
                                fig_overview = px.line(
                                    combined_df,
                                    x='Timestamp',
                                    y='Value',
                                    color='Metric',
                                    title=f'Instance Activity Over Last {activity_days_chart} Days',
                                    labels={'Value': 'Metric Value', 'Timestamp': 'Time'},
                                    template="plotly_dark",
                                    color_discrete_sequence=['#00d2ff', '#9d50bb', '#39ff14', '#ff3131']
                                )
                                fig_overview.update_layout(hovermode='x unified', height=400, showlegend=True)
                                st.plotly_chart(fig_overview, use_container_width=True)
                            else:
                                st.info("No activity data available for the selected period")
                        else:
                            st.info(f"No activity data available for the last {activity_days_chart} days")
                    
                    # CPU & Connections Tab
                    with chart_tabs[1]:
                        col1, col2 = st.columns(2)
                        with col1:
                            cpu_metric = historical_metrics.get('CPUUtilization', {})
                            if cpu_metric and cpu_metric.get('datapoints'):
                                df = pd.DataFrame(cpu_metric['datapoints'])
                                fig = px.line(df, x='Timestamp', y='Average', title='CPU Utilization (%)',
                                            labels={'Average': 'CPU %', 'Timestamp': 'Time'},
                                            template="plotly_dark")
                                fig.update_traces(line_color='#00d2ff')
                                fig.update_layout(hovermode='x', height=300)
                                st.plotly_chart(fig, use_container_width=True)
                            else:
                                fig = create_empty_chart('CPU Utilization (%)', 'CPU %', 'line', '#00d2ff')
                                st.plotly_chart(fig, use_container_width=True)
                        
                        with col2:
                            conn_metric = historical_metrics.get('DatabaseConnections', {})
                            if conn_metric and conn_metric.get('datapoints'):
                                df = pd.DataFrame(conn_metric['datapoints'])
                                fig = px.line(df, x='Timestamp', y='Average', title='Database Connections',
                                            labels={'Average': 'Connections', 'Timestamp': 'Time'},
                                            template="plotly_dark")
                                fig.update_traces(line_color='#9d50bb')
                                fig.update_layout(hovermode='x', height=300)
                                st.plotly_chart(fig, use_container_width=True)
                            else:
                                fig = create_empty_chart('Database Connections', 'Connections', 'line', '#9d50bb')
                                st.plotly_chart(fig, use_container_width=True)
                    
                    # IOPS Tab
                    with chart_tabs[2]:
                        col1, col2 = st.columns(2)
                        with col1:
                            read_metric = historical_metrics.get('ReadIOPS', {})
                            if read_metric and read_metric.get('datapoints'):
                                df = pd.DataFrame(read_metric['datapoints'])
                                fig = px.area(df, x='Timestamp', y='Average', title='Read IOPS',
                                            labels={'Average': 'IOPS', 'Timestamp': 'Time'},
                                            template="plotly_dark")
                                fig.update_traces(fillcolor='rgba(57, 255, 20, 0.1)', line_color='#39ff14')
                                fig.update_layout(hovermode='x', height=300)
                                st.plotly_chart(fig, use_container_width=True)
                            else:
                                fig = create_empty_chart('Read IOPS', 'IOPS', 'area', '#39ff14')
                                st.plotly_chart(fig, use_container_width=True)
                        
                        with col2:
                            write_metric = historical_metrics.get('WriteIOPS', {})
                            if write_metric and write_metric.get('datapoints'):
                                df = pd.DataFrame(write_metric['datapoints'])
                                fig = px.area(df, x='Timestamp', y='Average', title='Write IOPS',
                                            labels={'Average': 'IOPS', 'Timestamp': 'Time'},
                                            template="plotly_dark")
                                fig.update_traces(fillcolor='rgba(255, 49, 49, 0.1)', line_color='#ff3131')
                                fig.update_layout(hovermode='x', height=300)
                                st.plotly_chart(fig, use_container_width=True)
                            else:
                                fig = create_empty_chart('Write IOPS', 'IOPS', 'area', '#ff3131')
                                st.plotly_chart(fig, use_container_width=True)
                    
                    # Network Tab
                    with chart_tabs[3]:
                        col1, col2 = st.columns(2)
                        with col1:
                            net_rx = historical_metrics.get('NetworkReceiveThroughput', {})
                            if net_rx and net_rx.get('datapoints'):
                                df = pd.DataFrame(net_rx['datapoints'])
                                df['MB'] = df['Average'] / 1024 / 1024
                                fig = px.line(df, x='Timestamp', y='MB', title='Network Receive (MB/s)',
                                            labels={'MB': 'MB/s', 'Timestamp': 'Time'},
                                            template="plotly_dark")
                                fig.update_traces(line_color='#3867D6')
                                fig.update_layout(hovermode='x', height=300)
                                st.plotly_chart(fig, use_container_width=True)
                            else:
                                fig = create_empty_chart('Network Receive (MB/s)', 'MB/s', 'line', '#3867D6')
                                st.plotly_chart(fig, use_container_width=True)
                        
                        with col2:
                            net_tx = historical_metrics.get('NetworkTransmitThroughput', {})
                            if net_tx and net_tx.get('datapoints'):
                                df = pd.DataFrame(net_tx['datapoints'])
                                df['MB'] = df['Average'] / 1024 / 1024
                                fig = px.line(df, x='Timestamp', y='MB', title='Network Transmit (MB/s)',
                                            labels={'MB': 'MB/s', 'Timestamp': 'Time'},
                                            template="plotly_dark")
                                fig.update_traces(line_color='#8854D0')
                                fig.update_layout(hovermode='x', height=300)
                                st.plotly_chart(fig, use_container_width=True)
                            else:
                                fig = create_empty_chart('Network Transmit (MB/s)', 'MB/s', 'line', '#8854D0')
                                st.plotly_chart(fig, use_container_width=True)

                # ========== EBS CHARTS ==========
                elif service_type == 'EBS':
                    chart_tabs = st.tabs(["📊 Overview", "💾 IOPS", "🌐 Throughput"])
                    
                    # Overview Tab
                    with chart_tabs[0]:
                        st.markdown("**Activity Overview - Volume Ops**")
                        has_data = False
                        for metric_name in ['VolumeReadOps', 'VolumeWriteOps']:
                            metric = historical_metrics.get(metric_name)
                            if metric and isinstance(metric, dict) and metric.get('datapoints'):
                                has_data = True
                                break
                        
                        if has_data:
                            activity_scores = []
                            for m_name, display_name in [('VolumeReadOps', 'Read Ops'), ('VolumeWriteOps', 'Write Ops')]:
                                metric = historical_metrics.get(m_name, {})
                                if metric and metric.get('datapoints'):
                                    df = pd.DataFrame(metric['datapoints'])
                                    df['Metric'] = display_name
                                    df['Value'] = df['Average']
                                    activity_scores.append(df[['Timestamp', 'Metric', 'Value']])
                            
                            if activity_scores:
                                combined_df = pd.concat(activity_scores, ignore_index=True)
                                fig_overview = px.line(
                                    combined_df,
                                    x='Timestamp',
                                    y='Value',
                                    color='Metric',
                                    title='Volume Activity History',
                                    template="plotly_dark"
                                )
                                fig_overview.update_layout(hovermode='x unified', height=400)
                                st.plotly_chart(fig_overview, use_container_width=True)
                        else:
                            st.info("No volume activity data found for the selected period")
                    
                    # IOPS Tab
                    with chart_tabs[1]:
                        col1, col2 = st.columns(2)
                        with col1:
                            read_ops = historical_metrics.get('VolumeReadOps', {})
                            if read_ops and read_ops.get('datapoints'):
                                df = pd.DataFrame(read_ops['datapoints'])
                                fig = px.area(df, x='Timestamp', y='Average', title='Read IOPS',
                                            labels={'Average': 'Ops', 'Timestamp': 'Time'},
                                            template="plotly_dark")
                                fig.update_traces(fillcolor='rgba(0, 210, 255, 0.1)', line_color='#00d2ff')
                                fig.update_layout(hovermode='x', height=300)
                                st.plotly_chart(fig, use_container_width=True)
                            else:
                                fig = create_empty_chart('Read IOPS', 'Ops', 'area', '#00d2ff')
                                st.plotly_chart(fig, use_container_width=True)
                        
                        with col2:
                            write_ops = historical_metrics.get('VolumeWriteOps', {})
                            if write_ops and write_ops.get('datapoints'):
                                df = pd.DataFrame(write_ops['datapoints'])
                                fig = px.area(df, x='Timestamp', y='Average', title='Write IOPS',
                                            labels={'Average': 'Ops', 'Timestamp': 'Time'},
                                            template="plotly_dark")
                                fig.update_traces(fillcolor='rgba(255, 49, 49, 0.1)', line_color='#ff3131')
                                fig.update_layout(hovermode='x', height=300)
                                st.plotly_chart(fig, use_container_width=True)
                            else:
                                fig = create_empty_chart('Write IOPS', 'Ops', 'area', '#ff3131')
                                st.plotly_chart(fig, use_container_width=True)

                    # Throughput Tab
                    with chart_tabs[2]:
                        col1, col2 = st.columns(2)
                        with col1:
                            read_bytes = historical_metrics.get('VolumeReadBytes', {})
                            if read_bytes and read_bytes.get('datapoints'):
                                df = pd.DataFrame(read_bytes['datapoints'])
                                df['MB'] = df['Average'] / 1024 / 1024
                                fig = px.area(df, x='Timestamp', y='MB', title='Read Throughput (MB/s)',
                                            labels={'MB': 'MB/s', 'Timestamp': 'Time'},
                                            template="plotly_dark")
                                fig.update_traces(fillcolor='rgba(0, 210, 255, 0.1)', line_color='#00d2ff')
                                fig.update_layout(hovermode='x', height=300)
                                st.plotly_chart(fig, use_container_width=True)
                            else:
                                fig = create_empty_chart('Read Throughput (MB/s)', 'MB/s', 'area', '#00d2ff')
                                st.plotly_chart(fig, use_container_width=True)
                        
                        with col2:
                            write_bytes = historical_metrics.get('VolumeWriteBytes', {})
                            if write_bytes and write_bytes.get('datapoints'):
                                df = pd.DataFrame(write_bytes['datapoints'])
                                df['MB'] = df['Average'] / 1024 / 1024
                                fig = px.area(df, x='Timestamp', y='MB', title='Write Throughput (MB/s)',
                                            labels={'MB': 'MB/s', 'Timestamp': 'Time'},
                                            template="plotly_dark")
                                fig.update_traces(fillcolor='rgba(255, 49, 49, 0.1)', line_color='#ff3131')
                                fig.update_layout(hovermode='x', height=300)
                                st.plotly_chart(fig, use_container_width=True)
                            else:
                                fig = create_empty_chart('Write Throughput (MB/s)', 'MB/s', 'area', '#ff3131')
                                st.plotly_chart(fig, use_container_width=True)

                # ========== EC2 CHARTS ==========
                else:  # EC2
                    chart_tabs = st.tabs(["📊 Overview", "💻 CPU", "🌐 Network", "💾 Disk"])
                    
                    # Overview Tab
                    with chart_tabs[0]:
                        st.markdown("**Activity Overview - Multiple Metrics**")
                        has_data = False
                        for metric_name in ['CPUUtilization', 'NetworkIn', 'NetworkOut']:
                            metric = historical_metrics.get(metric_name)
                            if metric and isinstance(metric, dict) and metric.get('datapoints'):
                                has_data = True
                                break
                        
                        if has_data:
                            activity_scores = []
                            
                            cpu_metric = historical_metrics.get('CPUUtilization', {})
                            if cpu_metric and cpu_metric.get('datapoints'):
                                df_cpu = pd.DataFrame(cpu_metric['datapoints'])
                                df_cpu['Metric'] = 'CPU %'
                                df_cpu['Value'] = df_cpu['Average']
                                activity_scores.append(df_cpu[['Timestamp', 'Metric', 'Value']])
                            
                            if activity_scores:
                                combined_df = pd.concat(activity_scores, ignore_index=True)
                                fig_overview = px.line(
                                    combined_df,
                                    x='Timestamp',
                                    y='Value',
                                    color='Metric',
                                    title=f'Instance Activity Over Last {activity_days_chart} Days',
                                    labels={'Value': 'Metric Value', 'Timestamp': 'Time'},
                                    template="plotly_dark",
                                    color_discrete_sequence=['#00d2ff', '#9d50bb', '#39ff14', '#ff3131']
                                )
                                fig_overview.update_layout(hovermode='x unified', height=400, showlegend=True)
                                st.plotly_chart(fig_overview, use_container_width=True)
                            else:
                                st.info("No activity data available")
                        else:
                            st.info(f"No activity data available for the last {activity_days_chart} days")
                    
                    # CPU Tab
                    with chart_tabs[1]:
                        cpu_metric = historical_metrics.get('CPUUtilization', {})
                        if cpu_metric and cpu_metric.get('datapoints'):
                            df = pd.DataFrame(cpu_metric['datapoints'])
                            fig = px.line(df, x='Timestamp', y='Average', title='CPU Utilization (%)',
                                        labels={'Average': 'CPU %', 'Timestamp': 'Time'},
                                        template="plotly_dark")
                            fig.update_traces(line_color='#00d2ff')
                            fig.update_layout(hovermode='x', height=400)
                            st.plotly_chart(fig, use_container_width=True)
                        else:
                            fig = create_empty_chart('CPU Utilization (%)', 'CPU %', 'line', '#00d2ff')
                            st.plotly_chart(fig, use_container_width=True)
                    
                    # Network Tab
                    with chart_tabs[2]:
                        col1, col2 = st.columns(2)
                        with col1:
                            net_in = historical_metrics.get('NetworkIn', {})
                            if net_in and net_in.get('datapoints'):
                                df = pd.DataFrame(net_in['datapoints'])
                                df['MB'] = df['Average'] / 1024 / 1024
                                fig = px.line(df, x='Timestamp', y='MB', title='Network In (MB)',
                                            labels={'MB': 'MB', 'Timestamp': 'Time'},
                                            template="plotly_dark")
                                fig.update_traces(line_color='#39ff14')
                                fig.update_layout(hovermode='x', height=300)
                                st.plotly_chart(fig, use_container_width=True)
                            else:
                                fig = create_empty_chart('Network In (MB)', 'MB', 'line', '#39ff14')
                                st.plotly_chart(fig, use_container_width=True)
                        
                        with col2:
                            net_out = historical_metrics.get('NetworkOut', {})
                            if net_out and net_out.get('datapoints'):
                                df = pd.DataFrame(net_out['datapoints'])
                                df['MB'] = df['Average'] / 1024 / 1024
                                fig = px.line(df, x='Timestamp', y='MB', title='Network Out (MB)',
                                            labels={'MB': 'MB', 'Timestamp': 'Time'},
                                            template="plotly_dark")
                                fig.update_traces(line_color='#9d50bb')
                                fig.update_layout(hovermode='x', height=300)
                                st.plotly_chart(fig, use_container_width=True)
                            else:
                                fig = create_empty_chart('Network Out (MB)', 'MB', 'line', '#9d50bb')
                                st.plotly_chart(fig, use_container_width=True)
                    
                    # Disk Tab
                    with chart_tabs[3]:
                        col1, col2 = st.columns(2)
                        with col1:
                            disk_read = historical_metrics.get('DiskReadBytes', {})
                            if disk_read and disk_read.get('datapoints'):
                                df = pd.DataFrame(disk_read['datapoints'])
                                df['MB'] = df['Average'] / 1024 / 1024
                                fig = px.area(df, x='Timestamp', y='MB', title='Disk Read (MB)',
                                            labels={'MB': 'MB', 'Timestamp': 'Time'},
                                            template="plotly_dark")
                                fig.update_traces(fillcolor='rgba(0, 210, 255, 0.1)', line_color='#00d2ff')
                                fig.update_layout(hovermode='x', height=300)
                                st.plotly_chart(fig, use_container_width=True)
                            else:
                                fig = create_empty_chart('Disk Read (MB)', 'MB', 'area', '#00d2ff')
                                st.plotly_chart(fig, use_container_width=True)
                        
                        with col2:
                            disk_write = historical_metrics.get('DiskWriteBytes', {})
                            if disk_write and disk_write.get('datapoints'):
                                df = pd.DataFrame(disk_write['datapoints'])
                                df['MB'] = df['Average'] / 1024 / 1024
                                fig = px.area(df, x='Timestamp', y='MB', title='Disk Write (MB)',
                                            labels={'MB': 'MB', 'Timestamp': 'Time'},
                                            template="plotly_dark")
                                fig.update_traces(fillcolor='rgba(255, 49, 49, 0.1)', line_color='#ff3131')
                                fig.update_layout(hovermode='x', height=300)
                                st.plotly_chart(fig, use_container_width=True)
                            else:
                                fig = create_empty_chart('Disk Write (MB)', 'MB', 'area', '#ff3131')
                                st.plotly_chart(fig, use_container_width=True)
                
                st.markdown("---")
                
                # CloudWatch Metrics Summary
                st.markdown("### 📊 CloudWatch Metrics Summary")
                
                if service_type == 'RDS':
                    tab1, tab2, tab3 = st.tabs(["CPU & Connections", "IOPS", "Network"])
                    
                    with tab1:
                        col1, col2 = st.columns(2)
                        with col1:
                            cpu = metrics.get('CPUUtilization', {})
                            if cpu:
                                st.metric("CPU (Avg)", f"{cpu.get('average', 0):.2f}%")
                        with col2:
                            conn = metrics.get('DatabaseConnections', {})
                            if conn:
                                st.metric("Connections (Avg)", f"{conn.get('average', 0):.2f}")

                    with tab2:
                        col1, col2 = st.columns(2)
                        with col1:
                            read = metrics.get('ReadIOPS', {})
                            if read:
                                st.metric("Read IOPS (Avg)", f"{read.get('average', 0):.2f}")
                        with col2:
                            write = metrics.get('WriteIOPS', {})
                            if write:
                                st.metric("Write IOPS (Avg)", f"{write.get('average', 0):.2f}")
                    
                    with tab3:
                        col1, col2 = st.columns(2)
                        with col1:
                            net_in = metrics.get('NetworkReceiveThroughput', {})
                            if net_in:
                                st.metric("Network In (Avg)", f"{net_in.get('average', 0):.0f} B/s")
                                st.metric("Network In (Max)", f"{net_in.get('max', 0):.0f} B/s")
                        with col2:
                            net_out = metrics.get('NetworkTransmitThroughput', {})
                            if net_out:
                                st.metric("Network Out (Avg)", f"{net_out.get('average', 0):.0f} B/s")
                                st.metric("Network Out (Max)", f"{net_out.get('max', 0):.0f} B/s")
                
                elif service_type == 'EBS':
                    tab1, tab2 = st.tabs(["IOPS", "Throughput"])
                    
                    with tab1:
                        col1, col2 = st.columns(2)
                        with col1:
                            read = metrics.get('VolumeReadOps', {})
                            if read:
                                st.metric("Read IOPS (Avg)", f"{read.get('average', 0):.2f}")
                        with col2:
                            write = metrics.get('VolumeWriteOps', {})
                            if write:
                                st.metric("Write IOPS (Avg)", f"{write.get('average', 0):.2f}")
                                
                    with tab2:
                        col1, col2 = st.columns(2)
                        with col1:
                            read_bytes = metrics.get('VolumeReadBytes', {})
                            if read_bytes:
                                st.metric("Read Throughput (Avg)", f"{read_bytes.get('average', 0)/1024/1024:.2f} MB")
                        with col2:
                            write_bytes = metrics.get('VolumeWriteBytes', {})
                            if write_bytes:
                                st.metric("Write Throughput (Avg)", f"{write_bytes.get('average', 0)/1024/1024:.2f} MB")

                elif service_type == 'EC2':
                    tab1, tab2, tab3 = st.tabs(["CPU", "Network", "Disk"])
                    
                    with tab1:
                        cpu = metrics.get('CPUUtilization', {})
                        if cpu:
                            col1, col2 = st.columns(2)
                            with col1:
                                st.metric("CPU Utilization (Avg)", f"{cpu.get('average', 0):.2f}%")
                            with col2:
                                st.metric("CPU Utilization (Max)", f"{cpu.get('max', 0):.2f}%")
                    
                    with tab2:
                        col1, col2 = st.columns(2)
                        with col1:
                            net_in = metrics.get('NetworkIn', {})
                            if net_in:
                                st.metric("Network In (Avg)", f"{net_in.get('average', 0)/1024/1024:.2f} MB")
                                st.metric("Network In (Max)", f"{net_in.get('max', 0)/1024/1024:.2f} MB")
                        with col2:
                            net_out = metrics.get('NetworkOut', {})
                            if net_out:
                                st.metric("Network Out (Avg)", f"{net_out.get('average', 0)/1024/1024:.2f} MB")
                                st.metric("Network Out (Max)", f"{net_out.get('max', 0)/1024/1024:.2f} MB")
                    
                    with tab3:
                        col1, col2 = st.columns(2)
                        with col1:
                            disk_read = metrics.get('DiskReadBytes', {})
                            if disk_read:
                                st.metric("Disk Read (Avg)", f"{disk_read.get('average', 0)/1024/1024:.2f} MB")
                                st.metric("Disk Read (Max)", f"{disk_read.get('max', 0)/1024/1024:.2f} MB")
                        with col2:
                            disk_write = metrics.get('DiskWriteBytes', {})
                            if disk_write:
                                st.metric("Disk Write (Avg)", f"{disk_write.get('average', 0)/1024/1024:.2f} MB")
                                st.metric("Disk Write (Max)", f"{disk_write.get('max', 0)/1024/1024:.2f} MB")
                
                # Analysis Details
                st.markdown("### 🔍 Analysis Details")
                
                if analysis['indicators']:
                    st.markdown("**🔴 Idle Indicators**")
                    for reason in analysis['idle_reasons']:
                        st.markdown(f"• {reason}")
                
                if analysis.get('active_reasons'):
                    st.markdown("**🟢 Active Indicators**")
                    for reason in analysis['active_reasons']:
                        st.markdown(f"• {reason}")
                
                if not analysis['indicators'] and not analysis.get('active_reasons'):
                    st.info("No significant idle indicators detected")
                
            except Exception as e:
                logger.error(f"Error analyzing instance: {e}", exc_info=True)
                st.error("Error analyzing instance. Please check logs for details.")

    def run_scan(self, manager, service_type, cloudwatch_hours, activity_days, idle_threshold):
        """Run scan on all instances with batch-optimized processing for improved performance"""
        # Show scanning header
        st.markdown(f'## 🔍 Scanning {service_type} Resources')
        
        with st.spinner(f'Analyzing {service_type} resources...'):
            # Get instance list
            instances = manager.list_instances()
            
            if not instances:
                st.warning(f"⚠️ No {service_type} instances found in the selected region")
                st.markdown("""
                **Tips:**
                - Try selecting a different region
                - Click 'Refresh Data' in sidebar to load AWS resources
                - Check AWS credentials and permissions
                """)
                st.session_state.scanning = False
                return
            
            # Progress display
            progress_bar = st.progress(0, text="Initializing scan...")
            status_text = st.empty()
            
            # Extract instance IDs
            instance_ids = []
            for instance in instances:
                if service_type == 'EBS':
                    instance_ids.append(instance['volume_id'])
                else:
                    instance_ids.append(instance['instance_id'])
            
            # Batch fetch metrics and activity data (major performance optimization)
            status_text.info("📊 Batch fetching metrics...")
            try:
                batch_metrics = manager.get_etl_provider().get_cloudwatch_metrics_batch(instance_ids, cloudwatch_hours)
            except Exception as e:
                logger.warning(f"Batch metrics fetch failed, falling back to individual: {e}")
                batch_metrics = None
            
            try:
                batch_activities = manager.detect_last_activity_batch(instance_ids, activity_days)
            except Exception as e:
                logger.warning(f"Batch activity fetch failed, falling back to individual: {e}")
                batch_activities = None
            
            # Batch fetch EBS volumes for EC2 instances (prevents connection pool exhaustion)
            batch_volumes = None
            if service_type == 'EC2':
                try:
                    batch_volumes = manager.get_attached_volumes_batch(instance_ids)
                except Exception as e:
                    logger.warning(f"Batch volumes fetch failed, falling back to individual: {e}")
                    batch_volumes = None
            
            results = []
            start_time = datetime.now()
            
            # Process instances sequentially since all data is already batch-fetched
            # This avoids ThreadPoolExecutor overhead and connection pool issues
            status_text.info(f"⚡ Analyzing {len(instances)} instances...")
            
            for idx, instance in enumerate(instances):
                if service_type == 'EBS':
                    instance_id = instance['volume_id']
                else:
                    instance_id = instance['instance_id']
                
                try:
                    # Use batch data if available, otherwise fetch individually
                    if batch_metrics and instance_id in batch_metrics:
                        metrics = batch_metrics[instance_id]
                    else:
                        metrics = manager.get_cloudwatch_metrics(instance_id, cloudwatch_hours)
                    
                    if batch_activities and instance_id in batch_activities:
                        last_activity = batch_activities[instance_id]
                    else:
                        last_activity = manager.detect_last_activity(instance_id, activity_days)
                    
                    if service_type == 'RDS':
                        analysis = IdleAnalyzer.analyze_rds(metrics, last_activity, activity_days)
                    elif service_type == 'EC2':
                        analysis = IdleAnalyzer.analyze_ec2(metrics, last_activity, activity_days)
                    elif service_type == 'EBS':
                        analysis = IdleAnalyzer.analyze_ebs(metrics, last_activity, activity_days)
                    
                    days_idle = last_activity.get('days_since_activity')
                    
                    if analysis['idle_score'] >= idle_threshold:
                        status = 'idle'
                    else:
                        status = 'active'
                    
                    # Use batch volumes data if available, otherwise fetch individually
                    extra_info = {}
                    if service_type == 'EC2':
                        if batch_volumes and instance_id in batch_volumes:
                            extra_info['attached_volumes'] = batch_volumes[instance_id]
                        else:
                            extra_info['attached_volumes'] = manager.get_attached_volumes(instance_id)
                    
                    results.append({
                        'instance': instance,
                        'metrics': metrics,
                        'last_activity': last_activity,
                        'analysis': analysis,
                        'status': status,
                        'days_idle': days_idle,
                        'extra_info': extra_info
                    })
                
                except Exception as e:
                    results.append({
                        'instance': instance,
                        'status': 'error',
                        'error': str(e)
                    })
                
                # Update progress
                progress = (idx + 1) / len(instances)
                progress_bar.progress(progress, text=f"Analyzed {idx + 1}/{len(instances)}: {instance_id}")
            
            # Clear progress indicators
            progress_bar.empty()
            status_text.empty()
            
            # Calculate scan duration
            duration = (datetime.now() - start_time).total_seconds()
            
            # Store results
            st.session_state.scan_results = results
            st.session_state.scanning = False
            
            # Show completion message with performance stats
            idle_count = sum(1 for r in results if r.get('status') == 'idle')
            avg_time = duration / len(results) if results else 0
            st.success(f"✅ Scan complete! Analyzed {len(results)} resources in {duration:.1f} seconds ({avg_time:.2f}s avg). Found {idle_count} idle resources.")

    def display_scan_results(self, service_type, pricing_settings=None):
        """Display scan results with improved visual hierarchy"""
        
        # Default pricing settings if not provided
        if pricing_settings is None:
            pricing_settings = {
                'pricing_model': 'On-Demand',
                'ri_coverage': 0,
                'sp_coverage': 0,
                'use_actual_runtime': False,
                'actual_hours': None
            }
        results = st.session_state.scan_results
        if not results:
            return
        
        # Header with service type
        st.markdown(f'## 📊 {service_type} Scan Results')
        
        # Summary metrics with better visual distinction
        idle_count = sum(1 for r in results if r.get('status') == 'idle')
        active_count = sum(1 for r in results if r.get('status') == 'active')
        error_count = sum(1 for r in results if r.get('status') == 'error')
        
        # Summary cards
        summary_col1, summary_col2, summary_col3, summary_col4 = st.columns(4)
        
        with summary_col1:
            st.metric("Total Resources", len(results))
            if st.button("📊 View All", key=f"view_all_btn_{service_type}", use_container_width=True):
                st.session_state.status_filter = "All"
                st.rerun()
        with summary_col2:
            st.metric("🟢 Active", active_count)
            if st.button("✅ View Active", key=f"view_active_btn_{service_type}", use_container_width=True):
                st.session_state.status_filter = "Active"
                st.rerun()
        with summary_col3:
            st.metric(
                "🔴 Idle", 
                idle_count,
                delta=f"{idle_count/len(results)*100:.0f}%" if results else None,
                delta_color="inverse"
            )
            if st.button("🚫 View Idle", key=f"view_idle_btn_{service_type}", use_container_width=True):
                st.session_state.status_filter = "Idle"
                st.rerun()
        with summary_col4:
            st.metric("⚠️ Errors", error_count)
            if st.button("❌ View Errors", key=f"view_errors_btn_{service_type}", use_container_width=True):
                st.session_state.status_filter = "Error"
                st.rerun()
        
        # Cost savings section
        if idle_count > 0:
            st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
            st.markdown('### 💰 Potential Cost Savings (Considering only Idle Instances)')
            
            # Get pricing model settings
            ri_coverage = pricing_settings.get('ri_coverage', 0)
            sp_coverage = pricing_settings.get('sp_coverage', 0)
            discount_factor = 1.0 - max(ri_coverage, sp_coverage)
            use_actual_runtime = pricing_settings.get('use_actual_runtime', False)
            
            total_monthly_savings = 0
            pricing_unavailable = 0
            env = st.session_state.get('aws_environment', 'Default')
            
            for r in results:
                if r.get('status') == 'idle':
                    # Get actual hours for this instance if enabled
                    if use_actual_runtime:
                        try:
                            from analysis.cost_calculator import CostCalculator
                            instance_id = r['instance'].get('instance_id') or r['instance'].get('db_instance_identifier')
                            actual_hours = CostCalculator.get_actual_runtime_hours(instance_id)
                        except:
                            actual_hours = HOURS_PER_MONTH
                    else:
                        actual_hours = HOURS_PER_MONTH
                    
                    if service_type == 'RDS':
                        instance_class = r['instance']['instance_class'].replace('db.', '')
                        region = r['instance'].get('region', 'us-east-1')
                        database_engine = r['instance'].get('engine', '')
                        deployment_option = 'Multi-AZ' if r['instance'].get('multi_az') in [True, 'true', 'True', 'yes', 'Yes'] else 'Single-AZ'
                        hourly_cost = get_pricing_cached(
                            instance_class, region, 'RDS', env,
                            database_engine=database_engine,
                            deployment_option=deployment_option
                        )
                        if hourly_cost:
                            # Add RDS storage costs - use RDS-specific pricing (DIFFERENT from EBS!)
                            from analysis.cost_calculator import CostCalculator
                            storage_type = r['instance'].get('storage_type', 'gp2')
                            allocated_storage = r['instance'].get('allocated_storage', 0)
                            iops = r['instance'].get('iops', 0)
                            multi_az = r['instance'].get('multi_az', False)
                            
                            if allocated_storage and allocated_storage > 0:
                                storage_cost = CostCalculator.calculate_rds_storage_cost(
                                    int(allocated_storage), storage_type,
                                    iops=int(iops) if iops else None,
                                    multi_az=multi_az,
                                    region=region
                                )
                                monthly_storage = storage_cost.get('monthly', 0)
                                # Also get IOPS monthly cost if applicable
                                iops_monthly = storage_cost.get('iops_monthly', 0)
                            else:
                                monthly_storage = 0
                                iops_monthly = 0
                            
                            # Apply discount factor and use actual hours
                            instance_savings = ((hourly_cost * actual_hours) + monthly_storage + iops_monthly) * discount_factor
                            total_monthly_savings += instance_savings
                        else:
                            pricing_unavailable += 1
                    elif service_type == 'EC2':
                        instance_type = r['instance']['instance_type']
                        region = r['instance'].get('region', 'us-east-1')
                        operating_system = r['instance'].get('platform', 'Linux/UNIX')
                        tenancy = r['instance'].get('tenancy', 'shared')
                        hourly_cost = get_pricing_cached(
                            instance_type, region, 'EC2', env,
                            operating_system=operating_system,
                            tenancy=tenancy
                        )
                        if hourly_cost:
                            # Calculate EC2 compute cost with actual hours
                            ec2_monthly = (hourly_cost * actual_hours) * discount_factor
                            
                            # Add attached EBS volumes cost (CRITICAL - was missing!)
                            extra_info = r.get('extra_info', {})
                            attached_volumes = extra_info.get('attached_volumes', [])
                            ebs_monthly = sum(v.get('monthly_cost', 0) for v in attached_volumes) * discount_factor
                            
                            total_monthly_savings += ec2_monthly + ebs_monthly
                        else:
                            pricing_unavailable += 1
                    elif service_type == 'EBS':
                        total_monthly_savings += r['instance'].get('monthly_cost', 0) * discount_factor
            
            if pricing_unavailable > 0:
                st.warning(f"⚠️ Pricing data unavailable for {pricing_unavailable} instance(s). Click '💲 Reload Pricing' in sidebar.")
            
            # Savings display
            savings_col1, savings_col2, savings_col3 = st.columns(3)
            with savings_col1:
                st.metric("Monthly Savings", f"${total_monthly_savings:,.2f}")
            with savings_col2:
                st.metric("Annual Savings", f"${total_monthly_savings * 12:,.2f}")
            with savings_col3:
                # FIXED: Calculate daily savings rate using hourly * 24 for consistency
                # This is mathematically consistent with monthly = hourly * hours_per_month
                # Using average hours per day (24) for accurate daily rate
                daily_rate = total_monthly_savings / 30.42  # Average days per month
                st.metric("Daily Rate", f"${daily_rate:,.2f}/day")
            
            # Show pricing model info if not On-Demand
            pricing_model = pricing_settings.get('pricing_model', 'On-Demand')
            if pricing_model != 'On-Demand':
                coverage = int(max(ri_coverage, sp_coverage) * 100)
                st.caption(f"📊 {pricing_model} coverage applied: {coverage}% discount | Using actual hours: {use_actual_runtime}")
        
        # Detailed Results
        st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
        st.markdown('### 📋 Detailed Results')
        
        # Filter controls
        filter_col1, filter_col2 = st.columns([3, 1])
        
        with filter_col1:
            search_results = st.text_input(
                "🔍 Search by Instance ID or Name",
                placeholder="Type to filter results...",
                help="Filter results by instance ID, name, or bucket name (case-insensitive)",
                key="search_results"
            )
            # Security: Sanitize search input
            if search_results:
                search_results = re.sub(r'[^a-zA-Z0-9\-_./\s]', '', search_results)
        
        with filter_col2:
            # Status filter
            status_filter = st.selectbox(
                "Filter by Status",
                options=["All", "Idle", "Active", "Error"],
                key="status_filter"
            )
        
        # Filter results
        filtered_results = []
        for r in results:
            # Apply status filter
            if status_filter != "All":
                status = r.get('status', '').lower()
                if status_filter.lower() != status:
                    continue
            
            # Apply search filter
            if search_results:
                instance = r['instance']
                search_text = ""
                if service_type == 'RDS':
                    search_text = instance.get('instance_id', '')
                elif service_type == 'EC2':
                    search_text = f"{instance.get('instance_id', '')} {instance.get('name', '')}"
                elif service_type == 'EBS':
                    search_text = f"{instance.get('volume_id', '')} {instance.get('name', '')}"
                
                if search_results.lower() not in search_text.lower():
                    continue
            
            filtered_results.append(r)
        
        if search_results or status_filter != "All":
            if filtered_results:
                st.success(f"✓ Showing {len(filtered_results)} of {len(results)} result(s)")
            else:
                st.warning(f"No results match the current filters")
        
        results = filtered_results
        
        # Pagination for large result sets
        total_results = len(results)
        if total_results > 25:  # Only show pagination for larger sets
            # Pagination controls
            st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
            
            page_size = st.selectbox(
                "Results per page",
                options=[25, 50, 100, 250],
                index=0,
                key=f"page_size_{service_type}"
            )
            
            total_pages = max(1, (total_results + page_size - 1) // page_size)
            
            # Initialize current page if needed
            if f'current_page_{service_type}' not in st.session_state:
                st.session_state[f'current_page_{service_type}'] = 1
            
            current_page = st.session_state[f'current_page_{service_type}']
            
            # Page navigation
            nav_col1, nav_col2, nav_col3, nav_col4, nav_col5 = st.columns([1, 1, 2, 1, 1])
            
            with nav_col1:
                if st.button("⏮️ First", key=f"first_page_{service_type}", disabled=current_page == 1):
                    st.session_state[f'current_page_{service_type}'] = 1
                    st.rerun()
            
            with nav_col2:
                if st.button("◀️ Prev", key=f"prev_page_{service_type}", disabled=current_page == 1):
                    st.session_state[f'current_page_{service_type}'] = current_page - 1
                    st.rerun()
            
            with nav_col3:
                st.markdown(f"<div style='text-align: center; padding-top: 8px;'>Page {current_page} of {total_pages} ({total_results} results)</div>", unsafe_allow_html=True)
            
            with nav_col4:
                if st.button("Next ▶️", key=f"next_page_{service_type}", disabled=current_page >= total_pages):
                    st.session_state[f'current_page_{service_type}'] = current_page + 1
                    st.rerun()
            
            with nav_col5:
                if st.button("Last ⏭️", key=f"last_page_{service_type}", disabled=current_page >= total_pages):
                    st.session_state[f'current_page_{service_type}'] = total_pages
                    st.rerun()
            
            # Calculate page slice
            start_idx = (current_page - 1) * page_size
            end_idx = min(start_idx + page_size, total_results)
            results = results[start_idx:end_idx]
            
            st.caption(f"Showing results {start_idx + 1} - {end_idx} of {total_results}")
        
        # Display results
        for r in results:
            if r.get('status') == 'error':
                instance_id = r['instance'].get('name', r['instance'].get('instance_id', 'Unknown'))
                with st.expander(f"❌ {instance_id} - Error"):
                    st.error(r['error'])
            else:
                instance = r['instance']
                analysis = r['analysis']
                severity = analysis['severity']
                
                # Status icon based on severity
                if severity == 'CRITICAL':
                    icon = "🚨"
                    status_color = "status-dot critical"
                elif severity == 'HIGH':
                    icon = "🔴"
                    status_color = "status-dot high"
                elif severity == 'MEDIUM':
                    icon = "🟡"
                    status_color = "status-dot medium"
                else:
                    icon = "🟢"
                    status_color = "status-dot low"
                
                # Get display name - handle None values properly
                if service_type == 'RDS':
                    display_id = instance.get('name') or instance.get('instance_id', 'Unknown')
                elif service_type == 'EBS':
                    display_id = instance.get('name') or instance.get('volume_id', 'Unknown')
                else:
                    display_id = instance.get('name') or instance.get('instance_id', 'Unknown')
                
                if service_type == 'EBS':
                    actual_id = instance.get('volume_id', 'Unknown')
                else:
                    actual_id = instance.get('instance_id', 'Unknown')
                
                with st.expander(f"{icon} {display_id} - {severity} ({analysis['idle_score']:.0f}%)"):
                    # Info columns
                    info_col1, info_col2, info_col3 = st.columns(3)
                    
                    with info_col1:
                        if service_type == 'RDS':
                            st.write(f"**Class:** {instance['instance_class']}")
                            st.write(f"**Engine:** {instance['engine']}")
                        elif service_type == 'EC2':
                            st.write(f"**Type:** {instance['instance_type']}")
                            st.write(f"**Platform:** {instance['platform']}")
                        elif service_type == 'EBS':
                            st.write(f"**Volume Type:** {instance.get('volume_type')}")
                            st.write(f"**Size:** {instance.get('size_gb')} GB")
                    
                    with info_col2:
                        if service_type == 'EBS':
                            st.write(f"**Attached To:** {instance.get('attached_instance_id', 'Unattached')}")
                            st.write(f"**Status:** {instance.get('status')}")
                        else:
                            st.write(f"**Status:** {instance.get('status', instance.get('state'))}")
                        
                        # Last activity
                        last_activity = r.get('last_activity', {})
                        days_idle = r.get('days_idle')
                        last_time = last_activity.get('last_activity_time')
                        
                        if last_time:
                            if isinstance(last_time, str):
                                from datetime import datetime
                                last_time = datetime.fromisoformat(last_time.replace('Z', '+00:00'))
                            timestamp_str = last_time.strftime('%Y-%m-%d %H:%M UTC')
                            st.write(f"**Last Activity:** {days_idle:.1f} days ago")
                            st.caption(f"📅 {timestamp_str}")
                        elif days_idle is not None and days_idle != float('inf'):
                            if days_idle < 1:
                                st.write("**Last Activity:** <1 day ago")
                            else:
                                st.write(f"**Last Activity:** {days_idle:.1f} days ago")
                        else:
                            st.write("**Last Activity:** No data")
                            st.caption("ℹ️ Run ETL to collect metrics")
                    
                    with info_col3:
                        st.write(f"**Idle Score:** {analysis['idle_score']:.0f}%")
                        st.write(f"**{analysis['recommendation']}**")
                        
                        # Display tags inline (compact view)
                        tags = self.etl_provider.get_instance_tags(actual_id)
                        if tags:
                            # Show first few tags
                            tag_preview = []
                            for i, (k, v) in enumerate(tags.items()):
                                if i < 3:
                                    tag_preview.append(f"{k}: {v}")
                                else:
                                    tag_preview.append(f"+{len(tags)-3} more")
                                    break
                            st.caption(f"🏷️ {' | '.join(tag_preview)}")
                        
                        # Extra info for EC2
                        extra_info = r.get('extra_info', {})
                        if service_type == 'EC2' and extra_info.get('attached_volumes'):
                            vols = extra_info['attached_volumes']
                            total_ebs_cost = sum(v.get('monthly_cost', 0) for v in vols)
                            st.write(f"**Attached EBS:** {len(vols)} (${total_ebs_cost:.2f}/mo)")
                        
                        # Action button
                        if st.button(f"🔍 Analyze {actual_id}", key=f"analyze_{actual_id}"):
                            st.session_state.analyzing_instance = actual_id
                            st.session_state.instance_analysis_active = True
                            st.session_state.scan_results = None
                            st.rerun()

    def render_home_screen(self):
        """Render home screen with AWS Console styling and animated cards"""
        st.markdown("""
        <!-- Welcome Banner -->
        <div class="aws-home-banner">
            <div class="banner-content">
                <h2>🚀 Get Started</h2>
                <p>Configure your scan in the sidebar and discover idle AWS resources to optimize costs.</p>
            </div>
            <div class="banner-actions">
                <span class="aws-badge success">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
                        <polyline points="22 4 12 14.01 9 11.01"></polyline>
                    </svg>
                    Ready to Scan
                </span>
            </div>
        </div>
        
        <style>
        .aws-home-banner {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 1.5rem 2rem;
            background: linear-gradient(135deg, #232f3e 0%, #1a2332 100%);
            border-radius: 12px;
            margin-bottom: 2rem;
        }
        
        .banner-content h2 {
            color: #ffffff !important;
            margin: 0 0 0.5rem 0;
            font-size: 1.5rem;
        }
        
        .banner-content p {
            color: #aab7c4;
            margin: 0;
            font-size: 0.95rem;
        }
        
        .banner-actions {
            display: flex;
            gap: 0.75rem;
        }
        
        .aws-badge {
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.5rem 1rem;
            border-radius: 6px;
            font-size: 0.85rem;
            font-weight: 500;
        }
        
        .aws-badge.success {
            background: rgba(0,113,133,0.2);
            color: #00d8ff;
        }
        </style>
        
        <div class="section-divider"></div>
        """, unsafe_allow_html=True)
        
        # Feature cards in a modern layout
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown('''
            <div class="aws-feature-card" style="margin-bottom: 1.5rem;">
                <div class="feature-icon blue">📊</div>
                <h3>Real-time Monitoring</h3>
                <p>Scan all active clusters and instances across your AWS infrastructure with high-precision CloudWatch metrics.</p>
            </div>
            <div class="aws-feature-card">
                <div class="feature-icon orange">💰</div>
                <h3>Cost Optimization</h3>
                <p>Identify idle resources and calculate potential savings with detailed annual and monthly projections.</p>
            </div>
            ''', unsafe_allow_html=True)
            
        with col2:
            st.markdown('''
            <div class="aws-feature-card" style="margin-bottom: 1.5rem;">
                <div class="feature-icon green">🎯</div>
                <h3>Idle Detection</h3>
                <p>Advanced heuristics detect zombies, underutilized databases, and orphan EBS volumes based on activity patterns.</p>
            </div>
            <div class="aws-feature-card">
                <div class="feature-icon purple">🚀</div>
                <h3>Fast ETL Layer</h3>
                <p>Persistent SQLite data warehouse enables near-instant interface response times and offline analysis.</p>
            </div>
            ''', unsafe_allow_html=True)
        
        # Add custom CSS for feature cards
        st.markdown("""
        <style>
        .aws-feature-card {
            background: #ffffff;
            border: 1px solid #dfe3e8;
            border-radius: 10px;
            padding: 1.5rem;
            margin-bottom: 1rem;
            transition: all 0.3s ease;
        }
        
        .aws-feature-card:hover {
            border-color: #ff9900;
            box-shadow: 0 8px 24px rgba(0,0,0,0.1);
            transform: translateY(-3px);
        }
        
        .aws-feature-card .feature-icon {
            width: 48px;
            height: 48px;
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.5rem;
            margin-bottom: 1rem;
        }
        
        .aws-feature-card .feature-icon.blue { background: rgba(0,113,133,0.1); }
        .aws-feature-card .feature-icon.orange { background: rgba(255,153,0,0.1); }
        .aws-feature-card .feature-icon.green { background: rgba(0,113,133,0.1); }
        .aws-feature-card .feature-icon.purple { background: rgba(157,80,187,0.1); }
        
        .aws-feature-card h3 {
            color: #232f3e;
            font-size: 1.1rem;
            margin: 0 0 0.5rem 0;
        }
        
        .aws-feature-card p {
            color: #5f6b7c;
            font-size: 0.9rem;
            line-height: 1.5;
            margin: 0;
        }
        </style>
        """, unsafe_allow_html=True)
        
        # Quick tips section
        st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
        st.markdown('''
        <div style="
            background: #ffffff; 
            border: 1px solid #dfe3e8; 
            border-radius: 10px; 
            padding: 1.5rem; 
            margin: 1.5rem 0;
        ">
            <h3 style="
                color: #232f3e; 
                font-size: 1.1rem; 
                margin: 0 0 1rem 0;
            ">💡 Quick Tips</h3>
        </div>
        ''', unsafe_allow_html=True)
        
        tips_col1, tips_col2, tips_col3 = st.columns(3)
        
        with tips_col1:
            st.info("""
            **🔄 Keep Data Fresh**
            
            Run ETL regularly to ensure CloudWatch metrics are up-to-date for accurate idle detection.
            """)
            
        with tips_col2:
            st.info("""
            **📈 Adjust Thresholds**
            
            Use the sliders to fine-tune sensitivity. Higher thresholds = stricter idle detection.
            """)
            
        with tips_col3:
            st.info("""
            **🎯 Deep Analysis**
            
            Select "Analyze Single Instance" for detailed metrics and recommendations.
            """)
        
        # Keyboard shortcuts help
        with st.expander("⌨️ Keyboard Shortcuts"):
            st.markdown('''
            | Shortcut | Action |
            |----------|--------|
            | `Ctrl + R` | Refresh page |
            | `Esc` | Close dialogs |
            ''')


def main():
    """Main entry point with enhanced initialization"""
    # Configure page layout
    st.set_page_config(
        page_title="AWS Cost Optimizer",
        page_icon="🚀",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Initialize configuration
    Config.initialize()
    
    # Create UI instance
    ui = DashboardUI()
    
    # Apply custom styling
    ui.apply_custom_css()
    
    # Render header
    ui.render_header()
    
    # Get user inputs from sidebar
    manager, service_type, region, scan_button, analyze_button, selected_instance = ui.render_sidebar()
    cloudwatch_hours, activity_days, idle_threshold, pricing_settings = ui.render_parameters()

    # Handle analyze button
    if analyze_button and selected_instance:
        st.session_state.instance_analysis_active = True
        st.session_state.analyzing_instance = selected_instance
        st.session_state.scan_results = None

    # Handle scan button
    if scan_button:
        st.session_state.instance_analysis_active = False
        st.session_state.analyzing_instance = None
        st.session_state.scanning = True
        st.session_state.scan_results = None

    # Execute scan
    if st.session_state.scanning:
        ui.run_scan(manager, service_type, cloudwatch_hours, activity_days, idle_threshold)
        st.rerun()

    # Display single instance analysis
    if st.session_state.instance_analysis_active:
        ui.display_single_analysis(manager, service_type, st.session_state.analyzing_instance, cloudwatch_hours, activity_days, pricing_settings)
    
    # Display scan results
    elif st.session_state.scan_results:
        ui.display_scan_results(service_type, pricing_settings)
    
    # Display home screen
    else:
        ui.render_home_screen()


if __name__ == "__main__":
    main()
