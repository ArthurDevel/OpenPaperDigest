FROM apache/airflow:2.8.1

# Switch to root to install system-level packages
USER root
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        default-libmysqlclient-dev \
        build-essential \
        g++ \
        supervisor \
        sudo \
        chromium \
        chromium-driver \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Switch to airflow user before pip installs
USER airflow

# Copy requirements file
COPY airflow/requirements.txt .

# Run pip installs as airflow user with --user flag
RUN pip install --user --no-cache-dir -r requirements.txt
RUN pip install --user --no-cache-dir requests

# Copy DAGs and shared modules
COPY airflow/dags /opt/airflow/dags
COPY shared /opt/airflow/shared
COPY papers /opt/airflow/papers
COPY users /opt/airflow/users
COPY paperprocessor /opt/airflow/paperprocessor

# Create debugging output directory for paperprocessor (Railway deployment fix)
# This resolves Permission denied errors when paperprocessor tries to write debug files
USER root
RUN mkdir -p /opt/airflow/paperprocessor/debugging_output && \
    chown airflow:root /opt/airflow/paperprocessor/debugging_output && \
    chmod 755 /opt/airflow/paperprocessor/debugging_output
USER airflow

# Make sure PATH includes airflow binaries
ENV PATH="/home/airflow/.local/bin:$PATH"

# Copy supervisord configuration
USER root
COPY airflow/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Allow airflow user to use sudo without password for directory setup
RUN echo "airflow ALL=(ALL) NOPASSWD: /bin/mkdir, /bin/chown" >> /etc/sudoers

# Create entrypoint script
COPY airflow/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Expose port 8080 for webserver
EXPOSE 8080

USER airflow
ENTRYPOINT ["/entrypoint.sh"]