# tutorial-kubeflow



## 1. Create minikube cluster with nvidia gpu (ref fedpod repository docker-test folder) 
```bash
minikube start \
   --driver=docker \
   --cpus=12 \
   --memory=200g \
   --container-runtime=docker \
   --gpus=all \
   --mount --mount-string="/home2/dwnusa/mk02:/workspace" \
   --profile={USER OR HOSTNAME}

# GPU 노드 확인
kubectl get nodes "-o=custom-columns=NAME:.metadata.name,GPU:.status.allocatable.nvidia\.com/gpu"
>> 2
```

## 2. 스토리지 클래스 설정 바꾸기
```bash
# Provisioner 설치: 가장 간편한 Rancher Local Path Provisioner를 설치하여 노드의 디스크를 사용하도록 설정합니다.
kubectl apply -f https://raw.githubusercontent.com/rancher/local-path-provisioner/v0.0.24/deploy/local-path-storage.yaml
# 1. 기존 standard의 default 설정 해제 (false로 변경)
kubectl patch storageclass standard -p '{"metadata": {"annotations":{"storageclass.kubernetes.io/is-default-class":"false"}}}'
# 2. local-path를 default로 설정 (true로 변경)
kubectl patch storageclass local-path -p '{"metadata": {"annotations":{"storageclass.kubernetes.io/is-default-class":"true"}}}'
# 3. 확인: 제대로 적용되었는지 확인 이름 옆에 (default)가 붙어야 합니다.
kubectl get sc
```

## 3. Install kubeflow
```bash
# kustomize 설치
curl -s "https://raw.githubusercontent.com/kubernetes-sigs/kustomize/master/hack/install_kustomize.sh" | bash
sudo mv kustomize /usr/local/bin/

# Kubeflow manifests 다운로드
git clone https://github.com/kubeflow/manifests.git
cd manifests

# Kubeflow 설치 (시간 소요: 10-20분)
while ! kustomize build example | kubectl apply -f -; do echo "Retrying to apply resources"; sleep 10; done

# Minikube에서는 jobset-controller-manager 비활성화 권장
# Minikube에서 불필요한 컨트롤러 제거
kubectl delete deploy -n kubeflow-system \
  kubeflow-trainer-controller-manager \
  jobset-controller-manager

kubectl delete deploy -n kubeflow \
  kserve-controller-manager \
  kserve-localmodel-controller-manager \
  spark-operator-controller \
  spark-operator-webhook

# 설치 확인
kubectl get pods -n kubeflow
kubectl get pods -n kubeflow-user-example-com
```

## 4. 사용자 추가
1단계: 새 사용자(Namespace) 추가하기
Kubeflow에서는 **"Profile"**이라는 리소스를 생성하면, 자동으로 해당 사용자를 위한 Namespace와 권한(RBAC)이 만들어집니다.
profile-user.yaml 파일 
```yaml
apiVersion: kubeflow.org/v1
kind: Profile
metadata:
  name: user
spec:
  owner:
    kind: User
    name: user@example.com
```
new-user.yaml 파일 생성 원하는 사용자 이메일 주소(예: researcher@example.com)를 정해서 아래 내용을 작성합니다.
```yaml
apiVersion: kubeflow.org/v1beta1
kind: Profile
metadata:
  name: researcher-example-com   # 네임스페이스 이름이 됩니다 (보통 이메일 형식을 치환)
spec:
  owner:
    kind: User
    name: researcher@example.com # 실제 로그인할 때 사용할 이메일
```
researcher 계정 등록이 필요함
```bash
kubectl edit configmap dex -n auth
# staticPasswords:
# - email: user@example.com
#   hash: ... 
#   username: user
#   userID: 08a8684b-db88-4b73-90a9-3cd1661f5466
# # ▼ 여기부터 추가하세요 (들여쓰기 주의!)
# - email: researcher@example.com
#   hash: ...  # 위 user의 hash 값을 그대로 복사 붙여넣기
#   username: researcher
#   userID: researcher-user-id  # 아무거나 유니크한 문자열
```
적용하기
```bash
kubectl rollout restart deployment dex -n auth
# configmap/dex edited
```

적용하기
```bash
kubectl apply -f new-user.yaml
```
확인하기
```bash
kubectl get profiles
kubectl get ns | grep researcher
```
> 참고: 이 과정은 "작업 공간"을 만드는 것입니다. 실제 로그인 비밀번호 설정(Dex 설정)은 별도로 ConfigMap을 수정해야 하는데, 우선은 기본 계정(user@example.com)으로 로그인 후 상단 메뉴에서 이 네임스페이스를 선택해서 사용할 수 있습니다.

