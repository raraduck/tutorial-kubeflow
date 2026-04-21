#!/bin/bash

IMAGE="192.168.0.80:30002/kubeflow/vscode-v2.4:2"

NODES=(
  gn131 gn132 gn134 gn135
  gn137 gn138 gn140 gn142 gn143
  gn144 gn147 gn148 gn150 gn181
  gn182 gn183 gn184
)

for NODE in "${NODES[@]}"; do
  echo -n "[$NODE] 이미지 삭제 중... "
  RESULT=$(ssh -o StrictHostKeyChecking=no neuroman@$NODE \
    "sudo crictl -r unix:///run/containerd/containerd.sock rmi $IMAGE 2>&1")
  if echo "$RESULT" | grep -qE "Deleted"; then
    echo "✅ 삭제 완료"
  elif echo "$RESULT" | grep -q "no such image"; then
    echo "➖ 이미지 없음 (skip)"
  else
    echo "⚠️  오류: $RESULT"
  fi
done

echo ""
echo "완료. 이미지가 없는 노드는 skip 메시지가 출력됩니다."
