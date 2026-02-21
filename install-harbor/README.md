# NAS(NFS) 환경에 맞춘 PV / PVC 설정 가이드

NAS 볼륨을 쿠버네티스에서 바로 마운트하도록 nfs 타입의 PV를 작성하는 예시입니다. (만약 NAS가 이미 모든 워커 노드의 OS 자체에 마운트되어 있다면 이전 답변의 local 타입을 써도 되지만, 쿠버네티스가 직접 NFS 서버와 통신하게 하는 아래 방식이 더 안정적입니다.)

## 1. PV (Persistent Volume) 생성
NFS 서버의 IP 주소와 지정하신 경로를 입력해 줍니다.
```yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: harbor-nas-pv
spec:
  capacity:
    storage: 1024Gi # Harbor에서 사용할 예상 최대 용량
  volumeMode: Filesystem
  accessModes:
    - ReadWriteMany # NAS(NFS)의 장점인 다중 노드 읽기/쓰기 모드 사용
  persistentVolumeReclaimPolicy: Retain
  nfs:
    server: 192.168.X.X # 실제 NAS(NFS) 서버의 IP 주소로 변경해주세요.
    path: /cloudhome/dwnusa/GPU_storage/Local_registry
```

## 2. PVC (Persistent Volume Claim) 생성
Harbor 설치 시 Helm 차트가 이 PVC를 사용하도록 이름을 일치시킵니다.
```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: harbor-nas-pvc
  namespace: harbor # Harbor를 설치할 네임스페이스
spec:
  storageClassName: ""  # ★ 핵심: 빈 문자열로 설정하여 자동 StorageClass 주입 방지
  accessModes:
    - ReadWriteMany
  resources:
    requests:
      storage: 1024Gi # PV와 동일하게 설정
  volumeName: harbor-nas-pv # 위에서 만든 PV 이름을 명시적으로 지정하여 바인딩
```

> ⚠️ NAS 사용 시 필수 체크포인트
> - 디렉토리 권한 (중요): NFS 서버(NAS)의 /cloudhome/dwnusa/GPU_storage/Local_registry 경로에 Harbor의 컨테이너 유저(보통 UID 10000)가 읽고 쓸 수 있는 권한이 반드시 있어야 합니다. 권한이 없으면 Harbor 파드가 CrashLoopBackOff 상태에 빠질 수 있습니다. NAS 측에서 해당 디렉토리에 대한 권한을 넉넉히(예: chmod 777 등 내부 보안 규정에 맞게) 부여해야 합니다.
>
> - NFS 서버 허용 IP: NAS(NFS 서버) 설정에서 쿠버네티스 워커 노드들의 IP가 접근할 수 있도록 허용(export)되어 있는지 확인해야 합니다.


# Harbor 설치 준비
## 1. Harbor와 쿠브플로우의 네임스페이스 관계
Harbor는 쿠버네티스 클러스터 내부 또는 외부에 존재하는 '독립적인 이미지 저장소(웹 서버)' 역할을 합니다.

따라서 Harbor 자체를 K8s 상의 harbor 네임스페이스에 설치해 두더라도, 실제 쿠브플로우 작업이나 모델 학습용 파드들이 AIDev나 aiops 같은 완전히 다른 네임스페이스에서 실행되어도 이미지를 가져오는 데는 전혀 문제가 없습니다.

