# Longhorn 설치 (k8s)
## 1. 사전 요구사항 확인
```bash
# 전체 노드에서 iscsi 패키지 필요
# 현재 노드 목록 기준 (cn01, gn143, gn150, gn137...)
sudo apt install -y open-iscsi nfs-common

# 또는 전체 노드 한번에
for node in gn143 gn150 gn137; do
  ssh neuroman@$node "sudo apt install -y open-iscsi nfs-common"
done
```
## 2. 설치
```bash
helm repo add longhorn https://charts.longhorn.io
helm repo update

helm install longhorn longhorn/longhorn \
  --namespace longhorn-system \
  --create-namespace \
  --set defaultSettings.defaultReplicaCount=1 \
  --set defaultSettings.storageOverProvisioningPercentage=100 \
  --set persistence.defaultClassReplicaCount=1

# 확인
kubectl get pods -n longhorn-system
```

---

### 각 노드 디스크 등록

설치 후 Longhorn UI에서 각 노드의 `lv_storage` 마운트 경로를 등록합니다.
```bash
Longhorn UI → Node → 각 노드 Edit
→ Add Disk → /mnt/Rancher_storage 추가
```
## 3. Longhorn UI 접근
```bash
# NodePort로 노출
kubectl patch svc longhorn-frontend \
  -n longhorn-system \
  -p '{"spec":{"type":"NodePort","ports":[{"port":80,"nodePort":30880}]}}'

# 접속
http://192.168.0.80:30880
```

---

### 설치 후 작업 순서

```bash
1. Longhorn UI에서 각 노드 디스크 등록
2. StorageClass volumeBindingMode: WaitForFirstConsumer 설정
3. Kubeflow default StorageClass를 longhorn으로 변경
4. 기존 local-path PVC는 rsync로 순차 마이그레이션
```