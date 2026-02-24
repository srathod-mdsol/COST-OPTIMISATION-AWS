-- AWS Cost Optimization Database Initialization Script
-- This script runs when the PostgreSQL container starts for the first time

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";

-- Grant permissions to the application user
GRANT ALL PRIVILEGES ON DATABASE cost_optimization TO costadmin;

-- Set default schema
SET search_path TO public;

-- Log initialization
DO $$
BEGIN
    RAISE NOTICE 'Database initialized successfully for AWS Cost Optimization Tool';
END $$;
