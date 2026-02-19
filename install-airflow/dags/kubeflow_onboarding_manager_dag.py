from datetime import datetime
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.email import EmailOperator
from airflow.models.param import Param
from airflow.models import Variable
import logging
import requests

logger = logging.getLogger(__name__)

# --- 파싱 시점에 현재 등록된 이메일 목록 불러오기 및 정렬 ---
raw_emails_str = Variable.get("onboarded_user_emails", default_var="")

# 1. 쉼표 기준으로 나누고 공백 제거 후 빈 값 필터링
email_list = [email.strip() for email in raw_emails_str.split(',') if email.strip()]

# 2. 알파벳 순서로 정렬
sorted_email_list = sorted(email_list)

# 3. 화면에 띄울 때 보기 좋게 한 줄에 하나씩 줄바꿈(\n)으로 연결
display_emails_str = ", \n".join(sorted_email_list)

# --- UI 문서화 (Markdown) ---
dag_docs = f"""
### Kubeflow Onboarding Workflow
1. **Check**: 기존 등록 여부 및 입력값 검증 (Force proceed 지원)
2. **Provisioning**: Kubeflow Profile 및 ResourceQuota 생성 (Dry Run)
3. **Register**: 성공 시 `onboarded_user_emails` Variable 및 DB 업데이트
4. **Notify**: 사용자에게 가입 완료 안내 메일과 메신저 발송

**[현재 등록된 이메일 목록]**
```text
{display_emails_str if display_emails_str else '(등록된 이메일이 없습니다)'}
```
"""

default_args = {
    'owner': 'mlops-admin',
    'start_date': datetime(2025, 1, 1),
    'retries': 0
}

def get_current_user_set():
    current_str = Variable.get("onboarded_user_emails", default_var="")
    return {e.strip() for e in current_str.split(',') if e.strip()}

def check_user_exists(**context):
    """[Step 0] 사전 검증: 중복 체크 및 규칙 확인"""
    params = context['params']
    username = params.get('username').strip()
    force_proceed = params.get('force_proceed', False)
    
    current_set = get_current_user_set()

    if username in current_set and not force_proceed:
        error_msg = f"User '{username}' already exists. Use 'force_proceed' to overwrite."
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    logger.info(f"Validation passed for user: {username}")

def create_kubeflow_profile(**context):
    """[Step 1] 인프라 생성: Profile, Namespace, Quota 적용"""
    params = context['params'] 
    username = params.get('username')
    gpu_limit = params.get('gpu_limit')
    
    # TODO: 실제 kubectl apply 로직 혹은 Kubernetes 클라이언트 호출
    logger.info(f"== [Provisioning] Namespace creation & Quota({gpu_limit}) for {username} ==")

def register_user_after_success(**context):
    """[Step 2] 최종 확정: 모든 인프라 작업 성공 후 목록 업데이트"""
    params = context['params']
    username = params.get('username').strip()
    
    current_set = get_current_user_set()
    
    if username not in current_set:
        current_set.add(username)
        new_str = ", ".join(sorted(current_set))
        Variable.set("onboarded_user_emails", new_str)
        
        # [추가 제안] 실제 DB Insert 로직이 들어갈 자리
        # db_client.insert(user=username, created_at=datetime.now())
        logger.info(f"Successfully registered {username} to the cluster list.")
    else:
        logger.info(f"{username} was already in the list (Force Proceed). No update needed.")

def send_teams_onboarding_notification(**context):
    """[Step 4] Teams 알림 발송"""
    params = context['params']
    username = params.get('username')
    gpu_limit = params.get('gpu_limit')
    
    webhook_url = Variable.get("teams_webhook_url", default_var="")
    if not webhook_url:
        logger.error("Teams Webhook URL is missing.")
        return # 알림 실패가 전체 파이프라인 실패로 이어지지 않게 처리

    # 개선된 엣지 있는 MessageCard 스타일
    payload = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": "4B53BC",  # Kubeflow와 유사한 보라/다크블루 계열
        "summary": "신규 사용자 온보딩 알림",
        "sections": [{
            "activityTitle": "🚀 Kubeflow Onboarding Success",
            "activitySubtitle": f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "activityImage": "https://www.kubeflow.org/docs/images/logos/kubeflow.png",
            "text": "새로운 연구원이 클러스터에 성공적으로 합류했습니다. 주요 할당 리소스는 다음과 같습니다.",
            "facts": [
                {"name": "Researcher ID", "value": username},
                {"name": "GPU Resource", "value": f"{gpu_limit} Units"},
                {"name": "Status", "value": "Active (Provisioned)"}
            ],
            "markdown": True
        }],
        "potentialAction": [
            {
                "@type": "OpenUri",
                "name": "View Dashboard",
                "targets": [{"os": "default", "uri": "https://kubeflow.neurophet.com"}]
            }
        ]
    }
    
    requests.post(webhook_url, json=payload)
    logger.info(f"Teams notification sent for {username}")
    
# 정규표현식: 이메일 형식 검증
email_regex = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"

with DAG(
    'kubeflow_onboarding_manager_v26.02.2',
    default_args=default_args,
    schedule_interval=None,
    tags=['kubeflow', 'admin', 'onboarding'],
    doc_md=dag_docs,
    params={
        "username": Param(
            default="new-researcher@neurophet.com", 
            type="string", 
            pattern=email_regex,
            title="신규 사용자 이메일",
            description="Neurophet 업무용 이메일을 입력하세요."
        ),
        "force_proceed": Param(
            default=False, 
            type="boolean", 
            title="⚠️ 강제 진행",
            description="기존 사용자의 설정을 초기화하거나 강제로 다시 생성할 때 체크하세요."
        ),
        "gpu_limit": Param(
            default=4, 
            type="integer", 
            title="GPU Quota", 
            enum=[1, 2, 4],
        )
    },
    access_control={
        'KF_Team': {'can_read', 'can_edit'},
    }
) as dag:

    t0_check = PythonOperator(
        task_id='validate_user_request',
        python_callable=check_user_exists,
    )

    t1_provision = PythonOperator(
        task_id='provision_kubeflow_resources',
        python_callable=create_kubeflow_profile,
    )

    t2_register = PythonOperator(
        task_id='finalize_registration',
        python_callable=register_user_after_success,
    )

    t3_email = EmailOperator(
        task_id='send_welcome_email',
        to='{{ params.username }}',
        subject='[Kubeflow] AI 개발 환경 온보딩이 완료되었습니다.',
        html_content="""
        <h3>🎉 환영합니다!</h3>
        <p>Neurophet GPU 클러스터 사용을 위한 준비가 완료되었습니다.</p>
        <hr>
        <ul>
            <li><b>계정:</b> {{ params.username }}</li>
            <li><b>GPU 할당량:</b> {{ params.gpu_limit }}개</li>
        </ul>
        <p><a href="https://kubeflow.neurophet.com">Kubeflow Dashboard 바로가기</a></p>
        """
    )

    t4_teams = PythonOperator(
        task_id='send_teams_notification',
        python_callable=send_teams_onboarding_notification,
    )

    # 실행 순서: 검증 -> 리소스 생성 -> DB 등록 -> 이메일 발송 -> Teams 공지
    t0_check >> t1_provision >> t2_register >> t3_email >> t4_teams