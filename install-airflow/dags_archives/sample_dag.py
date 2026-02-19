from airflow import DAG
from airflow.operators.dummy_operator import DummyOperator  # 아무 동작도 하지 않는 placeholder Task
from airflow.operators.python_operator import PythonOperator  # Python 함수를 실행하는 Task
from datetime import datetime

# PythonOperator에서 실행할 간단한 함수
def print_hello():
    return "Hello, Airflow!"

def print_goodbye():
    return "Goodbye, Airflow!"

# DAG 정의
with DAG(
    dag_id="sample_dag",  # DAG 이름
    default_args={
        "start_date": datetime(2023, 1, 1)  # DAG 시작일 (schedule 기준)
    },
    schedule_interval="@daily",  # 매일 1회 실행
    catchup=False,  # 과거 실행 기록은 무시 (backfill 안 함),
    access_control={
        'NT_Team': {'can_read', 'can_edit'}  # 읽기 + 실행 권한 부여
    }
) as dag:

    # DummyOperator: 시작 지점 (아무 작업 안 함, 시각적으로만 사용)
    start = DummyOperator(task_id="start")

    # PythonOperator: 실제 Python 함수 실행 (Hello 출력)
    hello = PythonOperator(
        task_id="hello_task",
        python_callable=print_hello
    )

    # PythonOperator: 또 다른 Python 함수 실행 (Goodbye 출력)
    goodbye = PythonOperator(
        task_id="goodbye_task",
        python_callable=print_goodbye
    )

    # DummyOperator: 종료 지점
    end = DummyOperator(task_id="end")

    # Task 실행 순서 정의
    start >> hello >> goodbye >> end