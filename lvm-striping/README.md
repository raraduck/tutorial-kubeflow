# 루프백 디바이스를 사용하면 파일을 디스크처럼 만들어서 LVM 실습
```bash
# 가장 먼저 설치할 것
sudo apt update && sudo apt install lvm2 -y
```
## 루프백 디바이스로 가상 디스크 만들기
```bash
# 10GB 가상 디스크 파일 3개 생성
sudo dd if=/dev/zero of=/tmp/disk1.img bs=1M count=10240 
sudo dd if=/dev/zero of=/tmp/disk2.img bs=1M count=10240 
sudo dd if=/dev/zero of=/tmp/disk3.img bs=1M count=10240 
# dd는 데이터를 복사하는 저수준 명령어
# if=/dev/zero — 입력 소스로 /dev/zero를 사용
# /dev/zero는 0으로 채워진 데이터를 무한히 출력하는 리눅스 가상 장치
# of=/tmp/disk1.img — 출력 대상 파일 경로 (여기에 가상 디스크 이미지가 생성)
# bs=1M — 한 번에 읽고 쓰는 블록 크기를 1MB로 설정
# count=10240 — 블록을 10240번 반복합니다. 1MB × 10240 = 10GB
# 결과적으로 0으로 가득 찬 10GB 파일이 만들어집니다.

# 루프백 디바이스로 연결
sudo losetup /dev/loop1 /tmp/disk1.img
sudo losetup /dev/loop2 /tmp/disk2.img
sudo losetup /dev/loop3 /tmp/disk3.img
# losetup은 파일을 블록 디바이스(루프백 디바이스)로 연결해주는 명령어
# 리눅스는 /dev/loop0, /dev/loop1 등의 가상 블록 디바이스를 기본으로 제공하는데, 여기에 파일을 연결하면 OS가 해당 파일을 실제 디스크처럼 취급
# LVM, 파티셔닝, 포맷 등 디스크에 하는 모든 작업이 가능
# (만약 아래와 같이 실패하면)
# sudo losetup /dev/loop1 /tmp/disk1.img
# losetup: /tmp/disk1.img: failed to set up loop device: Device or resource busy
sudo losetup -l
# -f: 사용 가능한 loop 디바이스 자동 선택
# --show: 어떤 디바이스에 연결됐는지 출력
sudo losetup -f --show /tmp/disk1.img
sudo losetup -f --show /tmp/disk2.img
sudo losetup -f --show /tmp/disk3.img

# 실행하면 아래처럼 할당된 디바이스 이름을 알려줍니다.
# /dev/loop4
# /dev/loop5
# /dev/loop6

# 확인
sudo losetup -l
lsblk
```
이제 /dev/loop1~3이 실제 디스크처럼 보입니다.
## LVM 실습
```bash
# PV 생성
sudo pvcreate /dev/loop4 /dev/loop5 /dev/loop6
# loop 디바이스들을 LVM이 관리할 수 있는 물리 볼륨으로 초기화합니다. 각 디바이스 앞부분에 LVM 메타데이터(UUID, 크기 등)를 기록하는 작업입니다. 실제 디스크로 치면 "이 디스크를 LVM용으로 쓰겠다"고 표시하는 것입니다.
#   Physical volume "/dev/loop12" successfully created.
#   Physical volume "/dev/loop15" successfully created.
#   Physical volume "/dev/loop16" successfully created.

sudo pvs # 등록된 PV 목록과 크기, 소속 VG 등을 간략히 보여줍니다.
#   PV          VG Fmt  Attr PSize  PFree
#   /dev/loop12    lvm2 ---  10.00g 10.00g
#   /dev/loop15    lvm2 ---  10.00g 10.00g
#   /dev/loop16    lvm2 ---  10.00g 10.00g


# VG 생성
sudo vgcreate vg_cache /dev/loop1 /dev/loop2 /dev/loop3
# PV들을 하나의 볼륨 그룹으로 묶습니다. 이 시점부터 3개의 디스크가 하나의 거대한 저장소 풀로 합쳐집니다. vg_cache는 이 그룹의 이름입니다. LV를 만들 때 이 풀에서 용량을 잘라서 씁니다.
#   Volume group "vg_cache" successfully created
sudo vgs # VG 목록과 전체 용량, 남은 용량 등을 보여줍니다.
#   VG       #PV #LV #SN Attr   VSize   VFree
#   vg_cache   3   0   0 wz--n- <29.99g <29.99g

# Striped LV 생성 (-i 3: 3개 디스크에 스트라이핑)
sudo lvcreate -n lv_cache -l 100%FREE -i 3 -I 256 vg_cache # VG에서 실제로 사용할 논리 볼륨을 생성
sudo lvs # LV 목록과 크기, 소속 VG를 보여줍니다.
#   LV       VG       Attr       LSize   Pool Origin Data%  Meta%  Move Log Cpy%Sync Convert
#   lv_cache vg_cache -wi-a----- <29.99g

# 포맷 및 마운트
sudo mkfs.xfs /dev/vg_cache/lv_cache # XFS를 쓰는 이유는 대용량 파일 순차 읽기/쓰기 성능이 ext4보다 좋아서 딥러닝 데이터셋 캐시에 적합하기 때문
# LV를 XFS 파일시스템으로 포맷합니다. 포맷 전까지는 그냥 빈 블록 덩어리이고, 포맷해야 비로소 파일을 저장할 수 있는 구조가 만들어집니다. 
# /dev/vg_cache/lv_cache는 LVM이 자동으로 만들어주는 심볼릭 링크 경로입니다.
sudo mkdir -p /mnt/local_cache
sudo mount /dev/vg_cache/lv_cache /mnt/local_cache
# 포맷된 LV를 /mnt/local_cache 경로에 연결합니다. 
# 마운트 후부터 이 경로에 파일을 읽고 쓰면 실제로는 LVM 볼륨(= 3개 디스크에 스트라이핑된 공간)에 저장됩니다.

df -h /mnt/local_cache  # 약 30GB로 합쳐진 것 확인
# 마운트된 볼륨의 전체/사용/여유 용량을 사람이 읽기 쉬운 단위(GB)로 보여줍니다. 10GB짜리 3개가 합쳐져 약 30GB로 보이면 성공입니다.
## 전체 구조 요약
# /dev/loop12  ┐
# /dev/loop15  ├─ PV → VG(vg_cache) → LV(lv_cache) → XFS → /mnt/local_cache
# /dev/loop16  ┘
```
물리 디바이스 → PV → VG → LV → 파일시스템 → 마운트포인트 순서로 추상화 레이어가 쌓이는 구조입니다.

