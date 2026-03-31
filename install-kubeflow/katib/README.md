# buildah 빌드 순서

## 이미지 빌드
```bash
buildah build \
  -f Containerfile \
  -t 192.168.0.80:30002/dwnkim/pytorch-mnist-gpu:v2.0-nas \
  .
```
## 레지스트리 푸시
```bash
buildah push \
  --tls-verify=false \
  192.168.0.80:30002/dwnkim/pytorch-mnist-gpu:v2.0-nas
```
## 푸시 확인 후 실험 실행
```bash
kubectl apply -f katib-gpu-test-v5-nas.yaml
```
