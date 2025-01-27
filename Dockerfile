FROM python:3.9-bullseye

COPY requirements.txt .
COPY requirements-selenium.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ./bank-scraper /bank-scraper
COPY ./resources /bank-scraper/resources

ARG SELENIUM_SUPPORT=true

RUN bash -c 'if [ "$SELENIUM_SUPPORT" = "true" ]; then \
    # Install selenium Python dependencies
    pip install --no-cache-dir -r requirements-selenium.txt && \
    # Firefox headless related & ffmpeg
    apt update && \
    apt install firefox-esr wget bzip2 libxtst6 libgtk-3-0 libx11-xcb-dev libdbus-glib-1-2 libxt6 libpci-dev openssl ffmpeg flac curl -y && \
    # Geckodriver into /usr/local/bin/
    wget -qO /tmp/geckodriver.tar.gz \
    "https://github.com/mozilla/geckodriver/releases/download/v0.35.0/geckodriver-v0.35.0-linux-aarch64.tar.gz" && \
    tar -xzf /tmp/geckodriver.tar.gz -C /usr/local/bin/ && \
    rm /tmp/geckodriver.tar.gz && \
    apt clean && rm -rf /var/lib/apt/lists/*; \
fi'

ENV GECKODRIVER_PATH=/usr/local/bin/geckodriver

WORKDIR /bank-scraper

CMD ["python", "app.py"]