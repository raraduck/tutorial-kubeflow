# Prometheus와 Grafana Stack 을 설치하기 전에 GPU_storage 하위에 nfs용 PVC 목적폴더를 생성해서 연결해야합니다.
```bash
# Example
# Helm repo 추가 (이미 했다면 skip)
helm repo add nfs-subdir-external-provisioner \
  https://kubernetes-sigs.github.io/nfs-subdir-external-provisioner/
helm repo update

# 1. Kubeflow 사용자용 (User_storage)
# 사용자들이 사용할 Jupyter Notebook 등의 데이터를 담는 용도입니다.
helm install nfs-gpu-provisioner \
  nfs-subdir-external-provisioner/nfs-subdir-external-provisioner \
  --namespace kube-system \
  --set nfs.server=10.100.201.xx \
  --set nfs.path=/nas_경로/GPU_storage/User_storage \
  --set storageClass.name=gpu-storage \
  --set storageClass.reclaimPolicy=Retain \
  --set storageClass.defaultClass=false \
  --set storageClass.archiveOnDelete=true \
  --set storageClass.provisionerName=k8s-sigs.io/nfs-gpu-provisioner \
  --set storageClass.allowVolumeExpansion=true

# 2. Kubeflow 시스템용 (Kubeflow_storage)
# Kubeflow 자체 컴포넌트(Pipelines, Metadata 등)가 사용하는 용도입니다. defaultClass=true로 설정하여 별도 지정이 없으면 이곳에 생성됩니다.
helm install nfs-kubeflow-provisioner \
  nfs-subdir-external-provisioner/nfs-subdir-external-provisioner \
  --namespace kube-system \
  --set nfs.server=10.100.201.xx \
  --set nfs.path=/nas_경로/GPU_storage/Kubeflow_storage \
  --set storageClass.name=kubeflow-storage \
  --set storageClass.reclaimPolicy=Retain \
  --set storageClass.defaultClass=true \
  --set storageClass.archiveOnDelete=true \
  --set storageClass.provisionerName=k8s-sigs.io/nfs-kubeflow-provisioner \
  --set storageClass.allowVolumeExpansion=true

# 3. 모니터링용 (Monitoring_storage)
# Prometheus와 Grafana의 데이터를 저장하는 용도입니다. 앞서 작성하신 prometheus-values.yaml에서 이 SC를 사용하도록 이름을 맞췄습니다.
helm install nfs-monitoring-provisioner \
  nfs-subdir-external-provisioner/nfs-subdir-external-provisioner \
  --namespace kube-system \
  --set nfs.server=10.100.201.xx \
  --set nfs.path=/nas_경로/GPU_storage/Monitoring_storage \
  --set storageClass.name=monitoring-storage \
  --set storageClass.reclaimPolicy=Retain \
  --set storageClass.defaultClass=false \
  --set storageClass.archiveOnDelete=true \
  --set storageClass.provisionerName=k8s-sigs.io/nfs-monitoring-provisioner \
  --set storageClass.allowVolumeExpansion=true

# 4. 확인
kubectl get sc
```

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
cat > ~/workspace/kubeflow/prometheus-values.yaml <<EOF
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
          storageClassName: monitoring-storage
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
    
    # # 추가 스크래핑 설정
    # additionalScrapeConfigs:
    # # GPU 메트릭 수집 (DCGM Exporter)
    # - job_name: 'dcgm-exporter'
    #   kubernetes_sd_configs:
    #   - role: pod
    #     namespaces:
    #       names:
    #       - kube-system
    #   relabel_configs:
    #   - source_labels: [__meta_kubernetes_pod_label_app]
    #     regex: dcgm-exporter
    #     action: keep
    #   - source_labels: [__meta_kubernetes_namespace]
    #     target_label: namespace
    #   - source_labels: [__meta_kubernetes_pod_name]
    #     target_label: pod
    # # Kubeflow Profile 메트릭
    # - job_name: 'kubeflow-profiles'
    #   kubernetes_sd_configs:
    #   - role: pod
    #     namespaces:
    #       names:
    #       - kubeflow
    #   relabel_configs:
    #   - source_labels: [__meta_kubernetes_pod_label_kfam_kubeflow_org_user]
    #     target_label: kubeflow_user
    #   - source_labels: [__meta_kubernetes_namespace]
    #     target_label: namespace

