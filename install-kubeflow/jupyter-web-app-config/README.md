# jupyter 생성 화면에서 필요한 튜닝 작업
```bash
kubectl edit configmap jupyter-web-app-config-<Random Hash> -n kubeflow # 수정 대상 configmap
```
```bash
kubectl rollout restart deployment jupyter-web-app-deployment -n kubeflow # 수정후 재시작 적용
```
## 1. custom image 선택할 수 있도록 하기

```yaml
...
apiVersion: v1
data:
  spawner_ui_config.yaml: |
    # --------------------------------------------------------------
    # Configuration file for the Kubeflow Notebooks UI.
    #
    # About the `readOnly` configs:
    #  - when `readOnly` is set to "true", the respective option
    #    will be disabled for users and only set by the admin
    #  - when 'readOnly' is missing, it defaults to 'false'
    # --------------------------------------------------------------

    spawnerFormDefaults:
      ################################################################
      # Container Images
      ################################################################
      # if users can input custom images, or only select from dropdowns
      allowCustomImage: true

      # if the registry of the container image is hidden from display
      hideRegistry: true

      # if the tag of the container image is hidden from display
      hideTag: false

      # configs for the ImagePullPolicy
      imagePullPolicy:
        readOnly: false

        # the default ImagePullPolicy
        # (possible values: "Always", "IfNotPresent", "Never")
        value: IfNotPresent

      ################################################################
      # Jupyter-like Container Images
      #
      # NOTES:
      #  - the `image` section is used for "Jupyter-like" apps whose
      #    HTTP path is configured by the "NB_PREFIX" environment variable
      ################################################################
      image:
        # the default container image
        value: 10.246.246.89:30002/kubeflow/jupyter-custom:v1.0 # 이부분 추가

        # the list of available container images in the dropdown
        options:
        - ghcr.io/kubeflow/kubeflow/notebook-servers/jupyter-scipy:v1.10.0
        - ghcr.io/kubeflow/kubeflow/notebook-servers/jupyter-pytorch-full:v1.10.0
        - ghcr.io/kubeflow/kubeflow/notebook-servers/jupyter-pytorch-cuda-full:v1.10.0
        - ghcr.io/kubeflow/kubeflow/notebook-servers/jupyter-tensorflow-full:v1.10.0
        - ghcr.io/kubeflow/kubeflow/notebook-servers/jupyter-tensorflow-cuda-full:v1.10.0
        - 10.246.246.89:30002/kubeflow/jupyter-custom:v1.0 # 이부분 추가
...
```


## 2. affinity 로 gpu 모델 찾아서 pod 배치하도록 하기
### 2.1. node 마다 label 추가 (gpu model)
```bash
kubectl label nodes gn131 nvidia.com/gpu.model=rtx3090
kubectl label nodes gn132 nvidia.com/gpu.model=rtx3090
kubectl label nodes gn134 nvidia.com/gpu.model=rtx3090
kubectl label nodes gn135 nvidia.com/gpu.model=rtx3090
kubectl label nodes gn138 nvidia.com/gpu.model=rtx3090

kubectl label nodes gn139 nvidia.com/gpu.model=rtx3090
kubectl label nodes gn140 nvidia.com/gpu.model=rtx3090
kubectl label nodes gn137 nvidia.com/gpu.model=rtx3090


kubectl label nodes gn142 nvidia.com/gpu.model=rtx4090
kubectl label nodes gn143 nvidia.com/gpu.model=rtx4090
kubectl label nodes gn144 nvidia.com/gpu.model=rtx4090
kubectl label nodes gn147 nvidia.com/gpu.model=rtx4090
kubectl label nodes gn148 nvidia.com/gpu.model=rtx4090

kubectl label nodes gn150 nvidia.com/gpu.model=rtx5000
kubectl label nodes gn151 nvidia.com/gpu.model=rtx4000
```
### 2.2. configmap 수정하여 UI에서 gpu 모델 선택 활성화
```yaml
			affinityConfig:
        readOnly: false
        value: ""
        options:
          - configKey: "gpu-v100"
            displayName: "NVIDIA Tesla V100"
            affinity:
              nodeAffinity:
                requiredDuringSchedulingIgnoredDuringExecution:
                  nodeSelectorTerms:
                    - matchExpressions:
                        - key: "nvidia.com/gpu.model"
                          operator: "In"
                          values:
                            - "v100"

          - configKey: "gpu-p100"
            displayName: "NVIDIA Tesla P100"
            affinity:
              nodeAffinity:
                requiredDuringSchedulingIgnoredDuringExecution:
                  nodeSelectorTerms:
                    - matchExpressions:
                        - key: "nvidia.com/gpu.model"
                          operator: "In"
                          values:
                            - "p100"

          - configKey: "gpu-rtx3090"
            displayName: "NVIDIA RTX 3090"
            affinity:
              nodeAffinity:
                requiredDuringSchedulingIgnoredDuringExecution:
                  nodeSelectorTerms:
                    - matchExpressions:
                        - key: "nvidia.com/gpu.model"
                          operator: "In"
                          values:
                            - "rtx3090"

          - configKey: "gpu-rtx4090"
            displayName: "NVIDIA RTX 4090"
            affinity:
              nodeAffinity:
                requiredDuringSchedulingIgnoredDuringExecution:
                  nodeSelectorTerms:
                    - matchExpressions:
                        - key: "nvidia.com/gpu.model"
                          operator: "In"
                          values:
                            - "rtx4090"

          - configKey: "gpu-rtx5000"
            displayName: "NVIDIA Quadro RTX 5000"
            affinity:
              nodeAffinity:
                requiredDuringSchedulingIgnoredDuringExecution:
                  nodeSelectorTerms:
                    - matchExpressions:
                        - key: "nvidia.com/gpu.model"
                          operator: "In"
                          values:
                            - "rtx5000"

          - configKey: "gpu-rtx4000"
            displayName: "NVIDIA Quadro RTX 4000"
            affinity:
              nodeAffinity:
                requiredDuringSchedulingIgnoredDuringExecution:
                  nodeSelectorTerms:
                    - matchExpressions:
                        - key: "nvidia.com/gpu.model"
                          operator: "In"
                          values:
                            - "rtx4000"
```

## 3. 선택된 gpu 찾아 disk cache 연결하기


## (한방에 처리하는 더 안전한 방법)
```bash
# 1. 실제 이름(무작위 hash 9c2fbg2gdc 포함)으로 ConfigMap 덮어쓰기
kubectl create configmap jupyter-web-app-config-9c2fbg2gdc -n kubeflow \
  --from-file=spawner_ui_config.yaml=custom-spawner.yaml \
  -o yaml --dry-run=client | kubectl apply -f -

# 2. 적용을 위해 Jupyter Web App 디플로이먼트 재시작
kubectl rollout restart deployment jupyter-web-app-deployment -n kubeflow
``` 