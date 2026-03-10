"""
AWS Idle Identifier Dashboard Module

This module provides a modular structure for the Streamlit dashboard:
- cache.py: All caching functions for performance optimization
- components.py: Reusable UI components (header, sidebar sections, etc.)
- helpers.py: Helper functions for cost display and formatting
- main.py: Main DashboardUI class and entry point

For backward compatibility, imports from this module also work:
    from ui.dashboard import DashboardUI, main
    
Or directly from ui.dashboard modules:
    from ui.dashboard.cache import get_etl_provider_cached
    from ui.dashboard.components import render_header
    from ui.dashboard.helpers import display_ec2_cost_breakdown
"""

# Re-export everything for backward compatibility
# The actual implementation is in the submodules

__version__ = "2.0.0"
__all__ = [
    "DashboardUI",
    "main",
    # Cache functions
    "get_ec2_detailed_breakdown_cached",
    "get_rds_detailed_breakdown_cached",
    "get_ebs_detailed_breakdown_cached",
    "get_etl_provider_cached",
    "get_instances_cached",
    "get_data_freshness_cached",
    "get_pricing_cached",
    "get_instance_tags_cached",
    "get_manager_cached",
    "load_css_cached",
    # Helper functions
    "display_ec2_cost_breakdown",
    "display_rds_cost_breakdown",
    "display_ebs_cost_breakdown",
    "format_currency",
    "format_percentage",
]

# Import all cache functions
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

# Import helper functions
from ui.dashboard.helpers import (
    display_ec2_cost_breakdown,
    display_rds_cost_breakdown,
    display_ebs_cost_breakdown,
    format_currency,
    format_percentage,
)

