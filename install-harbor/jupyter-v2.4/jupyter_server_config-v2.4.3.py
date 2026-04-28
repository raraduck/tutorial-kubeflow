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
import os
nb_prefix = os.environ.get("NB_PREFIX", "/")
c.ServerApp.base_url = nb_prefix
c.ServerApp.tornado_settings = {"headers": {"Content-Security-Policy": "frame-ancestors *"}}
