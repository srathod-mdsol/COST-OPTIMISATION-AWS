"""
AWS Cost Optimization Tool - Package Setup
"""

from setuptools import setup, find_packages

setup(
    name="aws-cost-optimization",
    version="1.0.0",
    description="AWS Cost Optimization Tool - Analyze and optimize AWS resource costs",
    author="Your Name",
    author_email="your.email@example.com",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "boto3>=1.26.0",
        "streamlit>=1.28.0",
        "pandas>=2.0.0",
        "plotly>=5.18.0",
        "sqlalchemy>=2.0.0",
        "aiosqlite>=0.19.0",
        "python-dotenv>=1.0.0",
        "apscheduler>=3.10.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.21.0",
            "pytest-cov>=4.0.0",
            "black>=23.0.0",
            "flake8>=6.0.0",
            "mypy>=1.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "aws-cost-dashboard=ui.dashboard:main",
            "aws-cost-etl=main:main",
        ],
    },
    include_package_data=True,
    zip_safe=False,
)
