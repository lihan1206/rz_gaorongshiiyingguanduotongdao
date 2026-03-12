import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import alarms, auth, channels, dashboard, health, samples
from app.core.config import settings
from app.core.logging_config import setup_logging
from app.db.base import Base
from app.db.seed import run_seed
from app.db.session import SessionLocal, engine

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name, version="1.0.0")

origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
if not origins:
    origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(channels.router, prefix="/api")
app.include_router(samples.router, prefix="/api")
app.include_router(alarms.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")


@app.on_event("startup")
def startup_event() -> None:
    logger.info("准备初始化数据库表结构")
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        run_seed(db)
    finally:
        db.close()
    logger.info("系统启动完成")


@app.get("/")
def root():
    return {"message": "高融石英管多通道液位同步检测系统后端服务已启动"}