쿠브플로우 파드들은 K8s 내부 구조(PV/PVC)를 통해서 이미지를 읽어오는 것이 아니라, 네트워크 URL(예: http://192.168.0.x:30002)을 통해 Harbor API를 호출하여 이미지를 다운로드(Pull)하기 때문입니다.

> ⚠️ 다른 네임스페이스에서 이미지를 가져올 때 필수 조건
>
> Harbor를 구축하고 나면, 쿠브플로우(또는 AIDev, aiops 네임스페이스의 파드)가 Harbor에서 이미지를 정상적으로 Pull 하기 위해 ImagePullSecret이라는 자격 증명서가 필요합니다. Harbor가 비공개(Private) 상태일 경우, K8s가 이미지를 다운로드할 때 쓸 아이디와 비밀번호를 알아야 하기 때문입니다.

## 2. Harbor 전용 NFS Provisioner 설치 및 StorageClass 생성
NAS에 /cloudhome/dwnusa/GPU_storage/Harbor_storage 디렉토리를 미리 생성해 두셨다고 가정하고, 이 경로만 바라보는 전용 Provisioner를 Helm으로 설치합니다.

이 Provisioner는 Default StorageClass에 영향을 주지 않는 독립적인 StorageClass(harbor-nfs-sc)를 생성합니다.
```bash
# NFS Provisioner Helm 레포지토리 추가
helm repo add nfs-subdir-external-provisioner https://kubernetes-sigs.github.io/nfs-subdir-external-provisioner/

helm repo update

# Harbor 전용 Provisioner 설치 (네임스페이스는 harbor로 통일하거나 kube-system 사용 가능)
helm install harbor-nfs-provisioner nfs-subdir-external-provisioner/nfs-subdir-external-provisioner \
    --namespace harbor \
    --set nfs.server=<NAS_IP_주소> \
    --set nfs.path=/cloudhome/dwnusa/GPU_storage/Harbor_storage \
    --set storageClass.name=harbor-nfs-sc \
    --set storageClass.defaultClass=false # 기본 스토리지 클래스로 설정하지 않음 (User_storage 보호)
```
이 명령어를 실행하면 harbor-nfs-sc라는 이름의 StorageClass가 생성되며, 이 클래스를 호출할 때마다 지정한 NAS 경로 하위에 자동으로 폴더가 생성되고 PV/PVC가 연결됩니다.


# Harbor 설치
## 1. values.yaml 핵심 설정
앞서 만든 PVC(harbor-nas-pvc)를 Harbor 설치 시 연결하도록 Helm 차트의 values.yaml 파일을 구성해 보겠습니다.

Harbor는 컨테이너 이미지(registry) 외에도 데이터베이스(database), 캐시(redis), 취약점 스캐너(trivy) 등 여러 컴포넌트로 구성됩니다. 용량을 가장 많이 차지하는 **이미지 저장소(Registry)**를 지정하신 NAS에 연결하는 것이 핵심입니다.

가장 기본적인 values.yaml 파일의 수정 예시입니다. 아래 내용을 파일로 저장(예: my-values.yaml)하여 사용하시면 됩니다.

```yaml
# 1. Harbor 외부 접근 주소 설정 (필수)
# 클러스터 외부에서 Harbor에 접속할 때 사용할 주소입니다.
externalURL: http://10.246.246.89:30002 # 워커노드 사용
# http://<마스터_또는_워커노드_IP>:<NodePort번호>

# 2. 서비스 노출 방식
expose:
  type: nodePort
  tls:
    enabled: false
  nodePort:
    name: http
    ports:
      http:
        nodePort: 30002 # 30000~32767 사이의 포트. externalURL의 포트와 일치해야 합니다.

# 3. 스토리지(NAS PVC) 연결
persistence:
  enabled: true
  persistentVolumeClaim:
    registry:
      existingClaim: "harbor-nas-pvc"
      
# 4. 무거운 컴포넌트들을 cn20 노드에 할당 (nodeSelector 추가)
# 각 컴포넌트 하위에 kubernetes.io/hostname 값을 지정합니다.

core:
  nodeSelector:
    kubernetes.io/hostname: cn20

jobservice: # 이미지 복제 등 백그라운드 작업을 처리
  nodeSelector:
    kubernetes.io/hostname: cn20

registry: # 실제 이미지 Push/Pull을 처리
  nodeSelector:
    kubernetes.io/hostname: cn20

trivy: # 이미지 취약점 스캔 (CPU/메모리 사용량이 높음)
  nodeSelector:
    kubernetes.io/hostname: cn20

database: # Harbor 메타데이터 저장
  nodeSelector:
    kubernetes.io/hostname: cn20

redis: # 캐시 처리
  nodeSelector:
    kubernetes.io/hostname: cn20
```
이렇게 구성하면 Harbor 배포 시, K8s가 harbor-nfs-sc StorageClass에 요청을 보내고, NFS Provisioner가 알아서 DB, Redis, Trivy 등을 위한 폴더를 Harbor_storage 하위에 만들고 볼륨을 할당해 줍니다. 사용자용 default 스토리지인 User_storage는 전혀 건드리지 않게 됩니다!

```bash
helm repo add harbor https://helm.goharbor.io
# Harbor Helm Repo 업데이트
helm repo update

# 설치 실행
helm install my-harbor harbor/harbor -f my-values.yaml -n harbor
```
> 혹시 권한문제가 생긴다면
```bash
# 1. 레지스트리 (수동 PV) 경로
sudo chmod -R 777 GPU_storage/Local_registry

# 2. 동적 프로비저닝 (DB, Redis 등) 경로
sudo chmod -R 777 GPU_storage/Harbor_storage
```

# 이미지 레지스트리 실습
## 1. Docker Insecure Registry 설정 (★매우 중요)
현재 Harbor를 HTTPS(TLS) 없이 HTTP로 띄웠기 때문에, 이미지를 빌드하고 푸시할 작업 노드(예: cn01)의 Docker 데몬이 이 주소를 신뢰하도록 설정해야 합니다.

작업 중인 서버의 /etc/docker/daemon.json 파일을 열어(없으면 생성) 아래 내용을 추가합니다.
```json
{
  "insecure-registries": ["10.246.246.89:30002"]
}
```
설정 후 Docker 데몬을 재시작하여 적용합니다.
```bash
sudo systemctl restart docker
```

## (추가) 도커 데스크톱에서 Insecure Registry 설정하기 (win10 docker desktop 환경)
1. 도커 데스크톱 실행: 윈도우 우측 하단 작업 표시줄에서 도커(고래) 아이콘을 클릭하여 창을 엽니다.
2. 설정 열기: 우측 상단에 있는 톱니바퀴 모양(Settings) 아이콘을 클릭합니다.
3. Docker Engine 탭 이동: 좌측 메뉴에서 Docker Engine을 선택합니다.
4. JSON 내용 추가: 화면 중앙의 텍스트 편집기 창에 기존 설정들이 보일 것입니다. 여기에 "insecure-registries" 항목을 추가해 줍니다.
```json
{
  "builder": {
    "gc": {
      "defaultKeepStorage": "20GB",
      "enabled": true
    }
  },
  "experimental": false,
  "insecure-registries": [
    "10.246.246.89:30002"
  ]
}
```
5. 적용 및 재시작: 우측 하단의 Apply & restart 버튼을 클릭합니다. 도커 엔진이 10~20초 정도 재시작되면서 설정이 완벽하게 적용됩니다.

## 2. 나머지 워커노드에서도 http로 pull 할 수 있도록 허용 필요(매우 중요)
> 구 버전의 containerd (v2.2 이하) 정상동작 함
```bash
sudo vim /etc/containerd/config.toml
```
55~57번 줄을 아래처럼 교체
```bash
# ...
    [plugins."io.containerd.cri.v1.images".registry]
      config_path = ""

      [plugins."io.containerd.cri.v1.images".registry.mirrors]
        [plugins."io.containerd.cri.v1.images".registry.mirrors."10.246.246.89:30002"]
          endpoint = ["http://10.246.246.89:30002"]

      [plugins."io.containerd.cri.v1.images".registry.configs]
        [plugins."io.containerd.cri.v1.images".registry.configs."10.246.246.89:30002".tls]
          insecure_skip_verify = true
# ...
```
재시작
```bash
sudo systemctl restart containerd
sudo crictl pull 10.246.246.89:30002/kubeflow/jupyter-custom:v1.0
```

> 최신 버전의 containerd (v1.5 이상) 사용의 경우
> 
> 이전 버전들처럼 config.toml 파일 하나에 모든 설정을 길게 늘어쓰는 방식 대신, config_path = "/etc/containerd/certs.d:/etc/docker/certs.d" 설정에 따라 별도의 디렉토리에서 레지스트리 설정 파일들을 깔끔하게 관리하는 최신 방식이 적용되어 있습니다.
>
> 기존 config.toml 파일은 그대로 두시고, 아래 단계에 따라 설정 파일만 하나 만들기

1. 최신 Containerd 방식의 Insecure Registry 설정
    - 이 작업 역시 쿠브플로우 파드가 뜰 수 있는 **모든 워커 노드(cn20, gn01, gn02 등)**에서 진행

2. Harbor 주소 이름의 디렉토리 생성
    - 설정에 명시된 경로(/etc/containerd/certs.d) 하위에 Harbor의 IP와 포트 번호로 된 폴더를 만듭니다.
    ```bash
    sudo mkdir -p /etc/containerd/certs.d/10.246.246.89:30002
    ```
3. hosts.toml 파일 생성 및 편집
    - 방금 만든 폴더 안에 hosts.toml이라는 설정 파일을 생성합니다.
    ```bash
    sudo vim /etc/containerd/certs.d/10.246.246.89:30002/hosts.toml
    ```
4. HTTP 통신(TLS 무시) 내용 작성
    - 파일이 열리면 아래 내용을 그대로 복사하여 붙여넣습니다. (이 설정이 "HTTPS가 아니어도 이미지를 가져와라"라는 뜻입니다.)
    ```toml
    server = "http://10.246.246.89:30002"

    [host."http://10.246.246.89:30002"]
    capabilities = ["pull", "resolve"]
    skip_verify = true
    ```
    ```bash
    sudo systemctl restart containerd
    ```

## 3. Dockerfile 작성
원하시는 요구사항이 모두 반영된 Dockerfile을 작성합니다. 작업 디렉토리(예: ~/Workspace/custom-image/)를 만들고 아래 내용으로 Dockerfile을 저장하세요.
```dockerfile
# 1. Base Image 지정
FROM ghcr.io/kubeflow/kubeflow/notebook-servers/jupyter-pytorch-cuda-full:v1.10.0

# 2. 사용자 권한 설정 (Kubeflow 이미지는 보통 jovyan 사용자를 사용합니다)
USER root

# 3. 요구사항 패키지 설치 및 업그레이드
RUN pip install --upgrade "numpy>=2.0" && \
    pip install pytorch_lightning tensorboard

# 4. 원래 사용자로 복귀
USER jovyan
```
```bash
# 1. Dockerfile이 있는 디렉토리에서 이미지 빌드 (태그: v1.0)
docker build -t 10.246.246.89:30002/kubeflow/jupyter-custom:v1.0 .

# 2. Harbor에 로그인 (admin / Harbor12345 입력)
docker login 10.246.246.89:30002

# 3. 로컬 Harbor로 이미지 Push
docker push 10.246.246.89:30002/kubeflow/jupyter-custom:v1.0
```
## (Docker 없이 워커노드에서 바로 빌드하기)
> 워커노드의 containerd 는 docker가 설치되면 충돌을 일으킴
1. buildah를 이용한 서버 직접 빌드 가이드
```bash
sudo apt-get update
sudo apt-get install -y buildah
```
2. Buildah로 이미지 빌드
```bash
sudo buildah bud -t 10.246.246.89:30002/kubeflow/jupyter-custom:v1.0 .
```
3. Harbor로 다이렉트 Push
빌드가 완료되면, HTTPS(TLS) 검증을 무시하는 옵션(--tls-verify=false)을 주어 로컬 Harbor로 즉시 쏘아 올립니다.
```bash
sudo buildah push \
  --tls-verify=false \
  --creds admin:Harbor12345 \
  10.246.246.89:30002/kubeflow/jupyter-custom:v1.0
```
