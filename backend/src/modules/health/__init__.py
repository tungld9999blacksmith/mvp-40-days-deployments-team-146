"""Health module — dependency heartbeat for Redis, Qdrant and the database.

``GET /api/v1/health/dependencies``. The plain ``GET /health`` liveness probe in
``main.py`` stays dependency-free so container healthchecks never flap when a
backing service is down.
"""
