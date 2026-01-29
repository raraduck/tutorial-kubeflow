# Kubeflow HTTPS 접속 세팅
## 전체 과정 개요
```yaml
1. TLS 인증서 생성 (OpenSSL)
   ↓
2. Kubernetes Secret으로 저장
   ↓
3. Gateway에 HTTPS 설정 추가
```
## 🎯 핵심 포인트
1. 인증서는 OpenSSL로 직접 생성 (자체 서명)
2. Secret은 반드시 istio-system 네임스페이스에 생성
3. Gateway는 credentialName으로 Secret 참조
4. NodePort 31997이 자동으로 HTTPS 트래픽 처리
5. 브라우저 경고는 자체 서명 인증서의 정상적인 현상

### 1단계: TLS 인증서 생성 (OpenSSL)
```bash
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout tls.key -out tls.crt \
  -subj "/CN=kubeflow.local/O=kubeflow" \
  -addext "subjectAltName=DNS:kubeflow.local,DNS:*.kubeflow.local,IP:192.168.0.80"
```
### 각 옵션 설명:

| 옵션 | 의미 | 설명 |
|------|------|------|
| `req` | 인증서 요청 | 인증서 생성/관리 명령 |
| `-x509` | 자체 서명 인증서 | CA 없이 직접 서명한 인증서 생성 |
| `-nodes` | 암호화 없음 | 개인키를 암호로 보호하지 않음 (서버가 자동 시작 가능) |
| `-days 365` | 유효 기간 | 1년간 유효한 인증서 |
| `-newkey rsa:2048` | 새 키 생성 | 2048비트 RSA 개인키 생성 |
| `-keyout tls.key` | 개인키 파일 | 생성된 개인키 저장 위치 |
| `-out tls.crt` | 인증서 파일 | 생성된 인증서 저장 위치 |
| `-subj` | 주체 정보 | CN(Common Name), O(Organization) 설정 |
| `-addext` | 확장 필드 | SubjectAltName으로 추가 도메인/IP 지정 |

### SubjectAltName (SAN)의 중요성:
- `DNS:kubeflow.local` - 도메인 이름으로 접속 가능
- `DNS:*.kubeflow.local` - 와일드카드 서브도메인
- `IP:192.168.0.80` - **IP 주소로 직접 접속 가능** ✨

> 💡 **왜 SAN이 필요한가?** 최신 브라우저는 보안상 CN만으로는 부족하고 SAN이 반드시 있어야 인증서를 신뢰합니다.
```yaml
### 생성된 파일:
tls.key  (1.7KB) - RSA 개인키 (비밀)
tls.crt  (1.3KB) - X.509 인증서 (공개)
```
### 2단계: Kubernetes Secret으로 저장
### 2-1. 인증서를 Base64로 인코딩
Kubernetes Secret은 base64 인코딩된 데이터를 저장하므로 변환이 필요합니다:
```bash
# 인증서 인코딩
cat tls.crt | base64 -w 0
# 개인키 인코딩  
cat tls.key | base64 -w 0
```
> -w 0: 줄바꿈 없이 한 줄로 출력 (YAML에 넣기 위함)
### 2-2. Secret YAML 작성
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: kubeflow-tls-cert           # Secret 이름
  namespace: istio-system            # istio-ingressgateway가 있는 네임스페이스
type: kubernetes.io/tls              # TLS 전용 Secret 타입
data:
  tls.crt: LS0tLS1CRUdJTi...        # base64 인코딩된 인증서
  tls.key: LS0tLS1CRUdJTi...        # base64 인코딩된 개인키
```
### Secret 타입의 중요성:
| 타입 | 필수 키 | 용도 |
|------|------|------|
| `kubernetes.io/tls` | `tls.crt`, `tls.key` | TLS/HTTPS 인증서 |
| `Opaque` | 자유 | 일반 데이터 |
> ⚠️ 반드시 istio-system 네임스페이스에 생성: istio-ingressgateway Pod가 이 네임스페이스에서 Secret을 참조합니다.
### 2-3. Secret 생성
```bash
kubectl apply -f kubeflow-tls-secret.yaml
# 생성 결과 확인:
kubectl get secret kubeflow-tls-cert -n istio-system
```
### 3단계: Gateway에 HTTPS 설정 추가
### 기존 Gateway 설정 (HTTP만):
```yaml
apiVersion: networking.istio.io/v1
kind: Gateway
metadata:
  name: kubeflow-gateway
  namespace: kubeflow
spec:
  selector:
    istio: ingressgateway              # istio-ingressgateway Pod 선택
  servers:
  - hosts:
    - "*"                              # 모든 호스트 허용
    port:
      name: http
      number: 80                       # HTTP 포트
      protocol: HTTP
```
### HTTPS 추가된 Gateway 설정:
```bash
apiVersion: networking.istio.io/v1
kind: Gateway
metadata:
  name: kubeflow-gateway
  namespace: kubeflow
spec:
  selector:
    istio: ingressgateway
  servers:
  - hosts:
    - "*"
    port:
      name: http
      number: 80
      protocol: HTTP
  - hosts:                             # 🆕 HTTPS 서버 추가
    - "*"
    port:
      name: https
      number: 443                      # HTTPS 포트
      protocol: HTTPS
    tls:
      mode: SIMPLE                     # 단순 TLS (양방향 인증 X)
      credentialName: kubeflow-tls-cert  # Secret 이름 참조
```
### TLS 모드 설명:
| 모드 | 설명 | 클라이언트 인증서 필요 |
|------|------|------|
| `SIMPLE` | 서버만 인증서 제공 | ❌ 불필요 |
| `MUTUAL` | 양방향 인증 | ✅ 필요 |
| `PASSTHROUGH` | TLS 종료 없이 통과 | - |
### credentialName의 동작 원리:
1. Gateway가 credentialName: kubeflow-tls-cert 참조
2. Istio는 같은 네임스페이스(istio-system)에서 Secret 검색
3. Secret의 tls.crt, tls.key를 istio-ingressgateway Pod에 마운트
4. Pod가 HTTPS 연결 시 이 인증서 사용

### Gateway 적용:
```bash
kubectl apply -f kubeflow-gateway-https.yaml
```
```yaml
## 🔐 보안 관점에서 보는 흐름

### 1. **개인키 (tls.key)**
- 🔒 비밀로 유지되어야 함
- Kubernetes Secret에 base64로 저장 (암호화는 아님!)
- etcd에 저장됨 (etcd 암호화 권장)
- Pod에만 마운트되어 사용

### 2. **인증서 (tls.crt)**
- 🌐 공개되어도 무방
- 클라이언트(브라우저)에게 전송됨
- 서버 신원 증명용

### 3. **Secret → Pod 마운트**

istio-ingressgateway Pod 내부:
/etc/istio/ingressgateway-certs/
├── tls.crt
└── tls.key
```

### 확인
```bash
# 5. 확인
kubectl get gateway kubeflow-gateway -n kubeflow
kubectl get secret kubeflow-tls-cert -n istio-system
```
