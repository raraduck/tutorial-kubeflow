# 🔐 aiops 네임스페이스 격리 환경 구성 가이드
> 목표: 특정 사용자가 -n aiops 없이 aiops 네임스페이스만 사용하고, 다른 네임스페이스는 전혀 접근 불가하도록 설정

### 📋 전체 설정 순서
1. Namespace 생성
2. ServiceAccount 생성 (사용자별)
3. Role 생성 (aiops 내 권한 정의)
4. RoleBinding 생성 (사용자 ↔ Role 연결)
5. kubeconfig 파일 생성 (config-aiops)
6. 격리 검증
#### Step 1 — Namespace 생성
```bash
kubectl create namespace aiops
```
#### Step 2 — ServiceAccount 생성 (사용자별)
각 사용자마다 ServiceAccount를 생성합니다.
```yaml
# sa-user1.yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: user1          # 사용자 이름으로 변경
  namespace: aiops
---
# SA의 토큰을 명시적으로 생성 (k8s 1.24+ 필수)
apiVersion: v1
kind: Secret
metadata:
  name: user1-token
  namespace: aiops
  annotations:
    kubernetes.io/service-account.name: user1
type: kubernetes.io/service-account-token
```
```bash
kubectl apply -f sa-user1.yaml
```
#### Step 3 — Role 생성 (aiops 네임스페이스 내 전체 권한)

> ⚠️ ClusterRole이 아닌 Role 을 사용해야 다른 네임스페이스 접근이 원천 차단됩니다.

```yaml
# role-aiops-full.yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: aiops-full-access
  namespace: aiops
rules:
- apiGroups: ["*"]
  resources: ["*"]
  verbs: ["*"]
```
```bash
kubectl apply -f role-aiops-full.yaml
```
> 💡 권한을 더 세밀하게 제한하려면 resources와 verbs를 구체적으로 지정할 수 있습니다.

### Step 4 — RoleBinding 생성 (사용자와 Role 연결)
```yaml
# rolebinding-user1.yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: aiops-full-access-user1
  namespace: aiops
subjects:
- kind: ServiceAccount
  name: user1
  namespace: aiops
roleRef:
  kind: Role
  name: aiops-full-access
  apiGroup: rbac.authorization.k8s.io
```
```bash
kubectl apply -f rolebinding-user1.yaml
```
#### Step 5 — config-aiops kubeconfig 파일 생성
아래 스크립트를 실행하면 사용자별 kubeconfig가 자동 생성됩니다.
```bash
#!/bin/bash
# gen-kubeconfig.sh

# 인자 검증
if [ -z "$1" ] || [ -z "$2" ]; then
  echo "❌ 사용법: ./gen-kubeconfig.sh <username> <namespace>"
  echo "   예시:   ./gen-kubeconfig.sh user1 aiops"
  exit 1
fi

USER="$1"
NAMESPACE="$2"
CLUSTER_NAME=cluster.local

# 토큰 추출
TOKEN=$(kubectl get secret ${USER}-token -n ${NAMESPACE} \
  -o jsonpath='{.data.token}' | base64 --decode)

# CA 인증서 추출
CA=$(kubectl get secret ${USER}-token -n ${NAMESPACE} \
  -o jsonpath='{.data.ca\.crt}')

# API 서버 주소 확인
API_SERVER=$(kubectl config view \
  --minify -o jsonpath='{.clusters[0].cluster.server}')

# kubeconfig 생성
cat <<EOF > config-${NAMESPACE}-${USER}
apiVersion: v1
kind: Config
clusters:
- cluster:
    certificate-authority-data: ${CA}
    server: ${API_SERVER}
  name: ${CLUSTER_NAME}
contexts:
- context:
    cluster: ${CLUSTER_NAME}
    namespace: ${NAMESPACE}
    user: ${USER}
  name: ${NAMESPACE}-context
current-context: ${NAMESPACE}-context
users:
- name: ${USER}
  user:
    token: ${TOKEN}
EOF

echo "✅ config-${NAMESPACE}-${USER} 생성 완료"
```
```bash
chmod +x gen-kubeconfig.sh
# ./gen-kubeconfig.sh user1 aiops      # → config-aiops-user1 생성
# ./gen-kubeconfig.sh user2 dev        # → config-dev-user2 생성
# ./gen-kubeconfig.sh user3 staging    # → config-staging-user3 생성

USERS=("user1" "user2" "user3")
NAMESPACE="aiops"

for USER in "${USERS[@]}"; do
  ./gen-kubeconfig.sh $USER $NAMESPACE
done
```
#### Step 6 — 사용자가 받은 kubeconfig 사용법
```bash
# 방법 1: 파일 지정
export KUBECONFIG=~/config-aiops-user1

# 방법 2: 기존 config에 병합
cp config-aiops-user1 ~/.kube/config

# 이후 -n 없이도 aiops 네임스페이스가 기본값으로 동작
kubectl get pods          # aiops 네임스페이스의 pod 조회
kubectl apply -f app.yaml # aiops에 배포
```
### 🛡️ 격리 검증 방법
```bash
# ✅ 이건 가능해야 함
kubectl get pods
kubectl create deployment test --image=nginx

# ❌ 이건 차단되어야 함 (Error from server (Forbidden))
kubectl get pods -n default
kubectl get pods -n kube-system
kubectl get nodes
kubectl get namespaces
```
### 🔄 여러 사용자 일괄 처리 팁
사용자가 많다면 아래처럼 루프로 처리할 수 있습니다.
```bash
#!/bin/bash
# bulk-create-users.sh

# 인자 검증
if [ -z "$1" ]; then
  echo "❌ 사용법: ./bulk-create-users.sh <namespace> <user1> <user2> ..."
  echo "   예시:   ./bulk-create-users.sh aiops user1 user2 user3"
  exit 1
fi

NAMESPACE="$1"
shift  # 첫 번째 인자(namespace)를 제거하고 나머지를 USERS로 사용
USERS=("$@")

if [ ${#USERS[@]} -eq 0 ]; then
  echo "❌ 사용자 이름을 하나 이상 입력해주세요."
  exit 1
fi

echo "📦 Namespace: ${NAMESPACE}"
echo "👤 Users: ${USERS[*]}"
echo ""

for USER in "${USERS[@]}"; do
  echo "🔧 [$USER] 처리 중..."

  # SA 생성
  kubectl create sa "$USER" -n "$NAMESPACE"

  # Token Secret 생성
  kubectl apply -f - <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: ${USER}-token
  namespace: ${NAMESPACE}
  annotations:
    kubernetes.io/service-account.name: ${USER}
type: kubernetes.io/service-account-token
EOF

  # RoleBinding 생성 (roleRef.name 으로 수정)
  kubectl create rolebinding "aiops-full-access-${USER}" \
    --role=aiops-full-access \
    --serviceaccount="${NAMESPACE}:${USER}" \
    -n "$NAMESPACE"

  # kubeconfig 생성 (namespace 인자 추가)
  ./gen-kubeconfig.sh "$USER" "$NAMESPACE"

  echo "✅ [$USER] 완료"
  echo ""
done

echo "🎉 전체 완료: ${#USERS[@]}명 처리됨"
```