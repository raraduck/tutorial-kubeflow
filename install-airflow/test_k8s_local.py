"""
로컬 Python 환경에서 Kubernetes API 테스트

실행 전 준비:
1. pip install kubernetes
2. kubeconfig 파일 경로 확인 (보통 ~/.kube/config)
"""

from kubernetes import client, config
import time

def test_kubernetes_connection():
    """Kubernetes 클러스터 연결 테스트"""
    print("=" * 60)
    print("Kubernetes API 연결 테스트")
    print("=" * 60)
    
    try:
        # Kubeconfig 로드 (기본 위치: ~/.kube/config)
        config.load_kube_config()
        # Windows에서 특정 경로 지정 시: config.load_kube_config(config_file='C:/Users/YourName/.kube/config')
        
        print("✅ Kubeconfig 로드 성공")
        
        # API 클라이언트 생성
        v1 = client.CoreV1Api()
        
        # 클러스터 노드 조회
        print("\n📋 클러스터 노드 목록:")
        nodes = v1.list_node()
        for node in nodes.items:
            print(f"  - {node.metadata.name}: {node.status.conditions[-1].type}")
        
        print("\n✅ Kubernetes API 연결 성공!")
        return True
        
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        return False


def list_namespaces():
    """네임스페이스 목록 조회"""
    print("\n" + "=" * 60)
    print("네임스페이스 목록")
    print("=" * 60)
    
    config.load_kube_config()
    v1 = client.CoreV1Api()
    
    namespaces = v1.list_namespace()
    for ns in namespaces.items:
        print(f"  - {ns.metadata.name}")


def check_airflow_namespace():
    """airflow 네임스페이스 확인"""
    print("\n" + "=" * 60)
    print("airflow 네임스페이스 확인")
    print("=" * 60)
    
    config.load_kube_config()
    v1 = client.CoreV1Api()
    
    try:
        ns = v1.read_namespace(name='airflow')
        print(f"✅ airflow 네임스페이스 존재")
        print(f"   생성일: {ns.metadata.creation_timestamp}")
        print(f"   상태: {ns.status.phase}")
        return True
    except client.exceptions.ApiException as e:
        if e.status == 404:
            print("❌ airflow 네임스페이스가 존재하지 않습니다")
            print("\n생성 명령:")
            print("  kubectl create namespace airflow")
            return False
        else:
            print(f"❌ 오류 발생: {e}")
            return False


