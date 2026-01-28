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