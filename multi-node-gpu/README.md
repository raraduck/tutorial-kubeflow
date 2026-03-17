# multi-node-gpu setting for kubeflow
## **1. GPU 관련 필수 작업 3단계**
### 1.GPU 노드 OS 레벨 사전 조건 (GPU Worker)
필수
* NVIDIA Driver
* NVIDIA Container Toolkit
1. 추천 드라이버: nvidia-driver-535-server
- 안정성 (LTS): 535 버전은 NVIDIA의 LTS(Long Term Support) 브랜치입니다. Kubernetes와 같은 인프라 환경에서는 최신 기능보다 안정성이 최우선입니다.
- 호환성 (V100 & P100): V100과 P100은 세대가 다릅니다(Volta vs Pascal). 너무 최신 드라이버는 구형 아키텍처(P100)에서 예기치 않은 버그가 발생할 수 있습니다. 535버전은 두 카드를 모두 완벽하게 지원하는 검증된 버전입니다.
- CUDA 버전: 535 드라이버는 CUDA 12.2까지 지원합니다. 이는 최신 PyTorch, TensorFlow 등을 구동하기에 충분합니다.
- Server 패키지: 데스크탑용(nvidia-driver-535) 대신 서버용(-server) 패키지는 불필요한 그래픽 패키지(X11 관련) 의존성을 줄이고 연산(Compute)에 최적화되어 있습니다.
- utils 와 driver 를 모두 설치해야합니다. (utils 는 모니터링용, driver 는 실제 학습용)
> 다양한 GPU를 모두 커버하려면 570 드라이버를 추천합니다. 
> ```
> sudo apt install nvidia-driver-570-server nvidia-utils-570-server -y
> sudo apt install nvidia-driver-570-server-open nvida-utils-570-server -y
> ```
> RTX 5000 Blackwell이 핵심 제약 조건입니다. Blackwell 아키텍처(50xx 시리즈)는 비교적 최신이라 구버전 드라이버에서 지원이 안 됩니다. 570은 Blackwell을 공식 지원하는 드라이버 중 안정성이 검증된 버전입니다.)

