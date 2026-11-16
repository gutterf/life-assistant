"""云端/本地统一启动入口：监听平台注入的 PORT 环境变量。"""
import os

import uvicorn

from app.main import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
