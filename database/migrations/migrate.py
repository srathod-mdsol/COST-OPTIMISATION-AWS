#!/usr/bin/env python3
"""
Database migration utilities for AWS Cost Optimization Tool.

This script provides utilities for:
- Creating database tables
- Seeding initial data
- Migrating data from old SQLite databases
- Database backup and restore

Usage:
    python database/migrations/migrate.py --help
    python database/migrations/migrate.py init
    python database/migrations/migrate.py seed
    python database/migrations/migrate.py backup
    python database/migrations/migrate.py migrate-data --old-db path/to/old.db
"""

import argparse
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Load environment variables from .env file BEFORE importing database modules
from dotenv import load_dotenv
load_dotenv()

from database import init_db, drop_db, config
from database.client import SessionLocal
from database.models import EtlLock


class MigrationManager:
    """Manages database migrations and data transfer."""
    
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or config.database_url
        if self.db_path.startswith("sqlite:///"):
            self.db_path = self.db_path.replace("sqlite:///", "")
        elif self.db_path.startswith("file:"):
            self.db_path = self.db_path[5:]  # Remove 'file:' prefix
    
    def init(self) -> bool:
        """
        Initialize database tables using SQLAlchemy.
        
        Returns:
            True if successful, False otherwise.
        """
        try:
            init_db()
            print("Database tables created successfully")
            return True
        except Exception as e:
            print(f"Error creating tables: {e}")
            return False
    
    def reset(self) -> bool:
        """
        Drop and recreate all database tables.
        
        Returns:
            True if successful, False otherwise.
        """
        try:
            drop_db()
            init_db()
            print("Database reset successfully")
            return True
        except Exception as e:
            print(f"Error resetting database: {e}")
            return False
    
    def backup(self, backup_path: Optional[str] = None) -> str:
        """
        Create a backup of the current database.
        
        Args:
            backup_path: Optional path for backup file.
            
        Returns:
            Path to the backup file.
        """
        # Check if using SQLite (file-based) or PostgreSQL
        if config.is_sqlite:
            # SQLite backup - copy the file
            if not os.path.exists(self.db_path):
                raise FileNotFoundError(f"Database not found: {self.db_path}")
            
            if backup_path is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = f"{self.db_path}.backup_{timestamp}"
            
            shutil.copy2(self.db_path, backup_path)
            print(f"Backup created: {backup_path}")
            return backup_path
        else:
            # PostgreSQL backup - use pg_dump
            import subprocess
            
            if backup_path is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = f"postgresql_backup_{timestamp}.sql"
            
            # Parse DATABASE_URL for pg_dump
            # Format: postgresql://user:password@host:port/database
            db_url = config.database_url
            try:
                result = subprocess.run(
                    ["pg_dump", db_url, "-f", backup_path],
                    capture_output=True,
                    text=True
                )
                if result.returncode != 0:
                    raise Exception(f"pg_dump failed: {result.stderr}")
                print(f"PostgreSQL backup created: {backup_path}")
                return backup_path
            except FileNotFoundError:
                print("Warning: pg_dump not found. Install postgresql-client for PostgreSQL backups.")
                print(f"Database URL: {db_url}")
                return ""
    
    def migrate_data_from_sqlite(
        self,
        old_db_path: str,
        tables: Optional[List[str]] = None
    ) -> Dict[str, int]:
        """
        Migrate data from old SQLite database to new database.
        
        Args:
            old_db_path: Path to the old SQLite database.
            tables: List of tables to migrate. If None, migrates all tables.
            
        Returns:
            Dictionary with table names and row counts.
        """
        if not os.path.exists(old_db_path):
            raise FileNotFoundError(f"Old database not found: {old_db_path}")
        
        old_conn = sqlite3.connect(old_db_path)
        old_conn.row_factory = sqlite3.Row
        old_cursor = old_conn.cursor()
        
        # Get list of tables if not specified
        if tables is None:
            old_cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
            tables = [row['name'] for row in old_cursor.fetchall()]
        
        migrated_counts = {}
        
        # Use SQLAlchemy for the new database (works with both SQLite and PostgreSQL)
        from database.client import SessionLocal
        
        with SessionLocal() as session:
            for table in tables:
                try:
                    # Validate table name to prevent SQL injection
                    # Table names come from SQLite system table but we validate as a precaution
                    if not table.isidentifier():
                        raise ValueError(f"Invalid table name: {table}")

                    # Get column names - use quoted identifier for safety
                    old_cursor.execute(f"PRAGMA table_info('{table}')")
                    columns = [row['name'] for row in old_cursor.fetchall()]

                    # Get data from old table - use quoted identifier for safety
                    old_cursor.execute(f"SELECT * FROM '{table}'")
                    rows = old_cursor.fetchall()

                    if rows:
                        # Use raw SQL for inserting data
                        from sqlalchemy import text

                        placeholders = ', '.join([f':{col}' for col in columns])
                        column_names = ', '.join(columns)

                        for row in rows:
                            data = {col: row[col] for col in columns}
                            session.execute(
                                text(f"INSERT INTO {table} ({column_names}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"),
                                data
                            )

                        migrated_counts[table] = len(rows)
                        print(f"Migrated {len(rows)} rows from {table}")
                    else:
                        migrated_counts[table] = 0
                        print(f"No data in {table}")

                except Exception as e:
                    print(f"Error migrating {table}: {e}")
                    migrated_counts[table] = -1

            session.commit()
        
        old_conn.close()
        
        return migrated_counts
    
    def seed_initial_data(self) -> Dict[str, int]:
        """
        Seed the database with initial data.
        
        Returns:
            Dictionary with seeded table names and counts.
        """
        from contextlib import contextmanager
        
        @contextmanager
        def session_context():
            session = SessionLocal()
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()
        
        with session_context() as session:
            # Initialize ETL lock
            existing_lock = session.query(EtlLock).filter_by(lock_id=1).first()
            if not existing_lock:
                lock = EtlLock(lock_id=1, is_locked=False)
                session.add(lock)
                session.commit()
                print("Initial data seeded successfully")
                return {'etl_lock': 1}
            else:
                print("Initial data already exists")
                return {'etl_lock': 0}
    
    def verify_schema(self) -> bool:
        """
        Verify that the database schema matches the expected schema.
        
        Returns:
            True if schema is valid, False otherwise.
        """
        from sqlalchemy import inspect
        from database.client import engine
        
        expected_tables = [
            'etl_runs', 'raw_instances', 'raw_metrics', 'data_freshness',
            'etl_lock', 'analysis_cache', 'instance_tags', 'aws_pricing', 'ebs_pricing'
        ]
        
        # Use SQLAlchemy inspector which works with any database type
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()
        
        missing_tables = set(expected_tables) - set(existing_tables)
        if missing_tables:
            print(f"Missing tables: {missing_tables}")
            return False
        
        print("Schema verification passed")
        return True


