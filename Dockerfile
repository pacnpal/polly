FROM python:3.11-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Set working directory
WORKDIR /app

# Copy project files
COPY pyproject.toml uv.lock ./
COPY polly/ ./polly/
COPY templates/ ./templates/
COPY static/ ./static/
COPY migrate_database.py ./
COPY .env ./

# Ensure all template directories exist
RUN mkdir -p templates/htmx

# Install dependencies
RUN uv sync --frozen

# Create necessary directories
RUN mkdir -p static/uploads logs data

# Expose port
EXPOSE 8000

# Create entrypoint script
COPY docker-entrypoint.sh ./
RUN chmod +x docker-entrypoint.sh

# Run the application with migration
CMD ["./docker-entrypoint.sh"]
