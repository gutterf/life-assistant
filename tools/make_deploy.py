"""同步部署目录：backend 代码 + desktop 静态 + 云端 .env（官方直连）。

用法：python tools/make_deploy.py
产物：life-assistant/deploy/ （sites 发布的目录）
"""
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
DESKTOP = ROOT / "desktop"
DEPLOY = ROOT / "deploy"

SKIP_DESKTOP = {"_probe.html", "_cssonly.html"}


def sync() -> None:
    if DEPLOY.exists():
        shutil.rmtree(DEPLOY)
    (DEPLOY / "app").mkdir(parents=True)

    # 后端代码（排除缓存）
    for item in (BACKEND / "app").iterdir():
        if item.name == "__pycache__":
            continue
        dst = DEPLOY / "app" / item.name
        if item.is_dir():
            shutil.copytree(item, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            shutil.copy2(item, dst)

    shutil.copy2(BACKEND / "requirements.txt", DEPLOY / "requirements.txt")
    shutil.copy2(BACKEND / "serve.py", DEPLOY / "serve.py")

    # 桌面版静态
    shutil.copytree(
        DESKTOP,
        DEPLOY / "desktop",
        ignore=shutil.ignore_patterns("*.png", "*.log"),
    )
    for skip in SKIP_DESKTOP:
        p = DEPLOY / "desktop" / skip
        if p.exists():
            p.unlink()

    # 云端 .env：官方直连（云端没有本机 relay）
    env_src = (BACKEND / ".env").read_text(encoding="utf-8-sig")
    env_cloud = env_src.replace("http://127.0.0.1:17812", "https://api.deepseek.com")
    (DEPLOY / ".env").write_text(env_cloud, encoding="utf-8")

    print("deploy dir ready:", DEPLOY)
    print("desktop files:", len(list((DEPLOY / "desktop").rglob("*"))))
    print("env base_url:", [l for l in env_cloud.splitlines() if "BASE_URL" in l])


if __name__ == "__main__":
    sync()
