# Base: Kubeflow Code-Server Python notebook server
FROM ghcr.io/kubeflow/kubeflow/notebook-servers/codeserver-python:v1.10.0

# ── root 권한으로 시스템 패키지 설치 ──────────────────────────────────────
USER root

# Node.js 20 LTS 설치 (Claude Code는 Node.js 18+ 필요)
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        gnupg \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
       | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" \
       > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Claude Code 전역 설치
RUN npm install -g @anthropic-ai/claude-code

# ── jovyan 사용자 환경 설정 ────────────────────────────────────────────────
USER jovyan

# Claude 설정 디렉토리 준비
RUN mkdir -p /home/jovyan/.claude

# PATH에 npm global bin 추가 (혹시 누락된 경우 대비)
ENV PATH="/usr/bin:/usr/local/bin:${PATH}"

# ── 확인용 레이블 ────────────────────────────────────────────────────────
LABEL maintainer="devops-team" \
      base="ghcr.io/kubeflow/kubeflow/notebook-servers/codeserver-python:v1.10.0" \
      node.version="20" \
      claude-code.version="latest"