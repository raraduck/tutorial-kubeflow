"""
Kubeflow User Onboarding Automation DAG (Dry-Run Mode)
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.email import EmailOperator # [수정] 이 줄이 없어서 에러가 났습니다.
from airflow.models.param import Param 
from kubernetes import client, config
import logging

logger = logging.getLogger(__name__)

default_args = {
    'owner': 'mlops-admin',
    'start_date': datetime(2025, 1, 1),
    'retries': 0
}

# -------------------------------------------------------------------
# K8s Helper Functions (Mock / Dry-Run Mode)
# -------------------------------------------------------------------

def get_k8s_custom_api():
    # [주석 처리] 실제 클러스터 연결 방지
    # config.load_incluster_config()
    # return client.CustomObjectsApi()
    return None

def get_k8s_rbac_api():
    # [주석 처리] 실제 클러스터 연결 방지
    # config.load_incluster_config()
    # return client.RbacAuthorizationV1Api()
    return None

def create_kubeflow_profile(**context):
    """
    [Step 2] Kubeflow Profile 생성 (Dry Run)
    """
    params = context['params'] 
    username = params.get('username')
    gpu_limit = str(params.get('gpu_limit', "0"))

    # 매니페스트 구조 유지
    profile_manifest = {
        "apiVersion": "kubeflow.org/v1beta1",
        "kind": "Profile",
        "metadata": {"name": username.replace("@", "-").replace(".", "-")},
        "spec": {
            "owner": {"kind": "User", "name": username},
            "resourceQuotaSpec": {
                "hard": {
                    "requests.cpu": "2",
                    "requests.memory": "4Gi",
                    "requests.nvidia.com/gpu": gpu_limit,
                    "limits.nvidia.com/gpu": gpu_limit
                }
            }
        }
    }
    
    # [대체 로직] 로그만 출력
    logger.info(f"== [Dry Run] Create Profile Task ==")
    logger.info(f"Target User: {username}")
    logger.info(f"Manifest to apply: {profile_manifest}")
    logger.info("Skipping actual API call...")

def assign_shared_project(**context):
    """
    [Step 4] 공유 프로젝트 권한 할당 (Dry Run)
    """
    params = context['params']
    username = params.get('username')
    target_namespace = params.get('project_team')
    
    if not target_namespace: 
        logger.info("No shared project assigned.")
        return

    # [대체 로직] 로그만 출력
    logger.info(f"== [Dry Run] Assign Project Task ==")
    logger.info(f"Target User: {username}")
    logger.info(f"Target Namespace: {target_namespace}")
    logger.info("Skipping actual RBAC binding...")

def add_to_mailing_list_db(**context):
    """
    [Step 5] 메일링 리스트 DB 등록 로직 (Dry Run)
    """
    params = context['params']
    username = params.get('username')

    # [대체 로직] 로그만 출력
    logger.info(f"== [Dry Run] Database Insert Task ==")
    logger.info(f"Inserting user {username} into internal mailing list DB...")
    logger.info("Skipping actual DB Transaction...")

# -------------------------------------------------------------------
# DAG Definition
# -------------------------------------------------------------------

with DAG(
    'kubeflow_user_onboarding',
    default_args=default_args,
    schedule_interval=None,
    tags=['kubeflow', 'admin', 'onboarding'],
    params={
        "username": Param(
            default="new-user@example.com", 
            type="string", 
            title="사용자 이메일",
            minLength=5
        ),
        "project_team": Param(
            default="team-medical-ai", 
            type="string", 
            title="소속 팀 (Namespace)",
            description="권한을 부여할 공유 프로젝트 이름"
        ),
        "gpu_limit": Param(
            default=1, 
            type="integer", 
            title="GPU 할당량", 
            minimum=0, 
            maximum=8
        )
    },
    access_control={
        'NT_Team': {'can_read', 'can_edit'}  # 읽기 + 실행 권한 부여
    }
) as dag:

    # 1. 프로필 생성
    t1_create_profile = PythonOperator(
        task_id='create_personal_workspace',
        python_callable=create_kubeflow_profile,
    )

    # 2. 프로젝트 할당
    t2_assign_project = PythonOperator(
        task_id='assign_shared_project_access',
        python_callable=assign_shared_project,
    )

    # 3. (내부) 메일링 리스트 등록
    t3_add_db = PythonOperator(
        task_id='register_mailing_list_db',
        python_callable=add_to_mailing_list_db,
    )

    # 4. 실제 이메일 발송
    t4_send_email = EmailOperator(
        task_id='send_welcome_email',
        to='{{ params.username }}',
        subject='[Kubeflow] 계정 생성이 완료되었습니다.',
        html_content="""
        <h3>🎉 환영합니다!</h3>
        <p>요청하신 AI 개발 환경 구성이 완료되었습니다.</p>
        <hr>
        <ul>
            <li><b>ID:</b> {{ params.username }}</li>
            <li><b>Namespace:</b> {{ params.username | replace("@", "-") | replace(".", "-") }}</li>
            <li><b>GPU Quota:</b> {{ params.gpu_limit }}개</li>
            <li><b>Assigned Team:</b> {{ params.project_team }}</li>
        </ul>
        <p>지금 바로 <a href="https://kubeflow.your-company.com">Kubeflow 대시보드</a>에 접속해보세요.</p>
        """
    )

    # 실행 순서 연결
    t1_create_profile >> t2_assign_project >> t3_add_db >> t4_send_email