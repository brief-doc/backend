FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    libfreetype6 \
    libfreetype-dev \
    libfontconfig1 \
    libfontconfig1-dev \
    pkg-config \
    curl \
    build-essential \
    && ldconfig \
    && rm -rf /var/lib/apt/lists/*

# Rust 설치 (rhwp-python 소스 컴파일용)
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

COPY requirements.txt .
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir --no-binary rhwp-python rhwp-python && \
    rm -rf /root/.cargo /root/.rustup

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]