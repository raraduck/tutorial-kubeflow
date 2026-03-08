```bash
# ============================================================
# 내부 CA 생성 및 Harbor TLS 인증서 발급
# 실행 위치: cn01 마스터 노드
# ============================================================

mkdir -p ~/workspace/k8s/certs && cd ~/workspace/k8s/certs
```
# Step 1. 내부 CA 생성 (1회만 실행) 
```bash
# CA 개인키 생성
openssl genrsa -out ca.key 4096

# CA 인증서 생성 (유효기간 10년)
openssl req -x509 -new -nodes \
  -key ca.key \
  -sha256 \
  -days 3650 \
  -out ca.crt \
  -subj "/C=KR/ST=Seoul/L=Seoul/O=NeuroMaster/OU=K8s/CN=NeuroMaster-Internal-CA"

echo "✅ CA 생성 완료: ca.key, ca.crt"
```
# Step 2. Harbor 서버 인증서 발급 
```bash
# Harbor 개인키 생성
openssl genrsa -out harbor.key 2048

# SAN(Subject Alternative Name) 설정 파일 생성
cat > harbor-san.cnf <<EOF
[req]
req_extensions = v3_req
distinguished_name = req_distinguished_name
prompt = no

[req_distinguished_name]
C  = KR
ST = Seoul
L  = Seoul
O  = NeuroMaster
CN = harbor.192.168.0.80.nip.io

[v3_req]
keyUsage = keyEncipherment, dataEncipherment
extendedKeyUsage = serverAuth
subjectAltName = @alt_names

[alt_names]
DNS.1 = harbor.192.168.0.80.nip.io
DNS.2 = *.192.168.0.80.nip.io
IP.1  = 192.168.0.80
IP.2  = 192.168.0.143
EOF
```
```bash
# CSR (인증서 서명 요청) 생성
openssl req -new \
  -key harbor.key \
  -out harbor.csr \
  -config harbor-san.cnf

# CA로 Harbor 인증서 서명 (유효기간 2년)
openssl x509 -req \
  -in harbor.csr \
  -CA ca.crt \
  -CAkey ca.key \
  -CAcreateserial \
  -out harbor.crt \
  -days 730 \
  -sha256 \
  -extfile harbor-san.cnf \
  -extensions v3_req

echo "✅ Harbor 인증서 발급 완료: harbor.key, harbor.crt"
```

# Step 3. k8s Secret 등록 
```bash
kubectl create namespace harbor --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret tls harbor-tls \
  --cert=harbor.crt \
  --key=harbor.key \
  -n harbor \
  --dry-run=client -o yaml | kubectl apply -f -

echo "✅ harbor-tls Secret 등록 완료"
```
# Step 4. CA를 각 노드에 등록 
```bash
# cn01 (현재 노드)
sudo cp ca.crt /usr/local/share/ca-certificates/neuromaster-ca.crt
sudo update-ca-certificates

# gn143 워커 노드에도 복사 (ssh 접근 필요)
# scp ca.crt neuromaster@192.168.0.143:~/
# ssh neuromaster@192.168.0.143 "sudo cp ~/ca.crt /usr/local/share/ca-certificates/neuromaster-ca.crt && sudo update-ca-certificates"

# containerd에 CA 등록 (docker pull/push 시 필요)
sudo mkdir -p /etc/containerd/certs.d/harbor.192.168.0.80.nip.io
cat > /tmp/hosts.toml <<EOF
server = "https://harbor.192.168.0.80.nip.io"

[host."https://harbor.192.168.0.80.nip.io"]
  ca = "/usr/local/share/ca-certificates/neuromaster-ca.crt"
EOF
sudo cp /tmp/hosts.toml /etc/containerd/certs.d/harbor.192.168.0.80.nip.io/hosts.toml
sudo systemctl restart containerd

echo "✅ CA 노드 등록 완료"
echo ""
echo "📌 개발자 PC 브라우저에도 ca.crt를 등록해주세요."
echo "   Windows: certmgr.msc → 신뢰할 수 있는 루트 인증 기관"
echo "   Mac: 키체인 접근 → 시스템 → ca.crt 추가 후 항상 신뢰"
```