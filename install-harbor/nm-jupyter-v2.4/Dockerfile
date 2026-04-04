FROM nvidia/cuda:12.1.1-cudnn8-devel-ubuntu22.04

# ── 환경 변수 ────────────────────────────────────────────────────────────────
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV LD_LIBRARY_PATH=/usr/local/nvidia/lib:/usr/local/nvidia/lib64:/usr/local/cuda/lib64

# ── 1. 시스템 패키지 ─────────────────────────────────────────────────────────
# Ubuntu 22.04 기본 저장소에는 python3.10만 포함되므로 deadsnakes PPA 추가
RUN apt-get update && apt-get install -y --no-install-recommends \
        software-properties-common \
    && add-apt-repository -y ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y --no-install-recommends \
        python3.12 \
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
        vim \
        htop \
        # Kubeflow notebook server 요구사항
        tini \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.12 /usr/bin/python \
    && ln -sf /usr/bin/python3.12 /usr/bin/python3 \
    # pip는 deadsnakes PPA에 python3.12용 pip가 없으므로 get-pip.py 사용
    && curl -sS https://bootstrap.pypa.io/get-pip.py | python3.12

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

# ── 6. Miniconda 설치 (버전 고정: conda 24.7.1 포함) ────────────────────────
# py312_24.7.1-0 빌드에 conda 24.7.1 포함
ARG MINICONDA_VERSION=py312_24.7.1-0
RUN curl -fsSL https://repo.anaconda.com/miniconda/Miniconda3-${MINICONDA_VERSION}-Linux-x86_64.sh \
    -o /tmp/miniconda.sh \
    && bash /tmp/miniconda.sh -b -p /opt/conda \
    && rm /tmp/miniconda.sh \
    && /opt/conda/bin/conda config --set channel_priority flexible \
    && /opt/conda/bin/conda install -y --override-channels \
       -c https://repo.anaconda.com/pkgs/main \
       -c https://repo.anaconda.com/pkgs/r \
       python=3.12.9 \
    && /opt/conda/bin/conda clean -afy

# conda auto_activate_base 비활성화
RUN /opt/conda/bin/conda config --set auto_activate_base false

# conda 명령만 전역에서 접근 가능하도록 심볼릭 링크
RUN ln -s /opt/conda/bin/conda /usr/local/bin/conda

# ── 7. PyTorch 2.5.1 + CUDA 12.1 ────────────────────────────────────────────
RUN pip3 install --no-cache-dir --break-system-packages \
    --timeout=300 \
    torch==2.5.1+cu121 \
    torchvision==0.20.1+cu121 \
    --index-url https://download.pytorch.org/whl/cu121

# ── 8. 도메인 라이브러리 ─────────────────────────────────────────────────────
# numpy 2.x (torch 2.5.1은 numpy 2.x 지원)
RUN pip3 install --no-cache-dir --break-system-packages numpy==2.2.6

# 의료 영상 / 데이터 라이브러리
RUN pip3 install --no-cache-dir --break-system-packages \
    scipy==1.14.1 \
    matplotlib==3.10.6 \
    nibabel==5.4.0 \
    h5py==3.14.0 \
    pandas==2.2.0 \
    pyarrow==20.0.0 \
    joblib==1.3.2 \
    scikit-image==0.25.0 \
    pillow \
    tqdm==4.66.4 \
    natsort

# nnU-Net / MONAI / 의료 영상
RUN pip3 install --no-cache-dir --break-system-packages \
    nnunetv2==2.5.1 \
    monai \
    SimpleITK==2.4.0 \
    nilearn==0.10.4 \
    nipype==1.8.6 \
    medpy

# Web / API
RUN pip3 install --no-cache-dir --break-system-packages \
    fastapi==0.116.1 \
    fastapi-utils==0.6.0 \
    uvicorn==0.29.0 \
    httpx==0.28.1 \
    pydantic==2.10.4 \
    pydantic-settings==2.7.1

# 유틸리티
RUN pip3 install --no-cache-dir --break-system-packages \
    tensorboard \
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

# ── 9. JupyterLab + jupyter-server-proxy ────────────────────────────────────
RUN pip3 install --no-cache-dir --break-system-packages \
    jupyterlab \
    notebook \
    jupyter-server-proxy \
    ipykernel \
    pytorch_lightning

