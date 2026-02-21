@echo off
echo DNS 캐시를 플러시합니다...
ipconfig /flushdns
echo Docker 및 WSL을 재시작합니다...
wsl --shutdown
echo 완료되었습니다. Docker Desktop을 다시 실행해 주세요.
pause