```bash
# 2. NVIDIA 드라이버 설치
# 설치 여부 확인
dpkg -l | grep nvidia-container-toolkit
# 아무것도 안 나온다면: 아래 명령어로 설치합니다.

sudo rm /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit



# containerd 기본 설정 파일 생성
sudo mv /etc/containerd/config.toml /etc/containerd/config.toml.bak
containerd config default | sudo tee /etc/containerd/config.toml

# 쿠버네티스 필수 설정 수정 (SystemdCgroup)
sudo sed -i 's/SystemdCgroup = false/SystemdCgroup = true/g' /etc/containerd/config.toml

# NVIDIA 설정 다시 주입
# NVIDIA 설정을 다시 config.toml 및 conf.d에 반영
# sudo nvidia-ctk runtime configure --runtime=containerd 
sudo nvidia-ctk runtime configure --runtime=containerd --set-as-default

# 서비스 재시작
# (아직 안됨, 아래 작업 더 진행해야함) sudo systemctl restart containerd
```
> 만약, config.toml 파일만으로 설정을 완료하고싶을땐 아래와 같이 수정정
* /etc/containerd/config.toml
```toml
# vim /etc/containerd/config.toml
version = 2
root = "/var/lib/containerd"
state = "/run/containerd"

[grpc]
  address = "/run/containerd/containerd.sock"
  uid = 0
  gid = 0

[plugins]
  [plugins."io.containerd.grpc.v1.cri"]
    sandbox_image = "registry.k8s.io/pause:3.9"

    [plugins."io.containerd.grpc.v1.cri".containerd]
      # [핵심 1] 기본 런타임을 nvidia로 변경
      default_runtime_name = "nvidia"
      snapshotter = "overlayfs"

      [plugins."io.containerd.grpc.v1.cri".containerd.runtimes]

        # 2. NVIDIA 런타임 추가 (간단)
        # [plugins."io.containerd.grpc.v1.cri".containerd.runtimes.nvidia]
        #   runtime_type = "io.containerd.runc.v2"
        #   [plugins."io.containerd.grpc.v1.cri".containerd.runtimes.nvidia.options]
        #     BinaryName = "/usr/bin/nvidia-container-runtime"
        #     SystemdCgroup = true

        # [핵심 2] NVIDIA 런타임 정의 (오타 없음)
        [plugins."io.containerd.grpc.v1.cri".containerd.runtimes.nvidia]
          privileged_without_host_devices = false
          runtime_engine = ""
          runtime_root = ""
          runtime_type = "io.containerd.runc.v2"
          [plugins."io.containerd.grpc.v1.cri".containerd.runtimes.nvidia.options]
            BinaryName = "/usr/bin/nvidia-container-runtime"
            SystemdCgroup = true

        # 일반 runc 런타임 정의
        [plugins."io.containerd.grpc.v1.cri".containerd.runtimes.runc]
          runtime_type = "io.containerd.runc.v2"
          [plugins."io.containerd.grpc.v1.cri".containerd.runtimes.runc.options]
            BinaryName = "/usr/local/bin/runc"
            SystemdCgroup = true
```
1. 맨 윗줄에 `version = 2`가 있다면 그대로 둡니다.
2. 그 아래에 `imports` 라인을 추가합니다.
3. `[plugins."io.containerd.grpc.v1.cri".containerd]` 섹션을 찾아 `default_runtime_name`을 `nvidia`로 바꿉니다.
4. nvidia 런타임 Binary 경로도 추가
```bash
# imports 설정이 들어갔는지 확인
sudo grep 'imports' /etc/containerd/config.toml
# default 런타임을 nvidia로 변경
sudo sed -i 's/default_runtime_name = "runc"/default_runtime_name = "nvidia"/g' /etc/containerd/config.toml
# 또는 ansible gpu -i inventory/mycluster/inventory.ini -b -m shell -a "sed -i 's/default_runtime_name = \"runc\"/default_runtime_name = \"nvidia\"/g' /etc/containerd/config.toml"
# default 런타임이 runc 에서 nvidia로 변경되었는지 확인
sudo grep 'default_runtime_name' /etc/containerd/config.toml
# nvidia 런타임 Binary 경로 확인
sudo containerd config dump | grep 'nvidia-container-runtime'
# BinaryName = '/usr/bin/nvidia-container-runtime'

# BinaryName 을 직접 추가
sudo sed -i 's@BinaryName = \"\"@BinaryName = \"/usr/bin/nvidia-container-runtime\"@g' /etc/containerd/config.toml
# 또는 ansible gpu -i inventory/mycluster/inventory.ini -b -m shell -a "sed -i 's@BinaryName = \"\"@BinaryName = \"/usr/bin/nvidia-container-runtime\"@g' /etc/containerd/config.toml"

# BinaryName = '/usr/bin/nvidia-container-runtime' 확인
sudo grep 'BinaryName' /etc/containerd/config.toml
# 결과 예시: BinaryName = '/usr/bin/nvidia-container-runtime'

# harbor config_path도 config.toml에 직접 추가
sudo sed -i "0,/config_path = \"\"/s|config_path = \"\"|config_path = \"/etc/containerd/certs.d\"|" /etc/containerd/config.toml
sudo sed -i "0,/config_path = \"\"/s|config_path = \"\"|config_path = \"/etc/containerd/certs.d\"|" /etc/containerd/conf.d/99-nvidia.toml
# 0,/패턴/ 은 첫 번째 매칭만 변경합니다. registry 섹션의 config_path가 transfer 섹션보다 먼저 나오므로 정확히 원하는 곳만 변경됩니다.
sudo grep 'config_path' /etc/containerd/config.toml
sudo grep 'config_path' /etc/containerd/conf.d/99-nvidia.toml
sudo containerd config dump | grep config_path
    #   config_path = "/etc/containerd/certs.d"
    # plugin_config_path = "/etc/nri/conf.d"
    # config_path = "/etc/containerd/certs.d"

# # 1. registry 섹션 (harbor용 - 변경해야 함)
# [plugins."io.containerd.grpc.v1.cri".registry]
#   config_path = ""

# # 2. transfer 섹션 (건드리면 안 됨)
# [plugins."io.containerd.transfer.v1.local"]
#   config_path = ""

```