# Grafana 설정
grafana:
  enabled: true
  # [추가] 1. 컨테이너 시스템 시간대 설정 (로그 기록 등)
  
  env:
    TZ: Asia/Seoul

  # [추가] 2. Grafana 설정 파일 오버라이드 (대시보드 UI 기본 시간)
  grafana.ini:
    date_formats:
      default_timezone: Asia/Seoul
  # 관리자 비밀번호
  adminPassword: admin123!@#
  
  # Persistence
  persistence:
    enabled: true
    storageClassName: monitoring-storage
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
          storageClassName: monitoring-storage
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
> node 마다 라벨할당 필요
```bash
kubectl label no <node01 node02 node03> nvidia.com/gpu.present=true
```
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
cat > ~/workspace/kubeflow/dcgm-exporter.yaml <<EOF
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: dcgm-exporter
  namespace: kube-system
  labels:
    app: dcgm-exporter
    release: kube-prometheus-stack
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
        nvidia.com/gpu.present: "true" # 이부분 중요
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
    release: kube-prometheus-stack
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
    release: kube-prometheus-stack
spec:
  selector:
    matchLabels:
      app: dcgm-exporter
  endpoints:
  - port: metrics
    interval: 30s
    relabelings:
    # 노드 이름을 node 라벨로 추가 (DCGM이 제공하는 Hostname 라벨은 유지)
    - sourceLabels: [__meta_kubernetes_pod_node_name]
      targetLabel: node
    # DCGM Exporter Pod 이름 (디버깅용)
    - sourceLabels: [__meta_kubernetes_pod_name]
      targetLabel: exporter_pod
EOF

kubectl apply -f ~/workspace/kubeflow/dcgm-exporter.yaml

# 확인
kubectl get pods -n kube-system | grep dcgm

#  DCGM ServiceMonitor에 release: kube-prometheus-stack 라벨을 추가하여 Prometheus가 "이건 내가 관리해야 할 ServiceMonitor구나"라고 인식
kubectl patch servicemonitor dcgm-exporter -n kube-system \
  --type merge \
  -p '{"metadata":{"labels":{"release":"kube-prometheus-stack"}}}'
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
cat > ~/workspace/kubeflow/kubeflow-servicemonitors.yaml <<EOF
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
    matchExpressions:
    - key: notebook-name
      operator: Exists
  endpoints:
  - port: http
    interval: 30s
    path: /metrics
    relabelings:
    # 네임스페이스 이름 (항상 존재)
    - sourceLabels: [__meta_kubernetes_namespace]
      targetLabel: namespace
    
    # Notebook 이름 (항상 존재)
    - sourceLabels: [__meta_kubernetes_pod_label_notebook_name]
      targetLabel: notebook_name
    
    # Pod 이름 (항상 존재)
    - sourceLabels: [__meta_kubernetes_pod_name]
      targetLabel: pod
    
    # Owner annotation (Profile에서 자동 생성됨)
    - sourceLabels: [__meta_kubernetes_namespace_annotation_owner]
      targetLabel: owner
    
    # Pod IP
    - sourceLabels: [__meta_kubernetes_pod_ip]
      targetLabel: pod_ip
    
    # Node 이름
    - sourceLabels: [__meta_kubernetes_pod_node_name]
      targetLabel: node

---
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
    path: /metrics
EOF

kubectl apply -f ~/workspace/kubeflow/kubeflow-servicemonitors.yaml
```
### Step 5: 커스텀 Grafana 대시보드 생성
> 목적: Kubeflow 전용 모니터링 대시보드 제공
```bash
cat > ~/workspace/kubeflow/grafana-kubeflow-dashboard.yaml <<'EOF'
apiVersion: v1
kind: ConfigMap
metadata:
  name: kubeflow-namespace-dashboard
  namespace: monitoring
  labels:
    grafana_dashboard: "1"
