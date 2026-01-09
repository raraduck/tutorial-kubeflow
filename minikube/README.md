# tutorial-kubeflow

## 1. Create minikube cluster with nvidia gpu (ref fedpod repository docker-test folder) 
```bash
minikube start \
   --driver=docker \
   --cpus=24 \
   --memory=200g \
   --container-runtime=docker \
   --gpus=all \
   --mount --mount-string="/home2/dwnusa/mk02:/workspace" \
   --profile={USER OR HOSTNAME}

# GPU 노드 확인
kubectl get nodes "-o=custom-columns=NAME:.metadata.name,GPU:.status.allocatable.nvidia\.com/gpu"
>> 2
```

## 2. Install kubeflow
```bash
# kustomize 설치
curl -s "https://raw.githubusercontent.com/kubernetes-sigs/kustomize/master/hack/install_kustomize.sh" | bash
sudo mv kustomize /usr/local/bin/

# Kubeflow manifests 다운로드
git clone https://github.com/kubeflow/manifests.git
cd manifests

# Kubeflow 설치 (시간 소요: 10-20분)
while ! kustomize build example | kubectl apply -f -; do echo "Retrying to apply resources"; sleep 10; done

# 설치 확인
kubectl get pods -n kubeflow
kubectl get pods -n kubeflow-user-example-com
```
