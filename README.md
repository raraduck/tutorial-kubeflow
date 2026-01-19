# 22.04 세팅
## 업그레이드
만약 20.04 우분투라면 아래 명령을 통해서 업그레이드를 해야합니다.
### 1. 패키지 업데이트 및 세팅
```bash
# 1. 패키지 리스트 업데이트 및 업그레이드
sudo apt update && sudo apt upgrade -y

# 2. 불필요한 패키지 정리
sudo apt autoremove -y

# 3. 업그레이드 도구 설치 확인
sudo apt install update-manager-core -y
```

### 2. 예비용 ssh 접속포트 열어두기
sudo vi /etc/ssh/sshd_config
```bash
# 1. 기존 Port 22 아래에 Port 2022를 추가 (주석 #이 있다면 제거하세요.)
Port 22
Port 2022
# 2. SSH 서비스 재시작 및 방화벽 허용:
sudo systemctl restart ssh
sudo ufw allow 2022/tcp  # 방화벽 사용 시
```

### 3. 접속 테스트
```bash
ssh -p 2022 <userid>@<node ip>
```

### 4. 강제 체크 후 업데이트
```bash
# 강제 체크 후 업그레이드
sudo do-release-upgrade
```
