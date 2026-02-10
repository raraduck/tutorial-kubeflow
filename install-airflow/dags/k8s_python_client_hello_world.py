"""
Python Kubernetes Client를 사용한 Hello World Pod 생성 DAG

이 DAG는 kubernetes Python 라이브러리를 사용하여
직접 Kubernetes API를 호출해 Pod를 생성, 모니터링, 삭제합니다.
"""
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from kubernetes import client, config
import time
import logging

# 로거 설정
logger = logging.getLogger(__name__)

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2025, 1, 1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=2),
}


def create_hello_world_pod(**context):
    """
    Hello World Pod를 생성하는 함수
    """
    # Kubeconfig 로드
    config.load_kube_config(config_file='/opt/airflow/config/kubeconfig')
    
    # API 클라이언트 생성
    v1 = client.CoreV1Api()
    
    # Pod 정의
    pod_manifest = {
        'apiVersion': 'v1',
        'kind': 'Pod',
        'metadata': {
            'name': 'hello-world-python-client',
            'namespace': 'airflow',
            'labels': {
                'app': 'hello-world',
                'created-by': 'airflow-python-client',
                'dag-id': context['dag'].dag_id,
                'task-id': context['task'].task_id,
            }
        },
        'spec': {
            'restartPolicy': 'Never',
            'containers': [{
                'name': 'hello-container',
                'image': 'busybox:latest',
                'command': ['sh', '-c'],
                'args': [
                    'echo "========================================"; '
                    'echo "Hello World from Kubernetes!"; '
                    'echo "Pod Name: $HOSTNAME"; '
                    'echo "Namespace: airflow"; '
                    'echo "Created by: Airflow Python Client"; '
                    'echo "========================================"; '
                    'sleep 10; '
                    'echo "Task completed successfully!"'
                ],
                'resources': {
                    'requests': {
                        'memory': '64Mi',
                        'cpu': '100m'
                    },
                    'limits': {
                        'memory': '128Mi',
                        'cpu': '200m'
                    }
                }
            }]
        }
    }
    
    try:
        # Pod 생성
        logger.info("Creating Pod: hello-world-python-client in namespace: airflow")
        resp = v1.create_namespaced_pod(
            namespace='airflow',
            body=pod_manifest
        )
        logger.info(f"Pod created successfully. Status: {resp.status.phase}")
        
        # XCom에 Pod 이름 저장 (다음 태스크에서 사용)
        return resp.metadata.name
        
    except client.exceptions.ApiException as e:
        logger.error(f"Exception when creating Pod: {e}")
        raise


def wait_for_pod_completion(**context):
    """
    Pod가 완료될 때까지 대기하고 상태를 모니터링하는 함수
    """
    # 이전 태스크에서 Pod 이름 가져오기
    ti = context['ti']
    pod_name = ti.xcom_pull(task_ids='create_pod')
    
    # Kubeconfig 로드
    config.load_kube_config(config_file='/opt/airflow/config/kubeconfig')
    v1 = client.CoreV1Api()
    
    namespace = 'airflow'
    max_wait_time = 300  # 최대 5분 대기
    start_time = time.time()
    
    logger.info(f"Waiting for Pod {pod_name} to complete...")
    
    while True:
        # 타임아웃 체크
        if time.time() - start_time > max_wait_time:
            raise TimeoutError(f"Pod {pod_name} did not complete within {max_wait_time} seconds")
        
        try:
            # Pod 상태 조회
            pod = v1.read_namespaced_pod(name=pod_name, namespace=namespace)
            phase = pod.status.phase
            
            logger.info(f"Pod {pod_name} status: {phase}")
            
            if phase == 'Succeeded':
                logger.info(f"Pod {pod_name} completed successfully!")
                return 'success'
            elif phase == 'Failed':
                logger.error(f"Pod {pod_name} failed!")
                raise Exception(f"Pod {pod_name} failed")
            elif phase in ['Pending', 'Running']:
                logger.info(f"Pod {pod_name} is still {phase}. Waiting...")
                time.sleep(5)
            else:
                logger.warning(f"Pod {pod_name} in unexpected phase: {phase}")
                time.sleep(5)
                
        except client.exceptions.ApiException as e:
            logger.error(f"Exception when reading Pod status: {e}")
            raise


