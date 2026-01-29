# Storage Provisioner

## Dynamic Provisioning

### 1. Install nfs-subdir-external-provisioner using Helm
```
# 1. Helm 레포지토리 추가
helm repo add nfs-subdir-external-provisioner https://kubernetes-sigs.github.io/nfs-subdir-external-provisioner/

# 2. Provisioner 설치 (NFS 서버 IP와 경로를 본인 환경에 맞게 수정)
helm install nfs-provisioner nfs-subdir-external-provisioner/nfs-subdir-external-provisioner \
    --set nfs.server=192.168.x.x \
    --set nfs.path=/your/nfs/path \
    --set storageClass.name=nfs-client \
    --set storageClass.defaultClass=true
```

### 2. Default StorageClass 설정 확인
쿠브플로우 설치 시 별도의 설정을 하지 않으면 (default) 표기가 붙은 StorageClass를 사용합니다. 아래 명령어로 확인했을 때 nfs-client 옆에 (default)가 붙어 있어야 합니다.
```
kubectl get sc
# 결과 예시:
# NAME                   PROVISIONER                                     AGE
# nfs-client (default)   k8s-sigs.io/nfs-subdir-external-provisioner     5m

# 기존 default 해제
kubectl patch storageclass <기존-SC-이름> -p '{"metadata": {"annotations":{"storageclass.kubernetes.io/is-default-class":"false"}}}'

# nfs-client를 default로 설정
kubectl patch storageclass nfs-client -p '{"metadata": {"annotations":{"storageclass.kubernetes.io/is-default-class":"true"}}}'
```
> **주의사항 (On-premise 환경)**
> 
> 이 테스트를 진행하기 전에 모든 워커 노드에 nfs-common 패키지가 설치되어 있어야 합니다. 설치되어 있지 않으면 Pod가 생성될 때 MountVolume.SetUp failed 에러가 발생하며 진행되지 않습니다.


# 직접설치
[NFS_SUBDIR_EXTERNAL_PROVISIONER](https://github.com/raraduck/k8s_vagrant_m1)

