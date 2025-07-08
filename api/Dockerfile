FROM python:3.12-slim

WORKDIR /app

# Install required packages including Docker CLI
RUN apt-get update && \
    apt-get install -y docker.io && \
    rm -rf /var/lib/apt/lists/* && \
    pip install fastapi uvicorn aiohttp

# Copy the API server code
COPY *.py .

# Expose port
EXPOSE 8000

# Start the server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"] 