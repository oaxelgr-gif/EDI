# EDI - imagen mínima (~180 MB). Python slim + dependencias puras.
FROM python:3.12-slim

ARG WITH_WHISPER=false
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    EDI_DATA_DIR=/data EDI_CONFIG_DIR=/config

WORKDIR /app
COPY app/requirements*.txt ./
RUN pip install -r requirements.txt \
 && if [ "$WITH_WHISPER" = "true" ]; then pip install -r requirements-whisper.txt; fi

COPY app/ ./
# Corre como root dentro del contenedor a propósito: así puede escribir en ./data
# (carpeta montada desde tu Mac) sin pelear con permisos. Sólo escucha en 127.0.0.1.
RUN mkdir -p /data /config

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)" || exit 1

CMD ["uvicorn", "edi.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "warning"]
