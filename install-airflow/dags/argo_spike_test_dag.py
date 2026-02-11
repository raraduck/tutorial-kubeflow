from datetime import datetime
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.models.param import Param
from kubernetes import client, config
from kubernetes.client import models as k8s

def submit_argo_spike_test_via_api(**context):
    # 1. K8s 클라이언트 설정
    try:
        config.load_incluster_config()
    except:
        config.load_kube_config(config_file="/opt/airflow/config/kubeconfig")
    
    api = client.CustomObjectsApi()
    
    # 2. 파라미터 가져오기
    params = context['params']
    job_count = str(params['job_count'])    # 병렬 GPU 개수 (예: 12)
    burn_time = str(params['burn_time'])    # Burn 시간 (예: 60초)
    cool_time = str(params['cool_time'])    # 휴식 시간 (예: 30초)
    iterations = int(params['iterations'])  # 반복 횟수 (예: 10회)

    # 3-1. [GPU Burn] 컨테이너 정의 (부하 발생용)
    burn_container_spec = k8s.V1Container(
        name="gpu-burn",
        image="docker.io/jorghi21/gpu-burn-test:latest",
        args=["{{inputs.parameters.duration-sec}}"], 
        resources=k8s.V1ResourceRequirements(
            limits={"nvidia.com/gpu": "1"}
        )
    )

    # 3-2. [Cooldown] 컨테이너 정의 (전력 하강용)
    # 가벼운 Alpine 이미지로 sleep만 수행
    sleep_container_spec = k8s.V1Container(
        name="sleep",
        image="alpine:latest",
        command=["/bin/sh", "-c"],
        args=["echo 'Cooling down...'; sleep {{inputs.parameters.duration-sec}}"],
        resources=k8s.V1ResourceRequirements(
            requests={"cpu": "100m", "memory": "50Mi"} # 최소 자원
        )
    )

    # 4. Argo Workflow Steps 생성 (Python Loop로 순차적 단계 생성)
    # 로직: [Burn(병렬) -> Sleep] x 10회 반복
    main_steps = []
    
    for i in range(1, iterations + 1):
        # Step A: 모든 GPU 동시 가동 (Spike Up)
        step_burn = {
            "name": f"spike-{i}-burn",
            "template": "parallel-burn-template", # 아래에서 정의할 템플릿 호출
            "arguments": {
                "parameters": [{"name": "duration-sec", "value": burn_time}]
            }
        }
        main_steps.append([step_burn]) # 리스트로 감싸면 해당 단계는 병렬(여기선 1개지만)
        
        # Step B: 휴식 (Spike Down) - 마지막 회차 뒤에도 쿨다운 할지 선택 (여기선 포함)
        step_cool = {
            "name": f"spike-{i}-cooldown",
            "template": "cooldown-template",
            "arguments": {
                "parameters": [{"name": "duration-sec", "value": cool_time}]
            }
        }
        main_steps.append([step_cool])

    # 5. Argo Workflow 정의
    manifest = {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "Workflow",
        "metadata": {
            "generateName": "gpu-spike-test-",
            "namespace": "argo"
        },
        "spec": {
            "entrypoint": "main",
            "serviceAccountName": "argo",
            "templates": [
                # Template 1: Main Control Loop (위에서 만든 steps 사용)
                {
                    "name": "main",
                    "steps": main_steps
                },
                # Template 2: Parallel Burn Controller (Fan-out)
                {
                    "name": "parallel-burn-template",
                    "inputs": {"parameters": [{"name": "duration-sec"}]},
                    "steps": [
                        [
                            {
                                "name": "run-gpu-burn",
                                "template": "gpu-burn-task",
                                "arguments": {
                                    "parameters": [{"name": "duration-sec", "value": "{{inputs.parameters.duration-sec}}"}]
                                },
                                # [핵심] 여기서 GPU 개수만큼 병렬 확산
                                "withSequence": {
                                    "count": job_count
                                }
                            }
                        ]
                    ]
                },
                # Template 3: Actual GPU Worker
                {
                    "name": "gpu-burn-task",
                    "inputs": {"parameters": [{"name": "duration-sec"}]},
                    "container": burn_container_spec.to_dict()
                },
                # Template 4: Cooldown Worker
                {
                    "name": "cooldown-template",
                    "inputs": {"parameters": [{"name": "duration-sec"}]},
                    "container": sleep_container_spec.to_dict()
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
        print(f"Spike Test Workflow submitted! Name: {response['metadata']['name']}")
        return response['metadata']['name']
    except client.exceptions.ApiException as e:
        print(f"API Exception: {e}")
        raise

# DAG 정의
with DAG(
    'argo_gpu_spike_test_n_cycles',
    start_date=datetime(2025, 1, 1),
    schedule_interval=None,
    tags=['argo', 'gpu', 'stress-test', 'test'],
    params={
        "job_count": Param(12, type="integer", title="병렬 GPU 개수"),
        "burn_time": Param(60, type="integer", title="가동 시간(초) - Spike Up"),
        "cool_time": Param(30, type="integer", title="휴식 시간(초) - Spike Down"),
        "iterations": Param(10, type="integer", title="반복 횟수")
    },
    access_control={
        'K8s_Team': {'can_read', 'can_edit'},
    }
) as dag:

    run_spike_test = PythonOperator(
        task_id='submit_spike_test',
        python_callable=submit_argo_spike_test_via_api
    )