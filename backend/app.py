from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.cases import router as cases_router
from backend.api.health import router as health_router
from backend.api.orchestration import router as orchestration_router

app = FastAPI(
    title="RalphLex",
    description="Autonomous multi-agent legal reasoning system for pre-trial dispute resolution",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api")
app.include_router(cases_router, prefix="/api")
app.include_router(orchestration_router, prefix="/api")
