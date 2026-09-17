#!/bin/bash

# NAMESPACES=(aiops changseon dahyun donghyeon-kim doyeon dwnkim hajin htkim hyungyou jd-hwang jieunpark jikim jsy jylee kgy kyeoryelee mijung minho-lee shpark wjj910 wonlee yeg0311)
NAMESPACES=(limjh0875)

SERVER="https://192.168.0.80:6443"
BASE_PATH="/mnt/testfield/GPU_storage/Private_storage"

for NS in "${NAMESPACES[@]}"; do
  # 1. portforward Role/RoleBinding 적용
  kubectl apply -f - <<EOF
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: portforward-role
  namespace: $NS
rules:
- apiGroups: [""]
  resources: ["pods/portforward"]
  verbs: ["create"]
- apiGroups: [""]
  resources: ["pods"]
  verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: portforward-binding
  namespace: $NS
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: portforward-role
subjects:
- kind: ServiceAccount
  name: default-editor
  namespace: $NS
EOF

  # 2. default-editor Secret 토큰 조회
  SECRET=$(kubectl get secret -n $NS | grep editor | awk '{print $1}')
  if [ -z "$SECRET" ]; then
    echo "$NS: default-editor Secret 없음, 생성 중..."
    kubectl apply -f - <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: default-editor-token
  namespace: $NS
  annotations:
    kubernetes.io/service-account.name: default-editor
type: kubernetes.io/service-account-token
EOF
    kubectl wait --for=jsonpath='{.data.token}' secret/default-editor-token -n $NS --timeout=30s
    SECRET="default-editor-token"
  fi

  TOKEN=$(kubectl get secret $SECRET -n $NS -o jsonpath='{.data.token}' | base64 -d)

  # 3. kubeconfig 생성 (insecure-skip-tls-verify)
  KUBECONFIG_PATH="$BASE_PATH/$NS/kubeconfig"

  kubectl config set-cluster kubeflow-cluster \
    --server=$SERVER \
    --insecure-skip-tls-verify=true \
    --kubeconfig=$KUBECONFIG_PATH

  kubectl config set-credentials ${NS}-user \
    --token=$TOKEN \
    --kubeconfig=$KUBECONFIG_PATH

  kubectl config set-context $NS \
    --cluster=kubeflow-cluster \
    --user=${NS}-user \
    --namespace=$NS \
    --kubeconfig=$KUBECONFIG_PATH

  kubectl config use-context $NS \
    --kubeconfig=$KUBECONFIG_PATH

  echo "$NS 완료 → $KUBECONFIG_PATH"
done
