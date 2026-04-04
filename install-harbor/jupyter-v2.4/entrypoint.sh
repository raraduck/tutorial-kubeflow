#!/bin/bash
# ── Neuropean AI Workstation entrypoint ──────────────────────────────────────
# Kubeflow PVC 마운트 이후 실행되므로 홈 디렉토리 초기화를 여기서 처리

set -e

HOME_DIR="/home/jovyan"

# 1. README.md : PVC로 덮어씌워지므로 매 시작 시 원본에서 복사
cp -f /opt/neuropean/README.md "${HOME_DIR}/README.md"

# 2. .bashrc : 없으면 생성 (PVC 신규 마운트 시 빈 홈인 경우 대비)
if [ ! -f "${HOME_DIR}/.bashrc" ]; then
    touch "${HOME_DIR}/.bashrc"
fi

# 3. .bash_profile : .bashrc 를 source 하도록 (login shell 대비)
if [ ! -f "${HOME_DIR}/.bash_profile" ]; then
    printf '%s\n' \
        '# source .bashrc from .bash_profile' \
        '[[ -f ~/.bashrc ]] && source ~/.bashrc' \
        > "${HOME_DIR}/.bash_profile"
fi

# 4. SSH 서버 시작
mkdir -p /run/sshd
sudo /usr/sbin/sshd

# 5. CMD 실행 (jupyter lab 등)
exec "$@"