"""
Email Notification DAG (Group Selection + Boolean Toggle + Validation)
"""
from datetime import datetime
from airflow import DAG
from airflow.operators.email import EmailOperator
from airflow.operators.python import PythonOperator
from airflow.models.param import Param
import re
import logging

logger = logging.getLogger(__name__)

default_args = {
    'owner': 'admin',
    'start_date': datetime(2025, 1, 1),
    'retries': 0,
}

email_list_regex = r"^([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(\s*,\s*[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})*)$"

def validate_recipients(**context):
    """Boolean 플래그를 활용한 수신자 교차 검증"""
    params = context['params']
    target_group = params.get('target_group')
    use_additional = params.get('use_additional_emails', False)
    additional_emails = (params.get('additional_emails') or "").strip()

    # 1. 대상 그룹도 없고, 개별 추가 체크도 안 한 경우 (수신자 아예 없음)
    if target_group == 'none' and not use_additional:
        error_msg = "🚨 발송 실패: 수신자가 지정되지 않았습니다. 대상을 선택하거나 '개별 수신자 추가'를 체크하세요."
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    # 2. '개별 수신자 추가'를 체크했을 때의 엄격한 검증
    if use_additional:
        if not additional_emails:
            error_msg = "🚨 발송 실패: '개별 수신자 추가'를 체크했으나, 이메일이 입력되지 않았습니다."
            logger.error(error_msg)
            raise ValueError(error_msg)
            
        if not re.match(email_list_regex, additional_emails):
            error_msg = f"🚨 발송 실패: 개별 이메일 형식이 올바르지 않습니다. (입력값: {additional_emails})"
            logger.error(error_msg)
            raise ValueError(error_msg)
    
    logger.info("수신자 검증 성공. 메일 발송 단계로 넘어갑니다.")

with DAG(
    'kubeflow_email_notifier_v26.02.3',
    default_args=default_args,
    schedule_interval=None,
    tags=['notification', 'email', 'admin'],
    params={
        "target_group": Param(
            default="none", 
            type="string", 
            enum=["none", "all_user_emails", "onboarded_user_emails"], 
            title="1. 수신 그룹 선택",
            description="Variable에 등록된 그룹을 선택하세요."
        ),
        # [추가됨] Boolean 분기용 플래그
        "use_additional_emails": Param(
            default=False,
            type="boolean",
            title="2. 개별 수신자 추가 여부",
            description="체크하면 아래 입력된 개별 이메일도 수신자에 포함됩니다."
        ),
        "additional_emails": Param(
            default="noreply@neurophet.com",
            type=["string"],
            title="3. 추가/개별 수신자 이메일",
            description="위 체크박스를 켠 경우에만 반영됩니다. 콤마(,)로 구분하여 입력하세요."
        ),
        "email_subject": Param(
            default="[공지] 클러스터 운영 관련 안내드립니다.",
            type="string",
            title="4. 메일 제목",
            minLength=1
        ),
        "email_message": Param(
            default=["전달할 내용을 여기에 입력하세요."],
            type=["array"], 
            title="5. 전달 메시지",
            items={"type": "string"}
        )
    },
    access_control={
        'KF_Team': {'can_read', 'can_edit'}
    }
) as dag:

    t_validate = PythonOperator(
        task_id='validate_inputs',
        python_callable=validate_recipients,
    )

    t_send_email = EmailOperator(
        task_id='send_combined_email',
        # Jinja 분기 로직이 훨씬 깔끔해짐
        to="""
            {%- set group_emails = var.value.get(params.target_group, '') if params.target_group != 'none' else '' -%}
            {%- set direct_emails = params.additional_emails if params.use_additional_emails else '' -%}
            
            {%- if group_emails and direct_emails -%}
                {{ group_emails }},{{ direct_emails }}
            {%- elif group_emails -%}
                {{ group_emails }}
            {%- else -%}
                {{ direct_emails }}
            {%- endif -%}
        """,
        subject='{{ params.email_subject }}',
        html_content="""
        <div style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #2c3e50;">📢 클러스터 안내</h2>
            <div style="background-color: #f9f9f9; border-left: 4px solid #3498db; padding: 15px; margin: 20px 0;">
                {% if params.email_message %}
                    {{ (params.email_message or []) | join('<br>') }}
                {% else %}
                    (전달된 내용이 없습니다.)
                {% endif %}
            </div>
            <p style="font-size: 0.85em; color: #95a5a6; border-top: 1px solid #eee; padding-top: 10px;">
                <b>수신 그룹:</b> {{ params.target_group }}<br>
                본 메일은 Neurophet MLOps 관리 도구에 의해 발송되었습니다.
            </p>
        </div>
        """,
    )

    t_validate >> t_send_email