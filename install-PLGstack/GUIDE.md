# PLG 스택 설치 가이드
> kube-prometheus-stack + Loki + Promtail + DCGM Exporter
> 전략: 전체 Helm으로 통합 관리, 데이터는 cn01 로컬 HDD / Grafana는 NAS NFS

---

## 전체 아키텍처

```
[control-plane 노드: cn01, cn02, cn03]
  Promtail (DaemonSet) ──→ Loki

[GPU worker 노드: gn143, gn144 ...]
  DCGM Exporter (DaemonSet) ──→ Prometheus
  Promtail      (DaemonSet) ──→ Loki

[K8s - monitoring namespace]
  kube-prometheus-stack
  ├── Prometheus   → hostPath: cn01 /mnt/backup/monitoring/prometheus
  ├── Grafana      → NFS PV: 192.168.0.200
  │                  /volume1/testfield/GPU_storage/K8s_storage/Grafana_storage
  └── AlertManager / Node Exporter (자동 포함)

  Loki Stack
  ├── Loki         → hostPath: cn01 /mnt/backup/monitoring/loki
  └── Promtail     → DaemonSet (전체 노드: control-plane + GPU worker)

[nfs-provisioner namespace]
  grafana-nfs-provisioner (NFS StorageClass)
```

---

## 설치 순서 요약

```
1. 사전 준비
2. Namespace 생성
3. NFS StorageClass        (grafana-nfs-provisioner)
4. kube-prometheus-stack   (Prometheus + Grafana + AlertManager + Node Exporter)
5. DCGM Exporter           (GPU 메트릭, Helm)
6. Loki Stack              (Loki + Promtail)
7. 대시보드 및 사용자 계정 설정
```

---

## 1. 사전 준비

### cn01 로컬 HDD 디렉토리 생성
```bash
sudo mkdir -p /mnt/backup/monitoring/{prometheus,loki,alertmanager}
sudo chmod -R 777 /mnt/backup/monitoring

# 확인
df -h /mnt/backup
```

### NAS 폴더 사전 생성 (NAS 관리 UI에서 작업)
```
NAS UI →
  volume1/testfield/GPU_storage/K8s_storage/Grafana_storage  폴더 생성 확인
```

---

## 2. Namespace 생성

```bash
kubectl create namespace nfs-provisioner
kubectl create namespace monitoring

# 확인
kubectl get namespaces
```

---

## 3. NFS StorageClass 설치 (Grafana용)

```bash
helm repo add nfs-subdir-external-provisioner \
  https://kubernetes-sigs.github.io/nfs-subdir-external-provisioner/
helm repo update

helm install grafana-nfs-provisioner \
  nfs-subdir-external-provisioner/nfs-subdir-external-provisioner \
  --namespace nfs-provisioner \
  --set nfs.server=192.168.0.200 \
  --set nfs.path=/volume1/testfield/GPU_storage/K8s_storage/Grafana_storage \
  --set storageClass.name=grafana-nfs-sc \
  --set storageClass.reclaimPolicy=Retain \
  --set storageClass.defaultClass=false \
  --set storageClass.archiveOnDelete=true \
  --set storageClass.provisionerName=k8s-sigs.io/grafana-nfs-provisioner \
  --set storageClass.allowVolumeExpansion=true

# 확인
kubectl get pods -n nfs-provisioner
kubectl get storageclass | grep grafana-nfs-sc
```

---

## 4. kube-prometheus-stack 설치

```bash
helm repo add prometheus-community \
  https://prometheus-community.github.io/helm-charts
helm repo update
```

