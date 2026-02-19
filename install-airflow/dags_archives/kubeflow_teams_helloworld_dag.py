"""
Teams Notification Hello World DAG
"""
from datetime import datetime
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.models.param import Param
from airflow.models import Variable
import requests
import logging

logger = logging.getLogger(__name__)

default_args = {
    'owner': 'admin',
    'start_date': datetime(2025, 1, 1),
    'retries': 0,
}

def send_teams_hello_world(**context):
    """Teams Webhook을 통해 메시지를 전송하는 함수"""
    params = context['params']
    message = params.get('message')
    
    # 1. Variable에서 Webhook URL 가져오기
    webhook_url = Variable.get("teams_webhook_url", default_var="")
    
    if not webhook_url:
        logger.error("🚨 Teams Webhook URL이 설정되지 않았습니다. Variables를 확인하세요.")
        raise ValueError("Missing 'teams_webhook_url' in Airflow Variables.")

    # 2. Teams 메시지 페이로드 (MessageCard 형식)
    # 색상(themeColor)이나 제목(activityTitle)은 커스텀 가능합니다.
    payload = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": "0078D7", # 파란색 계열
        "summary": "Airflow 알림",
        "sections": [{
            "activityTitle": "📢 Airflow Hello World",
            "activitySubtitle": "Kubeflow Cluster Notification",
            "text": message
        }]
    }

    # 3. HTTP POST 요청 전송
    logger.info("Teams 웹훅으로 메시지를 전송합니다...")
    response = requests.post(webhook_url, json=payload)
    
    # 4. 전송 결과 확인
    if response.status_code == 200 and response.text == '1':
        logger.info("✅ Teams 메시지가 성공적으로 전송되었습니다.")
    else:
        logger.error(f"🚨 전송 실패: [HTTP {response.status_code}] {response.text}")
        raise Exception("Teams webhook request failed.")

with DAG(
    'teams_helloworld_notifier_v26.02.0',
    default_args=default_args,
    schedule_interval=None,
    tags=['notification', 'teams', 'admin'],
    params={
        "message": Param(
            default="Hello World! 이것은 Airflow에서 보낸 Teams 테스트 메시지입니다.",
            type="string",
            title="Teams 전송 메시지",
            description="채널에 발송할 내용을 입력하세요."
        )
    },
    access_control={
        'KF_Team': {'can_read', 'can_edit'}
    }
) as dag:

    t_send_teams = PythonOperator(
        task_id='send_hello_world_to_teams',
        python_callable=send_teams_hello_world,
    )