"""Lumi FastAPI 应用入口。"""

from __future__ import annotations

import logging

from fastapi import FastAPI

from lumi.device_graph.router import router as device_graph_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(
    title="Lumi",
    description="统一智能家居设备图与控制层",
    version="0.0.0.1",
)

app.include_router(device_graph_router)


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
