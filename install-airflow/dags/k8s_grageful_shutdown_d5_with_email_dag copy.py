"""
Kubernetes 5-Day Graceful Shutdown DAG (With Email Notification)

[진행 순서]
- D-5: [이메일] 종료 5일 전 알림 (백업 권고)
- [24시간 대기]
- D-4: [이메일] 종료 4일 전 알림 (내일부터 신규 할당 중단 예고)
- [24시간 대기]
- D-3: [Action] Cordon (신규 파드 생성 금지)
- [24시간 대기]
- D-2: [Action] Soft Drain (안전한 축출)
- [24시간 대기]
- D-1: [Action] Force Drain (강제 종료)
- [24시간 대기]
- D-0: [Action] Final Shutdown (클러스터 종료)
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.email import EmailOperator
from airflow.sensors.time_delta import TimeDeltaSensor
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
    'retry_delay': timedelta(minutes=5),
}

# -------------------------------------------------------------------
# K8s Helper Functions (Action Logic)
# -------------------------------------------------------------------

def get_k8s_client():
    try:
        config.load_incluster_config()
    except config.ConfigException:
        # 로컬 테스트용 (경로 수정 필요)
        config.load_kube_config(config_file='/opt/airflow/config/kubeconfig')
    return client.CoreV1Api()

def cordon_all_nodes_func(**context):
    """[D-3] 모든 노드 Cordon"""
    v1 = get_k8s_client()
    nodes = v1.list_node()
    logger.info("Starting D-3 Action: CORDON all nodes...")
    
    for node in nodes.items:
        node_name = node.metadata.name
        if node.spec.unschedulable:
            continue
        try:
            body = {"spec": {"unschedulable": True}}
            v1.patch_node(node_name, body)
            logger.info(f"Node {node_name} cordoned.")
        except client.exceptions.ApiException as e:
            logger.error(f"Failed to cordon {node_name}: {e}")

def drain_nodes_func(force=False, **context):
    """[D-2 & D-1] 노드 Drain (Soft vs Hard)"""
    mode_str = "FORCE DRAIN (D-1)" if force else "SOFT DRAIN (D-2)"
    logger.info(f"Starting {mode_str}...")
    
    v1 = get_k8s_client()
    nodes = v1.list_node()
    
    for node in nodes.items:
        node_name = node.metadata.name
        field_selector = f"spec.nodeName={node_name}"
        pods = v1.list_pod_for_all_namespaces(field_selector=field_selector)
        
        for pod in pods.items:
            # DaemonSet 등은 스킵하는 로직 포함 (간략화)
            if any(o.kind == 'DaemonSet' for o in (pod.metadata.owner_references or [])):
                continue

            try:
                if force:
                    v1.delete_namespaced_pod(
                        name=pod.metadata.name,
                        namespace=pod.metadata.namespace,
                        body=client.V1DeleteOptions(grace_period_seconds=0)
                    )
                else:
                    eviction = client.V1Eviction(
                        metadata=client.V1ObjectMeta(name=pod.metadata.name, namespace=pod.metadata.namespace),
                        delete_options=client.V1DeleteOptions(grace_period_seconds=60)
                    )
                    v1.create_namespaced_pod_eviction(
                        name=pod.metadata.name,
                        namespace=pod.metadata.namespace,
                        body=eviction
                    )
            except Exception as e:
                logger.warning(f"Error processing pod {pod.metadata.name}: {e}")

def final_shutdown_measure(**context):
    """[D-0] 최종 종료"""
    logger.info("!!! FINAL SHUTDOWN !!! Cluster is now safe to terminate.")

# -------------------------------------------------------------------
# DAG Definition
# -------------------------------------------------------------------

with DAG(
    'k8s_5day_shutdown_with_email',
    default_args=default_args,
    description='5-Day Graceful Shutdown with Email Notifications',
    schedule_interval=None,
    catchup=False,
    tags=['maintenance', 'shutdown', 'email'],
    
    # [핵심] 실행 시 이메일 주소를 입력받는 폼(Form) 설정
    params={
        "receiver_email": Param(
            default="admin@company.com", 
            type="string", 
            title="수신자 이메일 (Notification Receiver)",
            description="D-5, D-4 등 주요 단계마다 알림을 받을 이메일 주소입니다."
        )
    }
) as dag:

    # --- D-5: 공지 이메일 발송 ---
    d5_email = EmailOperator(
        task_id='d5_notify_backup',
        to='{{ params.receiver_email }}', # 입력받은 파라미터 사용
        subject='[D-5 Notice] Kubernetes 클러스터 종료 5일 전 알림',
        html_content="""
        <h3>🚨 클러스터 종료 카운트다운 시작 (D-5)</h3>
        <p>안녕하세요, MLOps Admin입니다.</p>
        <p>유지보수를 위해 <b>5일 뒤 클러스터가 완전히 종료될 예정</b>입니다.</p>
        <hr>
        <h4>[사용자 조치 사항]</h4>
        <ul>
            <li><b>데이터 백업:</b> 중요한 모델 가중치(Checkpoints)와 데이터셋을 S3/NAS로 백업하십시오.</li>
            <li><b>작업 정리:</b> 장기 실행 학습(Long-running Job)은 조기에 마무리해 주시기 바랍니다.</li>
        </ul>
        <p>감사합니다.</p>
        """
    )

    wait_d5_to_d4 = TimeDeltaSensor(
        task_id='wait_24h_d5_to_d4',
        delta=timedelta(days=1),
        mode='reschedule'
    )

    # --- D-4: 경고 이메일 발송 ---
    d4_email = EmailOperator(
        task_id='d4_notify_scheduling_stop',
        to='{{ params.receiver_email }}',
        subject='[D-4 Warning] 내일부터 신규 자원 할당이 중단됩니다',
        html_content="""
        <h3>⚠️ 신규 작업 생성 제한 예고 (D-4)</h3>
        <p>클러스터 종료 4일 전입니다.</p>
        <p><b>내일(D-3)부터 모든 노드가 Cordon 처리되어, 새로운 Pod 생성이 불가능합니다.</b></p>
        <hr>
        <ul>
            <li>현재 실행 중인 작업은 유지되지만, 내일부터는 실행되지 않습니다.</li>
            <li>배포 파이프라인(CI/CD)을 잠시 중단해 주십시오.</li>
        </ul>
        """
    )

    wait_d4_to_d3 = TimeDeltaSensor(
        task_id='wait_24h_d4_to_d3',
        delta=timedelta(days=1),
        mode='reschedule'
    )

    # --- D-3: Cordon ---
    d3_cordon = PythonOperator(
        task_id='d3_cordon_nodes',
        python_callable=cordon_all_nodes_func,
    )

    wait_d3_to_d2 = TimeDeltaSensor(
        task_id='wait_24h_d3_to_d2',
        delta=timedelta(days=1),
        mode='reschedule'
    )

    # --- D-2: Soft Drain ---
    d2_soft_drain = PythonOperator(
        task_id='d2_soft_drain',
        python_callable=drain_nodes_func,
        op_kwargs={'force': False},
    )

    wait_d2_to_d1 = TimeDeltaSensor(
        task_id='wait_24h_d2_to_d1',
        delta=timedelta(days=1),
        mode='reschedule'
    )

    # --- D-1: Hard Drain ---
    d1_hard_drain = PythonOperator(
        task_id='d1_hard_drain',
        python_callable=drain_nodes_func,
        op_kwargs={'force': True},
    )

    wait_d1_to_d0 = TimeDeltaSensor(
        task_id='wait_24h_d1_to_d0',
        delta=timedelta(days=1),
        mode='reschedule'
    )

    # --- D-0: Final Shutdown & 완료 메일 ---
    d0_shutdown = PythonOperator(
        task_id='d0_final_shutdown',
        python_callable=final_shutdown_measure,
    )
    
    d0_email = EmailOperator(
        task_id='d0_notify_complete',
        to='{{ params.receiver_email }}',
        subject='[D-0 Final] 클러스터 종료 프로세스 완료',
        html_content="""
        <h3>🔴 클러스터 종료 완료</h3>
        <p>모든 노드의 Pod가 정리되었으며, 인프라 종료 준비가 끝났습니다.</p>
        <p>이제 인스턴스 전원을 내리셔도 안전합니다.</p>
        """
    )

    # --- 실행 순서 연결 ---
    d5_email >> wait_d5_to_d4 >> \
    d4_email >> wait_d4_to_d3 >> \
    d3_cordon >> wait_d3_to_d2 >> \
    d2_soft_drain >> wait_d2_to_d1 >> \
    d1_hard_drain >> wait_d1_to_d0 >> \
    d0_shutdown >> d0_email