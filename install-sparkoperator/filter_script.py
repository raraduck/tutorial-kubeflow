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