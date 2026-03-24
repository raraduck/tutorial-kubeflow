# Kubeflow 사용자 kubectl 설정 가이드

> **클러스터**: `https://192.168.0.80:6443` (Kubernetes v1.29.10)  
> **목적**: 사용자별 `default-editor` 권한의 kubeconfig 생성  
> **권한 범위**: Knative 서비스 배포 + 노드 조회 포함

---

## 전체 진행 순서

```
[관리자] Step 1. kubeflow-node-reader ClusterRole 생성 (최초 1회)
[관리자] Step 2. 사용자 네임스페이스에 ClusterRoleBinding 추가
[관리자] Step 3. 사용자 네임스페이스에 Token Secret 생성
[사용자] Step 4. 노트북 터미널에서 kubeconfig 파일 생성
[사용자] Step 5. 동작 확인
```

---

## [관리자] Step 1. kubeflow-node-reader ClusterRole 생성 (최초 1회)

노드 조회는 클러스터 스코프 권한이므로 `kubeflow-edit`의 aggregation에 추가합니다.  
**한 번만 실행하면 이후 모든 사용자에게 자동 적용됩니다.**

```bash
kubectl apply -f - <<EOF
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: kubeflow-node-reader
  labels:
    # kubeflow-edit ClusterRole에 자동 집계되는 라벨
    rbac.authorization.kubeflow.org/aggregate-to-kubeflow-edit: "true"
rules:
- apiGroups: [""]
  resources:
  - nodes
  - nodes/status
  verbs:
  - get
  - list
  - watch
EOF
```

적용 확인:
```bash
kubectl get clusterrole kubeflow-node-reader
```

---

## [관리자] Step 2. 사용자 네임스페이스에 ClusterRoleBinding 추가

노드 조회는 네임스페이스 스코프 RoleBinding만으로는 동작하지 않으므로  
**사용자 네임스페이스의 `default-editor` SA에 ClusterRoleBinding을 추가합니다.**

```bash
# NAMESPACE 를 실제 사용자 네임스페이스로 변경
NAMESPACE=<사용자네임스페이스>

kubectl apply -f - <<EOF
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: ${NAMESPACE}-default-editor-node-reader
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: kubeflow-node-reader
subjects:
- kind: ServiceAccount
  name: default-editor
  namespace: ${NAMESPACE}
EOF
```

적용 확인:
```bash
kubectl get clusterrolebinding ${NAMESPACE}-default-editor-node-reader
```

---

## [관리자] Step 3. 사용자 네임스페이스에 Token Secret 생성

Kubernetes 1.24+ 환경은 SA 토큰이 자동 생성되지 않으므로 수동으로 생성합니다.

```bash
# NAMESPACE 를 실제 사용자 네임스페이스로 변경
NAMESPACE=<사용자네임스페이스>

kubectl apply -f - <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: ${NAMESPACE}-default-editor-token
  namespace: ${NAMESPACE}
  annotations:
    kubernetes.io/service-account.name: default-editor
type: kubernetes.io/service-account-token
EOF
```

토큰이 정상적으로 채워졌는지 확인 (token 필드가 있어야 함):
```bash
kubectl get secret ${NAMESPACE}-default-editor-token -n ${NAMESPACE} \
  -o jsonpath='{.data.token}' | base64 -d | head -c 20
```

---

## 현재 등록된 사용자 목록

아래 22개 네임스페이스에 대해 Step 2~3을 각각 실행해야 합니다.

