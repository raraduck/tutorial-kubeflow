"""
Kubernetes 5-Day Graceful Shutdown DAG

[진행 순서]
- Day 5: [알림] 종료 5일 전 알림, 데이터 백업 권고
- [24시간 대기]
- Day 4: [알림] 종료 4일 전 알림, 내일부터 신규 자원 할당 중단 예고
- [24시간 대기]
- Day 3: [Action] Cordon All Nodes (신규 Pod 스케줄링 금지)
- [24시간 대기]
- Day 2: [Action] Soft Drain (1차: 안전한 축출, PDB 준수)
- [24시간 대기]
- Day 1: [Action] Force Drain (2차: 강제 종료, GracePeriod=0)
- [24시간 대기]
- Day 0: [Action] Final Shutdown (클러스터/인스턴스 종료)
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.sensors.time_delta import TimeDeltaSensor
from kubernetes import client, config
import logging

# 로거 설정
logger = logging.getLogger(__name__)

default_args = {
    'owner': 'admin',
    'depends_on_past': False,
    'start_date': datetime(2025, 1, 1),
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

# -------------------------------------------------------------------
# Helper Functions (Notification & K8s)
# -------------------------------------------------------------------

def send_notification_func(day_label, message, **context):
    """
    사용자에게 알림을 보내는 함수 (Slack, Email 등 연동 포인트)
    """
    logger.info("=" * 50)
    logger.info(f"[D-{day_label} Notification]")
    logger.info(f"Message: {message}")
    logger.info("=" * 50)
    
    # [실제 구현 가이드]
    # 여기에 SlackWebhookOperator 로직이나 Email 발송 코드를 넣으세요.
    # 예: requests.post(slack_webhook_url, json={"text": message})
    pass

def get_k8s_client():
    """Kubeconfig 로드 및 API 클라이언트 반환"""
    try:
        config.load_incluster_config()
    except config.ConfigException:
        # 로컬 테스트용 경로 (환경에 맞게 수정)
        config.load_kube_config(config_file='/opt/airflow/config/kubeconfig')
    return client.CoreV1Api()

def cordon_all_nodes_func(**context):
    """[Day 3] 모든 노드 Cordon (Scheduling Disabled)"""
    v1 = get_k8s_client()
    nodes = v1.list_node()
    logger.info("Starting Day 3 Action: CORDON all nodes...")
    
    for node in nodes.items:
        node_name = node.metadata.name
        if node.spec.unschedulable:
            logger.info(f"Node {node_name} is already cordoned.")
            continue
        try:
            body = {"spec": {"unschedulable": True}}
            v1.patch_node(node_name, body)
            logger.info(f"Node {node_name} cordoned successfully.")
        except client.exceptions.ApiException as e:
            logger.error(f"Failed to cordon node {node_name}: {e}")

def drain_nodes_func(force=False, **context):
    """[Day 2 & Day 1] 노드 Drain 수행 (Soft vs Hard)"""
    mode_str = "FORCE DRAIN (Day 1)" if force else "SOFT DRAIN (Day 2)"
    logger.info(f"Starting {mode_str}...")
    
    v1 = get_k8s_client()
    nodes = v1.list_node()
    
    for node in nodes.items:
        node_name = node.metadata.name
        # 노드별 Pod 조회
        field_selector = f"spec.nodeName={node_name}"
        pods = v1.list_pod_for_all_namespaces(field_selector=field_selector)
        
        for pod in pods.items:
            namespace = pod.metadata.namespace
            pod_name = pod.metadata.name
            
            # DaemonSet/Mirror Pod 스킵
            owner_refs = pod.metadata.owner_references or []
            if any(o.kind == 'DaemonSet' for o in owner_refs) or \
               'kubernetes.io/config.mirror' in pod.metadata.annotations:
                continue

            try:
                if force:
                    # Day 1: 강제 종료
                    v1.delete_namespaced_pod(
                        name=pod_name,
                        namespace=namespace,
                        body=client.V1DeleteOptions(grace_period_seconds=0)
                    )
                    logger.info(f"[Force] Deleted pod {pod_name}")
                else:
                    # Day 2: Eviction 요청
                    eviction = client.V1Eviction(
                        metadata=client.V1ObjectMeta(name=pod_name, namespace=namespace),
                        delete_options=client.V1DeleteOptions(grace_period_seconds=60)
                    )
                    v1.create_namespaced_pod_eviction(
                        name=pod_name,
                        namespace=namespace,
                        body=eviction
                    )
                    logger.info(f"[Soft] Evicted pod {pod_name}")
            except client.exceptions.ApiException as e:
                if e.status != 404: # 이미 없는 경우 제외하고 로깅
                    logger.warning(f"Failed to process pod {pod_name}: {e}")

def final_shutdown_measure(**context):
    """[Day 0] 최종 종료"""
    logger.info("=" * 50)
    logger.info("!!! FINAL SHUTDOWN DAY !!!")
    logger.info("Cluster resource cleanup complete. Proceeding to terminate infra.")
    logger.info("=" * 50)

# -------------------------------------------------------------------
# DAG Definition
# -------------------------------------------------------------------

with DAG(
    'k8s_5day_shutdown_procedure',
    default_args=default_args,
    description='5일에 걸친 Kubernetes Graceful Shutdown',
    schedule_interval=None, 
    catchup=False,
    tags=['maintenance', 'shutdown', 'kubernetes'],
    # access_control={
    #     'NT_Team': {'can_read', 'can_edit'}  # 읽기 + 실행 권한 부여
    # }
) as dag:

    # --- Day 5: Notification ---
    task_d5_notify = PythonOperator(
        task_id='d5_notify_backup_start',
        python_callable=send_notification_func,
        op_kwargs={
            'day_label': '5',
            'message': '클러스터 종료 5일 전입니다. 중요 데이터를 백업하고 종료를 준비하세요.'
        }
    )

    wait_d5_to_d4 = TimeDeltaSensor(
        task_id='wait_24h_d5_to_d4',
        delta=timedelta(days=1),
        mode='reschedule'
    )

    # --- Day 4: Notification (Warning) ---
    task_d4_notify = PythonOperator(
        task_id='d4_notify_scheduling_stop_soon',
        python_callable=send_notification_func,
        op_kwargs={
            'day_label': '4',
            'message': '클러스터 종료 4일 전입니다. 내일부터 신규 자원 할당이 중단(Cordon)됩니다.'
        }
    )

    wait_d4_to_d3 = TimeDeltaSensor(
        task_id='wait_24h_d4_to_d3',
        delta=timedelta(days=1),
        mode='reschedule'
    )

    # --- Day 3: Action (Cordon) ---
    task_d3_cordon = PythonOperator(
        task_id='d3_cordon_nodes',
        python_callable=cordon_all_nodes_func,
    )

    wait_d3_to_d2 = TimeDeltaSensor(
        task_id='wait_24h_d3_to_d2',
        delta=timedelta(days=1),
        mode='reschedule'
    )

    # --- Day 2: Action (Soft Drain) ---
    task_d2_soft_drain = PythonOperator(
        task_id='d2_soft_drain',
        python_callable=drain_nodes_func,
        op_kwargs={'force': False},
    )

    wait_d2_to_d1 = TimeDeltaSensor(
        task_id='wait_24h_d2_to_d1',
        delta=timedelta(days=1),
        mode='reschedule'
    )

    # --- Day 1: Action (Hard Drain) ---
    task_d1_hard_drain = PythonOperator(
        task_id='d1_hard_drain',
        python_callable=drain_nodes_func,
        op_kwargs={'force': True},
    )

    wait_d1_to_d0 = TimeDeltaSensor(
        task_id='wait_24h_d1_to_d0',
        delta=timedelta(days=1),
        mode='reschedule'
    )

    # --- Day 0: Final Shutdown ---
    task_d0_shutdown = PythonOperator(
        task_id='d0_final_shutdown',
        python_callable=final_shutdown_measure,
    )

    # --- Flow 구성 ---
    task_d5_notify >> wait_d5_to_d4 >> \
    task_d4_notify >> wait_d4_to_d3 >> \
    task_d3_cordon >> wait_d3_to_d2 >> \
    task_d2_soft_drain >> wait_d2_to_d1 >> \
    task_d1_hard_drain >> wait_d1_to_d0 >> \
    task_d0_shutdown