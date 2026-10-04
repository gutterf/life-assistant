FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

# 先装依赖，利用镜像层缓存
COPY requirements.txt .
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
 && pip install --no-cache-dir -r requirements.txt \
 && rm -rf /var/lib/apt/lists/*

COPY app ./app

# 密钥一律运行时注入，镜像里不留任何 .env
ENV DEEPSEEK_API_KEY="" AMAP_KEY="" OCR_PROVIDER=auto

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=4).status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
