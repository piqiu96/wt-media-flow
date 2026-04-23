"""
serve — 启动 Web API 服务
"""
from app.cli import BaseCommand, register_command


@register_command
class ServeCommand(BaseCommand):
    command_name = "serve"
    command_help = "启动 Web API 服务 (FastAPI + Uvicorn)"

    def setup_parser(self, parser) -> None:
        parser.add_argument("--host", default="0.0.0.0", help="监听地址 (默认 0.0.0.0)")
        parser.add_argument("--port", type=int, default=8000, help="监听端口 (默认 8000)")
        parser.add_argument("--reload", action="store_true", help="开发模式自动重载")

    def execute(self, args) -> dict:
        import uvicorn

        host = args.host
        port = args.port
        reload = getattr(args, "reload", False)

        print(f"启动 Web API: http://{host}:{port}")
        print(f"API 文档: http://{host}:{port}/docs")

        uvicorn.run(
            "app.web.api:app",
            host=host,
            port=port,
            reload=reload,
        )
        return {"success": True, "message": "API 服务已停止"}