## 실제 디스크 활용 LVM

물리 디스크는 /dev/sdb, /dev/sdc 같은 형태이고, 파티션이 없는 raw 디스크 전체를 LVM에 넘기는 게 일반적입니다.
```bash
# 디스크 확인 먼저
lsblk

# 예시 출력
sda    # OS 디스크 - 건드리면 안됨
sdb    # 캐시용 디스크 1
sdc    # 캐시용 디스크 2
sdd    # 캐시용 디스크 3
```
기존에 data1, data2, data3으로 이미 마운트된 디스크라면 언마운트를 먼저 해야 합니다.
```bash
sudo umount /data1
sudo umount /data2
sudo umount /data3
```
그 다음부터는 loop 자리에 실제 디바이스명만 바꿔서 진행하면 됩니다.
```bash
sudo pvcreate /dev/sdb /dev/sdc /dev/sdd
sudo vgcreate vg_cache /dev/sdb /dev/sdc /dev/sdd
sudo lvcreate -n lv_cache -l 100%FREE -i 3 -I 256 vg_cache
sudo mkfs.xfs /dev/vg_cache/lv_cache
sudo mkdir -p /mnt/local_cache
sudo mount /dev/vg_cache/lv_cache /mnt/local_cache
```
주의할 점은 pvcreate 시점에 기존 디스크의 데이터가 전부 삭제된다는 것입니다. 캐시용으로 새로 쓸 디스크인지, 기존 데이터가 있는 디스크인지 lsblk와 df -h로 반드시 확인하고 진행하세요.

# local-path-provisioner 에 적용
1. local-path-provisioner 경로 변경

local-path-provisioner의 ConfigMap에서 경로를 /mnt/local_cache로 지정합니다.
```bash
kubectl edit configmap local-path-config -n local-path-storage
```
```yaml
data:
  config.json: |-
    {
      "nodePathMap": [
        {
          "node": "DEFAULT_PATH_FOR_NON_LISTED_NODES",
          "paths": ["/mnt/local_cache"]
        }
      ]
    }
```
노드마다 경로를 다르게 지정할 수도 있습니다.
```yaml
"nodePathMap": [
  {
    "node": "worker-node1",
    "paths": ["/mnt/local_cache"]
  },
  {
    "node": "worker-node2", 
    "paths": ["/mnt/local_disk"]
  },
  {
    "node": "worker-node3",
    "paths": ["/mnt/ssd_cache"]
  }
]
# local-path-provisioner가 PVC 요청이 오면 Pod가 스케줄된 노드를 확인하고, 그 노드에 맞는 paths 경로 아래에 자동으로 디렉토리를 만들어서 PV를 생성해줍니다.
```
```yaml
# 실제로는 노드마다 경로를 통일하는 게 관리가 편하긴 합니다. 나중에 노드가 늘어날 때 ConfigMap 수정 없이 DEFAULT_PATH_FOR_NON_LISTED_NODES로 처리할 수 있기 때문입니다.
"nodePathMap": [
  {
    "node": "DEFAULT_PATH_FOR_NON_LISTED_NODES",
    "paths": ["/mnt/local_cache"]
  }
]
# 이렇게 하면 모든 노드에서 /mnt/local_cache를 쓰는 것으로 통일되고, 새 노드 추가 시 ConfigMap을 건드릴 필요가 없습니다.
```
> 주의할 점
> 
> local-path-provisioner는 앞서 말씀드린 대로 최초 Pod가 뜬 노드를 기억해서 nodeAffinity를 자동으로 잡아주므로 재시작 시 동일 노드로 고정됩니다. 다만 그 노드가 다운되면 Pod가 뜨지 못하는 트레이드오프가 있습니다. 캐시 용도라면 허용 가능한 수준입니다.
>
> 또한 /mnt/local_cache가 모든 워커 노드에 동일하게 마운트되어 있어야 합니다. 노드마다 LVM 세팅을 반복해서 진행하셨는지 확인하세요.