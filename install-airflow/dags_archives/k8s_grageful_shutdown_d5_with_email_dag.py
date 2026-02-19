"""
Kubernetes 5-Day Graceful Shutdown DAG (With Email Notification & Dynamic Wait)

[진행 순서]
- D-5: [이메일] 종료 5일 전 알림 (백업 권고)
- [대기] 입력한 시간(Hour)만큼 대기
- D-4: [이메일] 종료 4일 전 알림 (내일부터 신규 할당 중단 예고)
- [대기] 입력한 시간(Hour)만큼 대기
- D-3: [Action] Cordon (신규 파드 생성 금지)
- [대기] 입력한 시간(Hour)만큼 대기
- D-2: [Action] Soft Drain (안전한 축출)
- [대기] 입력한 시간(Hour)만큼 대기
- D-1: [Action] Force Drain (강제 종료)
- [대기] 입력한 시간(Hour)만큼 대기
- D-0: [Action] Final Shutdown (클러스터 종료)
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.email import EmailOperator
from airflow.sensors.python import PythonSensor
from airflow.models.param import Param
from airflow.utils import timezone
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
# Helper Functions (Wait Logic)
# -------------------------------------------------------------------

def check_wait_time(prev_task_id, param_name, **context):
    """이전 태스크의 종료 시간을 기준으로 파라미터로 입력받은 시간(Hour)만큼 대기"""
    # 이전 태스크의 정보 가져오기
    ti = context['dag_run'].get_task_instance(prev_task_id)
    if not ti or not ti.end_date:
        return False
        
    # 파라미터에서 대기 시간(시간 단위) 가져오기
    wait_hours = float(context['params'].get(param_name, 24))
    
    # 목표 실행 시간 = 이전 태스크 종료 시간 + 대기 시간
    target_time = ti.end_date + timedelta(hours=wait_hours)
    
    logger.info(f"[{prev_task_id}] 종료 시간: {ti.end_date}")
    logger.info(f"대기 설정 시간: {wait_hours} 시간")
    logger.info(f"목표 다음 실행 시간: {target_time} | 현재 시간: {timezone.utcnow()}")
    
    # 현재 시간이 목표 시간을 넘었으면 True 반환하여 다음 태스크로 진행
    return timezone.utcnow() >= target_time


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
            # DaemonSet 등은 스킵
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
    'k8s_5day_shutdown_with_email_v2',
    default_args=default_args,
    description='Graceful Shutdown with Dynamic Wait Times & Email',
    schedule_interval=None,
    catchup=False,
    tags=['maintenance', 'shutdown', 'email'],
    
    # 실행 시 입력받는 폼(Form) 설정
    params={
        "receiver_email": Param(
            default="admin@company.com", 
            type="string", 
            title="수신자 이메일 (Notification Receiver)",
        ),
        "wait_hours_d5_to_d4": Param(
            default=24, 
            type="number", 
            title="D-5 -> D-4 대기(시간)",
            description="소수점 입력 가능 (예: 0.5 입력 시 30분 대기)"
        ),
        "wait_hours_d4_to_d3": Param(
            default=24, type="number", title="D-4 -> D-3 대기(시간)"
        ),
        "wait_hours_d3_to_d2": Param(
            default=24, type="number", title="D-3 -> D-2 대기(시간)"
        ),
        "wait_hours_d2_to_d1": Param(
            default=24, type="number", title="D-2 -> D-1 대기(시간)"
        ),
        "wait_hours_d1_to_d0": Param(
            default=24, type="number", title="D-1 -> D-0 대기(시간)"
        ),
    },
    access_control={
        'K8s_Team': {'can_read', 'can_edit'},
        'KF_Team': {'can_read', 'can_edit'}
    }
) as dag:

    # --- D-5: 공지 이메일 발송 ---
    d5_email = EmailOperator(
        task_id='d5_notify_backup',
        to='{{ params.receiver_email }}',
        subject='[D-5 Notice] Kubernetes 클러스터 종료 5일 전 알림',
        html_content="<h3>🚨 클러스터 종료 카운트다운 시작 (D-5)</h3><p>유지보수를 위해 5일 뒤 클러스터가 완전히 종료될 예정입니다.</p>"
    )

    wait_d5_to_d4 = PythonSensor(
        task_id='wait_d5_to_d4',
        python_callable=check_wait_time,
        op_kwargs={'prev_task_id': 'd5_notify_backup', 'param_name': 'wait_hours_d5_to_d4'},
        mode='reschedule', poke_interval=60 # 5분 주기로 체크
    )

    # --- D-4: 경고 이메일 발송 ---
    d4_email = EmailOperator(
        task_id='d4_notify_scheduling_stop',
        to='{{ params.receiver_email }}',
        subject='[D-4 Warning] 내일부터 신규 자원 할당이 중단됩니다',
        html_content="<h3>⚠️ 신규 작업 생성 제한 예고 (D-4)</h3><p>내일(D-3)부터 모든 노드가 Cordon 처리되어, 새로운 Pod 생성이 불가능합니다.</p>"
    )

    wait_d4_to_d3 = PythonSensor(
        task_id='wait_d4_to_d3',
        python_callable=check_wait_time,
        op_kwargs={'prev_task_id': 'd4_notify_scheduling_stop', 'param_name': 'wait_hours_d4_to_d3'},
        mode='reschedule', poke_interval=60
    )

    # --- D-3: Cordon ---
    d3_cordon = PythonOperator(
        task_id='d3_cordon_nodes',
        python_callable=cordon_all_nodes_func,
    )

    wait_d3_to_d2 = PythonSensor(
        task_id='wait_d3_to_d2',
        python_callable=check_wait_time,
        op_kwargs={'prev_task_id': 'd3_cordon_nodes', 'param_name': 'wait_hours_d3_to_d2'},
        mode='reschedule', poke_interval=60
    )

    # --- D-2: Soft Drain ---
    d2_soft_drain = PythonOperator(
        task_id='d2_soft_drain',
        python_callable=drain_nodes_func,
        op_kwargs={'force': False},
    )

    wait_d2_to_d1 = PythonSensor(
        task_id='wait_d2_to_d1',
        python_callable=check_wait_time,
        op_kwargs={'prev_task_id': 'd2_soft_drain', 'param_name': 'wait_hours_d2_to_d1'},
        mode='reschedule', poke_interval=60
    )

    # --- D-1: Hard Drain ---
    d1_hard_drain = PythonOperator(
        task_id='d1_hard_drain',
        python_callable=drain_nodes_func,
        op_kwargs={'force': True},
    )

    wait_d1_to_d0 = PythonSensor(
        task_id='wait_d1_to_d0',
        python_callable=check_wait_time,
        op_kwargs={'prev_task_id': 'd1_hard_drain', 'param_name': 'wait_hours_d1_to_d0'},
        mode='reschedule', poke_interval=60
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
        html_content="<h3>🔴 클러스터 종료 완료</h3><p>모든 인프라 종료 준비가 끝났습니다.</p>"
    )

    # --- 실행 순서 연결 ---
    d5_email >> wait_d5_to_d4 >> \
    d4_email >> wait_d4_to_d3 >> \
    d3_cordon >> wait_d3_to_d2 >> \
    d2_soft_drain >> wait_d2_to_d1 >> \
    d1_hard_drain >> wait_d1_to_d0 >> \
    d0_shutdown >> d0_email