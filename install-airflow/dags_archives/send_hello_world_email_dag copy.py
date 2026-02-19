"""
Email Hello World DAG
"""
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.email import EmailOperator
from airflow.models.param import Param

default_args = {
    'owner': 'admin',
    'start_date': datetime(2025, 1, 1),
    'retries': 0,
}

with DAG(
    'email_hello_world',
    default_args=default_args,
    schedule_interval=None, # 수동 실행
    tags=['notification', 'email'],
    # [입력 폼] 실행 시 수신자를 변경할 수 있습니다.
    params={
        "receiver_email": Param(
            default="your_email@example.com", 
            type="string", 
            title="수신자 이메일",
            description="메일을 받을 이메일 주소를 입력하세요."
        )
    },
    access_control={
        'KF_Team': {'can_read', 'can_edit'}  # 읽기 + 실행 권한 부여
    }
) as dag:

    send_email_task = EmailOperator(
        task_id='send_hello_world_email',
        # 입력받은 파라미터를 사용 (Jinja Templating)
        to='{{ params.receiver_email }}',
        subject='[Airflow] Hello World Notification',
        html_content="""
        <h3>Hello World!</h3>
        <p>Airflow에서 보낸 테스트 메일입니다.</p>
        <p>SMTP 설정이 정상적으로 작동하고 있습니다. 🎉</p>
        <br>
        <em>Sent from Airflow EmailOperator</em>
        """,
    )

    send_email_task