def create_hello_world_pod():
    """Hello World Pod 생성"""
    print("\n" + "=" * 60)
    print("Hello World Pod 생성")
    print("=" * 60)
    
    config.load_kube_config()
    v1 = client.CoreV1Api()
    
    # Pod Manifest
    pod_manifest = {
        'apiVersion': 'v1',
        'kind': 'Pod',
        'metadata': {
            'name': 'hello-world-local-test',
            'namespace': 'airflow',
            'labels': {
                'app': 'hello-world',
                'created-by': 'local-python-script'
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
                    'echo "Created by: Local Python Script"; '
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
        print("📝 Pod 생성 중...")
        resp = v1.create_namespaced_pod(
            namespace='airflow',
            body=pod_manifest
        )
        print(f"✅ Pod 생성 성공: {resp.metadata.name}")
        print(f"   상태: {resp.status.phase}")
        
        return resp.metadata.name
        
    except client.exceptions.ApiException as e:
        if e.status == 409:
            print("⚠️  Pod가 이미 존재합니다. 먼저 삭제해주세요:")
            print("   kubectl delete pod hello-world-local-test -n airflow")
        else:
            print(f"❌ Pod 생성 실패: {e}")
        return None


def wait_for_pod(pod_name, namespace='airflow', timeout=120):
    """Pod 완료 대기"""
    print("\n" + "=" * 60)
    print(f"Pod '{pod_name}' 완료 대기 중...")
    print("=" * 60)
    
    config.load_kube_config()
    v1 = client.CoreV1Api()
    
    start_time = time.time()
    
    while True:
        if time.time() - start_time > timeout:
            print(f"⏰ 타임아웃 ({timeout}초)")
            return False
        
        try:
            pod = v1.read_namespaced_pod(name=pod_name, namespace=namespace)
            phase = pod.status.phase
            
            print(f"  상태: {phase}", end='\r')
            
            if phase == 'Succeeded':
                print(f"\n✅ Pod 완료!")
                return True
            elif phase == 'Failed':
                print(f"\n❌ Pod 실패!")
                return False
            elif phase in ['Pending', 'Running']:
                time.sleep(2)
            else:
                print(f"\n⚠️  예상치 못한 상태: {phase}")
                time.sleep(2)
                
        except Exception as e:
            print(f"\n❌ 오류: {e}")
            return False


def get_pod_logs(pod_name, namespace='airflow'):
    """Pod 로그 조회"""
    print("\n" + "=" * 60)
    print(f"Pod '{pod_name}' 로그")
    print("=" * 60)
    
    config.load_kube_config()
    v1 = client.CoreV1Api()
    
    try:
        logs = v1.read_namespaced_pod_log(
            name=pod_name,
            namespace=namespace,
            container='hello-container'
        )
        print(logs)
        return logs
        
    except Exception as e:
        print(f"❌ 로그 조회 실패: {e}")
        return None


def delete_pod(pod_name, namespace='airflow'):
    """Pod 삭제"""
    print("\n" + "=" * 60)
    print(f"Pod '{pod_name}' 삭제")
    print("=" * 60)
    
    config.load_kube_config()
    v1 = client.CoreV1Api()
    
    try:
        v1.delete_namespaced_pod(
            name=pod_name,
            namespace=namespace,
            body=client.V1DeleteOptions()
        )
        print(f"✅ Pod 삭제 완료")
        
    except Exception as e:
        print(f"❌ Pod 삭제 실패: {e}")


def list_pods_in_namespace(namespace='airflow'):
    """특정 네임스페이스의 Pod 목록"""
    print("\n" + "=" * 60)
    print(f"'{namespace}' 네임스페이스의 Pod 목록")
    print("=" * 60)
    
    config.load_kube_config()
    v1 = client.CoreV1Api()
    
    try:
        pods = v1.list_namespaced_pod(namespace=namespace)
        
        if len(pods.items) == 0:
            print("  (Pod 없음)")
        else:
            for pod in pods.items:
                print(f"  - {pod.metadata.name}: {pod.status.phase}")
                
    except Exception as e:
        print(f"❌ 오류: {e}")


def main():
    """메인 실행 함수"""
    print("\n🚀 Kubernetes Python Client 로컬 테스트\n")
    
    # 1. 연결 테스트
    if not test_kubernetes_connection():
        print("\n❌ Kubernetes 연결 실패. kubeconfig를 확인해주세요.")
        return
    
    # 2. 네임스페이스 목록
    list_namespaces()
    
    # 3. airflow 네임스페이스 확인
    if not check_airflow_namespace():
        print("\n⚠️  airflow 네임스페이스를 먼저 생성해주세요.")
        return
    
    # 4. 실행 전 Pod 목록
    list_pods_in_namespace('airflow')
    
    # 5. Hello World Pod 생성
    pod_name = create_hello_world_pod()
    if not pod_name:
        return
    
    # 6. Pod 완료 대기
    if wait_for_pod(pod_name):
        # 7. Pod 로그 조회
        get_pod_logs(pod_name)
    
    # 8. Pod 삭제
    delete_pod(pod_name)
    
    # 9. 실행 후 Pod 목록
    time.sleep(2)
    list_pods_in_namespace('airflow')
    
    print("\n" + "=" * 60)
    print("✅ 테스트 완료!")
    print("=" * 60)


if __name__ == '__main__':
    main()