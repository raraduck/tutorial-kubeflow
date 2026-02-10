from datetime import datetime
from airflow import DAG
from airflow.models.param import Param
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator

with DAG(
    'trigger_argo_workflow_via_cli',
    start_date=datetime(2025, 1, 1),
    schedule_interval=None,
    tags=['argo', 'cli'],
    # Airflow UI에서 입력받을 파라미터
    params={
        "job_count": Param(12, type="integer"),
        "duration": Param(600, type="integer")
    }
) as dag:

    submit_argo = KubernetesPodOperator(
        task_id='submit_argo_workflow',
        name='argo-submitter',
        namespace='argo', # Argo가 설치된 네임스페이스
        
        # 1. Argo CLI 이미지를 사용
        image='quay.io/argoproj/argocli:latest',
        
        # [핵심 수정] 권한이 있는 Service Account 지정
        # 보통 'argo' 또는 'default'에 권한을 줬다면 그 이름을 씁니다.
        # 일단 'argo'로 시도해보세요.
        service_account_name='argo',

        # 2. 실행할 명령어 (argo submit ...)
        cmds=["argo"],
        arguments=[
            "submit",
            "https://raw.githubusercontent.com/argoproj/argo-workflows/master/examples/hello-world.yaml", # [수정필요] 실행할 Workflow 파일 경로
            "-n", "argo",           # 워크플로우가 실행될 네임스페이스
            "--watch",              # 완료될 때까지 대기 (중요)
            "--log",                # 로그 출력
            
            # 파라미터 전달 (-p 옵션)
            "-p", "job-count={{ params.job_count }}",
            "-p", "duration={{ params.duration }}",
            
            # (선택) 워크플로우 이름 지정
            "--generate-name", "gpu-burn-test-"
        ],
        
        # 3. K8s 인증 설정
        # Airflow가 클러스터 내부(In-cluster)에 있다면: True
        # 외부(Docker Compose)라면: False (이 경우 config_file 경로 지정 필요)
        in_cluster=False, 
        config_file="/opt/airflow/config/kubeconfig", 
        
        get_logs=True,              # Airflow UI에서 로그 확인
        is_delete_operator_pod=True # 실행이 끝나면 이 파드(Pod) 삭제
    )