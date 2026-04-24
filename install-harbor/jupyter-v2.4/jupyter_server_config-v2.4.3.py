import os

# Jupyter 서버 프로세스 umask 설정 (GUI 파일 생성 시 777 권한 적용)
os.umask(0o000)

c.ServerProxy.servers = {
    "vscode": {
        "command": [
            "code-server",
            "--auth", "none",
            "--bind-addr", "127.0.0.1:{port}",
            "/home/jovyan"
        ],
        "timeout": 30,
        "launcher_entry": {
            "enabled": True,
            "title": "VS Code",
        },
    }
}

# NB_PREFIX 기반 base_url 자동 반영
nb_prefix = os.environ.get("NB_PREFIX", "/")
c.ServerApp.base_url = nb_prefix
c.ServerApp.tornado_settings = {"headers": {"Content-Security-Policy": "frame-ancestors *"}}