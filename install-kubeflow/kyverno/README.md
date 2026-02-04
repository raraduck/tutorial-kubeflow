# kyverno 설치 (GPU 자원 할당)

## 1. 1단계: Kyverno 설치 확인 (중개자 고용; Helm 활용 설치) 
Kyverno를 먼저 설치해야 합니다. (Helm으로 설치하는 것이 가장 안정적입니다.)
```bash
# Helm 레포 추가
helm repo add kyverno https://kyverno.github.io/kyverno/
helm repo update

# Kyverno 설치 (최신 버전)
helm install kyverno kyverno/kyverno -n kyverno --create-namespace
```

## 2단계: Kyverno 정책(ClusterPolicy) 적용 (작업 지시서 전달)
```bash
# gpu-binding-policy.yaml
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: bind-gpu-nodeselector
spec:
  validationFailureAction: Enforce
  background: false
  rules:
  - name: inject-nodeselector-by-env
    match:
      any:
      - resources:
          kinds:
          - Pod
    mutate:
      # [변경점] 컨테이너의 모든 환경변수 목록(env[])을 직접 순회합니다.
      # 이렇게 하면 element는 무조건 개별 EnvVar 객체가 되므로, 값이 리스트가 될 수 없습니다.
      foreach:
      - list: "request.object.spec.containers[].env[]"
        preconditions:
          all:
          - key: "{{ element.name }}"
            operator: Equals
            value: "TARGET_GPU"
        patchStrategicMerge:
          spec:
            nodeSelector:
              # element.value는 무조건 String입니다.
              gpu.model: "{{ element.value }}"
```
```bash
kubectl apply -f gpu-binding-policy.yaml
```

## 3단계: PodDefault 환경변수로 '표식' 남기기
먼저 PodDefault는 nodeSelector 대신, **"나는 RTX3090을 원해"**라는 **환경변수(TARGET_GPU)**를 Pod에 주입하도록 합니다.
이 YAML을 shared-gpu-dwnkim.yaml로 저장하여 배포하세요.
```yaml
# shared-gpu-dwnkim.yaml
# 1. RTX 3090 선택 옵션 (환경변수 주입)
apiVersion: "kubeflow.org/v1alpha1"
kind: PodDefault
metadata:
  name: select-gpu-rtx3090
  namespace: dwnkim
spec:
  desc: "GPU: NVIDIA RTX 3090"
  selector:
    matchLabels:
      select-gpu-rtx3090: "true"
  env:
  - name: TARGET_GPU
    value: "rtx3090"

---
# 2. RTX 4090 선택 옵션
apiVersion: "kubeflow.org/v1alpha1"
kind: PodDefault
metadata:
  name: select-gpu-rtx4090
  namespace: dwnkim
spec:
  desc: "GPU: NVIDIA RTX 4090"
  selector:
    matchLabels:
      select-gpu-rtx4090: "true"
  env:
  - name: TARGET_GPU
    value: "rtx4090"

---
# 3. RTX 5000 선택 옵션
apiVersion: "kubeflow.org/v1alpha1"
kind: PodDefault
metadata:
  name: select-gpu-rtx5000
  namespace: dwnkim
spec:
  desc: "GPU: NVIDIA RTX 5000 (Ada Generation)"
  selector:
    matchLabels:
      select-gpu-rtx5000: "true"
  env:
  - name: TARGET_GPU
    value: "rtx5000"
```
```bash
kubectl create -f shared-gpu-dwnkim.yaml

# 각 노드에는 이미 node label 이 설정되어 있어야합니다.
# kubectl label node <gn001, gn002, gn003, ... > gpu.model=<rtx3090, rtx4090, rtx5000>
```