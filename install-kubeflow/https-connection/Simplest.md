# https 연결용 TLS 생성과 Gateway 연결
## 1단계: 인증서(Secret)가 잘 만들어졌는지 확인
```bash
kubectl get secret -n istio-system istio-ingressgateway-certs
```
정상 결과: NAME이 istio-ingressgateway-certs이고 DATA가 2 또는 3인 항목이 출력되면 성공입니다. (이미 준비된 상태입니다.)

만약 없다고 나온다면: 자동으로 생성이 안 된 것이므로 아래 단계를 진행

### 1단계: 인증서 파일 생성 (OpenSSL)
```bash
openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
  -keyout tls.key -out tls.crt \
  -subj "/CN=kubeflow.local/O=kubeflow"
```
### 2단계: 쿠버네티스에 Secret 등록
```bash
kubectl create secret tls istio-ingressgateway-certs \
  --key tls.key \
  --cert tls.crt \
  -n istio-system
```
### 2단계: Gateway 설정 적용 (연결 작업)
보통 Kubeflow를 설치하면 kubeflow-gateway라는 설정이 기본으로 깔리지만, 방금 우리가 수동으로 만든 인증서(istio-ingressgateway-certs)를 바라보도록 확실하게 지정해 주는 것이 좋습니다.

아래 명령어를 실행해서 Gateway 설정을 덮어씌워 주세요.
```yaml
# kubeflow-gateway.yaml
apiVersion: networking.istio.io/v1alpha3
kind: Gateway
metadata:
  name: kubeflow-gateway
  namespace: kubeflow
spec:
  selector:
    istio: ingressgateway
  servers:
  - port:
      number: 80
      name: http
      protocol: HTTP
    hosts:
    - "*"
    tls:
      httpsRedirect: true # (선택) HTTP로 들어오면 강제로 HTTPS로 보냄
  - port:
      number: 443
      name: https
      protocol: HTTPS
    hosts:
    - "*"
    tls:
      mode: SIMPLE
      credentialName: istio-ingressgateway-certs # <--- 아까 만든 Secret 이름과 일치해야 함!
```

```bash
kubectl create -f kubeflow-gateway.yaml
```

### 3단계: Istio 게이트웨이 재시작
```bash
kubectl rollout restart deployment -n istio-system istio-ingressgateway
```

### (대안) "경고창 뜨는 게 너무 싫어요"
만약 매번 경고창을 보는 게 불편하시거나, 내부 정책상 HTTPS 접속이 어렵다면, 아까 말씀드린 HTTP 접속 허용 설정을 적용하는 것이 가장 깔끔합니다.

#### HTTP 접속 허용 설정 (복습):
1. kubectl edit deployment -n kubeflow jupyter-web-app-deployment

2. env 목록에 아래 내용 추가:
```yaml
- name: APP_SECURE_COOKIES
  value: "false"
```