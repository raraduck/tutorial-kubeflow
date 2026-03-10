### 예상 진행 순서 (확인 후 결정)
```
현재: sdb sdc sdd sde → vg0 생성된 상태
                              ↓
1단계: PV 추가 확인     → 4개 SSD 모두 vg0에 포함됐는지 확인
                              ↓
2단계: LV 생성          → vg0에서 논리 볼륨 생성
                              ↓
3단계: 포맷             → mkfs.ext4 또는 xfs
                              ↓
4단계: 마운트           → /mnt/backup 등 원하는 경로에 마운트
                              ↓
5단계: fstab 등록       → 재부팅 후에도 자동 마운트
```

```bash
# VG 상태 확인
sudo vgdisplay vg0

# PV 상태 확인 (어떤 디스크가 vg0에 포함됐는지)
sudo pvdisplay

# LV 상태 확인
sudo lvdisplay

# 파티션 상태 확인
sudo lsblk -f
```
## 2단계: LV 생성
```bash
# RAID0 (striping) + 4개 SSD 적용하여 LV 생성
sudo lvcreate --type raid0 -i 4 -l 100%FREE -n lv_storage vg0
# 핵심 차이
# --type raid0 는 LVM이 RAID 메타데이터를 관리하며 향후 lvconvert로 RAID1/5/6 전환이 가능합니다.
# sudo lvcreate -l 100%FREE --stripes 4 --stripesize 256K -n lv_storage vg0
# --stripes 4 는 단순 LVM striping으로 RAID 메타데이터가 없어 더 가볍지만 RAID 레벨 변경이 불가합니다.
# 확인
sudo lvdisplay
```
## 3단계: 포맷
```bash
# ext4로 포맷 (대용량이라 시간 다소 소요)
sudo mkfs.ext4 /dev/vg0/lv_storage
```
## 4단계: 마운트 경로 생성 및 마운트
```bash
# 마운트 경로 생성 (용도에 맞게 변경 가능)
sudo mkdir -p /mnt/Rancher_storage

# 마운트
sudo mount /dev/vg0/lv_storage /mnt/Rancher_storage

# 확인
df -h | grep lv_storage
```
## 5단계: fstab 등록 (재부팅 후 자동 마운트)
```bash
# UUID 확인
sudo blkid /dev/vg0/lv_storage

# fstab에 추가
echo '/dev/vg0/lv_storage /mnt/Rancher_storage ext4 defaults 0 2' | sudo tee -a /etc/fstab

# fstab 검증
sudo mount -a && df -h | grep lv_storage
```