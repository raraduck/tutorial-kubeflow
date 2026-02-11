from datetime import datetime
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.models.param import Param
from kubernetes import client, config
from kubernetes.client import models as k8s

def submit_argo_step_up_test_via_api(**context):
    # 1. K8s 클라이언트 설정
    try:
        config.load_incluster_config()
    except:
        config.load_kube_config(config_file="/opt/airflow/config/kubeconfig")
    
    api = client.CustomObjectsApi()
    
    # 2. 파라미터 가져오기
    params = context['params']
    max_gpus = int(params['max_gpus'])      # 최대 도달 GPU 개수 (예: 12)
    step_duration = str(params['step_duration']) # 각 단계별 유지 시간 (예: 30초)

    # 3. [GPU Burn] 컨테이너 정의
    burn_container_spec = k8s.V1Container(
        name="gpu-burn",
        image="docker.io/jorghi21/gpu-burn-test:latest",
        args=["{{inputs.parameters.duration-sec}}"], 
        resources=k8s.V1ResourceRequirements(
            limits={"nvidia.com/gpu": "1"}
        )
    )

    # 4. Argo Workflow Steps 생성 (Staircase Pattern)
    # 로직: 1개 가동 -> 2개 가동 -> ... -> N개 가동 (중간 휴식 없음)
    main_steps = []
    
    for i in range(1, max_gpus + 1):
        step_name = f"step-up-level-{i}"
        
        step_burn = {
            "name": step_name,
            "template": "parallel-burn-template",
            "arguments": {
                "parameters": [
                    {"name": "duration-sec", "value": step_duration},
                    {"name": "count", "value": str(i)} # [핵심] 이번 단계에 실행할 GPU 개수
                ]
            }
        }
        main_steps.append([step_burn]) 

    # 5. Argo Workflow 정의
    manifest = {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "Workflow",
        "metadata": {
            "generateName": "gpu-step-up-test-",
            "namespace": "argo"
        },
        "spec": {
            "entrypoint": "main",
            "serviceAccountName": "argo",
            "templates": [
                # Template 1: Main Control Loop
                {
                    "name": "main",
                    "steps": main_steps
                },
                # Template 2: Dynamic Parallel Controller (개수를 입력받음)
                {
                    "name": "parallel-burn-template",
                    "inputs": {
                        "parameters": [
                            {"name": "duration-sec"},
                            {"name": "count"} # [변경] 개수를 파라미터로 받음
                        ]
                    },
                    "steps": [
                        [
                            {
                                "name": "run-gpu-burn",
                                "template": "gpu-burn-task",
                                "arguments": {
                                    "parameters": [{"name": "duration-sec", "value": "{{inputs.parameters.duration-sec}}"}]
                                },
                                # [핵심] 입력받은 count만큼 병렬 실행
                                "withSequence": {
                                    "count": "{{inputs.parameters.count}}"
                                }
                            }
                        ]
                    ]
                },
                # Template 3: Actual Worker
                {
                    "name": "gpu-burn-task",
                    "inputs": {"parameters": [{"name": "duration-sec"}]},
                    "container": burn_container_spec.to_dict()
                }
            ]
        }
    }

    # 6. API로 제출
    try:
        response = api.create_namespaced_custom_object(
            group="argoproj.io",
            version="v1alpha1",
            namespace="argo",
            plural="workflows",
            body=manifest
        )
        print(f"Step-Up Test Workflow submitted! Name: {response['metadata']['name']}")
        return response['metadata']['name']
    except client.exceptions.ApiException as e:
        print(f"API Exception: {e}")
        raise

# DAG 정의
with DAG(
    'argo_gpu_step_up_stress_test',
    start_date=datetime(2025, 1, 1),
    schedule_interval=None,
    tags=['argo', 'gpu', 'stress-test', 'step-up', 'test'],
    params={
        "max_gpus": Param(12, type="integer", title="최대 도달 GPU 개수 (1~N)"),
        "step_duration": Param(300, type="integer", title="단계별 유지 시간(초)"),
    },
    access_control={
        'K8s_Team': {'can_read', 'can_edit'},
    }
) as dag:

    run_step_up_test = PythonOperator(
        task_id='submit_step_up_test',
        python_callable=submit_argo_step_up_test_via_api
    )