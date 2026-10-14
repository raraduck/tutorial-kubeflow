# Multus 로 독립 데이터 평면 구성하기
## 1. 호스트 NIC 설정: 이름 통일, IP, MTU 9000
먼저 기존 netplan에 eno2나 eno2np1 설정이 있는지 확인합니다. NIC를 모두 동일한 이름으로 바꿔줍니다.
### 1.1. 현재 상태와 MAC 확인 (각 노드에서 작업)
```bash
ip -br link | grep eno2
cat /sys/class/net/eno2np1/address
sudo cat /etc/netplan/50-cloud-init.yaml
```
### 1.2. netplan 수정
```bash
sudo cp /etc/netplan/50-cloud-init.yaml /root/50-cloud-init.yaml.bak
sudo vi /etc/netplan/50-cloud-init.yaml
```
50 파일에서 eno2np1 (또는 eno2) 블록을 지운 뒤, 60 파일을 작성합니다.
```bash
# /etc/netplan/60-storage.yaml
network:
  version: 2
  ethernets:
    stor0:
      match:
        macaddress: "xx:xx:xx:xx:xx:xx"   # cat /sys/class/net/eno2np1/address (eno2np1 의 경우임)
      set-name: stor0
      dhcp4: false
      mtu: 9000
      addresses: [10.254.0.xxx/24]
```
```bash
sudo chmod 600 /etc/netplan/60-storage.yaml
echo 'network: {config: disabled}' | sudo tee /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg
sudo netplan get     # stor0가 한 번만, 의도한 값으로 나오는지 확인
# sudo reboot # (NFS v4 부터 필수) DNAT/SNAT 서비스 등록 이후에 재부팅 권장
```
50 파일에 eno2 블록이 다시 나타나지 않았다면, cloud-init 비활성화가 제대로 적용된 것입니다.
## 1.1. (NFS v4 부터 필수) DNAT/SNAT 서비스 등록
작업중인 노드에 접속한 상태에서 순서대로 실행하시면 됩니다. kubectl 명령은 kubeconfig가 있는 곳(관리 노드 등)에서 실행해 주세요.
### 사전확인
```bash
ethtool eno2 | grep -E "Speed|Link detected"   # 10000Mb/s, yes
ip -br a show eno2                              # 10.254.0.150/24 UP
ip route get 10.254.0.200                       # dev eno2 src 10.254.0.150
ping -c 3 10.254.0.200
timeout 5 bash -c "</dev/tcp/10.254.0.200/2049" && echo "2049 OPEN"
sudo iptables --version
sudo iptables -t nat -S | grep 2049             # 출력 없어야 함
```
### DNAT/SNAT 서비스 등록
```bash
SRC=$(ip route get 10.254.0.200 | grep -oP "src \K\S+"); echo $SRC

sudo tee /etc/systemd/system/nfs-10g-nat.service >/dev/null <<EOF
[Unit]
Description=Redirect NFS 192.168.0.200 to 10G 10.254.0.200
After=network-online.target
Wants=network-online.target
Before=kubelet.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/sbin/iptables -t nat -A OUTPUT -d 192.168.0.200 -p tcp --dport 2049 -j DNAT --to-destination 10.254.0.200:2049
ExecStart=/usr/sbin/iptables -t nat -A POSTROUTING -d 10.254.0.200 -p tcp --dport 2049 -j SNAT --to-source ${SRC}
ExecStop=/usr/sbin/iptables -t nat -D OUTPUT -d 192.168.0.200 -p tcp --dport 2049 -j DNAT --to-destination 10.254.0.200:2049
ExecStop=/usr/sbin/iptables -t nat -D POSTROUTING -d 10.254.0.200 -p tcp --dport 2049 -j SNAT --to-source ${SRC}

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable nfs-10g-nat.service
systemctl cat nfs-10g-nat.service | grep ExecStart
```
echo $SRC 결과가 10.254.0.150인지, 그리고 ExecStart 줄의 --to-source에 그 값이 들어갔는지 확인하세요.

