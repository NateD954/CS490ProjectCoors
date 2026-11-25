FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
# uvicorn is installed again in case requirements.txt only lists fastapi.
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir uvicorn

COPY app ./app
COPY services ./services

# Run as a normal user instead of root.
RUN useradd --create-home appuser
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
