from datetime import datetime
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.email import EmailOperator
from airflow.models.param import Param
from airflow.models import Variable
import logging
import requests

logger = logging.getLogger(__name__)

# --- 파싱 시점에 현재 등록된 온보딩 사용자 목록 불러오기 및 정렬 ---
raw_emails_str = Variable.get("onboarded_user_emails", default_var="")

email_list = [email.strip() for email in raw_emails_str.split(',') if email.strip()]

sorted_email_list = sorted(email_list)

display_emails_str = "\n".join(sorted_email_list)

# --- Trigger 화면 상단에 띄울 마크다운 문서 작성 ---
dag_docs = f"""
### 🛑 Kubeflow 사용자 오프보딩 (리소스 회수)
클러스터 사용이 종료된 연구원의 환경(Profile, Namespace, 할당된 GPU 및 Storage)을 삭제하고 접근 권한을 회수합니다.

⚠️ **데이터 유실 주의**
* 리소스(Profile) 삭제 시 해당 네임스페이스 내의 **모든 Notebook과 PVC(스토리지) 데이터가 영구 삭제**됩니다.
* 반드시 사전에 중요 데이터가 백업되었는지 점검하시고, 폼 하단의 `데이터 백업 확인`을 체크해 주세요.

**[현재 온보딩된 사용자 목록 (파싱 시점 기준)]**
아래 목록에서 삭제할 사용자의 이메일을 복사(`Ctrl+C`)하여 하단 입력 폼에 붙여넣으세요.
```text
{display_emails_str if display_emails_str else '(현재 온보딩된 사용자가 없습니다)'}
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

def check_user_exists_for_offboarding(**context):
    """[Step 0] 사전 검증: 목록 존재 여부 및 백업 확인"""
    params = context['params']
    username = params.get('username').strip()
    force_proceed = params.get('force_proceed', False)
    backup_checked = params.get('backup_checked', False)
    
    # 데이터 백업 확인 (강제 진행이 아닐 경우 필수)
    if not backup_checked and not force_proceed:
        error_msg = f"User '{username}' offboarding stopped. '데이터 백업 확인'을 체크해야 진행할 수 있습니다."
        logger.error(error_msg)
        raise ValueError(error_msg)

    current_set = get_current_user_set()

    # 삭제하려는 사용자가 목록에 없는 경우
    if username not in current_set and not force_proceed:
        error_msg = f"User '{username}' is not in the onboarded list. Use 'force_proceed' to run anyway."
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    logger.info(f"Offboarding validation passed for user: {username}")

def delete_kubeflow_profile(**context):
    """[Step 1] 인프라 회수: Profile 및 Namespace 삭제"""
    params = context['params'] 
    username = params.get('username')
    
    # TODO: 실제 kubectl delete profile <namespace> 로직 호출
    # (Profile 삭제 시 Namespace 내 리소스들이 연쇄적으로 Terminating 됩니다.)
    logger.info(f"== [Deprovisioning] Deleting Profile and resources for {username} ==")

def unregister_user_after_success(**context):
    """[Step 2] 최종 확정: 리소스 삭제 성공 후 목록에서 제외"""
    params = context['params']
    username = params.get('username').strip()
    
    current_set = get_current_user_set()
    
    if username in current_set:
        current_set.remove(username) # 집합에서 제거
        new_str = ", ".join(sorted(current_set))
        Variable.set("onboarded_user_emails", new_str)
        
        # [추가 제안] DB에서 삭제 또는 비활성화 처리 (Soft Delete)
        logger.info(f"Successfully removed {username} from the cluster list.")
    else:
        logger.info(f"{username} was not in the list. No variable update needed.")

def send_teams_offboarding_notification(**context):
    """[Step 4] Teams 알림 발송 (오프보딩 전용 빨간색 테마)"""
    params = context['params']
    username = params.get('username')
    
    webhook_url = Variable.get("teams_webhook_url", default_var="")
    if not webhook_url:
        logger.error("Teams Webhook URL is missing.")
        return 

    # 오프보딩에 맞춘 붉은색(E81123) MessageCard
    payload = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": "E81123",  # 붉은색 계열 (삭제/경고)
        "summary": "사용자 오프보딩 알림",
        "sections": [{
            "activityTitle": "🛑 Kubeflow Offboarding Complete",
            "activitySubtitle": f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "activityImage": "https://www.kubeflow.org/docs/images/logos/kubeflow.png",
            "text": "사용자의 클러스터 리소스가 안전하게 회수되었으며, 목록에서 제거되었습니다.",
            "facts": [
                {"name": "Researcher ID", "value": username},
                {"name": "Action", "value": "Profile & Resource Deletion"},
                {"name": "Status", "value": "Inactive (Deprovisioned)"}
            ],
            "markdown": True
        }]
    }
    
    requests.post(webhook_url, json=payload)
    logger.info(f"Teams offboarding notification sent for {username}")
    
# 정규표현식: 이메일 형식 검증
email_regex = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"

with DAG(
    'kubeflow_offboarding_manager_v26.02.0',
    default_args=default_args,
    schedule_interval=None,
    tags=['kubeflow', 'admin', 'offboarding'],
    doc_md=dag_docs, # [여기에 추가] 마크다운 문서를 연결합니다.
    params={
        "username": Param(
            default="", 
            type="string", 
            pattern=email_regex,
            title="삭제 대상 이메일",
            description="권한 및 리소스를 회수할 이메일을 입력하세요."
        ),
        "backup_checked": Param(
            default=False, 
            type="boolean", 
            title="💾 데이터 백업 확인 (필수)",
            description="해당 사용자의 Notebook, PVC 등 중요 데이터가 백업되었는지 확인 후 체크하세요."
        ),
        "force_proceed": Param(
            default=False, 
            type="boolean", 
            title="⚠️ 강제 진행",
            description="사용자가 목록에 없거나 백업 확인을 생략하고 강제로 삭제할 때 체크하세요."
        )
    },
    access_control={
        'KF_Team': {'can_read', 'can_edit'},
    }
) as dag:

    t0_check = PythonOperator(
        task_id='validate_offboarding_request',
        python_callable=check_user_exists_for_offboarding,
    )

    t1_deprovision = PythonOperator(
        task_id='deprovision_kubeflow_resources',
        python_callable=delete_kubeflow_profile,
    )

    t2_unregister = PythonOperator(
        task_id='finalize_unregistration',
        python_callable=unregister_user_after_success,
    )

    t3_email = EmailOperator(
        task_id='send_goodbye_email',
        to='{{ params.username }}',
        subject='[Kubeflow] AI 개발 환경 접근 권한이 회수되었습니다.',
        html_content="""
        <h3>안내 말씀 드립니다.</h3>
        <p>요청에 따라 아래 계정의 Neurophet GPU 클러스터(Kubeflow) 환경 접근 권한 및 할당된 리소스가 모두 회수되었습니다.</p>
        <hr>
        <ul>
            <li><b>계정:</b> {{ params.username }}</li>
            <li><b>조치 내용:</b> Profile, Namespace 및 내부 리소스(Notebook, PVC) 정리 완료</li>
        </ul>
        <p>그동안 수고 많으셨습니다.</p>
        """
    )

    t4_teams = PythonOperator(
        task_id='send_teams_offboarding_notification',
        python_callable=send_teams_offboarding_notification,
    )

    # 실행 순서: 검증 -> 리소스 삭제 -> 변수 목록 업데이트 -> 이메일 발송 -> Teams 알림
    t0_check >> t1_deprovision >> t2_unregister >> t3_email >> t4_teams