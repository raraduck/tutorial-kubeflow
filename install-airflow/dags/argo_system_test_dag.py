"""
GPU Burn Workflow Replication DAG

Argo 명령어:
argo submit -n argo gpu-burn-workflow.yaml -p job-count=12 -p duration=600

위 기능을 Airflow로 구현:
- 입력받은 job_count 만큼 GPU Burn Pod를 병렬 생성
- 입력받은 duration 만큼 부하 테스트 실행
- 모든 Pod 완료 대기 및 로그 확인
- 종료 후 자동 삭제
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.models.param import Param
from kubernetes import client, config
import time
import logging

# 로거 설정
logger = logging.getLogger(__name__)

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2025, 1, 1),
    'retries': 0,
}

# -------------------------------------------------------------------
# K8s Helper Functions
# -------------------------------------------------------------------

def get_k8s_client():
    """Kubeconfig 로드 및 CoreV1Api 반환"""
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config(config_file='/opt/airflow/config/kubeconfig')
    return client.CoreV1Api()

def create_gpu_burn_pods(**context):
    """
    [Step 1] job_count 만큼 GPU Burn Pod 생성
    """
    params = context['params']
    job_count = int(params.get('job_count', 1))
    duration = int(params.get('duration', 60))
    namespace = 'argo'  # 사용자의 argo 네임스페이스에 맞춤

    v1 = get_k8s_client()
    created_pods = []

    logger.info(f"Starting creation of {job_count} GPU-Burn pods (Duration: {duration}s)...")

    for i in range(job_count):
        pod_name = f"gpu-burn-{context['ts_nodash']}-{i}"
        
        # GPU Burn Pod 매니페스트 정의
        pod_manifest = {
            'apiVersion': 'v1',
            'kind': 'Pod',
            'metadata': {
                'name': pod_name,
                'namespace': namespace,
                'labels': {
                    'app': 'gpu-burn-test',
                    'airflow-dag': context['dag'].dag_id,
                    'airflow-run': context['run_id']
                }
            },
            'spec': {
                'restartPolicy': 'Never',
                'containers': [{
                    'name': 'gpu-burn',
                    'image': 'wittten/gpu-burn:latest',  # 또는 사용 중인 gpu-burn 이미지
                    'args': [str(duration)],             # duration 전달
                    'resources': {
                        'limits': {
                            'nvidia.com/gpu': '1'        # Pod 당 GPU 1개 할당
                        }
                    }
                }]
            }
        }

        try:
            v1.create_namespaced_pod(namespace=namespace, body=pod_manifest)
            logger.info(f"Created Pod: {pod_name}")
            created_pods.append(pod_name)
        except client.exceptions.ApiException as e:
            logger.error(f"Failed to create pod {pod_name}: {e}")
            raise

    # 생성된 Pod 이름 목록을 XCom에 저장
    return created_pods

def wait_for_pods_completion(**context):
    """
    [Step 2] 생성된 모든 Pod가 완료될 때까지 대기
    """
    ti = context['ti']
    pod_names = ti.xcom_pull(task_ids='submit_gpu_burn_jobs')
    namespace = 'argo'
    v1 = get_k8s_client()

    logger.info(f"Waiting for {len(pod_names)} pods to complete...")
    
    # 최대 대기 시간 (duration + 여유분 5분)
    params = context['params']
    duration = int(params.get('duration', 60))
    max_wait_time = duration + 300 
    start_time = time.time()

    while True:
        if time.time() - start_time > max_wait_time:
            raise TimeoutError("Timeout waiting for GPU burn jobs.")

        all_done = True
        running_count = 0
        
        for pod_name in pod_names:
            try:
                pod = v1.read_namespaced_pod(name=pod_name, namespace=namespace)
                phase = pod.status.phase
                
                if phase in ['Pending', 'Running']:
                    all_done = False
                    running_count += 1
                elif phase == 'Failed':
                    logger.error(f"Pod {pod_name} FAILED!")
                    # 실패해도 다른 Pod 로그 확인을 위해 일단 진행하거나 여기서 에러 발생 가능
                
            except client.exceptions.ApiException as e:
                # Pod가 이미 삭제되었거나 에러 발생 시
                logger.warning(f"Error reading pod {pod_name}: {e}")

        if all_done:
            logger.info("All GPU burn jobs completed.")
            break
        
        logger.info(f"{running_count} pods still running...")
        time.sleep(10) # 10초 간격 폴링

def cleanup_pods(**context):
    """
    [Step 3] 테스트 완료 후 Pod 정리 (선택 사항)
    """
    ti = context['ti']
    pod_names = ti.xcom_pull(task_ids='submit_gpu_burn_jobs')
    namespace = 'argo'
    v1 = get_k8s_client()

    if not pod_names:
        return

    logger.info("Cleaning up pods...")
    for pod_name in pod_names:
        try:
            v1.delete_namespaced_pod(
                name=pod_name, 
                namespace=namespace,
                body=client.V1DeleteOptions(grace_period_seconds=0)
            )
            logger.info(f"Deleted {pod_name}")
        except Exception as e:
            logger.warning(f"Failed to delete {pod_name}: {e}")

# -------------------------------------------------------------------
# DAG Definition
# -------------------------------------------------------------------

with DAG(
    'k8s_gpu_burn_simulation',
    default_args=default_args,
    description='Replicate Argo submit gpu-burn workflow with K8s Python Client',
    schedule_interval=None,
    tags=['gpu', 'benchmark', 'k8s-client'],
    
    # [입력 폼 설정] 재생 버튼 누르면 이 창이 뜹니다.
    params={
        "job_count": Param(
            default=12, 
            type="integer", 
            title="Job Count (Pod 개수)",
            description="동시에 실행할 GPU Burn Pod의 개수입니다."
        ),
        "duration": Param(
            default=600, 
            type="integer", 
            title="Duration (초)",
            description="GPU 부하 테스트 지속 시간(초)입니다."
        )
    },
    access_control={
        'NT_Team': {'can_read', 'can_edit'}  # 읽기 + 실행 권한 부여
    }
) as dag:

    # 1. Pod 병렬 생성
    submit_jobs = PythonOperator(
        task_id='submit_gpu_burn_jobs',
        python_callable=create_gpu_burn_pods,
    )

    # 2. 완료 대기
    wait_jobs = PythonOperator(
        task_id='wait_for_completion',
        python_callable=wait_for_pods_completion,
    )

    # 3. 정리 (대기가 끝나면 실행)
    cleanup = PythonOperator(
        task_id='cleanup_pods',
        python_callable=cleanup_pods,
        trigger_rule='all_done' # 실패하더라도 정리는 수행
    )

    submit_jobs >> wait_jobs >> cleanup