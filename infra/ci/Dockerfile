FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends software-properties-common ca-certificates \
    && add-apt-repository -y ppa:deadsnakes/ppa \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        git \
        jq \
        python3-pip \
        python3.10 \
        python3.10-dev \
        python3.10-distutils \
        python3.10-venv \
        python3.11 \
        python3.11-dev \
        python3.11-distutils \
        python3.11-venv \
        python3.12 \
        python3.12-dev \
        python3.12-venv \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt

RUN set -eux; \
    for py in python3.10 python3.11 python3.12; do \
      "$py" -m pip install --no-cache-dir --break-system-packages \
        black==26.3.1 \
        isort==5.13.2 \
        flake8==7.0.0 \
        mypy==1.8.0 \
        types-PyYAML \
        bandit==1.7.6 \
        pip-audit==2.7.3 \
        pytest==9.0.3 \
        pytest-cov==7.1.0 \
        pytest-mock==3.15.1 \
        PyYAML; \
      "$py" -m pip install --no-cache-dir --break-system-packages -r /tmp/requirements.txt; \
    done

RUN useradd --create-home --uid 1001 --shell /bin/bash ci \
    && mkdir -p /workspace \
    && chown -R ci:ci /workspace

WORKDIR /workspace
USER ci