```yaml
# prometheus-stack-values.yaml
prometheus:
  prometheusSpec:
    retention: 90d
    retentionSize: "40GB"
    nodeSelector:
      kubernetes.io/hostname: cn01
    tolerations:
      - key: "node-role.kubernetes.io/control-plane"
        operator: "Exists"
        effect: "NoSchedule"
    storageSpec:
      volumeClaimTemplate:
        spec:
          storageClassName: monitoring-nfs-sc
          accessModes: ["ReadWriteOnce"]
          resources:
            requests:
              storage: 40Gi

    # 리소스 설정 (지난주 설정 추가)
    resources:
      requests:
        cpu: 2000m
        memory: 4Gi
      limits:
        cpu: 4000m
        memory: 8Gi

    serviceMonitorSelectorNilUsesHelmValues: false
    podMonitorSelectorNilUsesHelmValues: false

  service:
    type: NodePort
    nodePort: 30900

# ── Grafana ──────────────────────────────────────────────
grafana:
  enabled: true
  adminPassword: "Grafana123!@#"

  nodeSelector:
    kubernetes.io/hostname: cn01
  tolerations:
    - key: "node-role.kubernetes.io/control-plane"
      operator: "Exists"
      effect: "NoSchedule"

  env:
    TZ: Asia/Seoul

  grafana.ini:
    server:
      root_url: http://192.168.0.80:30300
    date_formats:
      default_timezone: Asia/Seoul
    users:
      viewers_can_edit: false
    dashboards:
      default_home_dashboard_path: /tmp/dashboards/gpu-availability.json

  service:
    type: NodePort
    nodePort: 30300

  persistence:
    enabled: true
    storageClassName: grafana-nfs-sc
    size: 10Gi
    accessModes:
      - ReadWriteOnce

  # 리소스 설정 (지난주 설정 추가)
  resources:
    requests:
      cpu: 500m
      memory: 512Mi
    limits:
      cpu: 1000m
      memory: 1Gi

  sidecar:
    datasources:
      defaultDatasourceEnabled: true
      url: http://kube-prometheus-stack-prometheus:9090
    dashboards:
      enabled: true              # ← 추가
      searchNamespace: monitoring # ← 추가

  additionalDataSources:
    - name: Loki
      type: loki
      url: http://loki:3100
      isDefault: false
      jsonData:
        maxLines: 1000

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

  dashboards:
    default:
      kubernetes-cluster:
        gnetId: 7249
        revision: 1
        datasource: Prometheus
      node-exporter:
        gnetId: 1860
        revision: 27
        datasource: Prometheus
      nvidia-gpu:
        gnetId: 12239
        revision: 2
        datasource: Prometheus

# ── kube-state-metrics ───────────────────────────────────
kubeStateMetrics:
  enabled: true

kube-state-metrics:
  nodeSelector:
    kubernetes.io/hostname: cn01
  tolerations:
    - key: "node-role.kubernetes.io/control-plane"
      operator: "Exists"
      effect: "NoSchedule"

# ── Prometheus Operator ──────────────────────────────────
prometheusOperator:
  nodeSelector:
    kubernetes.io/hostname: cn01
  tolerations:
    - key: "node-role.kubernetes.io/control-plane"
      operator: "Exists"
      effect: "NoSchedule"

# ── AlertManager ─────────────────────────────────────────
alertmanager:
  enabled: true
  service:
    type: NodePort
    nodePort: 30903
  alertmanagerSpec:
    nodeSelector:
      kubernetes.io/hostname: cn01
    tolerations:
      - key: "node-role.kubernetes.io/control-plane"
        operator: "Exists"
        effect: "NoSchedule"
    storage:
      volumeClaimTemplate:
        spec:
          storageClassName: monitoring-nfs-sc
          accessModes: ["ReadWriteOnce"]
          resources:
            requests:
              storage: 5Gi

# ── Node Exporter ────────────────────────────────────────
nodeExporter:
  enabled: true
```

```bash
helm install kube-prometheus-stack \
  prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --values prometheus-stack-values.yaml

# 확인
kubectl get pods -n monitoring
kubectl get pvc -n monitoring
```

---

## 5. DCGM Exporter 직접 배포

```bash
kubectl apply -f dcgm-exporter.yaml
```

### 주요 GPU 메트릭
| 메트릭 | 설명 |
|--------|------|
| `DCGM_FI_DEV_FB_FREE` | GPU 남은 메모리 (MB) |
| `DCGM_FI_DEV_FB_USED` | GPU 사용 중인 메모리 (MB) |
| `DCGM_FI_DEV_FB_TOTAL` | GPU 전체 메모리 (MB) |
| `DCGM_FI_DEV_GPU_UTIL` | GPU 사용률 (%) |
---

## 6. Loki Stack 설치

```bash
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

# cn01에서 권한 변경
sudo chown -R 10001:10001 /mnt/backup/monitoring/loki
```