# ── 10. MOTD + README ────────────────────────────────────────────────────────
RUN printf '%s\n' \
    '╔══════════════════════════════════════════════════════════════════╗' \
    '║     Neuropean AI Workstation - 2-Stage Fiducial Detection        ║' \
    '╠══════════════════════════════════════════════════════════════════╣' \
    '║  Base    : nvidia/cuda:12.1.1-cudnn8-devel-ubuntu22.04           ║' \
    '║  Python  : 3.12.9 (system) / 3.12.9 (conda 24.7.1)              ║' \
    '║  PyTorch : 2.5.1+cu121 / torchvision 0.20.1+cu121               ║' \
    '║  Conda   : /opt/conda                                            ║' \
    '║  DDP     : torchrun + NCCL (4-GPU)                               ║' \
    '╠══════════════════════════════════════════════════════════════════╣' \
    '║  [DDP] 4-GPU 학습 실행                                            ║' \
    '║    torchrun --nproc_per_node=4 train.py                          ║' \
    '║                                                                  ║' \
    '║  [Conda] 환경 초기화 (최초 1회)                                     ║' \
    '║    conda init bash && source ~/.bashrc                           ║' \
    '║                                                                  ║' \
    '║  [Conda] 새 환경 생성                                              ║' \
    '║    conda create -n myenv python=3.12.9                           ║' \
    '║    conda activate myenv                                          ║' \
    '║    pip install -r requirements.txt                               ║' \
    '║                                                                  ║' \
    '║  [Jupyter] Conda 환경을 커널로 등록                                 ║' \
    '║    conda activate myenv                                          ║' \
    '║    pip install ipykernel                                         ║' \
    '║    python -m ipykernel install --user --name myenv               ║' \
    '║                                                                  ║' \
    '║  [Libs] 설치된 주요 라이브러리                                      ║' \
    '║    torch 2.5.1 / torchvision 0.20.1 / pytorch_lightning          ║' \
    '║    numpy 2.2.6 / scipy 1.14.1 / matplotlib 3.10.6               ║' \
    '║    nibabel 5.4.0 / h5py 3.14.0                                   ║' \
    '║    nnunetv2 / monai / SimpleITK                                  ║' \
    '║    fastapi / uvicorn / pydantic                                  ║' \
    '║                                                                  ║' \
    '║  [Claude] Claude Code 사용                                        ║' \
    '║    claude                                                        ║' \
    '║                                                                  ║' \
    '║  [GPU] 상태 확인                                                  ║' \
    '║    nvidia-smi                                                    ║' \
    '║    python -c "import torch; print(torch.cuda.is_available())"    ║' \
    '╚══════════════════════════════════════════════════════════════════╝' \
    > /etc/motd \
    && echo 'cat /etc/motd' > /etc/profile.d/motd.sh \
    && chmod +x /etc/profile.d/motd.sh \
    && echo 'cat /etc/motd' >> /etc/bash.bashrc

RUN mkdir -p /opt/neuropean \
    && printf '%s\n' \
       '# 🧠 Neuropean AI Workstation — 2-Stage Fiducial Detection' \
       '' \
       '> **Base**: `nvidia/cuda:12.1.1-cudnn8-devel-ubuntu22.04`  ' \
       '> **Python**: 3.12.9 (system) / 3.12.9 (conda 24.7.1)  ' \
       '> **PyTorch**: 2.5.1+cu121  ' \
       '> **torchvision**: 0.20.1+cu121  ' \
       '> **DDP**: torchrun + NCCL (4-GPU)  ' \
       '> **Conda**: `/opt/conda`' \
       '' \
       '---' \
       '' \
       '## 🚀 DDP 학습 실행' \
       '' \
       '```bash' \
       'torchrun --nproc_per_node=4 train.py' \
       '```' \
       '' \
       '## 🐍 Conda 환경' \
       '' \
       '```bash' \
       'conda init bash && source ~/.bashrc' \
       'conda create -n myenv python=3.12.9' \
       'conda activate myenv' \
       'pip install -r requirements.txt' \
       '```' \
       '' \
       '## 📦 핵심 라이브러리 버전' \
       '' \
       '| 패키지 | 버전 |' \
       '|--------|------|' \
       '| torch | 2.5.1+cu121 |' \
       '| torchvision | 0.20.1+cu121 |' \
       '| numpy | 2.2.6 |' \
       '| scipy | 1.14.1 |' \
       '| matplotlib | 3.10.6 |' \
       '| nibabel | 5.4.0 |' \
       '| h5py | 3.14.0 |' \
       > /opt/neuropean/README.md

# ── 11. Kubeflow 호환 jovyan 사용자 생성 ─────────────────────────────────────
RUN if getent passwd 1000 > /dev/null 2>&1; then \
        usermod -l jovyan -d /home/jovyan -m $(getent passwd 1000 | cut -d: -f1); \
    else \
        useradd -m -s /bin/bash -u 1000 jovyan; \
    fi \
    && echo "jovyan ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

# ── 12. jupyter-server-proxy로 code-server 등록 ─────────────────────────────
COPY jupyter_server_config.py /etc/jupyter/jupyter_server_config.py

# ── 13. entrypoint 스크립트 ──────────────────────────────────────────────────
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# ── 14. jovyan 환경 설정 ─────────────────────────────────────────────────────
USER jovyan
WORKDIR /home/jovyan

RUN mkdir -p /home/jovyan/.claude \
    && echo '{"autoUpdates":false}' > /home/jovyan/.claude/settings.json \
    && mkdir -p /home/jovyan/.local/share/code-server/extensions \
    && python3 -m ipykernel install --user --name python3 --display-name "Python 3.12.9 (CUDA 12.1)"

ENV PATH="/usr/bin:/usr/local/bin:${PATH}"
ENV NB_PREFIX="/"

ARG IMAGE_VERSION=v2.3.0
LABEL maintainer="neuropean" \
      version="${IMAGE_VERSION}" \
      type="jupyter" \
      base="nvidia/cuda:12.1.1-cudnn8-devel-ubuntu22.04" \
      python.version="3.12.9" \
      cuda.version="12.1.1" \
      torch.version="2.5.1+cu121" \
      node.version="20" \
      code-server.version="${CODE_SERVER_VERSION}"

EXPOSE 8888

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8888/api || exit 1

ENTRYPOINT ["tini", "--", "/usr/local/bin/entrypoint.sh"]
CMD ["jupyter", "lab", \
     "--ip=0.0.0.0", \
     "--port=8888", \
     "--no-browser", \
     "--NotebookApp.token=''", \
     "--NotebookApp.password=''"]