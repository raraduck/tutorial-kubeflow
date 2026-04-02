# Profile 생성 템플릿 (Grafana 모니터링 호환 버전)
## 1. Profile 생성 템플릿
### 패턴 요구사항:
- ❌ Profile 이름 패턴 상관없음 (kubeflow- 접두사 불필요)
- ✅ Profile에 레이블 추가 권장 (team, user 등)
- ✅ ServiceMonitor에서 레이블 기반 추출
```yaml
# AIOps 개인 Profile
apiVersion: kubeflow.org/v1
kind: Profile
metadata:
  name: gen01
  # labels:
  #   team: aiops
  #   user: john
  #   user-type: individual
spec:
  owner:
    kind: User
    name: user@example.com # john@neurophet.com
  resourceQuotaSpec:
    hard:
      cpu: "32"
      memory: "128Gi"
      requests.nvidia.com/gpu: "4"

---
# AIDev 공유 Profile
apiVersion: kubeflow.org/v1
kind: Profile
metadata:
  name: seg01
  # labels:
  #   team: aidev
  #   user-type: shared
spec:
  owner:
    kind: User
    name: user@example.com # aidev-lead@neurophet.com
  resourceQuotaSpec:
    hard:
      cpu: "64"
      memory: "256Gi"
      requests.nvidia.com/gpu: "8"
```
### 작동 방식:
- `kubeflow_namespace`: 네임스페이스 이름 그대로 (aiops-john, aidev-shared 등)
- `kubeflow_user`: Profile의 owner 정보에서 자동 추출
- `team`: Profile에 추가한 커스텀 레이블

## 2. 사용자 계정 추가
직접 사용자 계정을 추가
```bash
# 방법 1: Dex Pod에서 생성 (방법 새로 확인 필요, 지금 방법은 오류 발생)
# kubectl exec -n auth deployment/dex -- sh -c "echo 'dwnkim-password-123' | dex hash bcrypt"
# 출력: $2y$12$xxx... (dwnkim 비밀번호 해시)
```
```bash
kubectl edit ConfigMap dex -n auth
```
```yaml
...
    staticPasswords:
    - email: dwnkim@neurophet.com
      hashFromEnv: DEX_USER_PASSWORD # DEX_DWNKIM_PASSWORD
      username: dwnkim
      userID: "010----8498"
    
    - email: minho.lee@neurophet.com
      hashFromEnv: DEX_USER_PASSWORD # DEX_MINHO_PASSWORD 
      username: minho.lee
      userID: "010----2180"
    
    - email: donghyeon.kim@neurophet.com
      hashFromEnv: DEX_USER_PASSWORD # DEX_DONGHYEON_PASSWORD
      username: donghyeon.kim
      userID: "010----3781"
      
    - email: kyeoryelee@neurophet.com
      hashFromEnv: DEX_USER_PASSWORD # DEX_KYEORYEEE_PASSWORD
      username: kyeoryelee
      userID: "010----1355"
...
```
적용
```bash
kubectl rollout restart deployment dex -n auth
```
## 3. 프로필에 사용자를 추가하기
- UI에서 소유하고있는 프로필에 대한 Contributor에 사용자 계정을 추가해주면 됩니다.

# Dex update
```bash
kubectl create configmap dex -n auth   --from-file=config.yaml=dex.yaml   --dry-run=client -o yaml | kubectl apply -f -

kubectl rollout restart deployment dex -n auth
```

# Jupyter Spawner
```bash
kubectl create configmap jupyter-web-app-config-9c2fbg2gdc -n kubeflow   --from-file=spawner_ui_config.yaml=custom-spawner.yaml   -o yaml --dry-run=client | kubectl apply -f -

kubectl rollout restart deployment jupyter-web-app-deployment -n kubeflow
```