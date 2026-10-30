FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    WINEPREFIX=/opt/wineprefix \
    WINEARCH=win64 \
    DISPLAY=:99 \
    PYTHONUNBUFFERED=1

RUN dpkg --add-architecture i386 && apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl wget cabextract xvfb xauth wine64 wine32 fonts-liberation \
    python3 python3-pip && rm -rf /var/lib/apt/lists/*

# Install Windows Python inside the same Wine prefix used by the MT5 terminal.
RUN mkdir -p /opt/installers && \
    wget -q https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe -O /opt/installers/python.exe && \
    wineboot --init && \
    xvfb-run -a wine /opt/installers/python.exe /quiet InstallAllUsers=1 PrependPath=1 Include_test=0 && \
    rm -f /opt/installers/python.exe

# MetaTrader 5 terminal installer from MetaQuotes. The XM server is selected at login.
RUN wget -q https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe -O /opt/installers/mt5setup.exe && \
    xvfb-run -a wine /opt/installers/mt5setup.exe /auto && \
    rm -f /opt/installers/mt5setup.exe && \
    wineboot --shutdown

WORKDIR /app
COPY requirements-docker.txt ./requirements-docker.txt
RUN pip3 install --no-cache-dir -r requirements-docker.txt

COPY mt5_probe.py ./mt5_probe.py
COPY poc_app.py ./poc_app.py
COPY entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

EXPOSE 10000
CMD ["./entrypoint.sh"]
