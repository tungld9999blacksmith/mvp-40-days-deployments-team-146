"""
Vehicle example module.

Exports the FastAPI router so it can be mounted in main.py via:

    from src.modules.examples import vehicle_router
    app.include_router(vehicle_router, prefix="/api/v1")
"""

from src.modules.examples.route import vehicle_router

__all__ = ["vehicle_router"]
