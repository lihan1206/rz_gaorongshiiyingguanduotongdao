import logging
import atexit

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import alarms, auth, channels, dashboard, health, samples, data
from app.core.config import settings
from app.core.logging_config import setup_logging
from app.db.base import Base
from app.db.seed import run_seed
from app.db.session import SessionLocal, engine
from app.services.collector import init_collector, load_active_channels
from app.services.config_watcher import start_config_watcher, stop_config_watcher
from app.services.config_manager import get_config_manager

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
app.include_router(data.router, prefix="/api")


@app.on_event("startup")
def startup_event() -> None:
    logger.info("准备初始化数据库表结构")
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        run_seed(db)
        
        config_manager = get_config_manager()
        sampling_interval = config_manager.sampling_interval_ms
        
        collector = init_collector(SessionLocal, sampling_interval)
        load_active_channels(db, collector, use_mock=True)
        collector.start()
        logger.info("数据采集服务已启动")
        
        start_config_watcher()
        logger.info("配置热更新监听已启动")
        
    finally:
        db.close()
    logger.info("系统启动完成")


@app.on_event("shutdown")
def shutdown_event() -> None:
    logger.info("正在关闭系统...")
    
    stop_config_watcher()
    logger.info("配置监听已停止")
    
    from app.services.collector import get_collector
    collector = get_collector()
    if collector:
        collector.stop()
        logger.info("数据采集服务已停止")
    
    logger.info("系统已关闭")


@app.get("/")
def root():
    return {"message": "高融石英管多通道液位同步检测系统后端服务已启动"}