재부팅 후 확인
```bash
sudo reboot now
ip -br a show stor0; ip link show stor0 | grep -o 'mtu [0-9]*'
ls /etc/netplan/     # 50-cloud-init.yaml, 60-storage.yaml 두 파일만 있어야 함
```
재부팅 후 통신 속도 확인
```bash
sudo mkdir -p /mnt/t10g
sudo mount -t nfs 192.168.0.200:/volume1/testfield/GPU_storage/Private_storage/dwnkim /mnt/t10g
grep t10g /proc/mounts | fold -w 70
ss -tn dst 10.254.0.200:2049
sudo dd if=/dev/zero of=/mnt/t10g/ddtest bs=4M count=5120 conv=fdatasync status=progress
sudo rm -f /mnt/t10g/ddtest
sudo umount /mnt/t10g
```

# 2. Calico 대역 고정
먼저 현재 값을 확인합니다.
```bash
kubectl -n kube-system get ds calico-node -o yaml | grep -A1 IP_AUTODETECTION_METHOD
```
192.168.0.0/24 대역으로 고정합니다. 이 명령을 실행하면 calico-node 파드가 순차적으로 재시작됩니다.
> 이 단계는 "고정이 안 되어 있으니 고정하자"는 것이 아니라, NIC를 추가한 뒤에도 Calico가 엉뚱한 NIC를 고르지 않도록 감지 방식을 명시하자는 예방 조치였습니다. 그런데 kubespray 기본값을 고려하면 생략해도 될 가능성이 큽니다.
```bash
kubectl -n kube-system set env ds/calico-node IP_AUTODETECTION_METHOD=cidr=192.168.0.0/24
kubectl -n kube-system rollout status ds/calico-node
```
# 3. Whereabouts 설치
> Whereabouts는 Multus로 붙이는 보조 인터페이스(net1, lhnet1 등)에 클러스터 전체에서 겹치지 않는 IP를 나눠주는 IPAM 플러그인입니다.
> 왜 필요한가?
> NAD의 "ipam" 항목에는 IP를 어떤 방식으로 할당할지를 지정해야 합니다.
> `whereabouts` 은 할당 기록을 Kubernetes CRD(IPPool)에 저장해서 모든 노드가 공유할 수 있습니다.
```bash
BASE=https://raw.githubusercontent.com/k8snetworkplumbingwg/whereabouts/master/doc/crds
kubectl apply -f $BASE/daemonset-install.yaml \
  -f $BASE/whereabouts.cni.cncf.io_ippools.yaml \
  -f $BASE/whereabouts.cni.cncf.io_overlappingrangeipreservations.yaml
kubectl -n kube-system get pod -l app=whereabouts -o wide
```
### 동작 방식

1. 파드가 생성되면 Multus가 macvlan CNI를 호출합니다.
2. macvlan CNI가 Whereabouts에 IP를 요청합니다.
3. Whereabouts는 IPPool CRD를 확인해서, range_start부터 range_end(.200~.250) 사이에서 비어 있는 IP를 하나 골라 기록하고 반환합니다.
4. 파드가 삭제되면 그 IP를 반납합니다. 함께 설치되는 DaemonSet은 비정상 종료 등으로 반납되지 않은 IP를 주기적으로 정리합니다.
> 할당 현황은 다음 명령으로 볼 수 있습니다.
```bash
kubectl get ippools.whereabouts.cni.cncf.io -A -o yaml
```
# 4. NAD 생성 (master: stor0)
> 호스트 IP(.134, .135, .140)는 Whereabouts의 관리 대상이 아닙니다. 그래서 NAD에서 범위를 .200~.250으로 나눠, 호스트 IP와 겹치지 않게 한 것입니다.

**NAD에서 .200 제외: range_start를 .201로 바꿔도 되지만, exclude를 쓰면 "NAS 예약"이라는 의도가 드러나서 더 깔끔합니다.**

```bash
cat <<'EOF' | kubectl apply -f -
apiVersion: k8s.cni.cncf.io/v1
kind: NetworkAttachmentDefinition
metadata:
  name: storage-net
  namespace: kube-system
spec:
  config: |
    {
      "cniVersion": "0.3.1",
      "type": "macvlan",
      "master": "stor0",
      "mode": "bridge",
      "mtu": 9000,
      "ipam": {
        "type": "whereabouts",
        "range": "10.254.0.0/24",
        "range_start": "10.254.0.200",
        "range_end": "10.254.0.250",
        "exclude": ["10.254.0.200/32"]
      }
    }
EOF
```
#### 왜 하필 .200~.250인가?

