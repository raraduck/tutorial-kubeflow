"""
Kubernetes Cluster Startup DAG (With Email Notification)

[진행 순서]
- 1. [이메일] 클러스터 복구 시작 알림
- 2. [Action] Uncordon (모든 노드의 스케줄링 제한 해제)
- 3. [이메일] 클러스터 정상화 완료 및 사용 안내 알림
"""

from datetime import datetime
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.email import EmailOperator
from airflow.models.param import Param
from kubernetes import client, config
import logging

# 로거 설정
logger = logging.getLogger(__name__)

default_args = {
    'owner': 'admin',
    'depends_on_past': False,
    'start_date': datetime(2025, 1, 1),
    'retries': 1,
}

# -------------------------------------------------------------------
# K8s Helper Functions (Action Logic)
# -------------------------------------------------------------------

def get_k8s_client():
    try:
        config.load_incluster_config()
    except config.ConfigException:
        # 로컬/외부에서 실행 시
        config.load_kube_config(config_file='/opt/airflow/config/kubeconfig')
    return client.CoreV1Api()

def uncordon_all_nodes_func(**context):
    """모든 노드의 Cordon 상태를 해제 (Uncordon)"""
    v1 = get_k8s_client()
    nodes = v1.list_node()
    logger.info("Starting Action: UNCORDON all nodes...")
    
    uncordoned_count = 0
    for node in nodes.items:
        node_name = node.metadata.name
        
        # unschedulable이 True로 설정되어 있는 노드만 대상으로 함
        if node.spec.unschedulable:
            try:
                # unschedulable 속성을 False로 변경하여 스케줄링 허용
                body = {"spec": {"unschedulable": False}}
                v1.patch_node(node_name, body)
                logger.info(f"Node {node_name} successfully uncordoned.")
                uncordoned_count += 1
            except client.exceptions.ApiException as e:
                logger.error(f"Failed to uncordon {node_name}: {e}")
        else:
            logger.info(f"Node {node_name} is already schedulable. Skipping.")
            
    logger.info(f"Total {uncordoned_count} nodes have been uncordoned.")

# -------------------------------------------------------------------
# DAG Definition
# -------------------------------------------------------------------

with DAG(
    'k8s_cluster_startup_with_email_v1',
    default_args=default_args,
    description='Restore and Uncordon Kubernetes Cluster with Email Notifications',
    schedule_interval=None, # 수동 실행
    catchup=False,
    tags=['maintenance', 'startup', 'email'],
    
    params={
        "receiver_email": Param(
            default="admin@company.com", 
            type="string", 
            title="수신자 이메일 (Notification Receiver)",
            description="클러스터 복구 시작 및 완료 알림을 받을 이메일 주소입니다."
        )
    },
    access_control={
        'K8s_Team': {'can_read', 'can_edit'},
        # 'KF_Team': {'can_read', 'can_edit'}
    }
) as dag:

    # --- 1. 복구 시작 이메일 ---
    notify_startup_started = EmailOperator(
        task_id='notify_startup_started',
        to='{{ params.receiver_email }}',
        subject='[Notice] Kubernetes 클러스터 복구 작업 시작',
        html_content="""
        <h3>🟢 클러스터 복구 작업 시작</h3>
        <p>안녕하세요, MLOps Admin입니다.</p>
        <p>유지보수가 완료되어 <b>클러스터 복구(Uncordon) 작업을 시작</b>합니다.</p>
        <p>곧 모든 파드(Pod)가 정상적으로 노드에 할당되어 서비스가 재개될 예정입니다.</p>
        """
    )

    # --- 2. Uncordon 실행 ---
    uncordon_nodes = PythonOperator(
        task_id='uncordon_all_nodes',
        python_callable=uncordon_all_nodes_func,
    )

    # --- 3. 복구 완료 이메일 ---
    # Uncordon 명령이 K8s API 서버에 성공적으로 전달되면 곧바로 스케줄링이 시작되므로,
    # 바로 완료 메일을 보내도 무방합니다. (실제 파드 구동까지는 수 분이 소요될 수 있음)
    notify_startup_completed = EmailOperator(
        task_id='notify_startup_completed',
        to='{{ params.receiver_email }}',
        subject='[Complete] Kubernetes 클러스터 정상화 완료',
        html_content="""
        <h3>✅ 클러스터 정상화 완료</h3>
        <p>모든 노드의 스케줄링 제한이 해제되었습니다.</p>
        <hr>
        <h4>[사용자 안내 사항]</h4>
        <ul>
            <li>대기(Pending) 중이던 작업과 서비스가 순차적으로 실행(Running) 모드로 전환됩니다.</li>
            <li>서비스 규모에 따라 모든 파드가 정상화되는 데 <b>약 5~10분 정도 소요</b>될 수 있습니다.</li>
            <li>이제 새로운 파이프라인이나 학습 작업을 제출하셔도 됩니다.</li>
        </ul>
        <p>감사합니다.</p>
        """
    )

    # --- 실행 순서 연결 ---
    notify_startup_started >> uncordon_nodes >> notify_startup_completed