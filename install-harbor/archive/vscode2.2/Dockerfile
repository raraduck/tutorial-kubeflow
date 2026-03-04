FROM nvidia/cuda:12.8.1-cudnn-devel-ubuntu24.04

# ── 환경 변수 ────────────────────────────────────────────────────────────────
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV LD_LIBRARY_PATH=/usr/local/nvidia/lib:/usr/local/nvidia/lib64:/usr/local/cuda/lib64

# nnU-Net 환경 변수
ENV nnUNet_raw="/fedpod/nnUNet_raw"
ENV nnUNet_preprocessed="/fedpod/nnUNet_preprocessed"
ENV nnUNet_results="/fedpod/nnUNet_results"

# ── 1. 시스템 패키지 ─────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.12 \
        python3-pip \
        python3.12-dev \
        python3.12-venv \
        libgl1 \
        libglx-mesa0 \
        libglib2.0-0 \
        git \
        build-essential \
        curl \
        ca-certificates \
        gnupg \
        sudo \
        net-tools \
        wget \
        tini \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.12 /usr/bin/python \
    && ln -sf /usr/bin/python3.12 /usr/bin/python3

# ── 2. pip 전역 설정 (break-system-packages 영구 적용) ──────────────────────
RUN mkdir -p /etc/pip \
    && echo "[global]" > /etc/pip.conf \
    && echo "break-system-packages = true" >> /etc/pip.conf

# ── 3. Node.js 20 설치 ──────────────────────────────────────────────────────
RUN mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
       | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" \
       > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ── 4. code-server 설치 ─────────────────────────────────────────────────────
ARG CODE_SERVER_VERSION=4.92.2
RUN curl -fsSL https://code-server.dev/install.sh \
    | sh -s -- --version=${CODE_SERVER_VERSION} \
    && rm -rf /root/.cache

# ── 5. Claude Code 전역 설치 ────────────────────────────────────────────────
RUN npm install -g @anthropic-ai/claude-code

# ── 6. Miniconda 설치 ───────────────────────────────────────────────────────
ARG MINICONDA_VERSION=latest
RUN curl -fsSL https://repo.anaconda.com/miniconda/Miniconda3-${MINICONDA_VERSION}-Linux-x86_64.sh \
    -o /tmp/miniconda.sh \
    && bash /tmp/miniconda.sh -b -p /opt/conda \
    && rm /tmp/miniconda.sh \
    && /opt/conda/bin/conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main \
    && /opt/conda/bin/conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r \
    && /opt/conda/bin/conda install -y python=3.12 \
    && /opt/conda/bin/conda clean -afy

ENV PATH="/opt/conda/bin:${PATH}"

# conda 기본 채널 설정 및 base 환경 활성화
RUN conda init bash \
    && conda config --set auto_activate_base false

# ── 7. PyTorch 2.7.1 + CUDA 12.8 ────────────────────────────────────────────
RUN pip3 install --no-cache-dir --break-system-packages \
    torch==2.7.1 \
    torchvision \
    --index-url https://download.pytorch.org/whl/cu128

# ── 8. 도메인 라이브러리 ─────────────────────────────────────────────────────
RUN pip3 install --no-cache-dir --break-system-packages numpy==1.26.4

RUN pip3 install --no-cache-dir --break-system-packages \
    pandas==2.2.0 \
    scipy==1.14.1 \
    pyarrow==20.0.0 \
    joblib==1.3.2 \
    nnunetv2==2.5.1 \
    monai \
    SimpleITK==2.4.0 \
    nibabel==5.2.1 \
    nilearn==0.10.4 \
    nipype==1.8.6 \
    medpy \
    scikit-image==0.25.0 \
    fastapi==0.116.1 \
    fastapi-utils==0.6.0 \
    uvicorn==0.29.0 \
    httpx==0.28.1 \
    pydantic==2.10.4 \
    pydantic-settings==2.7.1 \
    matplotlib==3.10.0 \
    tqdm==4.66.4 \
    pillow \
    natsort \
    tensorboard \
    pytorch_lightning \
    python-dotenv==1.0.1 \
    requests==2.32.4 \
    urllib3==2.5.0 \
    six==1.17.0 \
    cryptography==46.0.3 \
    concurrent-log-handler==0.9.25 \
    notion-client==2.4.0 \
    openpyxl==3.1.5 \
    typing-inspect==0.9.0 \
    setuptools==78.1.1

# ── 9. Kubeflow 호환 jovyan 사용자 생성 ─────────────────────────────────────
# UID 1000이 이미 존재하면 해당 사용자를 jovyan으로 rename, 없으면 새로 생성
RUN if getent passwd 1000 > /dev/null 2>&1; then \
        usermod -l jovyan -d /home/jovyan -m $(getent passwd 1000 | cut -d: -f1); \
    else \
        useradd -m -s /bin/bash -u 1000 jovyan; \
    fi \
    && echo "jovyan ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

# ── 10. jovyan 환경 설정 ─────────────────────────────────────────────────────
USER jovyan
WORKDIR /home/jovyan

RUN mkdir -p /home/jovyan/.claude \
    && echo '{"autoUpdates":false}' > /home/jovyan/.claude/settings.json \
    && mkdir -p /home/jovyan/.local/share/code-server/extensions \
    # conda 초기화 (jovyan 사용자)
    && /opt/conda/bin/conda init bash

ENV PATH="/usr/bin:/usr/local/bin:/opt/conda/bin:${PATH}"
ENV NB_PREFIX="/"

ARG IMAGE_VERSION=v2.2.0
LABEL maintainer="neuropean" \
      version="${IMAGE_VERSION}" \
      type="vscode" \
      base="nvidia/cuda:12.8.0-cudnn-devel-ubuntu24.04" \
      python.version="3.12" \
      cuda.version="12.8" \
      node.version="20" \
      code-server.version="${CODE_SERVER_VERSION}"

EXPOSE 8888

ENTRYPOINT ["tini", "--"]
CMD ["code-server", \
     "--bind-addr", "0.0.0.0:8888", \
     "--auth", "none", \
     "/home/jovyan"]