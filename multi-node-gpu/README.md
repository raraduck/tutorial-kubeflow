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
```bash
# 2. NVIDIA 드라이버 설치
# 설치 여부 확인
dpkg -l | grep nvidia-container-toolkit
# 아무것도 안 나온다면: 아래 명령어로 설치합니다.
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg \
&& curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit

sudo nvidia-ctk runtime configure --runtime=containerd
```
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
grep "imports" /etc/containerd/config.toml
# default 런타임이 변경되었는지 확인
grep "default_runtime_name" /etc/containerd/config.toml
# nvidia 런타임 Binary 경로 확인
sudo containerd config dump | grep "nvidia-container-runtime"
# BinaryName = "/usr/bin/nvidia-container-runtime"
grep "BinaryName" /etc/containerd/config.toml
# 결과 예시: BinaryName = "/usr/bin/nvidia-container-runtime"
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
kubectl apply -f https://raw.githubusercontent.com/NVIDIA/k8s-device-plugin/v0.14.5/nvidia-device-plugin.yml

# 로그 확인
kubectl logs -n kube-system -l name=nvidia-device-plugin-ds
```
### 3. 노드 자원 인식 확인
Control Plane에서 아래 명령어를 입력해 보세요.
```bash
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
kubectl run gpu-test --rm -it --restart=Never --image=nvidia/cuda:12.2.0-base-ubuntu22.04 --limits=nvidia.com/gpu=1 -- nvidia-smi
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
### 0. python version change
```bash
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

### 10. labels 설정



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