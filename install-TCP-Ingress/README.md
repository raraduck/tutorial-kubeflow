# Auth: k8s
```bash
scp ~/.kube/config <mcp서버계정>@<mcp서버IP>:~/.kube/config

# 또는 내용을 직접 붙여넣기
mkdir -p ~/.kube
cat > ~/.kube/config << 'EOF'
# 여기에 마스터 노드의 ~/.kube/config 내용 붙여넣기
```

```
인증서 = "당신이 누구인지" 증명 (Authentication)
RBAC  = "무엇을 할 수 있는지" 제한 (Authorization)

인증서 발급 (CN=user1)
        ↓
RoleBinding으로 권한 연결
        ↓
허가된 동사(verbs)만 실행 가능

예시:
- get, list, watch  → 조회만 가능
- create, delete    → 금지
- nodes, secrets    → 금지
```
```yaml
# 연구자용 Role - 조회만 허용
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  namespace: kubeflow-user1
rules:
- apiGroups: [""]
  resources: ["pods", "services"]
  verbs: ["get", "list", "watch"]  # 조회만
# create, delete, update 제외 → 금지
# nodes, secrets 미포함 → 접근 불가
```
```bash
# user1 전용 kubeconfig 생성
kubectl config set-credentials user1 \
  --client-certificate=user1.crt \
  --client-key=user1.key

kubectl config set-context user1-context \
  --cluster=kubernetes \
  --namespace=kubeflow-user1 \
  --user=user1

# user1으로 전환
kubectl config use-context user1-context

# 이제 kubeflow-user1 네임스페이스만 접근 가능
kubectl get pods                    # ✅ kubeflow-user1만 조회
kubectl get pods -n kubeflow-user2  # ❌ 권한 없음
```

## 포트포워딩 권한만 허용
```
kubectl port-forward 명령 사용을 위해 필요한 권한:
- pods: get, list
- pods/portforward: create  ← 핵심
```

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: developer-role
  namespace: kubeflow-user1
rules:
# 파드 조회
- apiGroups: [""]
  resources: ["pods", "services", "configmaps"]
  verbs: ["get", "list", "watch"]

# 포트포워딩 허용 ← VSCode SSH용
- apiGroups: [""]
  resources: ["pods/portforward"]
  verbs: ["create"]

# 로그 조회
- apiGroups: [""]
  resources: ["pods/log"]
  verbs: ["get", "list"]

# 파이프라인/노트북 관리
- apiGroups: ["kubeflow.org"]
  resources: ["notebooks", "pipelines"]
  verbs: ["get", "list", "create", "delete"]
```

---

### Remote VSCode 접속 흐름
```
개발자 PC
  └── kubectl port-forward pod/jupyter-xxx 2222:22 -n kubeflow-user1
          ↓
  localhost:2222 → kubeflow pod:22
          ↓
  VSCode Remote SSH → localhost:2222 접속
```