## 5. 네트워크 오픈 (접속)
2단계: Minikube NodePort 열기
Minikube는 기본적으로 외부 접속을 차단합니다. Kubeflow의 관문인 istio-ingressgateway를 NodePort 타입으로 변경하여 호스트(Ubuntu 서버)의 특정 포트와 연결해야 합니다.

NodePort로 변경
```bash
kubectl patch service -n istio-system istio-ingressgateway -p '{"spec": {"type": "NodePort"}}'
# dwnusa@NODE01:~$ k get svc -n istio-system
# NAME                   TYPE        ...
# istio-ingressgateway   ClusterIP   ...  <-- ★ 바로 이 녀석입니다! (NodePort로 변경됨을 확인)
```
할당된 포트 및 Minikube IP 확인 Nginx 설정에 필요한 정보들입니다. 아래 두 명령어를 실행해 결과를 기록해 두세요.
```bash
# Minikube 내부 IP 확인:
minikube ip
# 예: 192.168.49.2

# 할당된 NodePort 포트 번호 확인:
kubectl -n istio-system get svc istio-ingressgateway -o jsonpath='{.spec.ports[?(@.name=="http2")].nodePort}'
# 예: 31345 (30000~32767 사이의 숫자가 나옵니다)
```

3단계: Nginx 리버스 프록시 설정 (외부 접속용)
이제 호스트 서버(Ubuntu)에 Nginx를 설치해서, 외부에서 http://서버IP로 접속하면 -> MinikubeIP:NodePort로 토스해주는 설정을 합니다.

Nginx 설치 (이미 있다면 패스)
```bash
sudo apt update
sudo apt install nginx -y
```
설정 파일 생성 /etc/nginx/sites-available/kubeflow 파일을 생성하고 편집합니다.
```bash
sudo vim /etc/nginx/sites-available/kubeflow
```

설정 내용 입력 아래 내용에서 <MINIKUBE_IP>와 <NODE_PORT>를 아까 확인한 값으로 바꿔서 넣으세요. (특히 Jupyter Notebook은 WebSocket을 쓰므로 관련 설정이 필수입니다.)
```nginx
server {
   listen 10008; # 80;
   server_name _;  # 또는 도메인이 있다면 도메인 입력

   location / {
      # 아까 확인한 minikube ip와 nodeport를 입력 (예: 192.168.49.2:31345)
      proxy_pass http://<MINIKUBE_IP>:<NODE_PORT>;

      # Kubeflow 필수 헤더 설정
      proxy_set_header Host $host;
      proxy_set_header X-Real-IP $remote_addr;
      proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

      # WebSocket 지원 (Jupyter Notebook 필수 ★)
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

# 기존 default 설정이 있다면 충돌 방지를 위해 삭제 (선택사항)
sudo rm /etc/nginx/sites-enabled/default

# 문법 검사
sudo nginx -t

# 재시작
sudo systemctl restart nginx
```

접속
```bash
minikube -p node01 service --all
```

## 6. 자원생성 테스트
자원생성 에러 발생시
> [403] Could not find CSRF cookie XSRF-TOKEN in the request. http://<IP>:<PORT>/jupyter/api/namespaces/user/notebooks

해결 방법 1: Jupyter Web App 설정 변경 (가장 유력)
Jupyter 노트북 화면을 담당하는 포드의 설정을 수정합니다.

Deployment 수정 모드로 진입
```bash
kubectl edit deployment -n kubeflow jupyter-web-app-deployment
kubectl edit deployment -n kubeflow tensorboards-web-app-deployment
```
```yaml
# ... 위 내용 생략 ...
spec:
  containers:
  - env:
    - name: APP_SECURE_COOKIES
      value: "false"  # <--- 여기를 "true"에서 "false"로 변경!
# ... 아래 내용 생략 ...
```

```bash
# 동일 문제 예방 체크리스트 (중요 ⭐)

# 아래 Web App들은 모두 같은 방식 필요합니다:

# Web App	Deployment
# Jupyter	jupyter-web-app-deployment
# TensorBoard	tensorboards-web-app-deployment
# Volumes	volumes-web-app-deployment
# KServe Models UI	kserve-models-web-app

APP_SECURE_COOKIES=false
```