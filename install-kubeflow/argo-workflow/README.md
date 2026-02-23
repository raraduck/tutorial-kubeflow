# kubeflow 에서 argo workflow 활용

1. argo 명령어 다운로드

Kubeflow에 Argo가 이미 설치되어 있어도 CLI는 별도로 받아야 합니다.

```bash
# 버전 확인 후 맞는 버전 설치 (Kubeflow 버전과 맞추는게 중요)
ARGO_VERSION="v3.5.14"
curl -sLO https://github.com/argoproj/argo-workflows/releases/download/${ARGO_VERSION}/argo-linux-amd64.gz
gunzip argo-linux-amd64.gz
chmod +x argo-linux-amd64
sudo mv argo-linux-amd64 /usr/local/bin/argo

argo version
```

2. MinIO 접근권한

Kubeflow의 Argo는 artifact를 MinIO에 저장하는데, 접근 설정이 필요합니다.

```bash
# MinIO 접속 정보 확인
kubectl get secret -n kubeflow mlpipeline-minio-artifact -o yaml

# artifact repository 설정 확인
kubectl get configmap -n kubeflow workflow-controller-configmap -o yaml
```

3. 네임스페이스 확인 후 워크플로우 실행

Kubeflow 설치 방식에 따라 Argo가 뜨는 네임스페이스가 다릅니다.

```bash
# 어느 네임스페이스에 있는지 확인
kubectl get pods -A | grep workflow-controller
```

kubeflow 네임스페이스에 있다면 argo 명령 실행 시 네임스페이스를 명시해야 합니다.

```bash
argo list -n kubeflow
argo submit -n kubeflow hello-world.yaml
argo logs -n kubeflow @latest
```
```yaml
# hello-world.yaml
apiVersion: argoproj.io/v1alpha1
kind: Workflow
metadata:
  generateName: hello-world-
spec:
  entrypoint: hello
  templates:
  - name: hello
    container:
      image: busybox
      command: [echo]
      args: ["hello from argo"]
```
> kubectl 모드에서는 CLI가 Argo Server API 대신 쿠버네티스 API 서버에 직접 Workflow CRD를 생성/조회합니다.

| 항목 | ml-pipeline-ui (Kubeflow) | Argo Workflow UI |
|------|--------------------------|-----------------|
| **워크플로우 정의** | Python SDK로 작성 후 컴파일 → 업로드 | YAML 직접 작성 또는 UI에서 제출 |
| **실행 단위** | Pipeline Run / Experiment | Workflow |
| **YAML 직접 제출** | ❌ 불가 | ✅ 가능 |
| **재실행/재시도 UI** | 제한적 | 세밀하게 가능 |
| **DAG 시각화** | ✅ | ✅ |
| **로그 확인** | ✅ | ✅ |
| **아티팩트 뷰어** | ✅ (metrics, confusion matrix 등) | 기본적인 수준 |
| **주요 사용자** | ML 엔지니어/데이터 사이언티스트 | DevOps/플랫폼 엔지니어 |

## **(별도 방법) Argo Server를 별도 배포 (UI가 필요한 경우)**

1. Argo Server ServiceAccount , RBAC 설정
- serviceaccount 생성
```bash
kubectl create serviceaccount argo-server -n kubeflow
```
- RBAC 설정
```yaml
# argo-server-role-rolebinding.yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: argo-server-role
rules:
- apiGroups: [""]
  resources: ["configmaps", "events", "pods", "pods/exec", "pods/log", "secrets", "serviceaccounts"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
- apiGroups: ["apps"]
  resources: ["deployments"]
  verbs: ["get", "list"]
- apiGroups: ["argoproj.io"]
  resources: ["eventsources", "sensors", "workflows", "workfloweventbindings", "workflowtemplates", "cronworkflows", "clusterworkflowtemplates"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: argo-server-binding
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: argo-server-role
subjects:
- kind: ServiceAccount
  name: argo-server
  namespace: kubeflow
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: argo-default-binding
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: argo-server-role
subjects:
- kind: ServiceAccount
  name: default
  namespace: kubeflow
```
```bash
kubectl apply -f argo-server-role-rolebinding.yaml
```

2. Kubeflow 내장 ml-pipeline-ui와 별도로 Argo 전용 UI가 필요하다면 Argo Server만 추가 배포할 수 있습니다. (NodePort 포함)
```yaml
# argo-ui.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: argo-server
  namespace: kubeflow
spec:
  selector:
    matchLabels:
      app: argo-server
  template:
    metadata:
      labels:
        app: argo-server
    spec:
      serviceAccountName: argo-server   # 1번에서 생성한 SA 참조
      containers:
      - name: argo-server
        image: quay.io/argoproj/argocli:v3.5.14
        args: [server, --auth-mode=server]
        ports:
        - containerPort: 2746
---
apiVersion: v1
kind: Service
metadata:
  name: argo-server
  namespace: kubeflow
spec:
  selector:
    app: argo-server
  ports:
  - port: 2746
    targetPort: 2746
---
apiVersion: v1
kind: Service
metadata:
  name: argo-server-nodeport
  namespace: kubeflow
spec:
  type: NodePort
  selector:
    app: argo-server
  ports:
  - port: 2746
    targetPort: 2746
    nodePort: 32746
```

```bash
# argo-server deployment만 추가 (workflow-controller는 이미 있으므로 생략)
kubectl apply -n kubeflow -f argo-ui.yaml
```

3. Istio 관련 주의사항 추가 권장

NodePort로 외부 접근 시 Kubeflow의 Istio sidecar가 트래픽을 차단할 수 있으므로 한 줄 추가하면 좋습니다:
```
# Istio 환경에서 외부 접근이 안 될 경우 port-forward로 대체
kubectl port-forward svc/argo-server -n kubeflow 2746:2746