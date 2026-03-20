# Spark-Operator 설치
## 1단계: Spark Operator 설치 확인 (Helm)
- 성공 기준: spark-operator라는 이름이 포함된 파드가 Running 상태여야 합니다.
```bash
# 1. 설치 여부 및 파드 상태 확인
kubectl get pods -n spark-operator

# (만약 설치가 안 되어 있다면 Helm으로 설치)
helm repo add spark-operator https://googlecloudplatform.github.io/spark-on-k8s-operator
helm install my-release spark-operator/spark-operator --namespace spark-operator --create-namespace
```
## 2단계: Spark 실행을 위한 서비스 계정(Service Account) 생성
- Spark Operator 자체는 관리자지만, 실제로 작업을 수행하는 드라이버(Driver) 파드가 엑스큐터(Executor) 파드를 생성하고 삭제하려면 권한이 필요합니다.
- 이 권한을 주는 spark-rbac.yaml 파일을 만들고 적용합니다.
```yaml
# spark-rbac.yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: spark-team-sa
  namespace: default
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: spark-team-role-binding
subjects:
- kind: ServiceAccount
  name: spark-team-sa
  namespace: default
roleRef:
  kind: ClusterRole
  name: edit # 'edit' 권한이면 파드 생성/삭제에 충분합니다.
  apiGroup: rbac.authorization.k8s.io
```
- 적용:
```bash
kubectl apply -f spark-rbac.yaml
```
## 3단계: PySpark 동작 테스트 (Pi 계산 예제)
- 이제 실험용 스토리지(/data1)를 연결하기 전에, 순수하게 PySpark가 클러스터 모드로 잘 도는지 확인하기 위해 가장 가벼운 SparkPi 예제를 돌려봅니다.
- 이미지: gcr.io/spark-operator/spark-py:v3.1.1 (구글 공식 PySpark 이미지 사용)
- 목표: 파이(π) 값을 계산하여 로그에 찍는지 확인
```yaml
# pyspark-pi-test.yaml
apiVersion: "sparkoperator.k8s.io/v1beta2"
kind: SparkApplication
metadata:
  name: pyspark-pi-test
  namespace: default
spec:
  type: Python
  pythonVersion: "3"
  mode: cluster
  # [수정됨] GCR 이미지 대신 Docker Hub의 공식 Apache Spark 이미지 사용
  image: "apache/spark-py:v3.1.3"
  imagePullPolicy: IfNotPresent
  
  # Apache 공식 이미지 내의 예제 파일 경로는 동일합니다 (/opt/spark/...)
  mainApplicationFile: "local:///opt/spark/examples/src/main/python/pi.py"
  
  sparkVersion: "3.1.3" # 이미지 버전에 맞춰 수정
  restartPolicy:
    type: Never
  
  driver:
    cores: 1
    coreLimit: "1200m"
    memory: "512m"
    labels:
      version: 3.1.3
    serviceAccount: spark-team-sa 

  executor:
    cores: 1
    instances: 2
    memory: "512m"
```
- 실행:
```bash
kubectl apply -f pyspark-pi-test.yaml
```
## 4단계: 실행 결과 및 로그 확인
- 파드 생성 확인:
```bash
# 드라이버와 엑스큐터 파드가 생성되는지 봅니다.
kubectl get pods -w
```
- pyspark-pi-test-driver (Running -> Completed)
- pyspark-pi-test-exec-1, exec-2 (Running -> Terminated)
- 위 과정이 보이면 Spark Operator와 권한 설정은 완벽한 상태입니다.

## cluster role and binding
### 1. spark-operator-controller 용 ClusterRole 생성
kubectl apply -f - <<EOF
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: spark-operator-controller-role
rules:
- apiGroups: ["sparkoperator.k8s.io"]
  resources: ["sparkapplications", "sparkapplications/status", "scheduledsparkapplications", "scheduledsparkapplications/status"]
  verbs: ["*"]
- apiGroups: ["batch"]
  resources: ["jobs"]
  verbs: ["*"]
- apiGroups: [""]
  resources: ["pods", "services", "configmaps", "persistentvolumeclaims", "events"]
  verbs: ["*"]
- apiGroups: ["admissionregistration.k8s.io"]
  resources: ["mutatingwebhookconfigurations", "validatingwebhookconfigurations"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
EOF

### 2. ClusterRoleBinding 생성
kubectl apply -f - <<EOF
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: spark-operator-controller-binding
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: spark-operator-controller-role
subjects:
- kind: ServiceAccount
  name: spark-operator-controller
  namespace: kubeflow
- kind: ServiceAccount
  name: spark-operator-webhook
  namespace: kubeflow
EOF

# 3. Pod 재시작
kubectl rollout restart deployment spark-operator-controller spark-operator-webhook -n kubeflow