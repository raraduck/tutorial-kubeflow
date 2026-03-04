FROM ghcr.io/kubeflow/kubeflow/notebook-servers/jupyter-pytorch-cuda-full:v1.10.0

USER root

# ── 1. Node.js 20 + code-server 의존 패키지 설치 ────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        gnupg \
        sudo \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
       | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" \
       > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ── 2. code-server 설치 ─────────────────────────────────────────────────────
ARG CODE_SERVER_VERSION=4.92.2
RUN curl -fsSL https://code-server.dev/install.sh \
    | sh -s -- --version=${CODE_SERVER_VERSION} \
    && rm -rf /root/.cache

# ── 3. jovyan sudo 권한 부여 ────────────────────────────────────────────────
RUN echo "jovyan ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

# ── 4. Claude Code 전역 설치 ────────────────────────────────────────────────
RUN npm install -g @anthropic-ai/claude-code

# ── 5. Python 패키지 ────────────────────────────────────────────────────────
RUN pip install --no-cache-dir --upgrade "numpy>=2.0" && \
    pip install --no-cache-dir \
        pytorch_lightning \
        tensorboard \
        jupyter-server-proxy

# ── 6. jupyter-server-proxy 로 code-server 등록 ─────────────────────────────
COPY jupyter_server_config.py /opt/conda/etc/jupyter/jupyter_server_config.py

# ── 7. jovyan 환경 설정 ─────────────────────────────────────────────────────
USER jovyan

RUN mkdir -p /home/jovyan/.claude \
    && echo '{"autoUpdates":false}' > /home/jovyan/.claude/settings.json \
    && mkdir -p /home/jovyan/.local/share/code-server/extensions

ENV PATH="/usr/bin:/usr/local/bin:${PATH}"

LABEL maintainer="neuropean" \
      base="jupyter-pytorch-cuda-full:v1.10.0" \
      node.version="20" \
      code-server.version="${CODE_SERVER_VERSION}"