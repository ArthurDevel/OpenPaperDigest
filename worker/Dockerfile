# ==============================================================================
# Worker Dockerfile - Airflow-based Python worker service
# ==============================================================================
# This Dockerfile builds the worker service that runs:
# - Airflow scheduler and webserver
# - Paper processing DAGs
# - All Python-based background processing tasks
#
# Responsibilities:
# - Process papers from ArXiv and other sources
# - Run scheduled DAGs for paper ingestion
# - Handle paper PDF processing and metadata extraction
# ==============================================================================

FROM apache/airflow:2.8.1

# ==============================================================================
# SYSTEM DEPENDENCIES
# ==============================================================================

USER root
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libpq-dev \
        build-essential \
        g++ \
        supervisor \
        sudo \
        chromium \
        chromium-driver \
        poppler-utils \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# ==============================================================================
# PYTHON DEPENDENCIES
# ==============================================================================

USER airflow

# Copy requirements file from worker directory
COPY worker/requirements.txt .

# Run pip installs as airflow user with --user flag
RUN pip install --user --no-cache-dir -r requirements.txt
RUN pip install --user --no-cache-dir requests

# ==============================================================================
# APPLICATION CODE
# ==============================================================================

# Copy all Python modules from worker directory
COPY worker/dags /opt/airflow/dags
COPY worker/shared /opt/airflow/shared
COPY worker/papers /opt/airflow/papers
COPY worker/users /opt/airflow/users
COPY worker/search /opt/airflow/search
COPY worker/paperprocessor /opt/airflow/paperprocessor

# Create debugging output directory for paperprocessor (Railway deployment fix)
USER root
RUN mkdir -p /opt/airflow/paperprocessor/debugging_output && \
    chown airflow:root /opt/airflow/paperprocessor/debugging_output && \
    chmod 755 /opt/airflow/paperprocessor/debugging_output
USER airflow

# ==============================================================================
# CONFIGURATION
# ==============================================================================

# Make sure PATH includes airflow binaries
ENV PATH="/home/airflow/.local/bin:$PATH"

# Set PYTHONPATH to include all modules
ENV PYTHONPATH="/opt/airflow/shared:/opt/airflow/papers:/opt/airflow/users:/opt/airflow/search:/opt/airflow/paperprocessor:$PYTHONPATH"

USER root

# Copy supervisord configuration
COPY worker/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Allow airflow user to use sudo without password for directory setup
RUN echo "airflow ALL=(ALL) NOPASSWD: /bin/mkdir, /bin/chown" >> /etc/sudoers

# Create entrypoint script
COPY worker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# ==============================================================================
# ENTRYPOINT
# ==============================================================================

# Expose port 8080 for Airflow webserver
EXPOSE 8080

USER airflow
ENTRYPOINT ["/entrypoint.sh"]