**[주의: 이하 작업은 kubespray 설치 이후 진행]** 

위 두 가지가 확인되었다면 서비스를 재시작합니다.
```bash
sudo systemctl restart containerd
sudo systemctl restart kubelet
```
### 2. 최종확인 (Control Plane)
```bash
# 기존 것 삭제
kubectl delete ds nvidia-device-plugin-daemonset -n kube-system

# 잠시 대기 후 재배포
# kubectl apply -f https://raw.githubusercontent.com/NVIDIA/k8s-device-plugin/v0.14.5/nvidia-device-plugin.yml
# 최신 버전으로 재설치 (helm 권장)
helm repo add nvdp https://nvidia.github.io/k8s-device-plugin
helm repo update

helm upgrade -i nvdp nvdp/nvidia-device-plugin \
  --namespace kube-system \
  --version 0.17.1

# GPU 확인
kubectl get nodes -o custom-columns=NAME:.metadata.name,GPU:.status.allocatable."nvidia\.com/gpu"

# 로그 확인
kubectl logs -n kube-system -l name=nvidia-device-plugin-ds
```
### 3. 노드 자원 인식 확인
Control Plane에서 아래 명령어를 입력해 보세요.
```bash
# 한방에 조회
kubectl get nodes -o custom-columns="NAME:.metadata.name,GPU:.status.allocatable.nvidia\.com/gpu"
# 15줄까지 조회하거나, nvidia 키워드로 직접 찾기
kubectl describe node node11 | grep -A 15 "Capacity"
# 또는
kubectl describe node node11 | grep "nvidia.com/gpu"
# 출력 결과의 Capacity와 Allocatable 항목에 nvidia.com/gpu: 2 (ex. V100 2개)가 보이면 정상입니다.
```
### 4. 실제 GPU 사용 테스트 (최종 점검)
숫자만 잡힌 게 아니라 실제로 컨테이너가 GPU를 쓸 수 있는지 확인하기 위해, cuda-vector-add 테스트 포드를 실행해 봅시다.

`test-gpu.yaml` 파일을 만들어 아래 내용을 붙여넣으세요.
```yaml
apiVersion: v1
kind: Pod
metadata:
  name: gpu-test
spec:
  restartPolicy: OnFailure
  containers:
  - name: cuda-vector-add
    image: "k8s.gcr.io/cuda-vector-add:v0.1"
    resources:
      limits:
        nvidia.com/gpu: 1
```
실행 및 결과 확인:
```bash
kubectl apply -f test-gpu.yaml
kubectl logs -f gpu-test
# 테스트용 포드 생성
# kubectl run gpu-test --rm -it --restart=Never --image=nvidia/cuda:12.2.0-base-ubuntu22.04 --limits=nvidia.com/gpu=1 -- nvidia-smi
# The error you're encountering happens because the --limits and --requests flags were removed from the kubectl run command in newer versions of Kubernetes.
```
```bash
+-----------------------------------------------------------------------------------------+
| NVIDIA-SMI 550.90.07              Driver Version: 550.90.07      CUDA Version: 12.4     |
|-----------------------------------------+------------------------+----------------------+
| GPU  Name                 Persistence-M | Bus-Id          Disp.A | Volatile Uncorr. ECC |
| Fan  Temp   Perf          Pwr:Usage/Cap |           Memory-Usage | GPU-Util  Compute M. |
|                                         |                        |               MIG M. |
|=========================================+========================+======================|
|   0  Tesla V100-PCIE-16GB           Off |   00000000:0B:00.0 Off |                    0 |
| N/A   31C    P0             25W /  250W |       1MiB /  16384MiB |      0%      Default |
|                                         |                        |                  N/A |
+-----------------------------------------+------------------------+----------------------+
|   1  Tesla V100-PCIE-16GB           Off |   00000000:13:00.0 Off |                    0 |
| N/A   30C    P0             27W /  250W |       1MiB /  16384MiB |      0%      Default |
|                                         |                        |                  N/A |
+-----------------------------------------+------------------------+----------------------+

+-----------------------------------------------------------------------------------------+
| Processes:                                                                              |
|  GPU   GI   CI        PID   Type   Process name                              GPU Memory |
|        ID   ID                                                               Usage      |
|=========================================================================================|
|  No running processes found                                                             |
+-----------------------------------------------------------------------------------------+

```

