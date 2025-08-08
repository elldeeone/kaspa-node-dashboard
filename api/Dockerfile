FROM python:3.12-slim

WORKDIR /app

# Install required Python packages
RUN pip install fastapi uvicorn aiohttp

# Copy the API server code
COPY *.py .

# Expose port
EXPOSE 8000

# Start the server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"] 