```yaml
# loki-values.yaml

# ── Loki ─────────────────────────────────────────────────
loki:
  auth_enabled: false

  nodeSelector:
    kubernetes.io/hostname: cn01      # cn01 고정
  tolerations:
    - key: "node-role.kubernetes.io/control-plane"
      operator: "Exists"
      effect: "NoSchedule"

  extraVolumes:
    - name: loki-data
      hostPath:
        path: /mnt/backup/monitoring/loki
        type: DirectoryOrCreate
  extraVolumeMounts:
    - name: loki-data
      mountPath: /data/loki

  config:
    storage_config:
      filesystem:
        directory: /data/loki/chunks
    limits_config:
      retention_period: 365d          # HDD 3.6T 기준 1년 보존 (ISO 27001)
    compactor:
      working_directory: /data/loki/compactor
      retention_enabled: true
      compaction_interval: 10m
      # delete_request_store: filesystem # 호환되지않아서 삭제!

# ── Grafana 연동 비활성화 ─────────────────────────────────
# loki-stack chart에는 Grafana가 기본으로 포함되어 있는데, 이미 kube-prometheus-stack으로 Grafana를 설치한 상태에서 loki-stack의 Grafana까지 뜨면 두 개의 Grafana가 충돌하거나 datasource 설정이 꼬일 수 있습니다.
grafana:
  enabled: false
  sidecar:
    datasources:
      enabled: false

# ── Promtail ─────────────────────────────────────────────
promtail:
  enabled: true

  # control-plane 포함 전체 노드에 배포 (ISO 27001: 모든 노드 로그 수집)
  tolerations:
    - key: "node-role.kubernetes.io/control-plane"
      operator: "Exists"
      effect: "NoSchedule"

  extraVolumes:
    - name: positions
      hostPath:
        path: /var/lib/promtail
        type: DirectoryOrCreate
  extraVolumeMounts:
    - name: positions
      mountPath: /var/lib/promtail

  config:
    positions:
      filename: /var/lib/promtail/positions.yaml

    clients:
      - url: http://loki:3100/loki/api/v1/push

    scrape_configs:
      - job_name: system
        static_configs:
          - targets: ['localhost']
            labels:
              job: syslog
              node_name: "${HOSTNAME}"   # ✅ 환경변수로 노드명 주입
              __path__: /var/log/*.log
        pipeline_stages:
          - labeldrop:
              - filename

      - job_name: auth
        static_configs:
          - targets: ['localhost']
            labels:
              job: auth
              node_name: "${HOSTNAME}"   # ✅ 환경변수로 노드명 주입
              __path__: /var/log/auth.log
```

```bash
helm install loki grafana/loki-stack \
  --namespace monitoring \
  --values loki-values.yaml

# 확인
kubectl get pods -n monitoring
kubectl get daemonset -n monitoring   # promtail DaemonSet 확인
```

---

## 7. GPU 대시보드 및 사용자 계정 설정

### Grafana 접속
```
http://cn01IP:30300
ID: admin / PW: ChangeMe123! (설치 후 변경)
```

### Viewer 계정 생성
```
Grafana UI → Administration → Users → New User (gpu-user/gpu123!@#)
  - Role: Viewer   ← 조회만 가능, 수정 불가
  - 사용자들에게 URL과 계정 공유
```

### GPU 대시보드 Import
```
Grafana UI → Dashboards → Import → ID: 12239
→ Prometheus 데이터소스 선택 → Import
```

### 주요 PromQL (노드별 GPU 현황)
```promql
# 노드별 GPU 남은 메모리 (GB)
DCGM_FI_DEV_FB_FREE / 1024

# 노드별 GPU 전체 메모리 (GB)
DCGM_FI_DEV_FB_TOTAL / 1024

# 노드별 GPU 사용률 (%)
DCGM_FI_DEV_GPU_UTIL
```

### 대시보드 접근 제어
```
Dashboards → 폴더 생성 (예: "GPU 모니터링")
→ 폴더 Settings → Permissions → Viewer 계정 추가
```

---

## 8. 노드 추가 시 작업

### GPU worker 노드 추가 시
```bash
# GPU 라벨 추가만 하면 DCGM + Promtail 자동 배포
kubectl label node <신규노드> nvidia.com/gpu.present=true
```

### 일반 worker 노드 추가 시
```bash
# Promtail 자동 배포 (taint 없으면 별도 작업 불필요)
# control-plane이라면 taint가 있으므로 toleration이 자동 적용됨
```

---

## 9. 저장 경로 최종 정리

| 서비스 | 배포 방식 | 저장 경로 |
|--------|-----------|-----------|
| Prometheus | Helm (K8s) hostPath | `cn01:/mnt/backup/monitoring/prometheus` |
| Loki | Helm (K8s) hostPath | `cn01:/mnt/backup/monitoring/loki` |
| Grafana | Helm (K8s) NFS PV | `NAS:/volume1/testfield/GPU_storage/K8s_storage/Grafana_storage` |

---

## 10. 접속 URL 및 포트 정리

| 서비스 | 접속 URL | 포트 |
|--------|----------|------|
| Grafana | `http://cn01IP:30300` | NodePort |
| Prometheus | `http://cn01IP:30900` | NodePort |
| AlertManager | `http://cn01IP:30903` | NodePort |
| DCGM Exporter | 내부 ClusterIP | 9400 |
| Node Exporter | 내부 ClusterIP | 9100 |
| Loki | 내부 ClusterIP | 3100 |

---

## 11. 용량 모니터링

```bash
# HDD 사용량 확인
df -h /mnt/backup/monitoring

# 서비스별 세부 용량
du -sh /mnt/backup/monitoring/*

# 일일 증가량 로그 (cron 등록 권장)
echo "$(date): $(du -sh /mnt/backup/monitoring)" \
  >> /var/log/monitoring_disk.log
```