# Airflow 설치 (사용자 PC, docker 에 구축하기)

## 주요 docker compose yaml 설정
- AIRFLOW_UID=501
- _PIP_ADDITIONAL_REQUIREMENTS=apache-airflow-providers-cncf-kubernetes kubernetes boto3 pandas numpy
### [추가] 이메일 설정
- AIRFLOW_SMTP_EMAIL_USER=
- AIRFLOW_SMTP_PASSWORD=
- AIRFLOW__WEBSERVER__SECRET_KEY=
```yaml
---
x-airflow-common:
    # ...<생략>...
    # .env 파일에서 가져오는 부분 (${변수명})
    AIRFLOW__SMTP__SMTP_USER: ${AIRFLOW_SMTP_EMAIL_USER}
    AIRFLOW__SMTP__SMTP_PASSWORD: ${AIRFLOW_SMTP_PASSWORD}
    AIRFLOW__SMTP__SMTP_MAIL_FROM: ${AIRFLOW_SMTP_EMAIL_USER}
    # --- [추가] Secret Key 환경변수 매핑 ---
    AIRFLOW__WEBSERVER__SECRET_KEY: ${AIRFLOW__WEBSERVER__SECRET_KEY}
    # ...<생략>...
```