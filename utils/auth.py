"""
Authentication module for AWS Cost Optimizer.

Provides role-based authentication with:
- Multiple admin user support
- Bcrypt password hashing
- Configurable session timeout
- Password change functionality
"""

import os
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple
from dotenv import load_dotenv

# Import bcrypt with fallback handling
try:
    import bcrypt
    BCRYPT_AVAILABLE = True
except ImportError:
    BCRYPT_AVAILABLE = False


class AuthManager:
    """Manages authentication for admin users.
    
    Features:
    - Multiple admin users from environment variable
    - Bcrypt password hashing and verification
    - Session management with configurable timeout
    - Password change with secure .env update
    
    Environment Variables:
        ADMIN_USERS: Comma-separated list of username:hash pairs
                     Format: "user1:hash1,user2:hash2"
        SESSION_TIMEOUT_MINUTES: Session inactivity timeout (default: 10)
    
    Example:
        >>> from utils.auth import AuthManager
        >>> auth = AuthManager()
        >>> if auth.login("admin", "password"):
        ...     print("Login successful")
    """
    
    # Session state keys
    SESSION_KEY = 'auth_session'
    USER_KEY = 'auth_user'
    LAST_ACTIVITY_KEY = 'auth_last_activity'
    
    def __init__(self):
        """Initialize the authentication manager."""
        load_dotenv()
        self._users: Dict[str, str] = {}  # username -> password_hash
        self._session_timeout_minutes: int = 10
        self._env_file_path: Optional[str] = None
        self._load_config()
    
    def _load_config(self) -> None:
        """Load admin users and session timeout from environment."""
        # Load session timeout
        timeout_str = os.environ.get('SESSION_TIMEOUT_MINUTES', '10')
        try:
            self._session_timeout_minutes = int(timeout_str)
        except ValueError:
            self._session_timeout_minutes = 10
        
        # Load admin users
        admin_users_str = os.environ.get('ADMIN_USERS', '')
        self._users = self._parse_admin_users(admin_users_str)
        
        # Find .env file path for password changes
        self._env_file_path = self._find_env_file()
    
    def _find_env_file(self) -> Optional[str]:
        """Find the .env file path."""
        # Check common locations
        possible_paths = [
            '.env',
            os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'),
        ]
        for path in possible_paths:
            if os.path.exists(path):
                return os.path.abspath(path)
        return None
    
    def _parse_admin_users(self, users_str: str) -> Dict[str, str]:
        """Parse admin users from environment variable.
        
        Format: "user1:hash1,user2:hash2"
        
        Args:
            users_str: Comma-separated username:hash pairs
            
        Returns:
            Dictionary mapping usernames to password hashes
        """
        users = {}
        if not users_str:
            return users
        
        for user_entry in users_str.split(','):
            user_entry = user_entry.strip()
            if ':' not in user_entry:
                continue
            
            # Split only on the first colon (hash may contain colons in rare cases)
            parts = user_entry.split(':', 1)
            if len(parts) == 2:
                username = parts[0].strip()
                password_hash = parts[1].strip()
                if username and password_hash:
                    users[username] = password_hash
        
        return users
    
    @property
    def session_timeout_minutes(self) -> int:
        """Get the session timeout in minutes."""
        return self._session_timeout_minutes
    
    @property
    def users(self) -> Dict[str, str]:
        """Get the dictionary of admin users."""
        return self._users.copy()
    
    def has_users(self) -> bool:
        """Check if any admin users are configured."""
        return len(self._users) > 0
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password using bcrypt.
        
        Args:
            password: Plain text password
            
        Returns:
            Bcrypt hash as string
        """
        if not BCRYPT_AVAILABLE:
            raise ImportError("bcrypt is required for password hashing. Install with: pip install bcrypt")
        
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed.decode('utf-8')
    
    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        """Verify a password against a bcrypt hash.
        
        Args:
            password: Plain text password to verify
            password_hash: Bcrypt hash to compare against
            
        Returns:
            True if password matches, False otherwise
        """
        if not BCRYPT_AVAILABLE:
            raise ImportError("bcrypt is required for password verification. Install with: pip install bcrypt")
        
        try:
            return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
        except Exception:
            return False
    
    def authenticate(self, username: str, password: str) -> Tuple[bool, str]:
        """Authenticate a user.
        
        Args:
            username: Username to authenticate
            password: Password to verify
            
        Returns:
            Tuple of (success, message)
        """
        if not self.has_users():
            return False, "No admin users configured. Please set ADMIN_USERS in .env"
        
        if username not in self._users:
            return False, "Invalid username or password"
        
        stored_hash = self._users[username]
        
        if self.verify_password(password, stored_hash):
            return True, "Authentication successful"
        else:
            return False, "Invalid username or password"
    
    def create_session(self, session_state: dict, username: str) -> None:
        """Create a new session for an authenticated user.
        
        Args:
            session_state: Streamlit session state dict
            username: Authenticated username
        """
        session_state[self.SESSION_KEY] = True
        session_state[self.USER_KEY] = username
        session_state[self.LAST_ACTIVITY_KEY] = datetime.now(timezone.utc)
    
    def is_authenticated(self, session_state: dict) -> bool:
        """Check if the current session is authenticated and valid.
        
        Args:
            session_state: Streamlit session state dict
            
        Returns:
            True if authenticated and session not expired
        """
        if not session_state.get(self.SESSION_KEY, False):
            return False
        
        # Check session timeout
        last_activity = session_state.get(self.LAST_ACTIVITY_KEY)
        if last_activity:
            timeout = timedelta(minutes=self._session_timeout_minutes)
            if datetime.now(timezone.utc) - last_activity > timeout:
                # Session expired
                self.logout(session_state)
                return False
        
        return True
    
    def get_current_user(self, session_state: dict) -> Optional[str]:
        """Get the currently authenticated username.
        
        Args:
            session_state: Streamlit session state dict
            
        Returns:
            Username if authenticated, None otherwise
        """
        if self.is_authenticated(session_state):
            return session_state.get(self.USER_KEY)
        return None
    
    def update_activity(self, session_state: dict) -> None:
        """Update the last activity timestamp.
        
        Args:
            session_state: Streamlit session state dict
        """
        if session_state.get(self.SESSION_KEY, False):
            session_state[self.LAST_ACTIVITY_KEY] = datetime.now(timezone.utc)
    
    def logout(self, session_state: dict) -> None:
        """End the current session.
        
        Args:
            session_state: Streamlit session state dict
        """
        session_state[self.SESSION_KEY] = False
        if self.USER_KEY in session_state:
            del session_state[self.USER_KEY]
        if self.LAST_ACTIVITY_KEY in session_state:
            del session_state[self.LAST_ACTIVITY_KEY]
    
    def get_remaining_session_time(self, session_state: dict) -> Optional[int]:
        """Get remaining session time in minutes.
        
        Args:
            session_state: Streamlit session state dict
            
        Returns:
            Remaining minutes if authenticated, None otherwise
        """
        if not session_state.get(self.SESSION_KEY, False):
            return None
        
        last_activity = session_state.get(self.LAST_ACTIVITY_KEY)
        if not last_activity:
            return None
        
        elapsed = datetime.now(timezone.utc) - last_activity
        remaining = timedelta(minutes=self._session_timeout_minutes) - elapsed
        
        if remaining.total_seconds() <= 0:
            return 0
        
        return int(remaining.total_seconds() / 60)
    
    def change_password(self, username: str, current_password: str, new_password: str) -> Tuple[bool, str]:
        """Change a user's password.
        
        Args:
            username: Username to change password for
            current_password: Current password for verification
            new_password: New password to set
            
        Returns:
            Tuple of (success, message)
        """
        # Verify current password
        auth_success, auth_msg = self.authenticate(username, current_password)
        if not auth_success:
            return False, auth_msg
        
        # Validate new password
        if len(new_password) < 8:
            return False, "Password must be at least 8 characters long"
        
        # Hash new password
        new_hash = self.hash_password(new_password)
        
        # Update .env file
        success, message = self._update_env_file(username, new_hash)
        
        if success:
            # Update in-memory users dict
            self._users[username] = new_hash
        
        return success, message
    
    def _update_env_file(self, username: str, new_hash: str) -> Tuple[bool, str]:
        """Update the .env file with a new password hash.
        
        Args:
            username: Username to update
            new_hash: New password hash
            
        Returns:
            Tuple of (success, message)
        """
        if not self._env_file_path:
            return False, "Could not locate .env file"
        
        try:
            # Read current .env content
            with open(self._env_file_path, 'r') as f:
                content = f.read()
            
            # Get current ADMIN_USERS value
            admin_users_str = os.environ.get('ADMIN_USERS', '')
            
            # Parse and update the user's hash
            updated_users = []
            for user_entry in admin_users_str.split(','):
                user_entry = user_entry.strip()
                if ':' not in user_entry:
                    continue
                
                parts = user_entry.split(':', 1)
                if len(parts) == 2:
                    entry_username = parts[0].strip()
                    entry_hash = parts[1].strip()
                    
                    if entry_username == username:
                        # Update this user's hash
                        updated_users.append(f"{username}:{new_hash}")
                    else:
                        updated_users.append(user_entry)
            
            new_admin_users = ','.join(updated_users)
            
            # Update the ADMIN_USERS line in .env
            # Pattern to match ADMIN_USERS=... (handles various formats)
            pattern = r'^ADMIN_USERS\s*=\s*.*$'
            replacement = f'ADMIN_USERS={new_admin_users}'
            
            if re.search(pattern, content, re.MULTILINE):
                new_content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
            else:
                # Add ADMIN_USERS if not present
                new_content = content.rstrip() + f'\nADMIN_USERS={new_admin_users}\n'
            
            # Write updated content
            with open(self._env_file_path, 'w') as f:
                f.write(new_content)
            
            # Update environment variable
            os.environ['ADMIN_USERS'] = new_admin_users
            
            return True, "Password updated successfully"
            
        except PermissionError:
            return False, "Permission denied. Could not write to .env file"
        except Exception as e:
            return False, f"Error updating password: {str(e)}"


# Singleton instance
_auth_manager: Optional[AuthManager] = None


def get_auth_manager() -> AuthManager:
    """Get the singleton AuthManager instance.
    
    Returns:
        AuthManager instance
    """
    global _auth_manager
    if _auth_manager is None:
        _auth_manager = AuthManager()
    return _auth_manager


def generate_password_hash(password: str) -> str:
    """Utility function to generate a password hash.
    
    Use this to generate initial hashes for the .env file.
    
    Args:
        password: Plain text password
        
    Returns:
        Bcrypt hash as string
    """
    return AuthManager.hash_password(password)


if __name__ == '__main__':
    # CLI utility for generating password hashes
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python -m utils.auth <password>")
        print("Generates a bcrypt hash for the given password.")
        print("Add the hash to ADMIN_USERS in .env as: username:hash")
        sys.exit(1)
    
    password = sys.argv[1]
    try:
        hash_value = generate_password_hash(password)
        print(f"Password hash: {hash_value}")
        print(f"\nAdd to .env as:")
        print(f"ADMIN_USERS=admin:{hash_value}")
    except ImportError as e:
        print(f"Error: {e}")
        sys.exit(1)
