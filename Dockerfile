FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    WINEPREFIX=/opt/wineprefix \
    WINEARCH=win64 \
    DISPLAY=:99 \
    PYTHONUNBUFFERED=1 \
    WINEDLLOVERRIDES="mscoree,mshtml="

# Use current WineHQ stable instead of Ubuntu 22.04's older Wine 6 package.
RUN dpkg --add-architecture i386 && apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl wget cabextract gnupg2 xvfb xauth x11-utils fonts-liberation \
    python3 python3-pip && \
    mkdir -p /etc/apt/keyrings && \
    wget -qO- https://dl.winehq.org/wine-builds/winehq.key | gpg --dearmor -o /etc/apt/keyrings/winehq-archive.key && \
    wget -qO /etc/apt/sources.list.d/winehq-jammy.sources https://dl.winehq.org/wine-builds/ubuntu/dists/jammy/winehq-jammy.sources && \
    apt-get update && apt-get install -y --install-recommends winehq-stable && \
    rm -rf /var/lib/apt/lists/*

# Keep one virtual X server alive for the complete Wine prefix initialization and installers.
RUN mkdir -p /opt/installers && \
    wget -q https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe -O /opt/installers/python.exe && \
    Xvfb :99 -screen 0 1280x800x24 -ac +extension GLX +render -noreset >/tmp/xvfb.log 2>&1 & \
    sleep 2 && \
    wineboot --init && \
    sleep 20 && \
    wine cmd /c ver && \
    wine /opt/installers/python.exe /quiet InstallAllUsers=1 TargetDir=C:\\Python311 Include_test=0 PrependPath=1 && \
    wine C:\\Python311\\python.exe -m pip install --upgrade pip MetaTrader5 && \
    rm -f /opt/installers/python.exe && \
    wget -q https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe -O /opt/installers/mt5setup.exe && \
    wine /opt/installers/mt5setup.exe /auto && \
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
