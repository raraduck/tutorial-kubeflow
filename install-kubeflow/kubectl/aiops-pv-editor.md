# PV Editor 권한 추가 절차
기존 kubeflow-node-reader 패턴과 동일한 방식으로 추가합니다.

## [관리자] Step A. kubeflow-pv-editor ClusterRole 생성 (최초 1회)
PV는 클러스터 스코프 리소스이므로 aggregation label을 붙여 kubeflow-edit에 자동 집계되도록 합니다.

한 번만 실행하면 이후 모든 사용자에게 자동 적용됩니다.

```bash
kubectl apply -f - <<EOF
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: kubeflow-pv-editor
  labels:
    rbac.authorization.kubeflow.org/aggregate-to-kubeflow-edit: "true"
rules:
- apiGroups: [""]
  resources:
  - persistentvolumes
  verbs:
  - get
  - list
  - watch
EOF
```

## 적용확인:
```bash
kubectl get clusterrole kubeflow-pv-editor
```

## [관리자] Step B. 사용자 네임스페이스에 ClusterRoleBinding 추가
```bash
NAMESPACE=aiops   # 다른 네임스페이스 추가 시 변경

kubectl apply -f - <<EOF
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: ${NAMESPACE}-default-editor-pv-editor
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: kubeflow-pv-editor
subjects:
- kind: ServiceAccount
  name: default-editor
  namespace: ${NAMESPACE}
EOF
```
## 적용확인:
```bash
kubectl get clusterrolebinding ${NAMESPACE}-default-editor-pv-editor
```
## [관리자] Step C. 권한 검증
```bash
# PV 조회 권한 확인
kubectl auth can-i list persistentvolumes \
  --as=system:serviceaccount:aiops:default-editor
# → yes

# PV 상세 조회 권한 확인
kubectl auth can-i get persistentvolumes \
  --as=system:serviceaccount:aiops:default-editor
# → yes

# PV 삭제는 불가 확인 (조회만 부여했으므로)
kubectl auth can-i delete persistentvolumes \
  --as=system:serviceaccount:aiops:default-editor
# → no
```