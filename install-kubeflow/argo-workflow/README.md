# kubeflow 의 argo 엔진을 사용하기

## 1. argo 명령어 다운로드

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
# 요약
1. SA 생성
2. ClusterRole + ClusterRoleBinding 적용
3. argo-ui.yaml 적용 (Deployment)
	1) argo-server 배포 
	2) HTTP 모드 적용 (TLS 비활성화)
	3) NetworkPolicy 해제
4. 사용자 권한 제어
	1) server 모드는 바로 접속 후 사용
	2) client 모드는 계정생성-권한연결-토큰발급


## 2. Argo Server 권한을 위한 ServiceAccount, RBAC 설정
### serviceaccount 생성
```bash
kubectl create serviceaccount argo-server -n kubeflow
```
### RBAC 설정 (client용 토큰검증 권한까지 포함)
```yaml
# argo-server-role-rolebinding-kubeflow.yaml
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
- apiGroups: ["authentication.k8s.io"]
  resources: ["tokenreviews"]
  verbs: ["create"]
- apiGroups: ["authorization.k8s.io"]
  resources: ["subjectaccessreviews"]
  verbs: ["create"]
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
kubectl apply -f argo-server-role-rolebinding-kubeflow.yaml
```



## 3. Argo Server 별도 배포 (UI)
### 1) argo-server 배포 
```bash
# UI + NodePort Service 생성 (전역권한: 인증없이 접속 기본)
# args: [ server, --auth-mode=server ]
kubectl apply -f argo-ui.yaml
```
### 2) HTTP 모드 적용 (TLS 비활성화)
NodePort 직접 접근 시 인증서 문제를 우회하기 위해 `--secure=false` 옵션을 추가합니다.
```bash
# insecure 모드로 우회접속 허용 및 접속권한 (개발/테스트 전역권한, server)
kubectl patch deployment argo-server -n kubeflow \
  --type=json \
  -p='[{"op":"replace","path":"/spec/template/spec/containers/0/args","value":["server","--auth-mode=server","--secure=false"]}]'
```
```bash
# insecure 모드로 우회접속 허용 및 접속권한 (다중사용자환경, client)
kubectl patch deployment argo-server -n kubeflow \
  --type=json \
  -p='[{"op":"replace","path":"/spec/template/spec/containers/0/args","value":["server","--auth-mode=client","--secure=false"]}]'

# 확인
kubectl rollout restart deployment argo-server -n kubeflow
kubectl rollout status deployment argo-server -n kubeflow 
```
### 3) NetworkPolicy 해제
현재 `default-allow-same-namespace` 정책이 외부 트래픽을 막고 있으므로 Argo Server용 정책을 추가합니다.
```bash
## 접속 흐름
브라우저
  → 노드IP:32746 (NodePort)
  → kube-proxy가 2746 포트로 포워딩
  → NetworkPolicy: 2746 허용 ✅        ← L4
  → Istio sidecar (istio-proxy)
      → AuthorizationPolicy 검사: rules-{} → 전체 허용 ✅    ← L7
      → mTLS 검사: 스킵 ✅
  → argo-server 컨테이너
```
```bash
# argo-server 전용 NetworkPolicy 추가
kubectl apply -f - <<EOF
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: argo-server-allow-external
  namespace: kubeflow
spec:
  podSelector:
    matchLabels:
      app: argo-server
  policyTypes:
  - Ingress
  ingress:
  - {}   # 모든 트래픽 허용 (외부 NodePort 포함)
EOF
# 위 방식은 출발지/포트 제한 없이 전체 허용이라 의도는 명확하지만, 보안상 더 좁히고 싶다면 아래처럼 포트만 제한할 수도 있습니다.
kubectl apply -f - <<EOF
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: argo-server-allow-external
  namespace: kubeflow
spec:
  podSelector:
    matchLabels:
      app: argo-server
  ingress:
  - ports:
    - port: 2746
      protocol: TCP
  policyTypes:
  - Ingress
EOF
```
argo-server용 Istio AuthorizationPolicy 추가:
```bash
kubectl apply -f - <<EOF
apiVersion: security.istio.io/v1beta1
kind: AuthorizationPolicy
metadata:
  name: argo-server-allow
  namespace: kubeflow
spec:
  selector:
    matchLabels:
      app: argo-server
  rules:
  - {}  # 모든 트래픽 허용
EOF
```

## 4. 사용자 권한 제어 (예시 aidev 계정=네임스페이스)
### ⚠️ Argo Workflow를 사용하는 모든 네임스페이스에 동일하게 적용 필요
내장된 argo-cluster-role을 그대로 활용하는 것을 권장합니다. (Kubeflow 파이프라인과의 호환성 때문)
```bash
# 현재 바인딩 확인
kubectl get rolebinding,clusterrolebinding -n aidev | grep default
# 전체 권한 (clusterrolebinding)
kubectl create clusterrolebinding argo-default-binding \
  --clusterrole=argo-cluster-role \
  --serviceaccount=aidev:default
# 또는 네임스페이스 범위로만 적용하고 싶다면 RoleBinding으로
kubectl create rolebinding argo-default-binding \
  -n aidev \
  --clusterrole=argo-cluster-role \
  --serviceaccount=aidev:default
```
토큰획득 
```bash
# default SA로 토큰을 발급하면 됩니다.
kubectl create token default -n aidev # 기본은 1시간입니다. --duration=720h  옵션으로 시간 조절 가능
# 토큰 확인
echo "Bearer $(kubectl create token default -n aidev --duration=720h)"

# 무제한 토큰은 아래와 같이 합니다.
kubectl apply -f - <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: default-argo-token
  namespace: aidev
  annotations:
    kubernetes.io/service-account.name: default
type: kubernetes.io/service-account-token
EOF
# 토큰 확인 (UI에 로그인할 때 토큰앞에 Bearer 를 붙여야합니다.)
echo "Bearer $(kubectl get secret default-argo-token -n aidev -o jsonpath='{.data.token}' | base64 -d)"
```
### 예시) dwnkim 사용자 네임스페이스에 Argo 권한 추가
Argo Workflow를 사용자 네임스페이스(예: dwnkim)에서 실행하려면 해당 네임스페이스의 default SA에도 권한을 부여해야 합니다.
```bash
# 사용자 네임스페이스의 default SA에 argo-cluster-role 바인딩
kubectl create rolebinding argo-default-binding \
  -n <namespace> \
  --clusterrole=argo-cluster-role \
  --serviceaccount=<namespace>:default

# 예시: dwnkim 네임스페이스
kubectl create rolebinding argo-default-binding \
  -n dwnkim \
  --clusterrole=argo-cluster-role \
  --serviceaccount=dwnkim:default
```

> **주의**: 이 설정이 없으면 Argo Workflow 실행 시 아래 에러가 발생합니다.
> ```
> pods "xxx" is forbidden: User "system:serviceaccount:<namespace>:default" 
> cannot patch resource "pods" in API group "" in the namespace "<namespace>"
> ```