## **2. kubespray 설치**

🎯 최적의 버전 스택 (2026년 기준)컴포넌트추천 버전선택 이유 및 비고
- Kubespray (v2.25.x): Ubuntu 24.04 공식 지원 시작 버전, K8s 1.29 기본 탑재
- Kubernetes (v1.29.x): Kubeflow 진영에서 가장 광범위하게 검증된(Validated) 안정화 버전
- Kubeflow (v1.10): Nested DAG, 향상된 스케줄링 등 복잡한 파이프라인 처리에 유리

### 0. python version change
```bash
sudo timedatectl set-timezone Asia/Seoul
sudo apt update
sudo apt-get install -y git python3 python3-pip python3-venv
python3 -m venv venv
source venv/bin/activate
(venv)
```
### 1.깃 저장소 복사
```bash
(venv) git clone --single-branch --branch=release-2.22 https://github.com/kubernetes-sigs/kubespray.git
(venv) cd kubespray
```
### 2.의존성 패키지 설치
```bash
(venv) python3 -m pip install --upgrade pip
(venv) pip3 install -r requirements.txt
(venv) pip3 install -r requirements-2.11.txt # (if python version 2.7, 3.5-3.9)
(venv) pip3 install -r requirements-2.12.txt # (if python version 3.8-3.10)
```
### 3.인벤토리 파일 준비
```bash
(venv) cp -rfp inventory/sample inventory/mycluster  
(venv) vim inventory/mycluster/inventory.ini
```
### 4.인벤토리 파일에 노드정보 작성
```bash
(venv)
cat << 'EOF' > inventory/mycluster/inventory.ini
[all]
cl00    ansible_host=10.246.246.* ip=10.246.246.* ansible_user=<user_id>
node01  ansible_host=10.246.246.* ip=10.246.246.* ansible_user=<user_id>

[kube_control_plane]
cl00

[etcd]
cl00

[kube_node]
node01

[calico_rr]

[k8s_cluster:children]
kube_control_plane
kube_node
calico_rr
EOF
```
### 5.swap off (모든 node에서 swap off)
```bash
(venv) sudo swapoff -a
(venv) sudo sed -i '/ swap / s/^/#/' /etc/fstab
```
### 5.설정편집
> etcd 용량을 늘리려면 작업 중이신 Kubespray 디렉토리 내의 inventory/mycluster/group_vars/all/etcd.yml 파일에 etcd_quota_backend_bytes: "8589934592" 한 줄을 추가해 두시는 것을 강력히 권장합니다.
```yaml
etcd_quota_backend_bytes: "8589934592"
```

