FROM python:3.13-slim

WORKDIR /app

# Install dependencies first (layer cache)
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Source is bind-mounted in dev — no COPY needed at runtime
# Needed only for image-standalone runs:
COPY ai_finder/ ./ai_finder/
COPY backend/ ./backend/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
