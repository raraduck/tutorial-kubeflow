# Kubeflow 설치 방법
주요 설치 방법 3가지

1. Kubeflow Manifests (권장) - 공식 매니페스트 기반
2. Kustomize - 커스터마이징이 용이
3. Kubeflow Operator - 운영 관리 편의성

## 권장 설치 방법: Kubeflow Manifests (v1.9.0)
> KServe와 Spark Operator의 불안정성을 고려하여 단계별 설치를 권장합니다.

## 설치 절차
### Step 0: Kubeflow용 NFS Provisioner 설치 (Helm 사용)
> 직접 수동 설치는 provisioner 폴더 참조!
```bash
# Helm repo 추가 (이미 했다면 skip)
helm repo add nfs-subdir-external-provisioner \
  https://kubernetes-sigs.github.io/nfs-subdir-external-provisioner/
helm repo update

# Kubeflow용 provisioner 설치
helm install nfs-kubeflow-provisioner \
  nfs-subdir-external-provisioner/nfs-subdir-external-provisioner \
  --namespace kube-system \
  --create-namespace \
  --set nfs.server=192.168.0.200 \
  --set nfs.path=/volume1/testfield/Kubeflow_storage \
  --set storageClass.name=kubeflow-storage \
  --set storageClass.defaultClass=true \
  --set storageClass.archiveOnDelete=true \
  --set storageClass.reclaimPolicy=Retain \
  --set storageClass.allowVolumeExpansion=true

# kubeflow-storage의 default 
kubectl patch storageclass kubeflow-storage \
    -p '{"metadata": {"annotations":{"storageclass.kubernetes.io/is-default-class":"true"}}}'
```
### 참고: Kubeflow 설치 완료 후, gpu-storage-dynamic 으로 default 복원
```bash
# kubeflow-storage의 default 
kubectl patch storageclass kubeflow-storage \
    -p '{"metadata": {"annotations":{"storageclass.kubernetes.io/is-default-class":"false"}}}'

# gpu-storage-dynamic을 default로 복원
kubectl patch storageclass gpu-storage-dynamic \
    -p '{"metadata": {"annotations":{"storageclass.kubernetes.io/is-default-class":"true"}}}'
```

### Step 1: 사전 준비
```bash
# 작업 디렉토리 생성
cd ~/workspace/kubeflow
mkdir -p kubeflow-manifests
cd kubeflow-manifests

# Kubeflow manifests 다운로드 (v1.9.0)
git clone https://github.com/kubeflow/manifests.git
cd manifests
git checkout v1.9.0

# 또는 최신 stable 버전
# git checkout v1.9.1
```
### Step 2: Cert-Manager 설치
```bash
# Cert-manager 설치
kustomize build common/cert-manager/cert-manager/base | kubectl apply -f -

# Cert-manager webhook 준비 대기 (중요!)
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=cert-manager -n cert-manager --timeout=300s
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=webhook -n cert-manager --timeout=300s

# 확인
kubectl get pods -n cert-manager
```
### Step 3: Istio 설치
```bash
# Istio 설치
kustomize build common/istio-1-22/istio-crds/base | kubectl apply -f -
kustomize build common/istio-1-22/istio-namespace/base | kubectl apply -f -
kustomize build common/istio-1-22/istio-install/overlays/oauth2-proxy | kubectl apply -f -

# Istio 준비 대기
kubectl wait --for=condition=ready pod -l app=istiod -n istio-system --timeout=300s

# 확인
kubectl get pods -n istio-system
```
### Step 4: Dex (인증) 설치
```bash
# Dex 설치
kustomize build common/dex/overlays/istio | kubectl apply -f -

# 확인
kubectl get pods -n auth
```
### Step 5: OIDC AuthService 설치
```bash
# OIDC AuthService 설치
kustomize build common/oidc-client/oidc-authservice/overlays/ibm-storage-class | kubectl apply -f -

# 확인
kubectl get pods -n istio-system | grep authservice
```
### Step 6: Knative Serving 설치 (KServe용)
```bash
# Knative CRDs
kustomize build common/knative/knative-serving/overlays/gateways | kubectl apply -f -

# Knative Serving
kustomize build common/knative/knative-eventing/base | kubectl apply -f -

# 준비 대기
kubectl wait --for=condition=ready pod -l app=controller -n knative-serving --timeout=300s
kubectl wait --for=condition=ready pod -l app=activator -n knative-serving --timeout=300s

# 확인
kubectl get pods -n knative-serving
kubectl get pods -n knative-eventing
```
### Step 7: Kubeflow Namespace 설치
```bash
# Kubeflow namespace
kustomize build common/kubeflow-namespace/base | kubectl apply -f -
```
### Step 8: Kubeflow 역할 및 바인딩
```bash
# Kubeflow roles
kustomize build common/kubeflow-roles/base | kubectl apply -f -
```
### Step 9: Kubeflow Istio Resources
```bash
# Kubeflow Istio resources
kustomize build common/istio-1-22/kubeflow-istio-resources/base | kubectl apply -f -
```
### Step 10: Kubeflow Pipelines (**주의**)
```bash
# Pipelines 설치
kustomize build apps/pipeline/upstream/env/cert-manager/platform-agnostic-multi-user | kubectl apply -f -

# 준비 대기 (시간이 걸릴 수 있음)
kubectl wait --for=condition=ready pod -l app=ml-pipeline -n kubeflow --timeout=600s

# 확인
kubectl get pods -n kubeflow | grep pipeline
```
#### minio 와 ml-pipeline-ui 용 이미지의 경로 변경 (직접변경)
```bash
# 최신 버전 사용
kubectl set image deployment/minio -n kubeflow minio=minio/minio:latest
# 진행 상황 확인
kubectl rollout status deployment/minio -n kubeflow
# Pod 확인
kubectl get pods -n kubeflow | grep minio

# 올바른 이미지로 변경
kubectl set image deployment/ml-pipeline-ui -n kubeflow ml-pipeline-ui=ghcr.io/kubeflow/kfp-frontend:2.15.0
# 기존 실패한 Pod 삭제
kubectl delete pod -n kubeflow -l app=ml-pipeline-ui
# 상태 확인
kubectl get pods -n kubeflow | grep ml-pipeline-ui
# 롤아웃 상태 확인
kubectl rollout status deployment/ml-pipeline-ui -n kubeflow

# 이 명령을 다시 수행하면 직접변경 사항이 다시 초기화되므로 주의!
# kustomize build apps/pipeline/upstream/env/cert-manager/platform-agnostic-multi-user | kubectl apply -f -
```

