"""Lumi FastAPI 应用入口。"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from lumi.device_graph.router import router as device_graph_router
from lumi.scenes.router import router as scenes_router
from lumi.websocket import router as ws_router, manager as ws_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期——启动时订阅 HA 事件。"""
    # 延迟导入避免循环
    from lumi.deps import get_ha_client
    from lumi.ha.events import start_ha_event_listener

    ha_client = get_ha_client()
    if ha_client:
        task = asyncio.create_task(
            start_ha_event_listener(ha_client, ws_manager),
            name="ha_event_listener",
        )
        logger.info("HA 事件监听器已启动")
    else:
        task = None
        logger.info("HA 未启用，跳过事件监听")

    yield  # 应用运行期间

    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        logger.info("HA 事件监听器已停止")


app = FastAPI(
    title="Lumi",
    description="统一智能家居设备图与控制层",
    version="0.0.0.3",
    lifespan=lifespan,
)

# CORS 配置（前端开发/跨域）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件目录（前端 build 产物）
# 访问 /ui/ 自动 serve index.html，支持 SPA
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/ui", StaticFiles(directory=str(static_dir), html=True), name="static")

# API 路由
app.include_router(device_graph_router)
app.include_router(scenes_router)
app.include_router(ws_router)


@app.get("/health")
async def health() -> dict[str, str]:
    """健康检查端点。"""
    return {"status": "ok"}


def start_server() -> None:
    """CLI 入口（lumi 命令）。"""
    import uvicorn
    from lumi.config import get_config

    config = get_config()
    uvicorn.run(
        "lumi.main:app",
        host=config.server.host,
        port=config.server.port,
        reload=False,
    )


if __name__ == "__main__":
    start_server()