- 서버 이름이 gn1xx이고 IP 끝자리를 호스트 번호와 맞추는 규칙이라면, 앞으로 추가될 서버도 .1xx를 쓰게 됩니다. .200 이상은 이런 호스트들과 겹칠 일이 없습니다.
- .251~.254는 스위치 관리 IP나 게이트웨이 같은 장비용으로 남겨두는 것이 관례라 범위에서 뺐습니다.
- 51개면 충분합니다. Longhorn instance-manager는 노드당 1개 정도만 쓰고, RWX share-manager를 포함해도 노드 3대 기준으로 10개 안팎입니다.

# 5. 테스트 파드로 확인
gn134와 gn135에 테스트 파드를 하나씩 띄웁니다.
```bash
for n in gn140 gn134 gn135; do
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: nettest-$n
  namespace: kube-system
  annotations:
    k8s.v1.cni.cncf.io/networks: kube-system/storage-net
spec:
  nodeName: $n
  containers:
  - name: c
    image: nicolaka/netshoot
    command: ["sleep","infinity"]
EOF
done
```
각 파드의 net1 IP를 확인합니다.
```bash
kubectl -n kube-system exec nettest-gn134 -- ip -br a show net1
kubectl -n kube-system exec nettest-gn135 -- ip -br a show net1
kubectl -n kube-system exec nettest-gn140 -- ip -br a show net1
```
gn134 파드에서 gn135 파드의 net1 IP로 점보 ping을 보냅니다.
```bash
kubectl -n kube-system exec nettest-gn134 -- ping -c3 -M do -s 8972 <gn135 파드의 net1 IP>
```
(선택) 대역폭 확인

netshoot 이미지에 iperf3가 들어 있어서 바로 측정할 수 있습니다.
```bash
kubectl -n kube-system exec nettest-gn135 -- iperf3 -s -D
kubectl -n kube-system exec nettest-gn134 -- iperf3 -c 10.254.0.201 -t 10 -P 4
```
10G 망이라면 9Gbps 이상이 나와야 정상입니다. 확인이 끝나면 테스트 파드를 정리합니다.
```bash
kubectl -n kube-system delete pod nettest-gn134 nettest-gn135 nettest-gn140
```
# 6. Longhorn 설치
먼저 Longhorn이 필요로 하는 패키지와 커널 모듈을 노드에 준비합니다. 이 작업은 세 노드 모두에 해야 합니다.
```bash
for h in 134 135; do
  ssh -t neuroman@gn$h "sudo apt-get install -y open-iscsi nfs-common && sudo systemctl enable --now iscsid && sudo modprobe iscsi_tcp && echo iscsi_tcp | sudo tee /etc/modules-load.d/iscsi_tcp.conf"
done
# 아래 줄은 gn140 자신을 위한 명령으로, 로컬에서 실행합니다.
sudo apt-get install -y open-iscsi nfs-common && sudo systemctl enable --now iscsid && sudo modprobe iscsi_tcp && echo iscsi_tcp | sudo tee /etc/modules-load.d/iscsi_tcp.conf
```
다음으로 Storage Network를 지정해서 Longhorn을 설치합니다.
설치 전에 해당 차트 버전이 v1.29를 지원하는지 확인합니다.
```bash
helm repo add longhorn https://charts.longhorn.io && helm repo update
helm show chart longhorn/longhorn --version 1.11.0 | grep kubeVersion
helm show values longhorn/longhorn --version 1.11.0 | grep -n defaultStorageClassName
```
```bash
helm install longhorn longhorn/longhorn --version 1.11.0 \
  --namespace longhorn-system --create-namespace \
  --set persistence.defaultClass=false \
  --set defaultSettings.defaultReplicaCount=2 \
  --set persistence.defaultClassReplicaCount=2 \
  --set defaultSettings.storageOverProvisioningPercentage=150 \
  --set defaultSettings.replicaAutoBalance=best-effort \
  --set defaultSettings.defaultDataLocality=best-effort \
  --set persistence.defaultDataLocality=best-effort \
  --set defaultSettings.defaultDataPath="/mnt/Rancher_storage" \
  --set defaultSettings.storageNetwork=kube-system/storage-net
  # 위 설정은 추가 필수. 볼륨을 만든 뒤에는 변경하기가 번거로우므로 처음 설치할 때 넣어야 함
  # --set persistence.volumeBindingMode=WaitForFirstConsumer \
  # --set persistence.defaultStorageClassName=local-ssd \ 1.11 longhorn 버전에서는 지원안함
  # 위 설정은 이제 필요없음
kubectl -n longhorn-system get pod -w
```