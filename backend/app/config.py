"""集中配置：所有密钥只从环境变量 / .env 读取，代码与仓库里不出现明文 key。"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- DeepSeek ----
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    # 意图判定与常识问答使用的模型（纯文本）
    deepseek_model: str = "deepseek-chat"
    # 需要多步推理时使用的模型（可选，同 key 同 endpoint）
    deepseek_reasoner_model: str = "deepseek-reasoner"
    deepseek_timeout_s: float = 30.0
    deepseek_max_retries: int = 2

    # ---- 高德地图 ----
    # 必须是「Web 服务」类型的 key，不是 iOS 平台 key
    amap_key: str = ""
    amap_base_url: str = "https://restapi.amap.com"
    amap_timeout_s: float = 12.0
    # 周边搜索半径，需求为 15km；高德 place/around 上限 50000m
    default_radius_m: int = 15000
    max_radius_m: int = 50000

    # ---- OCR ----
    # auto: 客户端已给 text 则直接用，否则退回本地 rapidocr
    # ios: 只用客户端 Vision 结果 | rapidocr: 只用服务端本地 OCR
    # baidu: 百度云 OCR（需下方 key） | none: 关闭
    ocr_provider: str = "auto"
    baidu_ocr_api_key: str = ""
    baidu_ocr_secret_key: str = ""

    # ---- 服务 ----
    max_upload_mb: int = 12
    cors_origins: str = "*"
    log_level: str = "INFO"

    @property
    def cors_origin_list(self) -> list[str]:
        raw = (self.cors_origins or "").strip()
        if not raw or raw == "*":
            return ["*"]
        return [item.strip() for item in raw.split(",") if item.strip()]

    def missing_required(self) -> list[str]:
        """返回缺失的必需配置项，供 /health 与启动自检使用。"""
        missing: list[str] = []
        if not self.deepseek_api_key:
            missing.append("DEEPSEEK_API_KEY")
        if not self.amap_key:
            missing.append("AMAP_KEY")
        return missing


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
