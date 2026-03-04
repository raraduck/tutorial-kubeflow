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
            "title": "VS Code"
        },
    }
}