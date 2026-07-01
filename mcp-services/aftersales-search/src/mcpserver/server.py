import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.middleware.cors import CORSMiddleware

from mcpserver import files
from mcpserver.config import HOST, PORT
from mcpserver.tools import device_profile, fqc_report, repair_process, sales_order

mcp = FastMCP("mcpserver", host=HOST, port=PORT)

sales_order.register(mcp)
repair_process.register(mcp)
device_profile.register(mcp)
fqc_report.register(mcp)


def main() -> None:
    app = mcp.streamable_http_app()
    files.register(app)
    files.start_sweeper()  # 后台周期清扫过期报告，回收磁盘
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "OPTIONS", "DELETE"],
        allow_headers=["*"],
        expose_headers=["Mcp-Session-Id"],
    )
    uvicorn.run(app, host=HOST, port=PORT)


if __name__ == "__main__":
    main()
