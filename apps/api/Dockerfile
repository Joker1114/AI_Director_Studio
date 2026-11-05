FROM python:3.12-slim
WORKDIR /opt/director
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY pyproject.toml .
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini .
RUN pip install --no-cache-dir .
RUN useradd --create-home director && mkdir -p /opt/director/data && chown director:director /opt/director/data
USER director
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1"]
