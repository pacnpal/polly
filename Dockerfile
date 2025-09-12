FROM python:3.13-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Set working directory
WORKDIR /app

# Copy project files
COPY pyproject.toml uv.lock ./
COPY polly/ ./polly/
COPY templates/ ./templates/
COPY *.py ./

# Ensure all template directories exist
RUN mkdir -p templates/htmx

# Install dependencies
RUN uv sync --frozen

# Create necessary directories
RUN mkdir -p static/uploads logs data

# Expose port
EXPOSE 8000

# User change
RUN adduser --disabled-password --gecos "" polly
RUN chown -R polly:polly /app/logs /app/data /app
RUN chmod -R 755 /app/logs /app/data /app
USER polly

# Create entrypoint script
COPY docker-entrypoint.sh ./
USER root
RUN chmod +x docker-entrypoint.sh
USER polly
# Run the application with migration
CMD ["./docker-entrypoint.sh"]
