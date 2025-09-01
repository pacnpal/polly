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

# Install dependencies
RUN uv sync --frozen

# Create uploads directory
RUN mkdir -p static/uploads

# Expose port
EXPOSE 8000

# Run the application
CMD ["uv", "run", "python", "-m", "polly.main"]
