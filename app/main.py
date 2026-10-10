from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.database import init_indexes
from app.routes.admin import router as admin_router
from app.routes.analytics import router as analytics_router
from app.routes.attendance import router as attendance_router
from app.routes.employees import router as employees_router
from app.routes.system import router as system_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database indexes on startup (idempotent)
    init_indexes()
    yield


app = FastAPI(
    title="Employee Attendance & Analytics API",
    version="2.0.0",
    lifespan=lifespan
)

# Include route modules
app.include_router(system_router)
app.include_router(employees_router)
app.include_router(attendance_router)
app.include_router(analytics_router)
app.include_router(admin_router)
