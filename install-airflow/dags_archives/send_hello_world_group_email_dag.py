"""
Email Hello World DAG (Dropdown Group Selection)
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
    'group_email_hello_world_dropdown',
    default_args=default_args,
    schedule_interval=None,
    tags=['notification', 'email'],
    # [입력 폼] enum을 사용하여 드롭다운 메뉴 생성
    params={
        "target_group": Param(
            default="all_users", 
            type="string", 
            # 이곳에 정의된 값들이 드롭다운의 선택지로 나타납니다. (Variable의 Key와 동일해야 함)
            enum=["all_user_emails", "onboarded_user_emails"], 
            title="수신자 그룹 선택",
            description="메일을 발송할 대상 그룹을 선택하세요."
        )
    },
    access_control={
        'KF_Team': {'can_read', 'can_edit'}
    }
) as dag:

    send_email_task = EmailOperator(
        task_id='send_hello_world_email',
        # 사용자가 드롭다운에서 선택한 값(params.target_group)을 Key로 삼아 Variable을 불러옴
        to='{{ var.value[params.target_group] }}',
        subject='[Airflow] {{ params.target_group }} 그룹 대상 알림',
        html_content="""
        <h3>Hello World!</h3>
        <p>선택하신 <b>{{ params.target_group }}</b> 그룹으로 발송된 테스트 메일입니다.</p>
        <p>SMTP 설정 및 드롭다운 기능이 정상적으로 작동하고 있습니다. 🎉</p>
        <br>
        <em>Sent from Airflow EmailOperator</em>
        """,
    )

    send_email_task