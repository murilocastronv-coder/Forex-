FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    WINEPREFIX=/opt/wineprefix \
    WINEARCH=win64 \
    PYTHONUNBUFFERED=1

RUN dpkg --add-architecture i386 && apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl wget cabextract xvfb xauth x11-utils wine wine64 wine32 fonts-liberation \
    python3 python3-pip && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /opt/installers && \
    wget -q https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe -O /opt/installers/python.exe && \
    xvfb-run -a sh -c 'wineboot --init; sleep 8; wine /opt/installers/python.exe /quiet InstallAllUsers=1 TargetDir=C:\\Python311 Include_test=0 PrependPath=1 && wine C:\\Python311\\python.exe -m pip install --upgrade pip MetaTrader5' && \
    rm -f /opt/installers/python.exe

RUN wget -q https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe -O /opt/installers/mt5setup.exe && \
    xvfb-run -a sh -c 'wine /opt/installers/mt5setup.exe /auto; wineboot --shutdown' && \
    rm -f /opt/installers/mt5setup.exe

WORKDIR /app
COPY requirements-docker.txt ./requirements-docker.txt
RUN pip3 install --no-cache-dir -r requirements-docker.txt

COPY mt5_probe.py ./mt5_probe.py
COPY poc_app.py ./poc_app.py
COPY entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

EXPOSE 10000
CMD ["./entrypoint.sh"]
