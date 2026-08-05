FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    LATTICE_HOST=0.0.0.0 \
    LATTICE_DATA_DIR=/data

WORKDIR /app
RUN useradd --create-home --uid 10001 lattice
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install .
RUN mkdir /data && chown -R lattice:lattice /data /app
USER lattice
EXPOSE 8765
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/health', timeout=3)"
CMD ["latticescholar", "--host", "0.0.0.0", "--no-browser"]
