from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import OUTPUTS_DIR
from app.routers.generate import router as generate_router
from app.routers.health import router as health_router

app = FastAPI(title="Short Video MVP")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api")
app.include_router(generate_router, prefix="/api")

app.mount("/outputs", StaticFiles(directory=OUTPUTS_DIR), name="outputs")
