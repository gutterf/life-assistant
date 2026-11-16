"""卫星地图 API：附近全类型 POI + 卫星回复开关。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..deps import get_amap
from ..services import satellite

router = APIRouter(prefix="/api/v1/satellite", tags=["satellite"])


class ToggleReq(BaseModel):
    enabled: bool


@router.get("/state")
def satellite_state() -> dict:
    return {"enabled": satellite.is_satellite_reply()}


@router.post("/toggle")
def satellite_toggle(req: ToggleReq) -> dict:
    return {"enabled": satellite.set_satellite_reply(req.enabled)}


@router.get("/nearby")
async def nearby(
    lat: float,
    lng: float,
    radius: int = 3000,
    client=Depends(get_amap),
) -> dict:
    """软件内卫星地图数据：以 (lng, lat) 为中心抓周边全类型 POI。"""
    return await satellite.nearby_pois(client, lat, lng, radius)
