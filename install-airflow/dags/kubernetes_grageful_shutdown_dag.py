"""
Kubernetes 3-Day Graceful Shutdown DAG

[진행 순서]
- Day 3: Cordon All Nodes (새로운 Pod 스케줄링 금지)
- [24시간 대기]
- Day 2: Soft Drain (종료된 작업 확인 및 안전한 Pod 축출)
- [24시간 대기]
- Day 1: Force Drain (남아있는 모든 Pod 강제 종료)
- [24시간 대기]
- Day 0: Final Shutdown (최종 조치 및 완료 선언)
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
    'start_date': datetime(2026, 2, 9),
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

# -------------------------------------------------------------------
# Kubernetes Helper Functions
# -------------------------------------------------------------------

def get_k8s_client():
    """Kubeconfig 로드 및 API 클라이언트 반환"""
    try:
        # Airflow 내부에서 실행 시
        config.load_incluster_config()
    except config.ConfigException:
        # 로컬 개발 환경용 (경로는 환경에 맞게 수정)
        config.load_kube_config(config_file='/opt/airflow/config/kubeconfig')
    
    return client.CoreV1Api()

def cordon_all_nodes_func(**context):
    """
    [Day 3] 모든 노드에 Cordon 설정 (unschedulable=True)
    """
    v1 = get_k8s_client()
    nodes = v1.list_node()
    
    logger.info("Starting to CORDON all nodes...")
    
    for node in nodes.items:
        node_name = node.metadata.name
        
        # 이미 Cordon 상태인지 확인
        if node.spec.unschedulable:
            logger.info(f"Node {node_name} is already cordoned.")
            continue
            
        try:
            # Patch를 통해 unschedulable 설정
            body = {"spec": {"unschedulable": True}}
            v1.patch_node(node_name, body)
            logger.info(f"Node {node_name} cordoned successfully.")
        except client.exceptions.ApiException as e:
            logger.error(f"Failed to cordon node {node_name}: {e}")
            # 일부 노드 실패하더라도 진행 (필요시 raise)

def drain_nodes_func(force=False, **context):
    """
    [Day 2 & Day 1] 노드 Drain 수행
    - force=False (Day 2): 데몬셋 제외, 일반 Pod에 대해 안전한 Eviction 요청
    - force=True (Day 1): GracePeriod=0 으로 강제 삭제
    """
    v1 = get_k8s_client()
    nodes = v1.list_node()
    
    logger.info(f"Starting DRAIN (Force={force})...")
    
    for node in nodes.items:
        node_name = node.metadata.name
        logger.info(f"Processing node: {node_name}")
        
        # 해당 노드의 Pod 목록 조회
        field_selector = f"spec.nodeName={node_name}"
        pods = v1.list_pod_for_all_namespaces(field_selector=field_selector)
        
        for pod in pods.items:
            namespace = pod.metadata.namespace
            pod_name = pod.metadata.name
            
            # 1. DaemonSet 및 Mirror Pod 건너뛰기 (일반적인 Drain 로직)
            owner_refs = pod.metadata.owner_references or []
            is_daemonset = any(owner.kind == 'DaemonSet' for owner in owner_refs)
            is_mirror = 'kubernetes.io/config.mirror' in pod.metadata.annotations
            
            if is_daemonset or is_mirror:
                logger.info(f"Skipping DaemonSet/Mirror pod: {pod_name}")
                continue
                
            # 2. Pod 삭제/축출 시도
            try:
                if force:
                    logger.warning(f"Forcing deletion of pod {pod_name}")
                    v1.delete_namespaced_pod(
                        name=pod_name,
                        namespace=namespace,
                        body=client.V1DeleteOptions(grace_period_seconds=0)
                    )
                else:
                    logger.info(f"Attempting graceful eviction for pod {pod_name}")
                    # Eviction API 사용 (policy/v1beta1 or v1)
                    eviction_body = client.V1Eviction(
                        metadata=client.V1ObjectMeta(name=pod_name, namespace=namespace),
                        delete_options=client.V1DeleteOptions(grace_period_seconds=60) # 1분 대기
                    )
                    v1.create_namespaced_pod_eviction(
                        name=pod_name,
                        namespace=namespace,
                        body=eviction_body
                    )
            except client.exceptions.ApiException as e:
                if e.status == 404:
                    logger.info(f"Pod {pod_name} already gone.")
                elif e.status == 429: # Too Many Requests (PDB 걸림 등)
                    logger.warning(f"Eviction blocked for {pod_name} (likely PDB). Skipping for now.")
                else:
                    logger.error(f"Failed to evict/delete pod {pod_name}: {e}")

def final_shutdown_measure(**context):
    """
    [Day 0] 최종 종료 조치
    """
    logger.info("=" * 50)
    logger.info("FINAL SHUTDOWN SEQUENCE INITIATED")
    logger.info("All nodes should be cordoned and drained.")
    logger.info("Ready for infrastructure termination.")
    logger.info("=" * 50)
    # 실제 환경에서는 여기서 알림을 보내거나, 특정 클라우드 API를 호출해 인스턴스를 끌 수 있습니다.

# -------------------------------------------------------------------
# DAG Definition
# -------------------------------------------------------------------

with DAG(
    'k8s_3day_shutdown_procedure',
    default_args=default_args,
    description='3일에 걸친 Kubernetes Graceful Shutdown',
    schedule_interval=None, # schedule_interval='@once',  # 한 번만 실행
    catchup=False,
    tags=['maintenance', 'shutdown', 'kubernetes'],
) as dag:

    # --- Day 3: Cordon ---
    task_day3_cordon = PythonOperator(
        task_id='day3_cordon_all_nodes',
        python_callable=cordon_all_nodes_func,
    )

    # [Wait 24 Hours]
    wait_for_day2 = TimeDeltaSensor(
        task_id='wait_24h_for_day2',
        delta=timedelta(days=1),
        mode='reschedule',  # 중요: 대기 중 워커 슬롯 반납
    )

    # --- Day 2: Soft Drain ---
    task_day2_soft_drain = PythonOperator(
        task_id='day2_soft_drain_nodes',
        python_callable=drain_nodes_func,
        op_kwargs={'force': False},  # 부드러운 종료
    )

    # [Wait 24 Hours]
    wait_for_day1 = TimeDeltaSensor(
        task_id='wait_24h_for_day1',
        delta=timedelta(days=1),
        mode='reschedule',
    )

    # --- Day 1: Force Drain ---
    task_day1_force_drain = PythonOperator(
        task_id='day1_force_drain_nodes',
        python_callable=drain_nodes_func,
        op_kwargs={'force': True},   # 강제 종료
    )

    # [Wait 24 Hours]
    wait_for_day0 = TimeDeltaSensor(
        task_id='wait_24h_for_day0',
        delta=timedelta(days=1),
        mode='reschedule',
    )

    # --- Day 0: Final Shutdown ---
    task_day0_shutdown = PythonOperator(
        task_id='day0_final_shutdown',
        python_callable=final_shutdown_measure,
    )

    # --- 실행 순서 연결 ---
    task_day3_cordon >> wait_for_day2 >> \
    task_day2_soft_drain >> wait_for_day1 >> \
    task_day1_force_drain >> wait_for_day0 >> \
    task_day0_shutdown