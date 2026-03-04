#!/bin/bash
set -e

NB_PREFIX="${NB_PREFIX:-/}"

# ── JupyterLab 백그라운드 실행 (8889 포트) ───────────────────────────────────
# jupyter lab \
#     --ip=0.0.0.0 \
#     --port=8889 \
#     --no-browser \
#     --NotebookApp.token="" \
#     --NotebookApp.password="" \
#     --NotebookApp.base_url="${NB_PREFIX}/jupyter" &

# echo "JupyterLab started on port 8889 (path: ${NB_PREFIX}jupyter)"

# ── code-server 포그라운드 실행 (8888 포트, Kubeflow 메인) ───────────────────
exec code-server \
    --bind-addr 0.0.0.0:8888 \
    --auth none \
    /home/jovyan