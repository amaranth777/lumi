"""Lumi FastAPI 应用入口。"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from lumi.device_graph.router import router as device_graph_router
from lumi.websocket import router as ws_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(
    title="Lumi",
    description="统一智能家居设备图与控制层",
    version="0.0.0.2",
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
