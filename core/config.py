import os
import sys
from dotenv import load_dotenv
from core.constants import (
    DEFAULT_REGION,
    LOCK_TIMEOUT_MINUTES,
    MAX_CONCURRENT_WORKERS,
    CLOUDWATCH_TIMEOUT_SECONDS,
    PRICING_BATCH_SIZE,
    CPU_IDLE_THRESHOLD,
    CPU_CRITICAL_THRESHOLD,
    DB_CONNECTIONS_IDLE_THRESHOLD,
    NETWORK_IDLE_THRESHOLD,
    DISK_READ_IDLE_THRESHOLD,
    DISK_WRITE_IDLE_THRESHOLD,
    READ_IOPS_IDLE_THRESHOLD,
    WRITE_IOPS_IDLE_THRESHOLD
)

# Load environment variables
load_dotenv()

class Config:
    """Configuration management for the Cost Optimization App.
    
    This class provides centralized configuration for the AWS Cost Optimizer,
    including database paths, AWS settings, and storage cost definitions.
    All settings can be overridden via environment variables.
    
    Environment Variables:
        - DATABASE_URL: SQLAlchemy connection string (supports PostgreSQL, MySQL, Oracle, MSSQL, SQLite)
        - ETL_DB_PATH: Path to the ETL database (legacy, for SQLite only)
        - PRICING_DB_PATH: Path to the pricing database (legacy, for SQLite only)
        - PRICING_JSON_DIR: Directory containing pricing JSON files
        - EC2_PRICING_JSON_PATH: Path to EC2 pricing JSON
        - RDS_PRICING_JSON_PATH: Path to RDS pricing JSON
    
    Example:
        >>> from core.config import Config
        >>> Config.initialize()
        >>> print(Config.DATABASE_URL)
    """
    
    # Execution Mode
    CLI_MODE = len(sys.argv) > 1 and not any('streamlit' in arg.lower() for arg in sys.argv)
    
    # Database Configuration
    # Primary: Use DATABASE_URL (SQLAlchemy connection string)
    DATABASE_URL = os.environ.get('DATABASE_URL', '')
    
    # Legacy support: Extract SQLite path from DATABASE_URL if applicable
    _database_url = DATABASE_URL
    if _database_url and _database_url.startswith('sqlite:///'):
        DEFAULT_ETL_DB_PATH = _database_url.replace('sqlite:///', '')
    elif _database_url and _database_url.startswith('file:'):
        DEFAULT_ETL_DB_PATH = _database_url[5:]  # Remove 'file:' prefix
    else:
        # For non-SQLite databases or when DATABASE_URL is not set
        DEFAULT_ETL_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'etl_database.db')
    
    # Legacy path (used only for SQLite fallback)
    ETL_DB_PATH = os.environ.get('ETL_DB_PATH', DEFAULT_ETL_DB_PATH)
    
    @classmethod
    def get_database_url(cls, environment_name: str = 'Default') -> str:
        """Get database URL for the specified environment.
        
        For SQLite, returns a path-based URL.
        For other databases, returns the DATABASE_URL with optional schema suffix.
        """
        if cls.DATABASE_URL and not cls.DATABASE_URL.startswith('sqlite'):
            # For PostgreSQL, MySQL, etc. - use the same connection
            # Multi-tenancy would require separate databases or schemas
            return cls.DATABASE_URL
        
        # For SQLite, create environment-specific database file
        db_path = cls.get_db_path(environment_name)
        return f"sqlite:///{db_path}"
    
    @classmethod
    def get_db_path(cls, environment_name: str = 'Default'):
        """Get environment-specific database path (for SQLite only)"""
        if not environment_name or environment_name == 'Default':
            return cls.ETL_DB_PATH
        
        # Format: etl_database_green.db
        suffix = environment_name.lower().replace(' ', '_')
        base_path = cls.ETL_DB_PATH
        if base_path.endswith('.db'):
            return base_path.replace('.db', f'_{suffix}.db')
        return f"{base_path}_{suffix}"
    
    @classmethod
    def is_sqlite(cls) -> bool:
        """Check if using SQLite database."""
        return cls.DATABASE_URL.startswith('sqlite') if cls.DATABASE_URL else True
    
    @classmethod
    def is_postgresql(cls) -> bool:
        """Check if using PostgreSQL database."""
        return cls.DATABASE_URL.startswith('postgresql') if cls.DATABASE_URL else False
    
    @classmethod
    def is_mysql(cls) -> bool:
        """Check if using MySQL database."""
        return cls.DATABASE_URL.startswith('mysql') if cls.DATABASE_URL else False
    
    @classmethod
    def is_oracle(cls) -> bool:
        """Check if using Oracle database."""
        return cls.DATABASE_URL.startswith('oracle') if cls.DATABASE_URL else False
    
    @classmethod
    def is_mssql(cls) -> bool:
        """Check if using MSSQL database."""
        return cls.DATABASE_URL.startswith('mssql') or cls.DATABASE_URL.startswith('sqlserver') if cls.DATABASE_URL else False

    # Separate Pricing Database (isolated from ETL to prevent data loss during truncate)
    DEFAULT_PRICING_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'pricing_database.db')
    PRICING_DB_PATH = os.environ.get('PRICING_DB_PATH', DEFAULT_PRICING_DB_PATH)
    
    # Pricing Database URL - separate from main database for pricing data
    # Defaults to SQLite for backwards compatibility, but can be set to PostgreSQL
    PRICING_DATABASE_URL = os.environ.get('PRICING_DATABASE_URL', f'sqlite:///{PRICING_DB_PATH}')
    
    @classmethod
    def get_pricing_database_url(cls) -> str:
        """Get the pricing database URL."""
        return cls.PRICING_DATABASE_URL
    
    @classmethod
    def get_pricing_db_path(cls) -> str:
        """Get the pricing database file path from URL (for SQLite only).
        
        Extracts the file path from PRICING_DATABASE_URL for SQLite databases.
        This ensures we check the correct path when the URL is set via environment variable.
        """
        if not cls.is_pricing_sqlite():
            return cls.PRICING_DB_PATH  # Return default for non-SQLite
        
        url = cls.PRICING_DATABASE_URL
        if url.startswith('sqlite:///'):
            return url.replace('sqlite:///', '')
        elif url.startswith('sqlite://'):
            return url[9:]  # Remove 'sqlite://' prefix
        return cls.PRICING_DB_PATH
    
    @classmethod
    def is_pricing_sqlite(cls) -> bool:
        """Check if pricing database is SQLite."""
        return cls.PRICING_DATABASE_URL.startswith('sqlite')
    
    # Pricing Data
    PRICING_JSON_DIR = os.environ.get('PRICING_JSON_DIR', os.path.join(os.path.dirname(os.path.dirname(__file__)), 'pricing'))
    PRICING_JSON_PATHS = {
        'ec2': os.environ.get('EC2_PRICING_JSON_PATH', os.path.join(PRICING_JSON_DIR, 'ec2_pricing.json')),
        'rds': os.environ.get('RDS_PRICING_JSON_PATH', os.path.join(PRICING_JSON_DIR, 'rds_pricing.json')),
    }
    
    # Logging Configuration
    LOG_DIR = os.path.join(os.getcwd(), 'logs')
    LOG_FILE = os.path.join(LOG_DIR, 'aws_monitor.log')
    
    # AWS Configuration
    DEFAULT_REGION = DEFAULT_REGION
    LOCK_TIMEOUT = LOCK_TIMEOUT_MINUTES
    MAX_WORKERS = MAX_CONCURRENT_WORKERS
    CLOUDWATCH_TIMEOUT = CLOUDWATCH_TIMEOUT_SECONDS
    
    # Idle Thresholds
    CPU_IDLE_THRESHOLD = float(os.environ.get('CPU_IDLE_THRESHOLD', CPU_IDLE_THRESHOLD))
    CPU_CRITICAL_THRESHOLD = float(os.environ.get('CPU_CRITICAL_THRESHOLD', CPU_CRITICAL_THRESHOLD))
    DB_CONNECTIONS_IDLE_THRESHOLD = float(os.environ.get('DB_CONNECTIONS_IDLE_THRESHOLD', DB_CONNECTIONS_IDLE_THRESHOLD))
    NETWORK_IDLE_THRESHOLD = float(os.environ.get('NETWORK_IDLE_THRESHOLD', NETWORK_IDLE_THRESHOLD))
    DISK_READ_IDLE_THRESHOLD = float(os.environ.get('DISK_READ_IDLE_THRESHOLD', DISK_READ_IDLE_THRESHOLD))
    DISK_WRITE_IDLE_THRESHOLD = float(os.environ.get('DISK_WRITE_IDLE_THRESHOLD', DISK_WRITE_IDLE_THRESHOLD))
    READ_IOPS_IDLE_THRESHOLD = float(os.environ.get('READ_IOPS_IDLE_THRESHOLD', READ_IOPS_IDLE_THRESHOLD))
    WRITE_IOPS_IDLE_THRESHOLD = float(os.environ.get('WRITE_IOPS_IDLE_THRESHOLD', WRITE_IOPS_IDLE_THRESHOLD))

    @classmethod
    def get_available_environments(cls):
        """Discover available AWS environments from environment variables.
        
        Returns a list of environment names.
        Scans for variables ending in '_ACCESS_KEY_ID'.
        """
        # Force reload from .env to pick up new changes without app restart
        load_dotenv(override=True)
        
        envs = []
        for key in os.environ:
            if key.endswith('_ACCESS_KEY_ID'):
                # Handle AWS_GREEN_ACCESS_KEY_ID -> AWS Green
                prefix = key.replace('_ACCESS_KEY_ID', '')
                if prefix == 'AWS':
                    continue
                
                # Format name: AWS_GREEN -> AWS Green
                name = prefix.replace('_', ' ').title()
                envs.append(name)
        
        # Always include 'Default' if standard AWS keys are present
        if os.environ.get('AWS_ACCESS_KEY_ID'):
            if 'Default' not in envs:
                envs.append('Default')
        
        return sorted(list(set(envs))) if envs else ['Default']

    @classmethod
    def get_aws_credentials(cls, environment_name):
        """Retrieve credentials for a specific environment.
        
        Args:
            environment_name (str): Name of the environment (e.g. 'AWS Green')
            
        Returns:
            dict: {access_key, secret_key, region, session_token}
        """
        if not environment_name or environment_name == 'Default':
            return {
                'aws_access_key_id': os.environ.get('AWS_ACCESS_KEY_ID'),
                'aws_secret_access_key': os.environ.get('AWS_SECRET_ACCESS_KEY'),
                'region_name': os.environ.get('AWS_DEFAULT_REGION', cls.DEFAULT_REGION),
                'aws_session_token': os.environ.get('AWS_SESSION_TOKEN')
            }
        
        # Convert 'AWS Green' back to 'AWS_GREEN'
        prefix = environment_name.upper().replace(' ', '_')
        
        return {
            'aws_access_key_id': os.environ.get(f'{prefix}_ACCESS_KEY_ID'),
            'aws_secret_access_key': os.environ.get(f'{prefix}_SECRET_ACCESS_KEY'),
            'region_name': os.environ.get(f'{prefix}_DEFAULT_REGION', cls.DEFAULT_REGION),
            'aws_session_token': os.environ.get(f'{prefix}_SESSION_TOKEN')
        }

    @classmethod
    def initialize(cls):
        """Prepare environment and directories with secure permissions"""
        # Create log directory
        try:
            os.makedirs(cls.LOG_DIR, exist_ok=True)
            # Set secure permissions (owner-only) on log directory
            try:
                os.chmod(cls.LOG_DIR, 0o700)
            except OSError:
                pass
        except (PermissionError, OSError) as e:
            # Log directory creation failed - likely running in container with host path
            pass
        
        # Ensure db directory exists and is secured
        db_dir = os.path.dirname(cls.ETL_DB_PATH)
        if db_dir:  # Only try if we have a valid directory path
            try:
                os.makedirs(db_dir, exist_ok=True)
                try:
                    os.chmod(db_dir, 0o700)
                except OSError:
                    pass
            except (PermissionError, OSError) as e:
                # DB directory creation failed - likely running in container with host path
                # This is acceptable for non-SQLite databases or mounted volumes
                pass

        # Secure individual database files if they exist
        for db_file in [cls.ETL_DB_PATH, cls.PRICING_DB_PATH]:
            if db_file and os.path.exists(db_file):
                try:
                    os.chmod(db_file, 0o600)
                except OSError:
                    pass

        # Secure .env file if it exists
        env_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
        if os.path.exists(env_file):
            try:
                os.chmod(env_file, 0o600)
            except OSError:
                pass

    # Authentication Configuration
    @classmethod
    def get_admin_users(cls) -> dict:
        """Get admin users from environment variable.
        
        Returns:
            Dictionary mapping usernames to password hashes
        """
        admin_users_str = os.environ.get('ADMIN_USERS', '')
        users = {}
        
        if not admin_users_str:
            return users
        
        for user_entry in admin_users_str.split(','):
            user_entry = user_entry.strip()
            if ':' not in user_entry:
                continue
            
            parts = user_entry.split(':', 1)
            if len(parts) == 2:
                username = parts[0].strip()
                password_hash = parts[1].strip()
                if username and password_hash:
                    users[username] = password_hash
        
        return users
    
    @classmethod
    def get_session_timeout_minutes(cls) -> int:
        """Get session timeout in minutes from environment.
        
        Returns:
            Session timeout in minutes (default: 10)
        """
        timeout_str = os.environ.get('SESSION_TIMEOUT_MINUTES', '10')
        try:
            return int(timeout_str)
        except ValueError:
            return 10
    
    @classmethod
    def has_admin_users(cls) -> bool:
        """Check if any admin users are configured.
        
        Returns:
            True if ADMIN_USERS is set and contains valid users
        """
        return len(cls.get_admin_users()) > 0
