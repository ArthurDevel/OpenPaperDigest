



## API

- endpoints are thin wrappers; they delegate to module client APIs or compose a few module calls to fulfill requests
- endpoints do not access the database directly; all DB reads/writes go through module `client.py`
- authentication/authorization is handled in this layer
- `api/endpoints/` stores the endpoints; `api/types/` stores the API DTOs (files named after the endpoint file)
- endpoints translate domain exceptions to HTTP errors; modules never raise HTTP-specific errors
- endpoints that touch DB/files remain sync; FastAPI threadpools handle concurrency
- use async in endpoints only when calling high-concurrency network I/O in specialized modules
- long-running jobs execute in workers/background tasks; endpoints only enqueue/monitor


## Modules

- each module exposes:
  - `name_of_module/client.py`: public functions used by API or other modules
  - `name_of_module/models.py`: SQLAlchemy ORM models (importable by API and other modules)
  - `name_of_module/internals/`: private helpers (not imported outside the module)
- modules own database access and transaction boundaries; they decide when to flush/commit
- modules raise domain exceptions (e.g., NotFound, Conflict); API translates to HTTP
- cross-module imports are allowed when needed; prefer clear separation of concerns and avoid cycles
- keep responsibilities clear


## shared/

- simple, leaf utilities with no dependency on API or domain modules
- examples: `shared/openrouter/client.py`, `shared/arxiv/client.py`, `shared/db.py`, `shared/config.py`


## Data and persistence

- ORM models live strictly under their module’s `models.py`
- API never defines ORM models and does not manipulate the DB directly
- foreign keys across modules are permitted; models must not import API code


## DTOs and mapping

- keep API DTOs separate from ORM classes under `api/types/`
- mapping from ORM to DTOs is explicit and localized in endpoints (or a small mapper utility if reused)


## Background processing

- long-running work resides in `workers/` and calls module client APIs
- background job orchestration/state belongs to workers/API, not domain modules -> nope, this depends, we will discuss when we get there
- workers do not import API endpoints


## Configuration, paths, and caching

- configuration is via `shared/config.settings` and environment variables
- centralize path rules in the responsible module (e.g., `papers/` for paper paths); use shared helpers only for cross-cutting, generic paths
- caching is kept local to modules; using decorators like `lru_cache` is acceptable; keying and invalidation should be simple and tied to inputs (e.g., directory fingerprint)


## Errors, logging, and conventions

- modules raise domain exceptions; API translates to HTTP statuses
- structured logging with useful context at API and worker boundaries
- absolute imports everywhere; avoid re-exporting via `__init__.py`
- avoid circular dependencies; `internals/` is private to its module

### Exceptions structure

- define shared base exceptions in `shared/errors.py`:
  - `DomainError` (base), `NotFoundError`, `ConflictError`, `ValidationError`, `PermissionDenied`, `ExternalServiceError`, `TransientError`
- define module-specific exceptions in `name_of_module/exceptions.py` that subclass shared ones (e.g., `PapersError(DomainError)`, `PaperNotFound(PapersError, NotFoundError)`, `SlugConflict(PapersError, ConflictError)`)
- modules raise their module-specific exceptions only; they do not raise HTTP exceptions
- add a single translator in API (e.g., `api/errors.py`) that maps shared base types to HTTP codes


## Alembic and migrations

- autogeneration is preferred when practical; ensure models are importable for metadata
- data migrations are case-by-case; default to schema-only unless requirements dictate otherwise