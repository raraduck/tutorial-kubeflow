# PySpark 스크립트 연동
## Step 1: PySpark 필터링 스크립트 작성 (filter_script.py)
- 먼저 로컬 컴퓨터(터미널)에서 파이썬 파일을 만듭니다. 이 스크립트는 NFS에 있는 Parquet 파일을 읽어서 영어(en)만 남기고 다시 NFS에 저장하는 역할을 합니다.
```python
# filter_script.py 파일 생성
from pyspark.sql import SparkSession
from pyspark.sql.functions import col
import sys

def main():
    # 1. Spark 세션 시작
    spark = SparkSession.builder \
        .appName("DataComp-Filter-EN") \
        .getOrCreate()

    print(">>> [Start] Loading Metadata...")

    # 2. 데이터 로드 (NFS 경로)
    # file:// 접두사를 붙여야 로컬(마운트된) 경로로 인식합니다.
    input_path = "file:///data1/datacomp-medium/metadata/*.parquet"
    
    try:
        df = spark.read.parquet(input_path)
        print(f">>> Total Rows (Before): {df.count()}")
        print(f">>> Columns Found: {df.columns}")
    except Exception as e:
        print(f"!!! Error reading parquet: {e}")
        sys.exit(1)

    # 3. 언어 컬럼 자동 감지 및 필터링
    # DataComp 버전에 따라 컬럼명이 다를 수 있어 안전장치를 둡니다.
    target_col = None
    if "language" in df.columns: target_col = "language"
    elif "cld3" in df.columns: target_col = "cld3"
    elif "lang" in df.columns: target_col = "lang"
    elif "fasttext" in df.columns: target_col = "fasttext"

    if target_col:
        print(f">>> Filtering by column: '{target_col}' == 'en'")
        filtered_df = df.filter(col(target_col) == "en")
    else:
        print("!!! Warning: No language column found. Skipping filter.")
        filtered_df = df

    # 4. 저장 (NFS 최적화: Repartition)
    # 중요: 파티션 수를 줄여서(예: 50~100개) NFS의 파일 생성 부하를 줄입니다.
    output_path = "file:///data1/datacomp-medium/filtered_metadata_en"
    print(f">>> Saving to {output_path} ...")
    
    # overwrite 모드로 기존 파일이 있다면 덮어씁니다.
    filtered_df.repartition(100).write.mode("overwrite").parquet(output_path)
    
    print(">>> [Success] Job Finished.")
    spark.stop()

if __name__ == "__main__":
    main()
```
## Step 2: 스크립트를 쿠버네티스에 등록 (ConfigMap)
- 매번 이미지를 빌드하는 건 번거롭습니다. 방금 만든 파이썬 파일을 ConfigMap으로 만들면 Spark 파드들이 바로 가져다 쓸 수 있습니다.
```bash
# 1. 혹시 기존에 만든게 있다면 삭제
kubectl delete configmap spark-filter-script-cm --ignore-not-found

# 2. ConfigMap 생성 (파일명: filter_script.py)
kubectl create configmap spark-filter-script-cm \
  --from-file=filter_script.py=filter_script.py \
  --namespace=default
```
## Step 3: SparkApplication YAML 작성 (filter-job.yaml)
- 이제 Spark Operator에게 일을 시킬 주문서를 작성합니다. 아까 성공했던 apache/spark-py:v3.1.3 이미지를 사용합니다.
```yaml
# filter-job.yaml
apiVersion: "sparkoperator.k8s.io/v1beta2"
kind: SparkApplication
metadata:
  name: datacomp-filter-en
  namespace: default
spec:
  type: Python
  pythonVersion: "3"
  mode: cluster
  image: "apache/spark-py:v3.1.3"  # 검증된 이미지
  imagePullPolicy: IfNotPresent
  
  # ConfigMap이 마운트될 경로를 지정
  mainApplicationFile: "local:///opt/spark/scripts/filter_script.py"
  sparkVersion: "3.1.3"
  restartPolicy:
    type: Never

  # [Driver 설정]
  driver:
    cores: 1
    memory: "2g"
    serviceAccount: spark-team-sa  # 권한 계정 (필수)
    volumeMounts:
      - name: nfs-data             # 데이터 볼륨
        mountPath: /data1
      - name: script-volume        # 스크립트 볼륨
        mountPath: /opt/spark/scripts

  # [Executor 설정 - 3대 노드 병렬 처리]
  executor:
    cores: 2                       # 코어 수 (서버 사양에 맞춰 조절)
    instances: 3                   # 3개의 파드 생성
    memory: "4g"                   # 메모리 (데이터가 크므로 넉넉히)
    volumeMounts:
      - name: nfs-data
        mountPath: /data1
      - name: script-volume
        mountPath: /opt/spark/scripts

  # [볼륨 정의]
  volumes:
    # 1. 실제 데이터가 있는 NFS (HostPath로 연결)
    - name: nfs-data
      hostPath:
        path: /data1
        type: Directory
    # 2. 파이썬 스크립트가 들어있는 ConfigMap
    - name: script-volume
      configMap:
        name: spark-filter-script-cm
```
## Step 4: 실행 및 모니터링
- 이제 작성한 YAML을 클러스터에 제출합니다.
1. 실행
```bash
kubectl apply -f filter-job.yaml
```
2. 상태 모니터링 (실시간)
```bash
# 파드 생성 및 상태 변화 관찰
kubectl get pods -w
```