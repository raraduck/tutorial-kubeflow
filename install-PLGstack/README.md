# Step 1: Prometheus용 NFS StorageClass 설치
```bash
helm install prometheus-nfs-provisioner \
  nfs-subdir-external-provisioner/nfs-subdir-external-provisioner \
  --namespace nfs-provisioner \
  --set nfs.server=192.168.0.200 \
  --set nfs.path=/volume1/testfield/GPU_storage/K8s_storage/Monitoring_storage \
  --set storageClass.name=monitoring-nfs-sc \
  --set storageClass.reclaimPolicy=Retain \
  --set storageClass.defaultClass=false \
  --set storageClass.archiveOnDelete=true \
  --set storageClass.provisionerName=k8s-sigs.io/monitoring-nfs-provisioner \
  --set storageClass.allowVolumeExpansion=true

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
kubectl get storageclass
```
# Step 2: kube-prometheus-stack 설치
```yaml
# prometheus-stack-values.yaml

# ── Prometheus ───────────────────────────────────────────
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

# Loki datasource는 kube-prometheus-stack의 Grafana에 직접 추가
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

kubectl get pods -n monitoring -w
```
# 다음 단계: DCGM + Loki 설치
```bash
# DCGM Exporter
helm install dcgm-exporter gpu-helm-charts/dcgm-exporter \
  --namespace monitoring \
  --values dcgm-values.yaml

# Loki Stack
helm install loki grafana/loki-stack \
  --namespace monitoring \
  --values loki-values.yaml
```
```yaml
# dcgm-values.yaml
serviceMonitor:
  enabled: true
  additionalLabels:
    release: kube-prometheus-stack
  relabelings:
    - sourceLabels: [__meta_kubernetes_pod_node_name]
      targetLabel: node
    - sourceLabels: [__meta_kubernetes_pod_name]
      targetLabel: exporter_pod

nodeSelector:
  nvidia.com/gpu.present: "true"

tolerations:
  - key: "node-role.kubernetes.io/control-plane"
    operator: "Exists"
    effect: "NoSchedule"

# ↓ 아래 내용 추가
# Service를 Headless로 변경하거나 PodMonitor 방식 선택
service:
  type: ClusterIP
  clusterIP: None          # Headless Service로 변경 → node IP로 수집
```
```yaml
# loki-values.yaml

# ── Loki ─────────────────────────────────────────────────
loki:
  auth_enabled: false

  nodeSelector:
    kubernetes.io/hostname: cn01
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
      retention_period: 365d
    compactor:
      working_directory: /data/loki/compactor
      retention_enabled: true
      compaction_interval: 10m

# ── Grafana 연동 비활성화 ─────────────────────────────────
# kube-prometheus-stack의 Grafana datasource와 충돌 방지
# loki-stack chart에는 Grafana가 기본으로 포함되어 있는데, 이미 kube-prometheus-stack으로 Grafana를 설치한 상태에서 loki-stack의 Grafana까지 뜨면 두 개의 Grafana가 충돌하거나 datasource 설정이 꼬일 수 있습니다.
grafana:
  enabled: false
  sidecar:
    datasources:
      enabled: false

# ── Promtail ─────────────────────────────────────────────
promtail:
  enabled: true

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
              __path__: /var/log/*.log
        relabel_configs:
          - source_labels: [__meta_kubernetes_pod_node_name]
            target_label: node_name
        pipeline_stages:
          - labeldrop:
              - filename

      - job_name: auth
        static_configs:
          - targets: ['localhost']
            labels:
              job: auth
              __path__: /var/log/auth.log
        relabel_configs:
          - source_labels: [__meta_kubernetes_pod_node_name]
            target_label: node_name
```