* inventory/mycluster/group_vars/k8s_cluster/addons.yml
```bash
# vim inventory/mycluster/group_vars/k8s_cluster/addons.yml
helm_enabled: true
metrics_server_enabled: true   
ingress_nginx_enabled: true

# <... 내용생략 후, 마지막줄 이후>

# 1. NVIDIA GPU 가속 기능 활성화 (필수)
# 이 옵션이 켜져야 containerd 설정에 nvidia-runtime을 추가해줍니다.
nvidia_accelerator_enabled: true

# 2. 드라이버 설치 비활성화 (매우 중요!)
# 이미 직접 설치하셨으므로 false로 설정해야 충돌이 안 납니다.
nvidia_driver_install: false

# 3. GPU Device Plugin 설치 (필수)
# K8s가 GPU 자원을 인식하고 파드에 할당하기 위해 필요한 플러그인입니다.
nvidia_gpu_device_plugin_enabled: true

# (선택사항) MIG(Multi-Instance GPU) 기능이 필요 없다면 명시적으로 끕니다. (V100/P100은 보통 false)
nvidia_gpu_device_plugin_mig_strategy: "none"
```
* inventory/mycluster/group_vars/k8s_cluster/k8s-cluster.yml
```bash
# vim inventory/mycluster/group_vars/k8s_cluster/k8s-cluster.yml
kube_proxy_strict_arp: true
```
### 6.앤서블 명령어로 설명 및 확인
```bash
(venv) ansible -m ping all -i inventory/mycluster/inventory.ini 
(venv) ansible all -i inventory/mycluster/inventory.ini \
  -m shell \
  -a "swapoff -a && sed -i '/[[:space:]]swap[[:space:]]/ s/^/#/' /etc/fstab" \
  -b
(venv) ansible all -i inventory/mycluster/inventory.ini -b -m command -a "swapon --show"
```
권장 (become 사용, 가장 안전) 및 swap 상태 확인
* `-m shell` : 파이프/정규식 사용 가능
* `-b` : sudo(become) 사용
* `swapoff -a` : 즉시 swap 해제
* `sed ... /etc/fstab` : swap 라인 주석 처리(영구)

### 7.앤서블 명령어로 설치
```bash
(venv) ansible all -i inventory/mycluster/inventory.ini -m apt -a 'update_cache=yes' -b
(venv) ansible-playbook -i inventory/mycluster/inventory.ini cluster.yml -b

# 설치실패시
(venv) ansible-playbook -i inventory/mycluster/inventory.ini reset.yml -b
```
### 8.설치 중 오류 발생 시 
```bash
(venv) ansible-playbook -i inventory/mycluster/inventory.ini cluster.yml -b --start-at-task="작업이름"
# 라고 입력하면 해당 위치부터 다시 이어서 시도
# TASK [network_plugin/calico : Set calico_pool_conf]
# 에서 만약 오류 발생 시 
# 대괄호([작업이름]) 안 글자 전체가 작업이름입니다.
(venv) ansible-playbook -i inventory/mycluster/inventory.ini cluster.yml -b --start-at-task="작업이름" --limit node1
```
### 9. context config 파일 복사
```bash
mkdir -p ~/.kube
sudo cp /etc/kubernetes/admin.conf ~/.kube/config-<HOSTNAME>
sudo chown $(id -u):$(id -g) ~/.kube/config-<HOSTNAME>
chmod 600 ~/.kube/config-<HOSTNAME>
```

### 10. labels 설정 (나중에 prometheus 에서 gpu 노드에서만 정보를 수집하기 위한 label과 동일)
```bash
# 1. 임시로 붙였던 accelerator=nvidia 라벨이 있다면 삭제 (마이너스 기호 주의)
k label nodes gn01 gn02 accelerator-

# 2. DCGM Exporter 표준 라벨로 새로 부여
k label nodes gn01 gn02 nvidia.com/gpu.present=true

# 3. 라벨 확인 (정상 부여 여부 체크)
k get nodes -l nvidia.com/gpu.present=true
```

