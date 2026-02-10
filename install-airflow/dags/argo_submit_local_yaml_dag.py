import os
from datetime import datetime
from airflow import DAG
from airflow.models.param import Param
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator
from kubernetes.client import models as k8s
# [수정 전] 상대 경로 계산 (복잡함)
# current_dir = os.path.dirname(os.path.abspath(__file__))
# project_root = os.path.dirname(current_dir)
# yaml_file_path = os.path.join(project_root, 'yaml', 'gpu-burn-workflow.yaml')

# [수정 후] 절대 경로 지정 (깔끔함)
# Docker에서 이 경로를 마운트했으므로 항상 존재한다고 확신할 수 있습니다.
yaml_file_path = '/opt/airflow/yaml/gpu-burn-workflow.yaml'

# (선택 사항) 파일 존재 여부 확인 로직은 유지하는 것이 좋습니다.
if not os.path.exists(yaml_file_path):
    raise FileNotFoundError(f"YAML file not found at {yaml_file_path}. Please check volume mount.")

workflow_content = ""
try:
    with open(yaml_file_path, 'r') as file:
        workflow_content = file.read()
except FileNotFoundError:
    print(f"Warning: {yaml_file_path} not found. Make sure the file exists.")

with DAG(
    'trigger_argo_local_yaml',
    start_date=datetime(2025, 1, 1),
    schedule_interval=None,
    tags=['argo', 'local-file'],
    params={
        "job_count": Param(12, type="integer"),
        "duration": Param(600, type="integer")
    }
) as dag:

    submit_argo = KubernetesPodOperator(
        task_id='submit_argo_workflow',
        name='argo-submitter',
        namespace='argo',
        image='quay.io/argoproj/argocli:latest',
        service_account_name='argo',
        
        # [핵심 1] 파일 내용을 환경변수로 주입
        env_vars={
            "WORKFLOW_YAML": workflow_content
        },

        # [핵심 2] 쉘 명령어로 변경
        # echo로 환경변수 내용을 출력하고 -> 파이프(|)로 argo submit에 넘김
        # '-' 기호는 표준 입력(Stdin)을 의미합니다.
        cmds=["/bin/sh", "-c"],
        arguments=[
            """
            echo "$WORKFLOW_YAML" | argo submit - \
            -n argo \
            --watch \
            --log \
            -p job-count={{ params.job_count }} \
            -p duration={{ params.duration }} \
            --generate-name gpu-burn-test-
            """
        ],
        
        in_cluster=False, 
        config_file="/opt/airflow/config/kubeconfig", 
        get_logs=True,
        is_delete_operator_pod=True
    )