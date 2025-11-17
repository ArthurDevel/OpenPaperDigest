# Open Paper Digest

[https://openpaperdigest.com](https://openpaperdigest.com)

Daily digest of popular research papers made accessible for everyone. Stay up to date with advanced research through a continuous feed of digestible paper summaries.

## Codebase Structure

Here is a high-level overview of the codebase structure:

```.
├── airflow/              # Airflow DAGs for data processing pipelines
├── api/                  # FastAPI backend application
├── frontend/             # Next.js frontend application
├── paperprocessor/       # Core logic for processing papers
├── papers/               # Database models and client for papers
├── search/               # Search functionality
├── shared/               # Shared utilities and clients for external services
├── users/                # User management
├── migrations/           # Database migrations
├── docker-compose.yml    # Docker services definition
├── Dockerfile            # Main application Dockerfile
└── requirements.txt      # Python dependencies
```

