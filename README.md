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

```bash
Checking package manager

Continue running under SSH?

This session appears to be running under ssh. It is not recommended
to perform a upgrade over ssh currently because in case of failure it
is harder to recover.

If you continue, an additional ssh daemon will be started at port
'1022'.
Do you want to continue?

Continue [yN] y

Starting additional sshd

To make recovery in case of failure easier, an additional sshd will
be started on port '1022'. If anything goes wrong with the running
ssh you can still connect to the additional one.
If you run a firewall, you may need to temporarily open this port. As
this is potentially dangerous it's not done automatically. You can
open the port with e.g.:
'iptables -I INPUT -p tcp --dport 1022 -j ACCEPT'
```
#### iptables 명령어로방화벽 열기 (다른 명령어)
iptables -I INPUT -p tcp --dport 1022 -j ACCEPT

-I INPUT: 들어오는(INPUT) 패킷 규칙의 **가장 맨 앞(Insert)**에 이 규칙을 넣어라. (가장 먼저 적용되게 함)

-p tcp: TCP 프로토콜 패킷에 대해.

--dport 1022: 목적지 포트가 1022번인 경우.

-j ACCEPT: 허용(ACCEPT) 