## **3. kubeflow 설치**
### 1.권장 버전
* 설치 방식: Manifests + kustomize
* 런타임: containerd (이미 OK)
```bash
git clone https://github.com/kubeflow/manifests.git
cd manifests
```
### 2.필수 도구
```bash
curl -s "https://raw.githubusercontent.com/kubernetes-sigs/kustomize/master/hack/install_kustomize.sh" | bash
sudo mv kustomize /usr/local/bin/
# or
sudo snap install kustomize
# or
sudo apt install -y kustomize

kustomize version
```
### 3. Kubeflow 전체 설치 (표준)
**스토리지 클래스**
1. Provisioner 설치: 가장 간편한 Rancher Local Path Provisioner를 설치하여 노드의 디스크를 사용하도록 설정합니다.
```bash
kubectl apply -f https://raw.githubusercontent.com/rancher/local-path-provisioner/v0.0.24/deploy/local-path-storage.yaml

# 로컬 경로 (/mnt 하위 디스크) 를 잡아줘야함
kubectl edit configmap local-path-config -n local-path-storage
```
2. Default StorageClass로 지정 (매우 중요): 이 설정이 있어야 Kubeflow가 "아, 여기서 공간을 얻으면 되는구나" 하고 Pending을 풉니다.
```bash
kubectl patch storageclass local-path -p '{"metadata": {"annotations":{"storageclass.kubernetes.io/is-default-class":"true"}}}'
```
3. 확인: 제대로 적용되었는지 확인: 다시 kubectl get sc를 입력했을 때, 아래처럼 이름 옆에 (default)가 붙어야 합니다.
```bash
kubectl get sc
# NAME                   PROVISIONER ...
# local-path (default)   rancher.io/local-path ...
```
4. 이제 설치 루프 실행
(default)가 확인되었다면, 아까 준비하신 설치 스크립트를 실행하세요. 이제 스토리지 문제가 해결되어 설치가 정상적으로 진행될 것입니다.
```bash
# while ! kustomize build example \
#   --load-restrictor LoadRestrictionsNone \
#   | kubectl apply -f -; do
#   echo "Retrying to apply resources..."
#   sleep 10
# done
# # or
while ! kustomize build example | kubectl apply -f -; do
  echo "Retrying to apply resources..."
  sleep 10
done

# or

# --server-side 옵션과 --force-conflicts 옵션 추가
while ! kustomize build example | sed 's/$(profile-name)/kubeflow-user/g' | kubectl apply --server-side --force-conflicts -f -; do
  echo "Retrying to apply resources..."
  sleep 15
done
```

5. MINIO 문제
```bash
# kubectl set image deployment/minio -n kubeflow minio=gcr.io/ml-pipeline/minio:RELEASE.2019-08-14T20-37-41Z-license-compliance
# -license-compliance 접미사를 뺀 공식 태그를 사용합니다.
kubectl set image deployment/minio -n kubeflow minio=minio/minio:RELEASE.2019-08-14T20-37-41Z
```

6. ml-pipeline-ui 문제 (미해결상태 gcr.io 경로가 deprecated 됨)
```bash
# UI 이미지를 gcr.io의 확실한 태그로 강제 지정
kubectl set image deployment/ml-pipeline-ui -n kubeflow ml-pipeline-ui=gcr.io/ml-pipeline/frontend:1.8.5
# 1. 이미지 저장소 변경 (us-docker -> gcr.io)
kubectl set image deployment/ml-pipeline-ui -n kubeflow ml-pipeline-ui=gcr.io/ml-pipeline/frontend:2.0.3
# 가장 안정적인 버전
# (대안) 가장 안정적인 호환 버전 사용
kubectl set image deployment/ml-pipeline-ui -n kubeflow ml-pipeline-ui=gcr.io/ml-pipeline/frontend:2.0.0-alpha.7
kubectl set image deployment/ml-pipeline-ui -n kubeflow ml-pipeline-ui=gcr.io/ml-pipeline/frontend:1.8.5
kubectl set image deployment/ml-pipeline-ui -n kubeflow ml-pipeline-ui=gcr.io/ml-pipeline/frontend:2.0.5
kubectl set image deployment/ml-pipeline-ui -n kubeflow ml-pipeline-ui=docker.io/kubeflownotebookswg/kfp-frontend:2.0.5
# 1. Docker Hub 이미지로 교체
kubectl set image deployment/ml-pipeline-ui -n kubeflow ml-pipeline-ui=docker.io/kubeflow/frontend:2.0.0-alpha.7
```
좀비 포드 정리 (필수)
```bash
# 에러 상태인 UI 포드 삭제 -> Deployment가 새 설정으로 다시 띄움
kubectl delete pod -n kubeflow -l app=ml-pipeline-ui
```

7. 접속하기

구글크롬설치
```bash
sudo apt update
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo dpkg -i google-chrome-stable_current_amd64.deb
```

