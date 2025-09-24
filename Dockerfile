FROM ghcr.io/astral-sh/uv:python3.13-alpine

# Set working directory in container
WORKDIR /app

# Copy pyproject.toml and uv.lock for dependency installation
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen

# Copy source code
COPY src/ ./src/

# Expose port 5000
EXPOSE 5000

# Set environment variables
ENV FLASK_APP=src/app.py
ENV FLASK_ENV=production
ENV PYTHONPATH=/app

# Run the application
CMD ["uv", "run", "python", "src/app.py"]
