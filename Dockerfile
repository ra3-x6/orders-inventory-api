FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY pyproject.toml ./
COPY src/ ./src/
RUN python -m pip install --no-cache-dir . && useradd --system --uid 10001 appuser
USER appuser
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "orders_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