* Kubeflow 대시보드 서비스 확인
kubectl get svc -n kubeflow | grep istio-ingressgateway

* Port-forward로 접속 (개발/테스트 환경)
kubectl port-forward svc/istio-ingressgateway -n istio-system 8080:80

> 브라우저에서: http://localhost:8080


# 연결하기

## 1. 노드포트 열고, nginx로 리버스프록시

```bash
# 1. Istio Ingress Gateway 서비스 수정 (패치)
kubectl patch svc istio-ingressgateway -n istio-system \
  --type='json' \
  -p='[{"op": "replace", "path": "/spec/type", "value": "NodePort"}, {"op": "replace", "path": "/spec/ports/1/nodePort", "value": 30080}]'

# or 

kubectl edit svc istio-ingressgateway -n istio-system
# ClusterIP 를 NodePort 로 변경
kubectl get svc -n istio-system istio-ingressgateway
# 외부로 열린 포트번호 확인
```

## 2. Nginx 설치 (안 되어 있다면)
```bash
sudo apt update
sudo apt install -y nginx
sudo vim /etc/nginx/sites-available/kubeflow
```
아래 내용을 복사해서 붙여넣으세요. (IP 부분은 실제 환경에 맞게 수정 필요)
```nginx
# Upstream 설정: 트래픽을 보낼 워커 노드들의 IP와 NodePort를 적습니다.
upstream kubeflow-cluster {
    # CL00, Node01, Node02 어디든 30080이 열려있으므로 다 적어주면 로드밸런싱 됩니다.
    server 10.246.246.xx:30080;  # CL00 IP (만약 마스터에도 스케줄링 되면)
    server 10.246.246.yy:30080;  # Node01 IP
    server 10.246.246.zz:30080;  # Node02 IP
}

server {
    listen 80;
    server_name _;  # 도메인이 있다면 도메인을 적고, 없으면 _ (모든 요청)

    location / {
        proxy_pass http://kubeflow-cluster;
        
        # 헤더 전달 (필수)
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # 웹소켓 지원 (Jupyter Notebook 사용 시 필수)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```
설정 활성화 및 재시작
```bash
# 심볼릭 링크 생성
sudo ln -s /etc/nginx/sites-available/kubeflow /etc/nginx/sites-enabled/

# 문법 검사
sudo nginx -t

# Nginx 재시작
sudo systemctl restart nginx
```
3단계: 접속 테스트
이제 외부(내 PC 브라우저)에서 호스트(CL00)의 공인 IP를 입력하고 접속해 봅니다.

주소: http://<CL00의-외부-IP>

로그인 창이 뜨면 성공입니다! (Email: user@example.com / PW: 12341234)

### Lens 설치시 nginx stream 기능으로 https 를 kubernetes api로 바로 전달해야함
```bash
stream {
    upstream kubernetes_api {
        server 127.0.0.1:6443;
    }

    server {
        listen 10000; # 외부 개방 포트 중 하나
        proxy_pass kubernetes_api;
    }
}
```

# 모든 설치 이후 etcd 용량 늘리기 (운영용)

🛠️ etcd 용량 8GB로 증설하기 (단계별 가이드)

이 작업은 **모든 마스터 노드(Control Plane)**에서 동일하게 수행해야 합니다.

## 1. 바이트 단위 계산

etcd는 설정값을 바이트(Byte) 단위로 받습니다.

- 2GB (기본값): 2147483648
- 4GB: 4294967296
- 8GB (권장): 8589934592

## 2. 설정 파일 수정 (etcd.yaml)

