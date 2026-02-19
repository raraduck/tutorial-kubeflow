"""
Cluster User Emails Variable Manager DAG (Dynamic UI - Corrected)
"""
from datetime import datetime
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.models import Variable
from airflow.models.param import Param
import logging

logger = logging.getLogger(__name__)

# --- 파싱 시점에 현재 등록된 이메일 목록 불러오기 및 정렬 ---
raw_emails_str = Variable.get("all_user_emails", default_var="")

# 1. 쉼표 기준으로 나누고 공백 제거 후 빈 값 필터링
email_list = [email.strip() for email in raw_emails_str.split(',') if email.strip()]

# 2. 알파벳 순서로 정렬
sorted_email_list = sorted(email_list)

# 3. 화면에 띄울 때 보기 좋게 한 줄에 하나씩 줄바꿈(\n)으로 연결
display_emails_str = ", \n".join(sorted_email_list)

# --- Trigger 화면 상단에 띄울 마크다운 문서 작성 ---
dag_docs = f"""
### 📧 클러스터 수신자 그룹 관리
현재 `all_user_emails` Variable에 등록된 전체 사용자 목록입니다. (알파벳 순 정렬)

⚠️ **안내:** Airflow 스케줄러의 파싱 주기로 인해, 목록 업데이트 직후 **화면 반영까지 약 30초~1분 정도 지연**이 발생할 수 있습니다. 
(작업 성공 시 실제 DB에는 즉시 반영되므로, 잠시 후 새로고침(F5)을 하시면 갱신된 목록을 확인할 수 있습니다.)

삭제가 필요한 메일은 아래 박스에서 복사(`Ctrl+C`)하여 제외 폼에 쉼표(,)로 구분해 붙여넣으세요.

**[현재 등록된 이메일 목록]**
```text
{display_emails_str if display_emails_str else '(등록된 이메일이 없습니다)'}
```
"""
# dropdown_options = current_list if current_list else ["(현재 등록된 이메일 없음)"]

default_args = {
    'owner': 'admin',
    'start_date': datetime(2025, 1, 1),
    'retries': 0,
}

def update_email_variable(**context):
    params = context['params']
    # UI에서 아무것도 입력하지 않아 None이 넘어올 경우 빈 문자열('')로 처리하도록 or '' 추가
    add_str = params.get('emails_to_add') or ''
    remove_str = params.get('emails_to_remove') or ''

    current_str = Variable.get("all_user_emails", default_var="")
    current_set = {email.strip() for email in current_str.split(',') if email.strip()}

    add_set = {email.strip() for email in add_str.split(',') if email.strip()}
    remove_set = {email.strip() for email in remove_str.split(',') if email.strip()}

    new_set = (current_set | add_set) - remove_set
    new_str = ", ".join(sorted(new_set))

    Variable.set("all_user_emails", new_str)

    logger.info("========================================")
    logger.info(f"업데이트 전 목록 : {current_str if current_str else '(비어있음)'}")
    logger.info(f"추가 요청된 메일 : {', '.join(add_set) if add_set else '(없음)'}")
    logger.info(f"제외 요청된 메일 : {', '.join(remove_set) if remove_set else '(없음)'}")
    logger.info(f"업데이트 후 목록 : {new_str}")
    logger.info("========================================")

email_list_regex = r"^$|^([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(\s*,\s*[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})*)$"

with DAG(
    'kubeflow_maillist_manager_v26.02.0',
    default_args=default_args,
    schedule_interval=None, 
    tags=['management', 'variable', 'email'],
    doc_md=dag_docs,
    params={
        "emails_to_add": Param(
            default="",
            type=["string", "null"], # [수정] 빈칸을 허용하도록 null 타입 추가
            pattern=email_list_regex, # [추가] 정규표현식 패턴 검증
            title="[추가] 할 이메일 목록",
            description="새로 추가할 이메일을 쉼표(,)로 구분하여 입력하세요. [추가할 메일이 없으면 비워두세요]"
        ),
        "emails_to_remove": Param(
            default="",
            type=["string", "null"], # [수정] 빈칸을 허용하도록 null 타입 추가
            pattern=email_list_regex, # [추가] 정규표현식 패턴 검증
            title="[제외] 할 이메일 목록",
            description="화면 상단의 목록에서 삭제할 이메일을 복사하여 붙여넣으세요. [쉼표(,)로 구분합니다. 만약, 삭제할 메일이 없으면 비워두세요]"
        )
    },
    access_control={
        'KF_Team': {'can_read', 'can_edit'} 
    }
) as dag:

    update_task = PythonOperator(
        task_id='update_email_list',
        python_callable=update_email_variable,
    )

    update_task