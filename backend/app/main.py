"""FastAPI 应用入口。"""
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import init_db, SessionLocal
from .routers.api import router as api_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sd-epm")

app = FastAPI(title="山东电价预测与储能套利系统", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(api_router)


@app.on_event("startup")
def startup():
    init_db()
    db = SessionLocal()
    try:
        from .models import PriceRecord
        if db.query(PriceRecord).count() == 0:
            logger.info("首次启动，正在初始化仿真数据（价格/天气/节假日）……")
            from .services.sync import sync_all
            result = sync_all(db)
            logger.info("初始化完成：%s", result)
    finally:
        db.close()


# 若存在前端构建产物（frontend/dist），由后端直接托管，实现单进程运行
import os
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

_DIST = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "frontend", "dist")
_DIST = os.path.normpath(_DIST)
if os.path.isdir(_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(_DIST, "assets")), name="assets")

    @app.get("/")
    def index():
        return FileResponse(os.path.join(_DIST, "index.html"))

    @app.get("/{path:path}")
    def spa(path: str):  # Vue Router history 模式回退
        if path.startswith("api/"):
            return {"detail": "Not Found"}
        return FileResponse(os.path.join(_DIST, "index.html"))
else:
    @app.get("/")
    def root():
        return {"name": "山东电价预测与储能套利系统", "docs": "/docs"}