대부분의 Kubernetes(Kubespray/kubeadm) 배포판에서 etcd는 Static Pod로 실행되며, 설정 파일은 아래 경로에 있습니다.
Kubespray 환경에서 etcd 용량을 8GB로 증설하려면 다음과 같이 systemd 환경 변수 파일을 수정해야 합니다.
```bash
# 🚨 주의: 재시작(Restart)은 절대 한 번에 하시면 안 됩니다!
# 파일 변경은 한 번에 묶어서 하더라도, 서비스 재시작(systemctl restart etcd) 명령을 전체 대상(ctl) 그룹에 동시에 날리시면 절대 안 됩니다.

# etcd는 3대 중 과반수(2대 이상)가 항상 살아있어야(Quorum) 쿠버네티스 클러스터가 유지됩니다. 만약 동시에 재시작 명령이 들어가면 클러스터 전체가 다운되는 장애가 발생합니다.

# 따라서 재시작만큼은 아래처럼 노드를 특정해서 하나씩 순차적으로 진행하셔야 합니다.

# ansible 로 한방에 처리
ansible ctl -i inventory/mycluster/inventory.ini -b -m shell -a "sed -i 's/ETCD_QUOTA_BACKEND_BYTES=2147483648/ETCD_QUOTA_BACKEND_BYTES=8589934592/g' /etc/etcd.env"
# 결과 조회
ansible ctl -i inventory/mycluster/inventory.ini -b -m shell -a "cat /etc/etcd.env | grep QUOTA" 

# etcd 재시작 적용(반드시 하나씩 적용!)
ansible cn01 -i inventory/mycluster/inventory.ini -b -m shell -a "systemctl restart etcd"
ansible cn02 -i inventory/mycluster/inventory.ini -b -m shell -a "systemctl restart etcd"
ansible cn03 -i inventory/mycluster/inventory.ini -b -m shell -a "systemctl restart etcd"
```
### 1. 백업 먼저 하기 (필수):
```bash
sudo cp /etc/kubernetes/manifests/etcd.yaml /etc/kubernetes/manifests/etcd.yaml.bak
```

### 2. 파일 편집:
```bash
# (kubeadm 경우) sudo vim /etc/kubernetes/manifests/etcd.yaml
sudo vim /etc/etcd.env
```

### 3. 옵션 추가:
`spec.containers.command` 섹션을 찾아 아래 줄을 추가하세요. (순서는 상관없으나 보기 좋게 중간에 넣으세요.)
```yaml
- --quota-backend-bytes=8589934592
```
[(kubespray 는 아래와 같은 화면)]
```bash
...
ETCD_QUOTA_BACKEND_BYTES=8589934592
...
```
[예시 화면 (kubeadm의 경우임)]
```yaml
spec:
  containers:
  - command:
    - etcd
    - --advertise-client-urls=https://192.168.1.10:2379
    - --cert-file=/etc/kubernetes/pki/etcd/server.crt
    - --quota-backend-bytes=8589934592  # <--- 여기에 추가!
    - --data-dir=/var/lib/etcd
    ...
```

## 3. 적용 및 재시작
```bash
sudo systemctl restart etcd
# 정상기동확인
sudo systemctl status etcd
```
Static Pod의 특성상, 파일을 저장하고 닫으면(Ctrl+O, Enter, Ctrl+X) kubelet이 변경 사항을 감지하고 자동으로 etcd 팟을 재시작합니다.

- 약 1~2분 정도 소요될 수 있습니다.
- watch crictl ps 또는 watch docker ps로 etcd 컨테이너가 새로 떴는지 확인하세요.

🚨 주의사항 및 마무리
1. 모든 마스터 노드 적용
만약 마스터 노드가 3대라면, 3대 모두 똑같이 설정하고 재시작해야 합니다. (하나씩 순차적으로 하세요. 한 번에 다 끄면 클러스터 멈춥니다.)

2. 알람 해제 (이미 꽉 찬 상태라면)
용량을 늘렸더라도, 현재 걸려 있는 NOSPACE 알람은 자동으로 사라지지 않습니다. 설정을 마친 후 마지막으로 알람을 꺼주세요.

```bash
sudo ETCDCTL_API=3 etcdctl --endpoints=https://127.0.0.1:2379 \
  --cacert=/etc/ssl/etcd/ssl/ca.pem \
  --cert=/etc/ssl/etcd/ssl/admin-cl01.pem \
  --key=/etc/ssl/etcd/ssl/admin-cl01-key.pem \
  alarm disarm
```
