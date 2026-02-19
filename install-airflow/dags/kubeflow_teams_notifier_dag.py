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

def send_teams_notification(**context):
    """Array 형태의 메시지를 받아 Teams 공지 형식으로 전송"""
    params = context['params']
    message_list = params.get('email_message', [])
    
    # 1. Variable에서 Webhook URL 가져오기
    webhook_url = Variable.get("teams_webhook_url", default_var="")
    
    if not webhook_url:
        logger.error("🚨 Teams Webhook URL이 설정되지 않았습니다.")
        raise ValueError("Missing 'teams_webhook_url' in Airflow Variables.")

    # 2. 리스트 내용을 Teams Bullet Point 형식으로 변환
    # Teams MessageCard에서는 표준 Markdown을 지원합니다.
    formatted_message = "\n\n".join([f"{msg}" for msg in message_list])

    # 3. Teams 메시지 페이로드 설정
    payload = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": "0078D7",
        "summary": "GPU통합관리시스템 공지 알림",
        "sections": [{
            "activityTitle": "📢 GPU 클러스터 공지사항",
            # "activitySubtitle": f"발송 일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "text": formatted_message if formatted_message else "전달된 내용이 없습니다."
        }]
    }

    # 4. 전송
    logger.info("Teams 웹훅으로 공지 메시지를 전송합니다...")
    response = requests.post(webhook_url, json=payload)
    
    if response.status_code == 200:
        logger.info("✅ Teams 메시지 전송 성공")
    else:
        logger.error(f"🚨 전송 실패: {response.status_code}, {response.text}")
        raise Exception("Teams webhook failed.")

with DAG(
    'kubeflow_teams_notifier_v26.02.0',
    default_args=default_args,
    schedule_interval=None,
    tags=['notification', 'teams', 'admin'],
    params={
        "email_message": Param(
            default=["내용을 입력하세요.", "- 공지사항1", "- 공지사항2"],
            type=["array"], 
            title="전달 메시지",
            items={"type": "string"},
            description="전달할 공지 내용을 한 줄씩 입력하세요."
        )
    },
    access_control={
        'KF_Team': {'can_read', 'can_edit'}
    }
) as dag:

    t_send_teams = PythonOperator(
        task_id='send_announcement_to_teams',
        python_callable=send_teams_notification,
    )