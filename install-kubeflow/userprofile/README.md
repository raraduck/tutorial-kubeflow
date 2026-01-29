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
  name: aiops-john
  labels:
    team: aiops
    user: john
    user-type: individual
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
  name: aidev-shared
  labels:
    team: aidev
    user-type: shared
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

## 2. Grafana 쿼리 예시
```promql
# 팀별 GPU 사용량
sum(DCGM_FI_DEV_GPU_UTIL) by (team)

# 개인 vs 공유 비교
sum(rate(container_cpu_usage_seconds_total[5m])) by (user_type)

# 특정 사용자 모니터링
sum(rate(container_cpu_usage_seconds_total{user="john"}[5m]))

# AIOps 팀 전체
sum(rate(container_cpu_usage_seconds_total{team="aiops"}[5m]))
```