data:
  kubeflow-namespace.json: |
    {
      "title": "Kubeflow Resources by Node and Namespace",
      "uid": "kubeflow-namespace",
      "timezone": "browser",
      "schemaVersion": 38,
      "version": 1,
      "refresh": "30s",
      "time": {
        "from": "now-1h",
        "to": "now"
      },
      "panels": [
        {
          "id": 1,
          "title": "GPU Usage by Node",
          "type": "timeseries",
          "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0},
          "targets": [{
            "expr": "avg by (Hostname) (DCGM_FI_DEV_GPU_UTIL)",
            "legendFormat": "{{Hostname}}",
            "refId": "A"
          }],
          "fieldConfig": {
            "defaults": {
              "unit": "percent",
              "min": 0,
              "max": 100
            }
          }
        },
        {
          "id": 2,
          "title": "CPU Usage by Namespace",
          "type": "timeseries",
          "gridPos": {"h": 8, "w": 12, "x": 12, "y": 0},
          "targets": [{
            "expr": "sum by (namespace) (rate(container_cpu_usage_seconds_total{namespace=~\"dwnkim|aiops|argo|gen01|3dvlm\", container!=\"POD\"}[5m]))",
            "legendFormat": "{{namespace}}",
            "refId": "A"
          }],
          "fieldConfig": {
            "defaults": { "unit": "cores" }
          }
        },
        {
          "id": 3,
          "title": "Memory Usage by Namespace",
          "type": "timeseries",
          "gridPos": {"h": 8, "w": 12, "x": 0, "y": 8},
          "targets": [{
            "expr": "sum by (namespace) (container_memory_working_set_bytes{namespace=~\"dwnkim|aiops|argo|gen01|3dvlm\", container!=\"POD\"})",
            "legendFormat": "{{namespace}}",
            "refId": "A"
          }],
          "fieldConfig": {
            "defaults": { "unit": "bytes" }
          }
        },
        {
          "id": 4,
          "title": "GPU Details (Who is using?)",
          "type": "table",
          "gridPos": {"h": 8, "w": 12, "x": 12, "y": 8},
          "targets": [{
            "expr": "DCGM_FI_DEV_GPU_UTIL",
            "format": "table",
            "instant": true,
            "refId": "A"
          }],
          "transformations": [{
            "id": "organize",
            "options": {
              "excludeByName": {
                "Time": true,
                "__name__": true,
                "job": true,
                "instance": true,
                "UUID": true,
                "device": true
              },
              "indexByName": {
                "Hostname": 0,
                "namespace": 1,
                "pod": 2,
                "modelName": 3,
                "gpu": 4,
                "Value": 5
              },
              "renameByName": {
                "Hostname": "Node",
                "namespace": "Namespace",
                "pod": "Pod Name",
                "modelName": "Model",
                "gpu": "GPU Index",
                "Value": "Util %"
              }
            }
          }],
          "fieldConfig": {
            "overrides": [
              {
                "matcher": {"id": "byName", "options": "Util %"},
                "properties": [
                  { "id": "unit", "value": "percent" },
                  { "id": "custom.displayMode", "value": "gradient-gauge" },
                  { "id": "max", "value": 100 },
                  { "id": "min", "value": 0 }
                ]
              }
            ]
          }
        },
        {
          "id": 7,
          "title": "GPU Capacity Status (Free / Total)",
          "type": "stat",
          "gridPos": {"h": 4, "w": 24, "x": 0, "y": 16},
          "targets": [
            {
              "expr": "sum by (node) (kube_node_status_capacity{resource=\"nvidia_com_gpu\"}) - on(node) group_left() sum by (node) (kube_pod_container_resource_requests{resource=\"nvidia_com_gpu\"}) or sum by (node) (kube_node_status_capacity{resource=\"nvidia_com_gpu\"})",
              "legendFormat": "{{node}} (Free)",
              "refId": "A"
            },
            {
              "expr": "sum by (node) (kube_node_status_capacity{resource=\"nvidia_com_gpu\"})",
              "legendFormat": "{{node}} (Total)",
              "refId": "B",
              "hide": true
            }
          ],
          "description": "각 노드별로 남은 GPU 개수를 보여줍니다. (Capacity - Requests)",
          "fieldConfig": {
            "defaults": {
              "color": { "mode": "thresholds" },
              "thresholds": {
                "mode": "absolute",
                "steps": [
                  { "color": "red", "value": 0 },
                  { "color": "orange", "value": 1 },
                  { "color": "green", "value": 2 }
                ]
              },
              "min": 0,
              "decimals": 0
            }
          }
        },
        {
          "id": 5,
          "title": "GPU Allocated by Namespace",
          "type": "table",
          "gridPos": {"h": 6, "w": 12, "x": 0, "y": 20},
          "targets": [{
            "expr": "sum by (namespace) (kube_pod_container_resource_requests{resource=\"nvidia_com_gpu\", namespace=~\"dwnkim|aiops|argo|gen01|3dvlm\"})",
            "format": "table",
            "instant": true,
            "refId": "A"
          }],
          "transformations": [{
            "id": "organize",
            "options": {
              "excludeByName": { "Time": true, "__name__": true },
              "renameByName": { "namespace": "Namespace", "Value": "GPU Count" }
            }
          }]
        },
        {
          "id": 6,
          "title": "Running Pods by Namespace",
          "type": "stat",
          "gridPos": {"h": 6, "w": 12, "x": 12, "y": 20},
          "targets": [{
            "expr": "count by (namespace) (kube_pod_info{namespace=~\"dwnkim|aiops|argo|gen01|3dvlm\", pod=~\".*\"})",
            "refId": "A"
          }],
          "options": {
            "colorMode": "value",
            "graphMode": "area",
            "textMode": "value_and_name"
          }
        }
      ]
    }
