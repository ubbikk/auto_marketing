FROM python:3.11-slim

WORKDIR /app

# Copy project files
COPY pyproject.toml ./
COPY src/ ./src/
COPY data/ ./data/
COPY docs/ ./docs/
COPY static/ ./static/
COPY prompts/ ./prompts/

# Install dependencies
RUN pip install --no-cache-dir -e .

# Create output directories
RUN mkdir -p /app/data/carousels /app/output/runs

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["uvicorn", "src.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
