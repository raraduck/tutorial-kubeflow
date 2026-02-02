# 베이스 이미지로 파이썬 3.10 사용
FROM python:3.10-slim

# 시스템 의존성 설치 (이미지 처리 및 네트워크 도구)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 작업 디렉토리 설정
WORKDIR /app

# 필요한 패키지 미리 설치
# 캐시를 삭제하여 이미지 용량 최적화
RUN pip install --no-cache-dir \
    img2dataset \
    pyarrow \
    pandas

# 실행 권한 부여 및 환경 변수 설정 (필요 시)
ENV PYTHONUNBUFFERED=1

# 기본 실행 명령은 bash로 설정 (Argo에서 덮어쓰기 때문)
CMD ["/bin/bash"]