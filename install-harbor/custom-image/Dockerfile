# 1. Base Image 지정
FROM ghcr.io/kubeflow/kubeflow/notebook-servers/jupyter-pytorch-cuda-full:v1.10.0

# 2. 사용자 권한 설정 (Kubeflow 이미지는 보통 jovyan 사용자를 사용합니다)
USER root

# 3. 요구사항 패키지 설치 및 업그레이드
RUN pip install --upgrade "numpy>=2.0" && \
    pip install pytorch_lightning tensorboard

# 4. 원래 사용자로 복귀
USER jovyan