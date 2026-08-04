FROM nvidia/cuda:12.8.1-cudnn-runtime-ubuntu22.04

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-dev python3-pip build-essential libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /worker
COPY requirements.txt .
RUN python3 -m pip install -r requirements.txt
COPY . .

CMD ["python3", "handler.py"]
