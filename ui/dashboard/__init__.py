"""
AWS Idle Identifier Dashboard Module

This module provides a modular structure for the Streamlit dashboard:
- cache.py: All caching functions for performance optimization
- components.py: Reusable UI components (header, sidebar sections, etc.)
- helpers.py: Helper functions for cost display and formatting
- views_single_analysis.py: Single instance analysis views
- admin/: Admin panel components

For backward compatibility, imports from this module also work:
    from ui.dashboard import DashboardUI, main
"""

import importlib.util
import os

# Get the path to the parent directory (workspace/cloud-shell)
# The main dashboard.py file is in ui/ directory
_dashboard_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'ui', 'dashboard.py')

# Load the dashboard module from the file without adding to sys.modules prematurely
spec = importlib.util.spec_from_file_location("_dashboard_module", _dashboard_file)
if spec and spec.loader:
    _dashboard_module = importlib.util.module_from_spec(spec)
    
    # We need to set up the path for ui.dashboard submodules first
    # before executing the dashboard module
    import sys
    _original_path = sys.path.copy()
    
    try:
        # Add parent to path so imports like 'from ui.dashboard.cache' work
        _parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if _parent_dir not in sys.path:
            sys.path.insert(0, _parent_dir)
        
        # Execute the module
        spec.loader.exec_module(_dashboard_module)
        
        # Now export the main and DashboardUI
        main = _dashboard_module.main
        DashboardUI = _dashboard_module.DashboardUI
    finally:
        sys.path = _original_path

# Re-export for backward compatibility
__version__ = "2.1.0"
__all__ = ["DashboardUI", "main", "admin"]
