FROM python:3.13-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Set working directory
WORKDIR /app

# Copy dependency files first for better caching
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen

# Copy application code
COPY polly/ ./polly/
COPY templates/ ./templates/
COPY *.py ./

# Create non-root user
RUN adduser --disabled-password --gecos "" --uid 1000 polly

# Create entrypoint script and make it executable
COPY docker-entrypoint.sh ./
RUN chmod +x docker-entrypoint.sh

# Change ownership of the app directory to polly user
RUN chown -R polly:polly /app

# Switch to non-root user
USER polly

# Expose port
EXPOSE 8000

# Run the application
CMD ["./docker-entrypoint.sh"]
