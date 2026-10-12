FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3-tk \
        scrot \
        x11vnc \
        xauth \
        xclip \
        xvfb \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt

RUN pip install --upgrade pip \
    && pip install -r /app/requirements.txt \
    && playwright install --with-deps chromium

COPY . /app

RUN mkdir -p \
    /app/send_uploads \
    /app/data \
    /app/playwright_profile \
    /app/playwright_profiles

RUN chmod +x /app/docker-entrypoint.sh

EXPOSE 5000
# VNC: watch the headed Chromium automation windows running on the virtual display
EXPOSE 5900

CMD ["/app/docker-entrypoint.sh"]
