# onboarding 에 필요한 설정들
> - poddefault 에서 설정한 사항들을 configurations 에서 선택할 수 있도록 합니다.
> - poddefault 는 이름단위로 네임스페이스에 할당되기 때문에 필요한 기능을 선택할 수 있습니다.
## 0. profile 생성 (자원 할당 등)
```yaml
apiVersion: kubeflow.org/v1
kind: Profile
metadata:
  name: gen01
spec:
  owner:
    kind: User
    name: dwnkim@neurophet.com  # 변경된 소유자
  # 이 해당 네임스페이스 전체에 리소스가 명시되지 않은 파드는 절대 생성 불가라는 엄격한 규칙
  resourceQuotaSpec: 
    hard:
        # cpu, memory 항목을 삭제합니다.
        # 이 항목들이 없으면 파드 생성 시 리소스를 안 적어도 쿼터 에러가 나지 않습니다.
        # 나중에 pvcviewer 생성할때 이것 때문에 pod 생성이 안됩니다.
    #   cpu: "100"
    #   memory: 100Gi
    # CPU/Memory는 삭제하여 PVC Viewer 등 유틸리티 파드 생성 보장
      persistentvolumeclaims: "10" # PVC 객체의 총 개수를 10개로 제한
      requests.storage: "5Ti"       # 이 네임스페이스에서 쓰는 모든 볼륨 용량의 합을 5TB로 제한
      # GPU 개수를 제한하여 특정 유저의 자원 독점 방지
      limits.nvidia.com/gpu: "8"
```

## 1. volume 에서 local-path 를 생성할수 있도록 하는게 좋음
```yaml

```
## 1. local emphemeral cache 기능 활성화 (정지하면 삭제되어 캐시 재사용성 감소)
```yaml
apiVersion: "kubeflow.org/v1alpha1"
kind: PodDefault
metadata:
  name: lvm-ephemeral-local
  namespace: gen01
spec:
  desc: "High-Speed Data Volume (주의: 파드 종료 시 소멸 - ReadWrite)"
  selector:
    matchLabels:
      lvm-ephemeral-local: "true"
  volumeMounts:
    - name: lvm-local
      mountPath: /home/jovyan/data
  volumes:
    - name: lvm-local
      ephemeral:
        volumeClaimTemplate:
          spec:
            accessModes: [ "ReadWriteOnce" ]
            storageClassName: "local-path" # LVM과 연결된 프로비저너 이름
            resources:
              requests:
                storage: 500Gi
```
## 2. readonly NAS 데이터 선택 (ydb2, ydb3, researchdata)
```yaml
apiVersion: "kubeflow.org/v1alpha1"
kind: PodDefault
metadata:
  name: shared-researchdata-ro
  namespace: gen01  # <--- 적용할 유저 네임스페이스로 변경하세요! (여러 곳이면 여러 번 배포)
spec:
  desc: "공용 데이터셋 연결 (ResearchData - ReadOnly)"
  selector:
    matchLabels:
      shared-researchdata-ro: "true"
  volumeMounts:
    # 1. Research Data 마운트
    - name: researchdata
      mountPath: /home/jovyan/ResearchData
      readOnly: true
  volumes:
    # 실제 NFS 서버 정보 입력 (PV/PVC를 거치지 않고 직접 연결하여 충돌 방지)
    - name: researchdata
      nfs:
        server: 192.168.0.200       # NFS 서버 IP
        path: /volume1/ResearchData # NFS 실제 경로
        readOnly: true
```
```yaml
apiVersion: "kubeflow.org/v1alpha1"
kind: PodDefault
metadata:
  name: shared-ydb2-ro
  namespace: dwnkim  # <--- 적용할 유저 네임스페이스로 변경하세요! (여러 곳이면 여러 번 배포)
spec:
  desc: "공용 데이터셋 연결 (YDB2 - ReadOnly)"
  selector:
    matchLabels:
      shared-ydb2-ro: "true"
  volumeMounts:
    # 2. YDB2 마운트
    - name: ydb2
      mountPath: /home/jovyan/YDB2
      readOnly: true
  volumes:
    # 실제 NFS 서버 정보 입력 (PV/PVC를 거치지 않고 직접 연결하여 충돌 방지)
    - name: ydb2
      nfs:
        server: 192.168.0.200
        path: /volume3/YDB2
        readOnly: true
```
```yaml
apiVersion: "kubeflow.org/v1alpha1"
kind: PodDefault
metadata:
  name: shared-ydb3-ro
  namespace: gen01  # <--- 적용할 유저 네임스페이스로 변경하세요! (여러 곳이면 여러 번 배포)
spec:
  desc: "공용 데이터셋 연결 (YDB3 - ReadOnly)"
  selector:
    matchLabels:
      shared-ydb3-ro: "true"
  volumeMounts:
    # 3. YDB3 마운트
    - name: ydb3
      mountPath: /home/jovyan/YDB3
      readOnly: true
  volumes:
    # 실제 NFS 서버 정보 입력 (PV/PVC를 거치지 않고 직접 연결하여 충돌 방지)
    - name: ydb3
      nfs:
        server: 192.168.0.200
        path: /volume2/YDB3
        readOnly: true
```

## 2. timezone 등 환경설정 사항들 (기본으로 KST가 선택 및 체크)
> jupyter-web-app-configmap 에서 설정
```yaml
################################################################
# Environment
################################################################
environment:
  readOnly: false
  value:
    TZ: "Asia/Seoul" # timezone
    # 한글 깨짐 및 인코딩 방지
    LANG: "C.UTF-8"
    LC_ALL: "C.UTF-8"
    # 캐시 경로를 개인 영구볼륨 (local 또는 nas) 로 지정
    HF_HOME: "/home/jovyan/workspace/.cache/huggingface" 
    TORCH_HOME: "/home/jovyan/workspace/.cache/torch"
    XDG_CACHE_HOME: "/home/jovyan/workspace/.cache"
```
## 3. Jupyter Notebook 생성 UI에서 "Attach Existing" 원천 차단
> 사용자가 노트북을 만들 때 Workspace Volume과 Data Volumes 섹션에서 기존 PVC를 선택하지 못하도록 설정 파일(spawner_ui_config)을 잠가버립니다.
```yaml
################################################################
  # Workspace Volumes
  ################################################################
  workspaceVolume:
    readOnly: false  # <--- 핵심: true로 변경하여 UI 조작(Attach Existing 등) 불가 상태로 고정
    value:
      mount: /home/jovyan
      newPvc:
        metadata:
          name: "{notebook-name}-workspace"
        spec:
          accessModes:
            - ReadWriteOnce
          resources:
            requests:
              storage: 10Gi
          # storageClassName: "nfs-client" # Workspace용 기본 스토리지 클래스가 있다면 지정 권장

  ################################################################
  # Data Volumes
  ################################################################
  dataVolumes:
    readOnly: true  # <--- 핵심: true로 변경하여 "Add Volume" 버튼 및 Attach 기능 비활성화
    value: []
```