EOF

kubectl apply -f ~/workspace/kubeflow/grafana-kubeflow-dashboard.yaml
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
### Step 9: Grafana 에 STMP 이메일 등록 (알림용)
grafana-smtp-values.yaml
> 임시방편임 (안전하게는 secret으로 app password를 추가해야함)
```bash
helm upgrade kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  -n monitoring \
  -f prometheus-values.yaml \
  -f grafana-smtp-values.yaml \
  --set grafana.assertNoLeakedSecrets=false
```
트래픽 알림용 PromQL
```bash
# dwnkim 네임스페이스의 총 트래픽 양 (Byte/sec)
sum(rate(container_network_receive_bytes_total{namespace="dwnkim"}[1m])) + sum(rate(container_network_transmit_bytes_total{namespace="dwnkim"}[1m]))
```

### 안전한 Secret 등록 방법
```bash
# 1. 실제 앱 비밀번호로 Secret 생성
kubectl create secret generic grafana-smtp-secret \
  --from-literal=smtp-password='여기에실제앱비밀번호입력' \
  -n monitoring
```
주의사항:
- Gmail 앱 비밀번호는 16자리 문자열입니다 (공백 포함 또는 제외 둘 다 가능)
- 작은따옴표 '...' 안에 넣어야 특수문자가 있어도 안전합니다
- 예시: 'abcd efgh ijkl mnop' 또는 'abcdefghijklmnop'

아래와 같이 grafana-smtp-secret.yaml 을 만들어 Helm 차트 업그레이드
> `grafana-smtp-secret` 이 이름으로 연결되는것임 
```yaml
# grafana-smtp-secret.yaml 
grafana:
  envFromSecret: grafana-smtp-secret
  grafana.ini:
    smtp:
      enabled: true
      host: smtp.gmail.com:587
      user: your-email@gmail.com
      password: $__env{smtp-password}  # Secret에서 가져옴
      skip_verify: false
      from_address: your-email@gmail.com
      from_name: Grafana Monitoring
      startTLS_policy: MandatoryStartTLS
```
```bash
# Helm 차트 업그레이드
helm upgrade kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  -n monitoring \
  -f prometheus-values.yaml \
  -f grafana-smtp-secret.yaml

# 업데이트 반영
kubectl rollout status deployment/kube-prometheus-stack-grafana -n monitoring
```