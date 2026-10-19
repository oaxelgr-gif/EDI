# EDI - imagen mínima. Python slim + dependencias puras.
FROM python:3.12-slim

ARG WITH_WHISPER=false
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    EDI_DATA_DIR=/data EDI_CONFIG_DIR=/config

WORKDIR /app
COPY app/requirements*.txt ./
RUN pip install -r requirements.txt \
 && if [ "$WITH_WHISPER" = "true" ]; then pip install -r requirements-whisper.txt; fi

COPY app/ ./
# Corre como root dentro del contenedor para poder escribir en ./data (carpeta montada desde tu Mac).
RUN mkdir -p /data /config

EXPOSE 8000 8443
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)" || exit 1

# 8000 = tu Mac (HTTP) · 8443 = otros dispositivos de tu red (HTTPS + PIN)
CMD ["python", "-m", "edi.serve"]
