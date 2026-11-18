# syntax=docker/dockerfile:1.7
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV MPLBACKEND=Agg
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PIP_DEFAULT_TIMEOUT=120
ENV PIP_RETRIES=10

RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    libglib2.0-0 \
    libgl1 \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/api.txt requirements/api.txt
COPY requirements/base.txt requirements/base.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements/api.txt

COPY requirements/pipeline.txt requirements/pipeline.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements/pipeline.txt

COPY app ./app
COPY prediction ./prediction

ENTRYPOINT ["python", "-m", "prediction.run_forecast"]
CMD ["--help"]
