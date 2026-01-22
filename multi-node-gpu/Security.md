[//]: # (Update: Security strategy with Bastion Server and RBAC - 2026-01-22)

# [Technical Report] AIOps 클러스터 접근 보안 및 Bastion 서버 구축 전략

## 1. 개요
AIOps 팀의 클러스터 자원 관리 자율성을 보장하면서, 동시에 컨트롤 노드 및 타 서비스의 보안성을 확보하기 위해 권한이 제어된 배스천 서버(Bastion Host) 환경을 구축함.

## 2. 주요 설계 원칙
최소 권한 원칙 (Least Privilege): 관리자에게 클러스터 전체 권한(admin.conf)을 부여하지 않고, 필요한 네임스페이스 내의 권한만 부여함.
접점 단일화: 클러스터 직접 접근을 차단하고, NodePort로 개방된 배스천 서버를 통해서만 kubectl 및 argo 명령을 수행함.
환경 격리: 배스천 서버를 컨트롤 노드에 배치하되, RBAC을 통해 시스템 핵심 자원에 대한 접근을 물리적으로 차단함.

## 3. 세부 구현 사항
#### 3.1. 배스천 서버 배치 및 가용성 설정

컨트롤 노드 고정 배치: 시스템 복구 시 최우선적으로 가동되도록 nodeSelector를 사용하여 컨트롤 노드에 배치함.
Taint 무시 설정: 일반 Pod 배치가 제한된 컨트롤 노드에 입성하기 위해 tolerations를 적용함.

#### 3.2. RBAC 기반 권한 제어

ServiceAccount 활용: 배스천 서버에 aiops-bastion-sa 신분증을 부여하고, 이를 기반으로 권한을 제어함.
RoleBinding 범위 제한: aiops-management 네임스페이스 내에서만 자원(Pod, Workflow, Service 등)을 조작할 수 있도록 한정함.
로그 및 이벤트 권한 추가: 원활한 트러블슈팅을 위해 pods/log 및 events 조회 권한을 명시적으로 포함함.
#### 3.3. 관리자 접속 환경 자동화

자동 신원 증명: SSH 접속 시 .bashrc 스크립트를 통해 Pod 내부의 SA 토큰을 kubectl 인증 정보로 자동 등록함.

## 4. 보안 안정성 검증
리눅스 root 권한과 K8s 권한의 분리

배스천 서버 내에서 관리자가 root 계정을 사용하더라도, kubectl 명령은 주입된 ServiceAccount의 제한된 토큰을 사용함.
따라서 배스천 서버가 탈취되거나 관리자가 실수하더라도 kube-system 등 타 영역의 자원 삭제나 클러스터 설정 변경은 불가능함.
Argo CLI 동작 범위 한정

argo submit 등 워크플로우 관련 명령 역시 동일한 SA 권한을 공유하므로, 허가되지 않은 네임스페이스로의 작업 제출이 원천 차단됨.

## 5. 향후 유지관리 계획
서버실 전원 공사 대응: 클러스터 재부팅 시 컨트롤 노드와 함께 배스천 서버가 자동 복구되는지 점검.
감사 로그 모니터링: aiops-bastion-sa를 통해 수행되는 모든 API 호출 내역을 기록하여 보안 감사 추적성 유지.
접속 IP 제한: NodePort로 노출된 포트에 대해 사내 특정 IP 대역에서만 접근 가능하도록 방화벽(ACL) 추가 적용.

## Appendix. (중요) aiops에서 워크플로우 실행을 위한 권한 설정
Argo를 argo 네임스페이스에 설치했지만, 실제 워크플로우는 aiops 네임스페이스에서 돌리고 싶으실 겁니다. aiops 네임스페이스에서 워크플로우가 파드를 생성하려면 default ServiceAccount에 권한이 있어야 합니다.

간단하게 aiops의 기본 계정에 관리자 권한을 주는 명령어를 실행해 두세요. (이게 없으면 나중에 워크플로우 돌릴 때 Permission Denied 뜹니다.)
```bash
# aiops의 default 계정에게 admin 권한 부여 (워크플로우 실행용)
kubectl create rolebinding default-admin \
  --clusterrole=admin \
  --serviceaccount=aiops:default \
  -n aiops
```
---
**Last Updated:** 2026-01-22  
**Changes:** Implement security strategy with Bastion Server and RBAC
