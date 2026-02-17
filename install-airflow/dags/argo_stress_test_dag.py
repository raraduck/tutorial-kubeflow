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
    max_gpus = int(params['max_gpus'])      # 최대 도달 GPU 개수
    step_duration = str(params['step_duration']) # 각 단계별 유지 시간
    step_size = int(params['step_size'])    # [변경] 증가 단위 (예: 10)

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
    # 로직: step_size개 가동 -> 2*step_size개 가동 -> ... -> max_gpus
    main_steps = []
    
    # [변경] range(시작값, 끝값, 증가값)을 파라미터로 동적 처리
    # 예: step_size=10 이면 -> 10, 20, 30 ... 순으로 진행
    for i in range(step_size, max_gpus + 1, step_size):
        step_name = f"step-up-level-{i}"
        
        step_burn = {
            "name": step_name,
            "template": "parallel-burn-template",
            "arguments": {
                "parameters": [
                    {"name": "duration-sec", "value": step_duration},
                    {"name": "count", "value": str(i)} # 이번 단계에 실행할 GPU 개수
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
                # Template 2: Dynamic Parallel Controller
                {
                    "name": "parallel-burn-template",
                    "inputs": {
                        "parameters": [
                            {"name": "duration-sec"},
                            {"name": "count"}
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
        "max_gpus": Param(60, type="integer", title="최대 도달 GPU 개수 (1~N): 60=서버 15개"),
        "step_duration": Param(600, type="integer", title="단계별 유지 시간(초): 600=10분 (기본 10개씩 증가)"),
        # [변경] 증가 단위 파라미터 추가
        "step_size": Param(10, type="integer", title="증가 단위 (GPU 개수): 예 10 -> 10, 20, 30..."),
    },
    access_control={
        'K8s_Team': {'can_read', 'can_edit'},
    }
) as dag:

    run_step_up_test = PythonOperator(
        task_id='submit_step_up_test',
        python_callable=submit_argo_step_up_test_via_api
    )

