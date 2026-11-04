# syntax=docker/dockerfile:1
# YouCube server image: Python 3.12, FFmpeg (DFPWM), sanjuuni, Node.js, latest yt-dlp.
# OpenCL is off by default. Build with --build-arg ENABLE_OPENCL=true to compile
# sanjuuni with OpenCL headers (still needs a GPU ICD at runtime).

FROM python:3.12-slim-trixie AS sanjuuni

ARG ENABLE_OPENCL=false
ARG SANJUUNI_COMMIT=148e68e776e08d0ac465c965371dfc21391023e0
ARG SANJUUNI_SHA512=945f343738489996ac04808cc99393cc020463284f78db4b22dc46608e6addf7bc608c11117959a6519e5c8d5aa00629d4d39ca629a4956503b1671dd93d615f

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        pkg-config \
        wget \
        zlib1g-dev \
        libpoco-dev \
        libavcodec-dev \
        libavdevice-dev \
        libavfilter-dev \
        libavformat-dev \
        libavutil-dev \
        libswresample-dev \
        libswscale-dev \
    && if [ "$ENABLE_OPENCL" = "true" ]; then \
        apt-get install -y --no-install-recommends \
            ocl-icd-opencl-dev \
            opencl-c-headers \
            opencl-clhpp-headers; \
    fi \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
RUN wget -q -O sanjuuni.tar.gz \
        "https://github.com/MCJack123/sanjuuni/archive/${SANJUUNI_COMMIT}.tar.gz" \
    && echo "${SANJUUNI_SHA512}  sanjuuni.tar.gz" | sha512sum -c - \
    && tar -xzf sanjuuni.tar.gz --strip-components=1 \
    && ./configure \
    && make -j"$(nproc)"

FROM python:3.12-slim-trixie

ARG ENABLE_OPENCL=false
ARG NODE_VERSION=22.23.4

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        ffmpeg \
        libpoco-dev \
        wget \
        xz-utils \
    && if [ "$ENABLE_OPENCL" = "true" ]; then \
        apt-get install -y --no-install-recommends ocl-icd-libopencl1; \
    fi \
    && arch="$(dpkg --print-architecture)" \
    && case "$arch" in \
        amd64) node_arch=x64 ;; \
        arm64) node_arch=arm64 ;; \
        *) echo "unsupported architecture: $arch" >&2; exit 1 ;; \
    esac \
    && wget -q -O "node-v${NODE_VERSION}-linux-${node_arch}.tar.xz" \
        "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-${node_arch}.tar.xz" \
    && wget -q -O SHASUMS256.txt \
        "https://nodejs.org/dist/v${NODE_VERSION}/SHASUMS256.txt" \
    && grep "node-v${NODE_VERSION}-linux-${node_arch}.tar.xz" SHASUMS256.txt \
        | sha256sum -c - \
    && tar -xJf "node-v${NODE_VERSION}-linux-${node_arch}.tar.xz" -C /usr/local --strip-components=1 \
    && rm "node-v${NODE_VERSION}-linux-${node_arch}.tar.xz" SHASUMS256.txt \
    && rm -rf /var/lib/apt/lists/*

COPY --from=sanjuuni /src/sanjuuni /usr/local/bin/sanjuuni

RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin youcube \
    && python -m venv /opt/venv \
    && mkdir -p /opt/server \
    && chown -R youcube:youcube /opt/venv /opt/server

COPY requirements.txt /tmp/requirements.txt
RUN /opt/venv/bin/pip install --no-cache-dir -U pip \
    && /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt \
    && /opt/venv/bin/pip install --no-cache-dir -U yt-dlp yt-dlp-ejs \
    && rm /tmp/requirements.txt \
    && chown -R youcube:youcube /opt/venv

WORKDIR /opt/server
COPY --chown=youcube:youcube youcube/ /opt/server/
COPY --chown=youcube:youcube docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
# A fresh named volume is seeded from this directory, including ownership.
# Create it as youcube before dropping root, or the mount stays root:root and
# FFmpeg cannot write /opt/server/data/<id>.dfpwm.
RUN chmod 755 /usr/local/bin/docker-entrypoint.sh /usr/local/bin/sanjuuni \
    && mkdir -p /opt/server/data \
    && chown youcube:youcube /opt/server/data

ENV HOST=0.0.0.0 \
    PORT=5000 \
    PATH="/opt/venv/bin:${PATH}" \
    XDG_CACHE_HOME=/opt/server/.cache \
    YTDLP_AUTO_UPDATE=true \
    FFMPEG_PATH=ffmpeg \
    SANJUUNI_PATH=sanjuuni

USER youcube
EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT', '5000'))"

ENTRYPOINT ["docker-entrypoint.sh"]
