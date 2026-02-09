# Argo Workflow 생성 및 실행 (datacomp-workflow.yaml)

## 참고: kubeflow 로 설치된 argo 를 사용할때에는 사용자 네임스페이스마다 minio secret 권한이 필요함
```bash
# kubeflow 네임스페이스에 있는 yaml 을 복사하여 <namespace> 로 치환한 뒤 secret 생성
kubectl get secret mlpipeline-minio-artifact -n kubeflow -o yaml | sed 's/namespace: kubeflow/namespace: <namespace>/' | kubectl apply -f 
# networkpolicy 에서 차단되든 경우가 있을 수 있으므로 kubeflow 네임스페이스에서 networkpolicy 를 모두 허용
kubectl delete networkpolicy --all -n kubeflow
```

## 단계 1. 데이터 복사 (보존 복사) 
- 기존 /data2 에 있던 다국적언어를 포함하여 다운받은 600GB 용량 파일들을 /data4로 옮기는 효율적인 방법
> (주의: /data2/ 뒤에 슬래시 /를 붙여야 /data4/data2 폴더가 생기는 걸 방지하고 내용물만 들어갑니다.)
```bash
# 옵션 설명:
# -a: 권한(Permission), 시간, 소유자 등 속성 그대로 유지 (archive)
# -v: 진행 상황 표시 (verbose)
# -h: 용량을 보기 편하게 표시 (human-readable)
# --progress: 전송 진행률 바 표시 (필수!)

rsync -avh --progress /data2/ /data4/

# 파일 개수 비교
ls -1 /data2 | wc -l
ls -1 /data4 | wc -l

# sudo를 붙여서 다시 실행 (데이터 검증 효과)
sudo rsync -avh --progress /data2/ /data4/

rm -rf /data2/*
```
요약
- df -h로 같은 디스크인지 확인한다.
    - 같으면 mv (1초 컷).
    - 다르면 rsync -avh --progress로 복사 후 rm으로 삭제. (mv 금지)

