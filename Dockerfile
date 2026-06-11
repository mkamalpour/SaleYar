FROM python:3.10-slim

WORKDIR /app

# Install system dependencies needed for lightgbm and numpy
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Install Python packages
RUN pip install --no-cache-dir -r requirements.txt

# Copy entire project
COPY .. .

# Expose Gradio port
EXPOSE 7860

# Run the app
CMD ["python", "ui/developer.py"]