| 네임스페이스 | Token Secret 이름 | ClusterRoleBinding 이름 |
|---|---|---|
| `aiops` | `aiops-default-editor-token` | `aiops-default-editor-node-reader` |
| `changseon` | `changseon-default-editor-token` | `changseon-default-editor-node-reader` |
| `dahyun` | `dahyun-default-editor-token` | `dahyun-default-editor-node-reader` |
| `donghyeon-kim` | `donghyeon-kim-default-editor-token` | `donghyeon-kim-default-editor-node-reader` |
| `doyeon` | `doyeon-default-editor-token` | `doyeon-default-editor-node-reader` |
| `dwnkim` | `dwnkim-default-editor-token` | `dwnkim-default-editor-node-reader` |
| `hajin` | `hajin-default-editor-token` | `hajin-default-editor-node-reader` |
| `htkim` | `htkim-default-editor-token` | `htkim-default-editor-node-reader` |
| `hyungyou` | `hyungyou-default-editor-token` | `hyungyou-default-editor-node-reader` |
| `jd-hwang` | `jd-hwang-default-editor-token` | `jd-hwang-default-editor-node-reader` |
| `jieunpark` | `jieunpark-default-editor-token` | `jieunpark-default-editor-node-reader` |
| `jikim` | `jikim-default-editor-token` | `jikim-default-editor-node-reader` |
| `jsy` | `jsy-default-editor-token` | `jsy-default-editor-node-reader` |
| `jylee` | `jylee-default-editor-token` | `jylee-default-editor-node-reader` |
| `kgy` | `kgy-default-editor-token` | `kgy-default-editor-node-reader` |
| `kyeoryelee` | `kyeoryelee-default-editor-token` | `kyeoryelee-default-editor-node-reader` |
| `mijung` | `mijung-default-editor-token` | `mijung-default-editor-node-reader` |
| `minho-lee` | `minho-lee-default-editor-token` | `minho-lee-default-editor-node-reader` |
| `shpark` | `shpark-default-editor-token` | `shpark-default-editor-node-reader` |
| `wjj910` | `wjj910-default-editor-token` | `wjj910-default-editor-node-reader` |
| `wonlee` | `wonlee-default-editor-token` | `wonlee-default-editor-node-reader` |
| `yeg0311` | `yeg0311-default-editor-token` | `yeg0311-default-editor-node-reader` |

### 전체 사용자 일괄 적용 스크립트

신규 클러스터 구성 시 위 22개를 한번에 처리합니다.

```bash
NAMESPACES=(
  aiops changseon dahyun donghyeon-kim doyeon dwnkim
  hajin htkim hyungyou jd-hwang jieunpark jikim
  jsy jylee kgy kyeoryelee mijung minho-lee
  shpark wjj910 wonlee yeg0311
)

for NS in "${NAMESPACES[@]}"; do
  echo "=== 처리 중: ${NS} ==="

  # ClusterRoleBinding 생성
  kubectl apply -f - <<EOF
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: ${NS}-default-editor-node-reader
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: kubeflow-node-reader
subjects:
- kind: ServiceAccount
  name: default-editor
  namespace: ${NS}
EOF

  # Token Secret 생성
  kubectl apply -f - <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: ${NS}-default-editor-token
  namespace: ${NS}
  annotations:
    kubernetes.io/service-account.name: default-editor
type: kubernetes.io/service-account-token
EOF

  echo "✓ ${NS} 완료"
done
```

---

## [사용자] Step 4. 노트북 터미널에서 kubeconfig 생성

Kubeflow 노트북을 실행한 뒤 터미널을 열고 아래를 실행합니다.

### 4-1. 네임스페이스 변수 설정

```bash
# 본인 네임스페이스로 변경
NAMESPACE=<본인네임스페이스>
```

예시:
```bash
NAMESPACE=aiops
```

### 4-2. kubeconfig 자동 생성

```bash
# Secret에서 토큰과 CA 자동 추출 후 kubeconfig 생성
TOKEN=$(kubectl get secret ${NAMESPACE}-default-editor-token \
  -n ${NAMESPACE} \
  -o jsonpath='{.data.token}' | base64 -d)

CA=$(kubectl get secret ${NAMESPACE}-default-editor-token \
  -n ${NAMESPACE} \
  -o jsonpath='{.data.ca\.crt}')

mkdir -p ~/.kube

cat <<EOF > ~/.kube/${NAMESPACE}-config.yaml
apiVersion: v1
kind: Config
clusters:
- cluster:
    server: https://192.168.0.80:6443
    certificate-authority-data: ${CA}
  name: gpu-cluster
contexts:
- context:
    cluster: gpu-cluster
    namespace: ${NAMESPACE}
    user: default-editor
  name: ${NAMESPACE}-context
current-context: ${NAMESPACE}-context
users:
- name: default-editor
  user:
    token: ${TOKEN}
EOF

chmod 600 ~/.kube/${NAMESPACE}-config.yaml
echo "✓ kubeconfig 생성 완료: ~/.kube/${NAMESPACE}-config.yaml"
```

