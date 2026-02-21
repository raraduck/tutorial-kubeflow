# 직접 설치: NFS-Subdir-External-Provisioner 

```
echo "✅ YAML 파일 생성 완료!"
echo ""
echo "실행 순서:"
echo "1. kubectl apply -f step1_remove_default_storageclass.yaml"
echo "2. kubectl apply -f step2_rbac.yaml"
echo "3. kubectl apply -f step3_deployment.yaml"
echo "4. kubectl apply -f step4_storageclass.yaml"
echo "5. kubectl apply -f step5_test_pvc.yaml  # 테스트용"
echo ""
echo "확인 명령어:"
echo "- kubectl get storageclass"
echo "- kubectl get pods -n kube-system | grep nfs-kubeflow"
echo "- kubectl get pvc test-kubeflow-pvc"
echo "- kubectl get pv"
```

# Rancher-local-path-provisioner 설치후 운영할때 nodeAffinity 기능 필요함
아래와 같이 edit 필요
```bash
kubectl edit configmap jupyter-web-app-config-<이름확인필요> -n kubeflow

# 아래 설정 적용후 재시작
kubectl rollout restart deployment jupyter-web-app -n kubeflow
```
```yaml
    affinityConfig:
        readOnly: false
        value: ""
        options:
          - configKey: "gpu-v100"
            displayName: "▶ NVIDIA Tesla V100"
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
            displayName: "▶ NVIDIA Tesla P100"
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
            displayName: "▶ NVIDIA RTX 3090"
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
            displayName: "▶ NVIDIA RTX 4090"
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
            displayName: "▶ NVIDIA Quadro RTX 5000"
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
            displayName: "▶ NVIDIA Quadro RTX 4000"
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