### Step 11: KServe 설치 (선택적 - 문제 발생 시 스킵)
```bash
# KServe 설치
kustomize build contrib/kserve/kserve | kubectl apply -f -
kustomize build contrib/kserve/models-web-app/overlays/kubeflow | kubectl apply -f -

# 준비 대기
kubectl wait --for=condition=ready pod -l control-plane=kserve-controller-manager -n kserve --timeout=300s

# 확인
kubectl get pods -n kserve
```
#### 문제 발생 시:
```bash
# KServe 제거
kustomize build contrib/kserve/kserve | kubectl delete -f -
kustomize build contrib/kserve/models-web-app/overlays/kubeflow | kubectl delete -f -
```
### Step 12: Katib (AutoML)
```bash
# Katib 설치
kustomize build apps/katib/upstream/installs/katib-with-kubeflow | kubectl apply -f -

# 확인
kubectl get pods -n kubeflow | grep katib
```
### Step 13: Central Dashboard
```bash
# Central Dashboard
kustomize build apps/centraldashboard/upstream/overlays/kserve | kubectl apply -f -

# 확인
kubectl get pods -n kubeflow | grep centraldashboard
```
### Step 14: Admission Webhook
```bash
# Admission webhook
kustomize build apps/admission-webhook/upstream/overlays/cert-manager | kubectl apply -f -

# 확인
kubectl get pods -n kubeflow | grep admission-webhook
```
### Step 15: Notebook Controller & Web App
```bash
# Notebook controller
kustomize build apps/jupyter/notebook-controller/upstream/overlays/kubeflow | kubectl apply -f -

# Jupyter Web App
kustomize build apps/jupyter/jupyter-web-app/upstream/overlays/istio | kubectl apply -f -

# 확인
kubectl get pods -n kubeflow | grep notebook
kubectl get pods -n kubeflow | grep jupyter-web
```
### Step 16: Profiles + KFAM
```bash
# Profiles
kustomize build apps/profiles/upstream/overlays/kubeflow | kubectl apply -f -

# 확인
kubectl get pods -n kubeflow | grep profiles
```
### Step 17: Volumes Web App
```bash
# Volumes Web App
kustomize build apps/volumes-web-app/upstream/overlays/istio | kubectl apply -f -

# 확인
kubectl get pods -n kubeflow | grep volumes-web-app
```
### Step 18: Tensorboards
```bash
# Tensorboard controller
kustomize build apps/tensorboard/tensorboard-controller/upstream/overlays/kubeflow | kubectl apply -f -

# Tensorboard Web App
kustomize build apps/tensorboard/tensorboards-web-app/upstream/overlays/istio | kubectl apply -f -

# 확인
kubectl get pods -n kubeflow | grep tensorboard
```
### Step 19: Training Operator
```bash
# Training Operator
kustomize build apps/training-operator/upstream/overlays/kubeflow | kubectl apply -f -

# 확인
kubectl get pods -n kubeflow | grep training-operator
```
### Step 21: Spark Operator (선택적 - 문제 발생 시 스킵)
```bash
# Spark Operator
kustomize build apps/spark/spark-operator/upstream/overlays/kubeflow | kubectl apply -f -

# 확인
kubectl get pods -n kubeflow | grep spark-operator
```
#### 문제발생시
```bash
# Spark Operator 제거
kustomize build apps/spark/spark-operator/upstream/overlays/kubeflow | kubectl delete -f -
```
#### 별도로 Spark Operator 설치
```bash
# Spark Operator Helm으로 설치
helm repo add spark-operator https://kubeflow.github.io/spark-operator
helm repo update

helm install spark-operator spark-operator/spark-operator \
  --namespace spark-operator \
  --create-namespace \
  --set webhook.enable=true \
  --set sparkJobNamespace=default
```

### Step 22: User Namespace 생성
```bash
# 예제 사용자 프로필 생성
kubectl apply -f - <<EOF
apiVersion: kubeflow.org/v1
kind: Profile
metadata:
  name: kubeflow-user-example-com
spec:
  owner:
    kind: User
    name: user@example.com
  resourceQuotaSpec:
    hard:
      cpu: "100"
      memory: 100Gi
      requests.nvidia.com/gpu: "10"
      persistentvolumeclaims: "20"
EOF
```