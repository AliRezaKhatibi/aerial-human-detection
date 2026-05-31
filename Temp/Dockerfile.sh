cat > Dockerfile << 'EOF'
FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04

# Set working directory
WORKDIR /app

# Install Python and system dependencies
RUN apt-get update && apt-get install -y \
    python3.10 \
    python3-pip \
    ffmpeg \
    libsm6 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements/base.txt requirements/base.txt

# Install Python packages
RUN pip3 install --no-cache-dir -r requirements/base.txt

# Copy project
COPY . .

# Default command
CMD ["python3", "-c", "print('Aerial Human Detection Ready!')"]
EOF