def main():
    """Main entry point for migration script."""
    parser = argparse.ArgumentParser(
        description="Database migration utilities"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Init command
    subparsers.add_parser("init", help="Initialize database tables")
    
    # Reset command
    subparsers.add_parser("reset", help="Drop and recreate all tables")
    
    # Seed command
    subparsers.add_parser("seed", help="Seed initial data")
    
    # Backup command
    backup_parser = subparsers.add_parser("backup", help="Backup database")
    backup_parser.add_argument("--path", help="Backup file path")
    
    # Migrate data command
    migrate_data_parser = subparsers.add_parser(
        "migrate-data", help="Migrate data from old database"
    )
    migrate_data_parser.add_argument("--old-db", required=True, help="Old database path")
    migrate_data_parser.add_argument("--tables", nargs="*", help="Tables to migrate")
    
    # Verify command
    subparsers.add_parser("verify", help="Verify database schema")
    
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        return
    
    manager = MigrationManager()
    
    if args.command == "init":
        success = manager.init()
        sys.exit(0 if success else 1)
    
    elif args.command == "reset":
        success = manager.reset()
        sys.exit(0 if success else 1)
    
    elif args.command == "seed":
        manager.seed_initial_data()
    
    elif args.command == "backup":
        manager.backup(args.path)
    
    elif args.command == "migrate-data":
        manager.migrate_data_from_sqlite(args.old_db, args.tables)
    
    elif args.command == "verify":
        success = manager.verify_schema()
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
