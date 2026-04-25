-- Apache AGE Initialization Script for PATHS
-- Run this on the PostgreSQL instance after AGE extension is installed.

-- Enable the AGE extension
CREATE EXTENSION IF NOT EXISTS age;

-- Load AGE into the session
LOAD 'age';

-- Set search path to include ag_catalog
SET search_path = ag_catalog, "$user", public;

-- Create the application graph if it doesn't exist
SELECT create_graph('paths_graph');
