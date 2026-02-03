# 노드(Host) 설정 변경 (권장)
- 쿠버네티스 워커 노드(Argo가 실행 중인 노드들)에 SSH로 접속하여 아래 명령어를 입력 (재부팅 없이 즉시 적용됩니다.)
- img2dataset이 너무 많은 파일을 동시에 열거나 감시(watch)하려고 해서 리눅스 커널의 제한(Limit)에 걸린 상태입니다.
- 구체적으로는 failed to create fsnotify watcher 에러이므로, 단순한 파일 개수(nofile)보다는 파일 시스템 감시자(inotify watch)의 개수 제한을 초과했을 가능성이 매우 높습니다.
```bash
# 1. inotify 인스턴스 및 감시(Watch) 제한을 대폭 늘립니다.
sudo sysctl -w fs.inotify.max_user_instances=8192
sudo sysctl -w fs.inotify.max_user_watches=524288

# 2. (선택) 전체 파일 오픈 제한도 넉넉하게 늘려줍니다.
sudo sysctl -w fs.file-max=100000

# 3. 설정 영구 보존 (재부팅 후에도 유지)
echo "fs.inotify.max_user_instances=8192" | sudo tee -a /etc/sysctl.conf
echo "fs.inotify.max_user_watches=524288" | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```