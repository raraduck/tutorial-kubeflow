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
# Helper Functions (Wait Logic & Time Formatting)
# -------------------------------------------------------------------

def format_wait_time(hours_float):
    """소수점 형태의 시간(Hour)을 'X시간 Y분' 포맷의 문자열로 변환합니다."""
    total_minutes = int(float(hours_float) * 60)
    hours = total_minutes // 60
    minutes = total_minutes % 60
    
    result = []
    if hours > 0:
        result.append(f"{hours}시간")
    if minutes > 0:
        result.append(f"{minutes}분")
        
    return " ".join(result) if result else "즉시(0분)"

def check_wait_time(prev_task_id, param_name, **context):
    """이전 태스크의 종료 시간을 기준으로 파라미터로 입력받은 시간(Hour)만큼 대기"""
    ti = context['dag_run'].get_task_instance(prev_task_id)
    if not ti or not ti.end_date:
        return False
        
    wait_hours = float(context['params'].get(param_name, 24))
    target_time = ti.end_date + timedelta(hours=wait_hours)
    
    logger.info(f"[{prev_task_id}] 종료 시간: {ti.end_date}")
    logger.info(f"대기 설정 시간: {wait_hours} 시간")
    logger.info(f"목표 다음 실행 시간: {target_time} | 현재 시간: {timezone.utcnow()}")
    
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
    'k8s_dynamic_shutdown_with_email',
    default_args=default_args,
    description='Graceful Shutdown with Dynamic Wait Times & Email',
    schedule_interval=None,
    catchup=False,
    tags=['maintenance', 'shutdown', 'email'],
    # 사용자 정의 매크로 등록 (템플릿에서 format_time 사용 가능)
    user_defined_macros={
        'format_time': format_wait_time
    },
    params={
        "receiver_email": Param(
            default="admin@company.com", 
            type="string", 
            title="수신자 이메일 (Notification Receiver)",
            description="단계별 진행 상황 및 알림을 수신할 담당자의 이메일 주소를 입력하세요."
        ),
        "wait_hours_d5_to_d4": Param(
            default=24, type="number", title="1단계 -> 2단계 대기 (시간)",
            description="[현재] 종료 1차 안내 메일 발송 → [다음] '신규 할당 중단 예고 메일' 발송 전까지 대기합니다. (소수점 입력 가능. 예: 0.5 = 30분)"
        ),
        "wait_hours_d4_to_d3": Param(
            default=24, type="number", title="2단계 -> 3단계 대기 (시간)",
            description="[현재] 신규 할당 중단 예고 메일 발송 → [다음] 'Cordon (신규 파드 생성 금지)' 조치 전까지 대기합니다."
        ),
        "wait_hours_d3_to_d2": Param(
            default=24, type="number", title="3단계 -> 4단계 대기 (시간)",
            description="[현재] Cordon 조치 완료 → [다음] 'Soft Drain (기존 파드 안전 축출)' 조치 전까지 대기합니다."
        ),
        "wait_hours_d2_to_d1": Param(
            default=24, type="number", title="4단계 -> 5단계 대기 (시간)",
            description="[현재] Soft Drain 조치 완료 → [다음] 'Hard Drain (남은 파드 강제 종료)' 조치 전까지 대기합니다."
        ),
        "wait_hours_d1_to_d0": Param(
            default=24, type="number", title="5단계 -> 최종 완료 대기 (시간)",
            description="[현재] Hard Drain 조치 완료 → [다음] '최종 클러스터 종료(Final Shutdown) 선언 및 완료 메일' 발송 전까지 대기합니다."
        ),
    },
    access_control={
        'K8s_Team': {'can_read', 'can_edit'},
        # 'KF_Team': {'can_read', 'can_edit'}
    }
) as dag:

    # --- D-5: 공지 이메일 발송 ---
    d5_email = EmailOperator(
        task_id='d5_notify_backup',
        to='{{ params.receiver_email }}',
        subject='[Phase 1] Kubernetes 클러스터 유지보수 프로세스 시작 알림',
        # 사용자 정의 매크로(format_time)를 활용해 대기 시간 동적 계산
        html_content="""
        <h3>🚨 클러스터 종료 프로세스가 시작되었습니다.</h3>
        <p>유지보수를 위해 클러스터 안전 종료 시퀀스가 가동되었습니다. 필요한 데이터는 사전에 백업해 주시길 권고합니다.</p>
        <p><b>다음 단계 예정 시간:</b> {{ format_time(params.wait_hours_d5_to_d4) }} 뒤에 다음 단계(신규 자원 할당 중단 예고)가 진행됩니다.</p>
        """
    )

    wait_d5_to_d4 = PythonSensor(
        task_id='wait_d5_to_d4',
        python_callable=check_wait_time,
        op_kwargs={'prev_task_id': 'd5_notify_backup', 'param_name': 'wait_hours_d5_to_d4'},
        mode='reschedule', poke_interval=60
    )

    # --- D-4: 경고 이메일 발송 ---
    d4_email = EmailOperator(
        task_id='d4_notify_scheduling_stop',
        to='{{ params.receiver_email }}',
        subject='[Phase 2] 신규 자원 할당 중단 예고',
        html_content="""
        <h3>⚠️ 신규 작업 생성 제한 예고</h3>
        <p><b>{{ format_time(params.wait_hours_d4_to_d3) }}</b> 뒤에 모든 노드가 Cordon 처리되어, 새로운 파드(Pod) 생성이 전면 차단됩니다.</p>
        <p>현재 동작 중인 서비스는 당분간 유지되나, 신규 배포는 불가능해집니다.</p>
        """
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
        subject='[Phase Final] 클러스터 종료 프로세스 완료',
        html_content="""
        <h3>🔴 클러스터 종료 완료</h3>
        <p>모든 노드의 Cordon 및 Drain 작업이 정상적으로 마무리되었으며 인프라 종료 준비가 완료되었습니다.</p>
        """
    )

    # --- 실행 순서 연결 ---
    d5_email >> wait_d5_to_d4 >> \
    d4_email >> wait_d4_to_d3 >> \
    d3_cordon >> wait_d3_to_d2 >> \
    d2_soft_drain >> wait_d2_to_d1 >> \
    d1_hard_drain >> wait_d1_to_d0 >> \
    d0_shutdown >> d0_email