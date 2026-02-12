from datetime import datetime
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.models.param import Param
from kubernetes import client, config

# [핵심] 표준 K8s 객체를 가져옵니다.
from kubernetes.client import models as k8s

def submit_argo_workflow_via_api(**context):
    # 1. K8s 클라이언트 설정 (In-cluster 또는 Local)
    try:
        config.load_incluster_config() # Airflow가 클러스터 내부일 때
    except:
        config.load_kube_config(config_file="/opt/airflow/config/kubeconfig") # 로컬 개발 시
    
    # CRD(Custom Resource Definition)를 다루는 API
    api = client.CustomObjectsApi()
    
    # 2. 파라미터 가져오기
    params = context['params']
    job_count = str(params['job_count'])
    duration = str(params['duration'])

    # 3. [핵심] Kubernetes 표준 객체로 컨테이너 정의 (타입 체크 가능!)
    #    client.V1Container를 쓰면 오타를 줄일 수 있습니다.
    container_spec = k8s.V1Container(
        name="gpu-burn",
        image="docker.io/jorghi21/gpu-burn-test:latest",
        args=["{{inputs.parameters.duration-sec}}"], # Argo 변수
        resources=k8s.V1ResourceRequirements(
            limits={"nvidia.com/gpu": "1"}
        )
    )

    # 4. Argo Workflow 정의 (Dictionary)
    #    Argo 전용 필드는 dict로, K8s 표준 필드는 위에서 만든 객체의 .to_dict()를 씁니다.
    manifest = {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "Workflow",
        "metadata": {
            "generateName": "gpu-burn-test-",
            "namespace": "argo"  # 네임스페이스 지정
        },
        "spec": {
            "entrypoint": "main",
            "serviceAccountName": "argo", # 권한 있는 SA 필수
            "arguments": {
                "parameters": [
                    {"name": "job-count", "value": job_count},
                    {"name": "duration", "value": duration}
                ]
            },
            "templates": [
                # Template 1: Main DAG
                {
                    "name": "main",
                    "steps": [
                        [
                            {
                                "name": "run-burn-jobs",
                                "template": "gpu-burn-task",
                                "arguments": {
                                    "parameters": [
                                        {
                                            "name": "duration-sec",
                                            "value": "{{workflow.parameters.duration}}"
                                        }
                                    ]
                                },
                                "withSequence": {
                                    "count": "{{workflow.parameters.job-count}}"
                                }
                            }
                        ]
                    ]
                },
                # Template 2: Worker Task
                {
                    "name": "gpu-burn-task",
                    "inputs": {
                        "parameters": [{"name": "duration-sec"}]
                    },
                    # [여기서 합체!] 위에서 정의한 K8s 객체를 Dictionary로 변환하여 주입
                    "container": container_spec.to_dict()
                }
            ]
        }
    }

    # 5. API로 제출 (argo submit 명령어와 동일한 효과)
    try:
        response = api.create_namespaced_custom_object(
            group="argoproj.io",
            version="v1alpha1",
            namespace="argo",
            plural="workflows",
            body=manifest
        )
        print(f"Workflow submitted successfully! Name: {response['metadata']['name']}")
        return response['metadata']['name']
        
    except client.exceptions.ApiException as e:
        print(f"Exception when calling CustomObjectsApi->create_namespaced_custom_object: {e}")
        raise

with DAG(
    'argo_gpu_endurance_test',
    start_date=datetime(2025, 1, 1),
    schedule_interval=None,
    tags=['argo', 'gpu', 'endurance-test', 'test'],
    params={
        "job_count": Param(60, type="integer", title="병렬 GPU 개수: 60=서버 15개"),
        "duration": Param(3600, type="integer", title="가동 시간(초): 3600=1시간")
    },
    access_control={
        'K8s_Team': {'can_read', 'can_edit'},
    }
) as dag:

    # KubernetesPodOperator 대신 PythonOperator를 사용합니다.
    submit_workflow = PythonOperator(
        task_id='submit_workflow_python',
        python_callable=submit_argo_workflow_via_api
    )