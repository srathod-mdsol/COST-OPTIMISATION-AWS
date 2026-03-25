#!/usr/bin/env python3
"""
AWS Idle Instance Monitor - Entry Point
Delegates execution to either the CLI interface or the Streamlit dashboard.
"""

import sys
import os

# Add the current directory to sys.path to ensure imports work correctly
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def is_streamlit_running():
    """Detect if the script is being run via 'streamlit run'"""
    # Streamlit sets certain environment variables or changes sys.argv
    return 'streamlit' in sys.argv[0] or any('streamlit' in arg for arg in sys.argv)

def main():
    """ Main entry point that selects between CLI and UI modes """
    
    # Check if we are in CLI mode (direct python execution with arguments)
    # or if we are being run via streamlit
    
    # If there are arguments and it's not a streamlit call, use CLI
    is_cli = len(sys.argv) > 1 and not is_streamlit_running()
    
    if is_cli:
        from ui.cli import CLIInterface
        cli = CLIInterface()
        cli.run()
    else:
        # For Streamlit, we just import and run the dashboard main
        # Note: When running 'streamlit run main.py', this block will execute
        try:
            import streamlit as st
            # Import directly from the dashboard.py file
            from ui.dashboard import main as dashboard_main
            dashboard_main()
        except ImportError as e:
            from core.logger import setup_logger
            logger = setup_logger(__name__)
            logger.error(f"Streamlit not found: {e}. Please install it with 'pip install streamlit'")
            logger.error("Alternatively, use CLI mode: python main.py --service rds --check-all")
            sys.exit(1)

if __name__ == "__main__":
    main()

