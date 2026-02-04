FROM python:3.11-slim

WORKDIR /app

# Install Playwright/Chromium dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libdbus-1-3 libxkbcommon0 libatspi2.0-0 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2 \
    libpango-1.0-0 libcairo2 fonts-liberation fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml ./
COPY src/ ./src/
COPY data/ ./data/
COPY docs/ ./docs/
COPY static/ ./static/

# Install dependencies
RUN pip install --no-cache-dir -e .

# Install Playwright browser
RUN playwright install chromium && playwright install-deps chromium

# Create output directories
RUN mkdir -p /app/data/carousels /app/output/runs

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["uvicorn", "src.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