---

## [사용자] Step 5. 동작 확인

### 기본 동작 확인

```bash
# Pod 목록 조회
KUBECONFIG=~/.kube/${NAMESPACE}-config.yaml kubectl get pods -n ${NAMESPACE}

# 노드 목록 조회 (신규 추가 권한)
KUBECONFIG=~/.kube/${NAMESPACE}-config.yaml kubectl get nodes

# Knative 서비스 조회
KUBECONFIG=~/.kube/${NAMESPACE}-config.yaml kubectl get ksvc -n ${NAMESPACE}
```

### 권한 확인

```bash
KUBECONFIG=~/.kube/${NAMESPACE}-config.yaml \
  kubectl auth can-i list nodes
# → yes

KUBECONFIG=~/.kube/${NAMESPACE}-config.yaml \
  kubectl auth can-i create services.serving.knative.dev -n ${NAMESPACE}
# → yes
```

### 기본 kubeconfig에 병합 (선택)

매번 `KUBECONFIG=` 없이 사용하려면:

```bash
cp ~/.kube/config ~/.kube/config.bak 2>/dev/null || true

KUBECONFIG=~/.kube/config:~/.kube/${NAMESPACE}-config.yaml \
  kubectl config view --flatten > /tmp/merged-config

mv /tmp/merged-config ~/.kube/config
chmod 600 ~/.kube/config

kubectl config use-context ${NAMESPACE}-context
kubectl config current-context
```

---

## 권한 범위 요약

| 리소스 | 가능한 작업 |
|---|---|
| Pods / Deployments / Services | 생성, 조회, 수정, 삭제 |
| Knative Services (ksvc) | 생성, 조회, 수정, 삭제 ✅ |
| Kubeflow Notebooks / Pipelines | 생성, 조회, 삭제 |
| PersistentVolumeClaims | 생성, 조회, 삭제 |
| Secrets / ConfigMaps | 조회 (읽기 전용) |
| **Nodes (클러스터 전체)** | **get, list, watch ✅** |
| 다른 사용자 네임스페이스 | 불가 ❌ |
| `serviceaccounts/token` 생성 | 불가 ❌ (관리자만 가능) |

---

## 트러블슈팅

### Secret이 없는 경우
```
Error from server (NotFound): secrets "xxx-default-editor-token" not found
```
→ 관리자에게 Step 3 실행을 요청하세요.

### 노드 조회 불가
```
Error from server (Forbidden): nodes is forbidden
```
→ 관리자에게 Step 1~2 실행을 요청하세요. (`kubeflow-node-reader` ClusterRole 및 ClusterRoleBinding 누락)

### 토큰 생성 권한 오류
```
serviceaccounts "default-editor" is forbidden: cannot create resource "serviceaccounts/token"
```
→ `kubectl create token` 명령은 사용 불가합니다. 반드시 Secret 방식(Step 3)을 사용하세요.

### Knative 배포 오류 (nodeSelector 관련)
```
admission webhook denied: must not set the field(s): spec.template.spec.nodeSelector
```
→ 관리자에게 `config-features` ConfigMap에 `kubernetes.podspec-nodeselector: "enabled"` 설정을 요청하세요.
```bash
kubectl patch configmap config-features -n knative-serving \
  --type merge \
  -p '{"data":{"kubernetes.podspec-nodeselector":"enabled"}}'
```

---

## 참고

- **Token 유효기간**: Secret 방식은 Secret이 삭제되기 전까지 영구 유효
- **Token 갱신**: `kubectl delete secret ${NAMESPACE}-default-editor-token -n ${NAMESPACE}` 후 Step 3 재실행
- **보안 주의**: kubeconfig 파일을 외부에 공유하지 마세요 (`chmod 600` 유지)
- **API 서버**: `https://192.168.0.80:6443`
- **클러스터 버전**: Kubernetes v1.29.10 / Ubuntu 24.04 LTS