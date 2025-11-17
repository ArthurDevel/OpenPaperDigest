import logging
import os
import sys
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from shared.config import settings
import uvicorn

from api.endpoints import paper_processing_endpoints
from api.endpoints import admin as admin_endpoints
from api.endpoints import search as search_endpoints
from api.endpoints import user_endpoints

# --- Start Centralized Logging Configuration ---
# Remove any existing handlers
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout  # Explicitly direct logs to stdout
)
logger = logging.getLogger(__name__)
logger.info("Logging configured.")
# --- End Centralized Logging Configuration ---

# Add project root to the Python path to allow for absolute imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

app = FastAPI()

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)


app.include_router(paper_processing_endpoints.router, tags=["paper-processing"])
app.include_router(admin_endpoints.router, tags=["admin"])
app.include_router(search_endpoints.router, tags=["search"])
app.include_router(user_endpoints.router, tags=["users"])


@app.on_event("startup")
async def _log_registered_routes() -> None:
    try:
        logger.info("Registered routes (in order):")
        for idx, route in enumerate(app.router.routes):
            try:
                methods = sorted(list(getattr(route, "methods", []) or []))
                path = getattr(route, "path", str(route))
                name = getattr(route, "name", "")
                logger.info("%03d: %s %s name=%s", idx, ",".join(methods), path, name)
            except Exception:
                logger.exception("Failed to log route entry")
    except Exception:
        logger.exception("Failed to enumerate routes")


@app.middleware("http")
async def _log_request_and_match(request: Request, call_next):
    try:
        method = request.method
        path = request.url.path
        route = request.scope.get("route")
        route_path = getattr(route, "path", None)
        endpoint = request.scope.get("endpoint")
        endpoint_name = getattr(endpoint, "__name__", None)
        logger.info("REQ %s %s -> matched route=%s endpoint=%s", method, path, route_path, endpoint_name)
    except Exception:
        logger.exception("Logging request before call_next failed")
    response = await call_next(request)
    try:
        logger.info("RESP %s %s status=%s", request.method, request.url.path, response.status_code)
    except Exception:
        logger.exception("Logging response failed")
    return response


@app.get("/")
def read_root():
    return {"message": "Welcome to the API"}


@app.get("/health")
def health_check():
    """
    Health check endpoint for Railway deployment.
    Returns 200 OK if the backend service is running.
    The frontend proxy automatically handles /api/health -> /health.
    """
    return {"status": "healthy"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=settings.CONTAINERPORT_API)