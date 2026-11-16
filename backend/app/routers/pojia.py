# -*- coding: utf-8 -*-
"""破甲中心路由：注入 POJIA 执行层 + 满血无审查开关。"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from ..services import filters, pojia

router = APIRouter(prefix="/api/v1/pojia", tags=["pojia"])


class InstallBody(BaseModel):
 seats: Optional[list[str]] = None
 topic: Optional[str] = "未指定主题"
 nofilter: bool = True


@router.get("/status")
async def status() -> dict:
 verify = pojia.verify_all()
 marked = [r for r in verify if r.get("marked")]
 return {
  "activation": pojia.ACTIVATION,
  "nofilter_global": filters.is_global_nofilter(),
  "seats": pojia.detect(),
  "marked": [r["seat"] for r in marked],
  "verify": verify,
 }


@router.post("/install")
async def install(body: InstallBody) -> dict:
 seats = body.seats or ["workbuddy"]
 log_lines: list[str] = []
 done = pojia.install_all(body.topic, seats=seats, log=lambda m: log_lines.append(str(m)))
 if body.nofilter:
  filters.set_global_nofilter(True)
 verify = pojia.verify_all()
 marked = [r for r in verify if r.get("marked")]
 return {
  "ok": True,
  "done": done,
  "log": log_lines,
  "nofilter_global": filters.is_global_nofilter(),
  "marked": [r["seat"] for r in marked],
  "verify": verify,
 }


@router.post("/uninstall")
async def uninstall() -> dict:
 log_lines: list[str] = []
 done = pojia.uninstall_all(log=lambda m: log_lines.append(str(m)))
 filters.set_global_nofilter(False)
 verify = pojia.verify_all()
 marked = [r for r in verify if r.get("marked")]
 return {
  "ok": True,
  "done": done,
  "log": log_lines,
  "nofilter_global": filters.is_global_nofilter(),
  "marked": [r["seat"] for r in marked],
  "verify": verify,
 }
