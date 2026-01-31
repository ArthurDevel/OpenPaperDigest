#!/bin/bash
# ==============================================================================
# Worker Entrypoint - Airflow initialization and startup
# ==============================================================================
# This script initializes and starts the Airflow worker service.
#
# Responsibilities:
# - Set up volume permissions for DAG storage
# - Initialize Airflow database
# - Create/update admin user
# - Start Airflow scheduler and webserver via supervisord
# ==============================================================================

set -e

# ==============================================================================
# VOLUME SETUP
# ==============================================================================

# Set up volume permissions if directory exists
if [ -d "/opt/airflow-data" ]; then
    mkdir -p /opt/airflow-data/{dags,logs,plugins} 2>/dev/null || true
    # Skip ownership changes on Railway if they fail
    chmod -R 755 /opt/airflow-data 2>/dev/null || true

    # Sync DAGs from container to volume (always update on deploy)
    echo "Syncing DAGs to volume..."
    cp -r /opt/airflow/dags/* /opt/airflow-data/dags/ 2>/dev/null || true
fi

# ==============================================================================
# PYTHON PATH CONFIGURATION
# ==============================================================================

# Add shared modules to Python path so DAGs can import them
export PYTHONPATH="/opt/airflow/shared:/opt/airflow/papers:/opt/airflow/users:/opt/airflow/search:/opt/airflow/paperprocessor:$PYTHONPATH"

# ==============================================================================
# AIRFLOW INITIALIZATION
# ==============================================================================

# Initialize Airflow database and create admin user
echo "Initializing Airflow database..."
airflow db init

echo "Setting up admin user..."
# Require ADMIN_BASIC_PASSWORD to be set
if [ -z "$ADMIN_BASIC_PASSWORD" ]; then
    echo "ERROR: ADMIN_BASIC_PASSWORD environment variable is not set!"
    echo "Please set ADMIN_BASIC_PASSWORD to secure your Airflow instance."
    exit 1
fi

# Try to create user, if it fails (user exists), update the password instead
if airflow users create \
    --username admin \
    --password "$ADMIN_BASIC_PASSWORD" \
    --firstname Anonymous \
    --lastname User \
    --role Admin \
    --email admin@example.org 2>&1 | grep -q "already exists"; then
    echo "Admin user already exists, updating password..."
    airflow users reset-password \
        --username admin \
        --password "$ADMIN_BASIC_PASSWORD"
fi

# ==============================================================================
# START SERVICES
# ==============================================================================

echo "Starting Airflow scheduler and webserver..."
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
