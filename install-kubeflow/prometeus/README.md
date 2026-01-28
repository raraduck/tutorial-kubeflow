# 모니터링 스택 설치 전략
> Kubeflow와 통합된 모니터링을 위해 kube-prometheus-stack (Prometheus Operator + Grafana)을 사용하겠습니다.

## Kubeflow 모니터링 스택 설치 가이드

### Step 1: Helm 설치 확인
```bash
# Helm 버전 확인
helm version

# 없다면 설치
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
```
### Step 2: kube-prometheus-stack 설치
목적: Prometheus + Grafana + AlertManager + Exporters를 한 번에 설치
```yaml
# 주요 구성 요소:
# # 1. Prometheus (메트릭 수집 엔진)
# retention: 30d           # 데이터 보관 기간 30일
# retentionSize: "50GB"    # 최대 50GB까지 저장
# storage: 100Gi           # PVC 크기
# # 2. Grafana (시각화 도구)
# adminPassword: admin123!@#  # 초기 관리자 비밀번호
# persistence: true           # 설정/대시보드 영구 저장
# nodePort: 30300            # 외부 접속용 포트
# # 3. 사전 구성 대시보드
# kubernetes-cluster (gnetId: 7249): 클러스터 전체 상태
# node-exporter (gnetId: 1860): 노드별 CPU/메모리/디스크
# nvidia-gpu (gnetId: 12239): GPU 사용률/온도/메모리
# 4. 자동 발견 설정
# yamlserviceMonitorSelectorNilUsesHelmValues: false
# 모든 네임스페이스의 ServiceMonitor 자동 감지
# Kubeflow Profile별 메트릭 자동 수집
# 5. 추가 스크래핑 설정
# dcgm-exporter: GPU 메트릭 수집
# kubeflow-profiles: 사용자별 메트릭에 레이블 추가
# 설치 결과:
# monitoring 네임스페이스에 모든 컴포넌트 배포
# Prometheus는 자동으로 클러스터 메트릭 수집 시작
# Grafana는 포트 30300으로 접속 가능
```
```bash
# Helm repo 추가
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

# monitoring 네임스페이스 생성
kubectl create namespace monitoring

# values.yaml 생성 (Kubeflow 최적화)
cat > ~/workspace/kubeflow/prometheus-values.yaml <<'EOF'
# Prometheus 설정
prometheus:
  prometheusSpec:
    # 데이터 보존 기간
    retention: 30d
    retentionSize: "50GB"
    
    # 스토리지 설정
    storageSpec:
      volumeClaimTemplate:
        spec:
          storageClassName: kubeflow-storage
          accessModes: ["ReadWriteOnce"]
          resources:
            requests:
              storage: 100Gi
    
    # 리소스 설정
    resources:
      requests:
        cpu: 2000m
        memory: 4Gi
      limits:
        cpu: 4000m
        memory: 8Gi
    
    # ServiceMonitor 자동 발견
    serviceMonitorSelectorNilUsesHelmValues: false
    podMonitorSelectorNilUsesHelmValues: false
    
    # 추가 스크래핑 설정
    additionalScrapeConfigs:
    # GPU 메트릭 수집 (DCGM Exporter)
    - job_name: 'dcgm-exporter'
      kubernetes_sd_configs:
      - role: pod
        namespaces:
          names:
          - kube-system
      relabel_configs:
      - source_labels: [__meta_kubernetes_pod_label_app]
        regex: dcgm-exporter
        action: keep
      - source_labels: [__meta_kubernetes_namespace]
        target_label: namespace
      - source_labels: [__meta_kubernetes_pod_name]
        target_label: pod
    
    # Kubeflow Profile 메트릭
    - job_name: 'kubeflow-profiles'
      kubernetes_sd_configs:
      - role: pod
        namespaces:
          names:
          - kubeflow
      relabel_configs:
      - source_labels: [__meta_kubernetes_pod_label_kfam_kubeflow_org_user]
        target_label: kubeflow_user
      - source_labels: [__meta_kubernetes_namespace]
        target_label: namespace

# Grafana 설정
grafana:
  enabled: true
  
  # 관리자 비밀번호
  adminPassword: admin123!@#
  
  # Persistence
  persistence:
    enabled: true
    storageClassName: kubeflow-storage
    size: 10Gi
  
  # Ingress 또는 NodePort 설정
  service:
    type: NodePort
    nodePort: 30300
  
  # 리소스
  resources:
    requests:
      cpu: 500m
      memory: 512Mi
    limits:
      cpu: 1000m
      memory: 1Gi
  
  # 대시보드 자동 로드
  dashboardProviders:
    dashboardproviders.yaml:
      apiVersion: 1
      providers:
      - name: 'default'
        orgId: 1
        folder: ''
        type: file
        disableDeletion: false
        editable: true
        options:
          path: /var/lib/grafana/dashboards/default
  
  # 사전 구성 대시보드
  dashboards:
    default:
      # Kubernetes 클러스터 대시보드
      kubernetes-cluster:
        gnetId: 7249
        revision: 1
        datasource: Prometheus
      
      # Node Exporter 대시보드
      node-exporter:
        gnetId: 1860
        revision: 27
        datasource: Prometheus
      
      # GPU 모니터링 대시보드
      nvidia-gpu:
        gnetId: 12239
        revision: 2
        datasource: Prometheus

# Node Exporter (노드 메트릭)
nodeExporter:
  enabled: true

# kube-state-metrics (쿠버네티스 리소스 메트릭)
kubeStateMetrics:
  enabled: true

# AlertManager (알림)
alertmanager:
  enabled: true
  alertmanagerSpec:
    storage:
      volumeClaimTemplate:
        spec:
          storageClassName: kubeflow-storage
          accessModes: ["ReadWriteOnce"]
          resources:
            requests:
              storage: 10Gi
EOF

# kube-prometheus-stack 설치
helm install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --values ~/workspace/kubeflow/prometheus-values.yaml \
  --create-namespace

# 설치 확인
kubectl get pods -n monitoring
```
### Step 3: NVIDIA DCGM Exporter 설치 (GPU 모니터링)
> 목적: GPU 메트릭을 Prometheus가 수집할 수 있도록 노출
```yaml
# DCGM (Data Center GPU Manager) Exporter란?
# NVIDIA GPU의 세부 메트릭을 제공:

# GPU 사용률 (%)
# GPU 메모리 사용량
# GPU 온도
# 전력 소비
# SM(Streaming Multiprocessor) 활성도
# 에러 카운터

# DaemonSet으로 배포
# yamlnodeSelector:
#   nvidia.com/gpu.present: "true"

# GPU가 있는 모든 노드에 자동 배포
# 각 노드에서 GPU 메트릭을 9400 포트로 노출

# ServiceMonitor 생성
# yamlkind: ServiceMonitor
# metadata:
#   name: dcgm-exporter

# Prometheus가 DCGM Exporter를 자동으로 발견
# 30초마다 GPU 메트릭 수집

# 결과:

# 각 GPU 노드에서 실시간 GPU 메트릭 수집
# Prometheus에서 DCGM_FI_DEV_GPU_UTIL 같은 메트릭 사용 가능
```
```bash
# NVIDIA GPU Operator가 없다면 DCGM Exporter만 설치
cat > ~/workspace/kubeflow/dcgm-exporter.yaml <<'EOF'
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: dcgm-exporter
  namespace: kube-system
  labels:
    app: dcgm-exporter
spec:
  selector:
    matchLabels:
      app: dcgm-exporter
  template:
    metadata:
      labels:
        app: dcgm-exporter
    spec:
      nodeSelector:
        nvidia.com/gpu.present: "true"
      hostNetwork: true
      hostPID: true
      containers:
      - name: dcgm-exporter
        image: nvcr.io/nvidia/k8s/dcgm-exporter:3.3.5-3.4.0-ubuntu22.04
        securityContext:
          runAsNonRoot: false
          runAsUser: 0
          privileged: true
        ports:
        - name: metrics
          containerPort: 9400
        volumeMounts:
        - name: pod-gpu-resources
          readOnly: true
          mountPath: /var/lib/kubelet/pod-resources
      volumes:
      - name: pod-gpu-resources
        hostPath:
          path: /var/lib/kubelet/pod-resources
---
apiVersion: v1
kind: Service
metadata:
  name: dcgm-exporter
  namespace: kube-system
  labels:
    app: dcgm-exporter
spec:
  type: ClusterIP
  ports:
  - name: metrics
    port: 9400
    targetPort: 9400
  selector:
    app: dcgm-exporter
---
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: dcgm-exporter
  namespace: kube-system
  labels:
    app: dcgm-exporter
spec:
  selector:
    matchLabels:
      app: dcgm-exporter
  endpoints:
  - port: metrics
    interval: 30s
EOF

kubectl apply -f ~/workspace/kubeflow/dcgm-exporter.yaml

# 확인
kubectl get pods -n kube-system | grep dcgm
```
### Step 4: Kubeflow 사용자별 메트릭 수집을 위한 ServiceMonitor
> 목적: Kubeflow의 Notebook/Pipeline을 사용자별로 추적
```yaml
# ServiceMonitor 1: Kubeflow Notebooks
# yamlrelabelings:
# - sourceLabels: [__meta_kubernetes_namespace]
#   regex: "kubeflow-(.+)"
#   targetLabel: kubeflow_user
#   replacement: "$1"
# 작동 방식:

# 네임스페이스 이름이 kubeflow-alice인 경우
# 정규식으로 alice 추출
# kubeflow_user=alice 레이블 추가

# 결과 쿼리 예시:
# promql# Alice의 CPU 사용량
# sum(rate(container_cpu_usage_seconds_total{kubeflow_user="alice"}[5m]))

# # Alice의 GPU 사용률
# DCGM_FI_DEV_GPU_UTIL{kubeflow_user="alice"}
# ServiceMonitor 2: Kubeflow Pipelines
# yamlselector:
#   matchLabels:
#     app: ml-pipeline

# Pipeline 실행 메트릭 수집
# 파이프라인 성공/실패율 추적

# 효과:

# 사용자별, 팀별 리소스 사용량 추적 가능
# "누가 얼마나 GPU를 사용했는가?" 답변 가능
```
```bash
cat > ~/workspace/kubeflow/kubeflow-servicemonitors.yaml <<'EOF'
# Kubeflow Notebooks 모니터링
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: kubeflow-notebooks
  namespace: monitoring
  labels:
    monitoring: kubeflow
spec:
  namespaceSelector:
    any: true
  selector:
    matchLabels:
      notebook-name: ""
  endpoints:
  - port: http
    interval: 30s
    relabelings:
    # 사용자 정보 추출
    - sourceLabels: [__meta_kubernetes_namespace]
      regex: "kubeflow-(.+)"
      targetLabel: kubeflow_user
      replacement: "$1"
    - sourceLabels: [__meta_kubernetes_pod_label_notebook_name]
      targetLabel: notebook_name

---
# Kubeflow Pipelines 모니터링
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: kubeflow-pipelines
  namespace: monitoring
  labels:
    monitoring: kubeflow
spec:
  namespaceSelector:
    matchNames:
    - kubeflow
  selector:
    matchLabels:
      app: ml-pipeline
  endpoints:
  - port: http
    interval: 30s
EOF

kubectl apply -f ~/workspace/kubeflow/kubeflow-servicemonitors.yaml
```
### Step 5: 커스텀 Grafana 대시보드 생성
> 목적: Kubeflow 전용 모니터링 대시보드 제공
```yaml
# 대시보드 구성:
# Panel 1: GPU Usage by Profile
# json"expr": "sum(DCGM_FI_DEV_GPU_UTIL) by (namespace, pod)"

# 각 Profile(사용자)의 GPU 사용률을 시계열 그래프로 표시
# 어느 사용자가 GPU를 많이 쓰는지 한눈에 확인

# Panel 2: CPU Usage by Profile
# json"expr": "sum(rate(container_cpu_usage_seconds_total{namespace=~\"kubeflow.*\"}[5m])) by (namespace)"

# Profile별 CPU 사용량 (cores 단위)
# 5분 평균 사용률

# Panel 3: Memory Usage by Profile
# json"expr": "sum(container_memory_usage_bytes{namespace=~\"kubeflow.*\"}) by (namespace)"

# Profile별 메모리 사용량 (bytes → GB 자동 변환)

# Panel 4: PVC Usage by Profile
# json"expr": "kubelet_volume_stats_used_bytes{namespace=~\"kubeflow.*\"}"

# 각 사용자의 스토리지 사용량
# PVC별 용량/사용량 테이블

# ConfigMap으로 배포:
# yamllabels:
#   grafana_dashboard: "1"

# 이 레이블이 있으면 Grafana가 자동으로 대시보드 로드
# Grafana 재시작 없이 즉시 사용 가능
```
```bash
cat > ~/workspace/kubeflow/grafana-kubeflow-dashboard.yaml <<'EOF'
apiVersion: v1
kind: ConfigMap
metadata:
  name: kubeflow-resource-dashboard
  namespace: monitoring
  labels:
    grafana_dashboard: "1"
data:
  kubeflow-resources.json: |
    {
      "dashboard": {
        "title": "Kubeflow Resource Usage by User/Team",
        "tags": ["kubeflow", "gpu", "resources"],
        "timezone": "browser",
        "panels": [
          {
            "title": "GPU Usage by Profile",
            "type": "graph",
            "targets": [
              {
                "expr": "sum(DCGM_FI_DEV_GPU_UTIL) by (namespace, pod)",
                "legendFormat": "{{namespace}} - {{pod}}"
              }
            ]
          },
          {
            "title": "CPU Usage by Profile",
            "type": "graph",
            "targets": [
              {
                "expr": "sum(rate(container_cpu_usage_seconds_total{namespace=~\"kubeflow.*\"}[5m])) by (namespace)",
                "legendFormat": "{{namespace}}"
              }
            ]
          },
          {
            "title": "Memory Usage by Profile",
            "type": "graph",
            "targets": [
              {
                "expr": "sum(container_memory_usage_bytes{namespace=~\"kubeflow.*\"}) by (namespace)",
                "legendFormat": "{{namespace}}"
              }
            ]
          },
          {
            "title": "PVC Usage by Profile",
            "type": "table",
            "targets": [
              {
                "expr": "kubelet_volume_stats_used_bytes{namespace=~\"kubeflow.*\"}",
                "format": "table"
              }
            ]
          }
        ]
      }
    }
EOF

kubectl apply -f ~/workspace/kubeflow/grafana-kubeflow-dashboard.yaml
```
### Step 6: PrometheusRule 생성 (알림 규칙)
> 목적: 문제 상황을 자동으로 감지하고 알림
```yaml
# Alert 1: HighGPUUtilization
# yamlexpr: DCGM_FI_DEV_GPU_UTIL > 95
# for: 10m
# 의미:

# GPU 사용률이 95% 이상
# 10분 이상 지속
# → 경고 발생

# 활용:

# GPU가 과부하 상태임을 알림
# 더 많은 GPU가 필요한지 판단

# Alert 2: NamespaceQuotaExceeded
# yamlexpr: |
#   kube_resourcequota{type="used"} / 
#   kube_resourcequota{type="hard"} > 0.9
# 의미:

# ResourceQuota의 90% 사용
# → 곧 할당량 초과 예상

# 활용:

# 사용자가 리소스 한계에 도달하기 전 경고
# Quota 조정 필요 여부 판단
# Alert 3: NotebookIdleTooLong
# 클러스터 외부에서 직접 접속
# 방화벽 설정 필요 없음
```
```bash
cat > ~/workspace/kubeflow/prometheus-rules.yaml <<'EOF'
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: kubeflow-alerts
  namespace: monitoring
  labels:
    prometheus: kube-prometheus
spec:
  groups:
  - name: kubeflow.rules
    interval: 30s
    rules:
    # GPU 사용률 알림
    - alert: HighGPUUtilization
      expr: DCGM_FI_DEV_GPU_UTIL > 95
      for: 10m
      labels:
        severity: warning
      annotations:
        summary: "GPU utilization is very high"
        description: "GPU {{ $labels.gpu }} on {{ $labels.instance }} has been >95% for 10 minutes"
    
    # ResourceQuota 초과 경고
    - alert: NamespaceQuotaExceeded
      expr: |
        kube_resourcequota{type="used"} / 
        kube_resourcequota{type="hard"} > 0.9
      for: 5m
      labels:
        severity: warning
      annotations:
        summary: "Namespace {{ $labels.namespace }} approaching quota limit"
        description: "{{ $labels.resource }} usage is at {{ $value }}% of quota"
    
    # Notebook 장시간 유휴
    - alert: NotebookIdleTooLong
      expr: |
        (time() - kube_pod_created{namespace=~"kubeflow.*", pod=~".*notebook.*"}) > 86400
        and
        rate(container_cpu_usage_seconds_total{namespace=~"kubeflow.*", pod=~".*notebook.*"}[1h]) < 0.1
      for: 1h
      labels:
        severity: info
      annotations:
        summary: "Notebook {{ $labels.pod }} has been idle"
        description: "Notebook in {{ $labels.namespace }} has low CPU usage for >1 day"
EOF

kubectl apply -f ~/workspace/kubeflow/prometheus-rules.yaml
```
### Step 7: 접근 및 확인
```bash
# Grafana 접속 정보
kubectl get svc -n monitoring | grep grafana

# NodePort로 접속
# http://192.168.0.80:30300
# ID: admin
# PW: admin123!@#

# 또는 포트포워딩
kubectl port-forward --address 0.0.0.0 svc/kube-prometheus-stack-grafana -n monitoring 3000:80

# Prometheus UI 접속
kubectl port-forward --address 0.0.0.0 svc/kube-prometheus-stack-prometheus -n monitoring 9090:9090
```
### Step 8: 설치 검증
```bash
# 모든 Pod 확인
kubectl get pods -n monitoring

# Prometheus targets 확인
kubectl port-forward svc/kube-prometheus-stack-prometheus -n monitoring 9090:9090
# 브라우저: http://192.168.0.80:9090/targets

# ServiceMonitor 확인
kubectl get servicemonitor -n monitoring

# DCGM Exporter 메트릭 확인
kubectl exec -n kube-system $(kubectl get pod -n kube-system -l app=dcgm-exporter -o jsonpath='{.items[0].metadata.name}') -- curl localhost:9400/metrics
```
```yaml
# 설치 후 바로 확인 가능한 것들
# Grafana에서 즉시 확인:

# 클러스터 전체 상태

# Dashboards → Kubernetes / Compute Resources / Cluster
# 전체 CPU/메모리 사용률
# 노드 상태


# GPU 상태

# Dashboards → NVIDIA DCGM Exporter Dashboard
# GPU 사용률, 온도, 메모리
# GPU별 상세 정보


# 노드별 상태

# Dashboards → Node Exporter Full
# 각 워커 노드의 디스크/네트워크/CPU



# 사용자 Profile 생성 후 확인 가능:
# yaml# Profile 생성 후
# apiVersion: kubeflow.org/v1
# kind: Profile
# metadata:
#   name: aiops-john

# 사용자별 리소스

# Dashboards → Kubeflow Resource Usage
# aiops-john의 GPU/CPU/메모리 사용량
# 시간대별 사용 패턴


# Quota 사용률

# 각 Profile의 할당량 대비 사용률
# 초과 위험 경고




# 이 8단계를 완료하면:

# ✅ GPU를 포함한 모든 클러스터 리소스 모니터링
# ✅ 사용자/팀별 리소스 추적
# ✅ 자동 알림으로 문제 조기 발견
# ✅ 30일간 히스토리 데이터 분석
```