def get_pod_logs(**context):
    """
    Pod의 로그를 가져오는 함수
    """
    ti = context['ti']
    pod_name = ti.xcom_pull(task_ids='create_pod')
    
    config.load_kube_config(config_file='/opt/airflow/config/kubeconfig')
    v1 = client.CoreV1Api()
    
    namespace = 'airflow'
    
    try:
        logger.info(f"Fetching logs for Pod: {pod_name}")
        logs = v1.read_namespaced_pod_log(
            name=pod_name,
            namespace=namespace,
            container='hello-container'
        )
        
        logger.info("=" * 60)
        logger.info("POD LOGS:")
        logger.info("=" * 60)
        logger.info(logs)
        logger.info("=" * 60)
        
        return logs
        
    except client.exceptions.ApiException as e:
        logger.error(f"Exception when reading Pod logs: {e}")
        raise


def delete_pod(**context):
    """
    Pod를 삭제하는 함수
    """
    ti = context['ti']
    pod_name = ti.xcom_pull(task_ids='create_pod')
    
    config.load_kube_config(config_file='/opt/airflow/config/kubeconfig')
    v1 = client.CoreV1Api()
    
    namespace = 'airflow'
    
    try:
        logger.info(f"Deleting Pod: {pod_name}")
        v1.delete_namespaced_pod(
            name=pod_name,
            namespace=namespace,
            body=client.V1DeleteOptions()
        )
        logger.info(f"Pod {pod_name} deleted successfully")
        
    except client.exceptions.ApiException as e:
        logger.error(f"Exception when deleting Pod: {e}")
        # 삭제 실패는 critical하지 않으므로 로그만 남김
        logger.warning("Pod deletion failed, but continuing...")


def list_pods_in_namespace(**context):
    """
    airflow 네임스페이스의 모든 Pod를 조회하는 함수
    """
    config.load_kube_config(config_file='/opt/airflow/config/kubeconfig')
    v1 = client.CoreV1Api()
    
    namespace = 'airflow'
    
    try:
        logger.info(f"Listing all pods in namespace: {namespace}")
        pods = v1.list_namespaced_pod(namespace=namespace)
        
        logger.info("=" * 60)
        logger.info(f"PODS IN NAMESPACE '{namespace}':")
        logger.info("=" * 60)
        
        for pod in pods.items:
            logger.info(f"Pod: {pod.metadata.name}, Status: {pod.status.phase}")
        
        logger.info("=" * 60)
        
        return [pod.metadata.name for pod in pods.items]
        
    except client.exceptions.ApiException as e:
        logger.error(f"Exception when listing Pods: {e}")
        raise


# DAG 정의
with DAG(
    'kubernetes_python_client_hello_world',
    default_args=default_args,
    description='Python Kubernetes Client를 사용한 Hello World Pod 생성',
    schedule_interval=None,
    catchup=False,
    tags=['kubernetes', 'python-client', 'hello-world'],
) as dag:

    # Task 1: 네임스페이스의 Pod 목록 조회 (실행 전)
    list_pods_before = PythonOperator(
        task_id='list_pods_before',
        python_callable=list_pods_in_namespace,
        provide_context=True,
    )

    # Task 2: Pod 생성
    create_pod = PythonOperator(
        task_id='create_pod',
        python_callable=create_hello_world_pod,
        provide_context=True,
    )

    # Task 3: Pod 완료 대기
    wait_pod = PythonOperator(
        task_id='wait_for_completion',
        python_callable=wait_for_pod_completion,
        provide_context=True,
    )

    # Task 4: Pod 로그 조회
    get_logs = PythonOperator(
        task_id='get_pod_logs',
        python_callable=get_pod_logs,
        provide_context=True,
    )

    # Task 5: Pod 삭제
    cleanup_pod = PythonOperator(
        task_id='delete_pod',
        python_callable=delete_pod,
        provide_context=True,
        trigger_rule='all_done',  # 이전 태스크 성공/실패 관계없이 실행
    )

    # Task 6: 네임스페이스의 Pod 목록 조회 (실행 후)
    list_pods_after = PythonOperator(
        task_id='list_pods_after',
        python_callable=list_pods_in_namespace,
        provide_context=True,
    )

    # Task 의존성 설정
    list_pods_before >> create_pod >> wait_pod >> get_logs >> cleanup_pod >> list_pods_after