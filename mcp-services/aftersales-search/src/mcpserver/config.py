import os

from dotenv import load_dotenv

load_dotenv()


HOST = os.getenv("MCP_HOST", "")
PORT = int(os.getenv("MCP_PORT", "8765"))

SEARCH_SN_IN_SALES_POST_ORDER_URL = os.getenv(
    "SEARCH_SN_IN_SALES_POST_ORDER_URL",
    "https://e.com/api/c/c044/SearchSNInSalesPostOrder",
)

JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_ISSUER = os.getenv("JWT_ISSUER", "")
# LOGIN_URL（换票据）所用的 JWT 凭证与其它接口不同；未配置时回退到主集。
LOGIN_JWT_SECRET = os.getenv("LOGIN_JWT_SECRET", "") or JWT_SECRET
LOGIN_JWT_ISSUER = os.getenv("LOGIN_JWT_ISSUER", "") or JWT_ISSUER
LOGIN_USERNAME = os.getenv("LOGIN_USERNAME", "")
LOGIN_PASSWORD = os.getenv("LOGIN_PASSWORD", "")
LOGIN_URL = os.getenv("LOGIN_URL", "https://as/pi/s/m/login")
GETSN_URL = os.getenv("GETSN_URL", "https://ti/open/m/m/m/GetSn")
GET_DEVICE_PROFILE_URL = os.getenv("GET_DEVICE_PROFILE_URL", "https://placeholder/GetDeviceProfile")
GET_FQC_REPORT_URL = os.getenv("GET_FQC_REPORT_URL", "https://placeholder/GetFqcReport")

# FQC 报告解码后落地保存的目录
FQC_REPORT_DIR = os.path.expanduser(os.getenv("FQC_REPORT_DIR") or "~/fqc_reports")

# FQC 报告文件/下载链接的有效期（小时）。文件 mtime 超过该时长后：
# 下载端点直接返回 404（链接失效），后台清扫任务负责删除文件回收磁盘。
# 设为 <=0 表示永不过期（回到旧行为）。同一 SN 再次查询会覆盖文件并刷新有效期。
FQC_REPORT_TTL_HOURS = float(os.getenv("FQC_REPORT_TTL_HOURS", "2"))

# 后台清扫任务运行间隔（分钟）。最低 1 分钟。
FQC_REPORT_SWEEP_INTERVAL_MINUTES = float(
    os.getenv("FQC_REPORT_SWEEP_INTERVAL_MINUTES", "15")
)

# 服务对外可访问的基础地址，用于拼接文件下载链接。
# 远程部署时必须填真实公网/内网地址，如 https://mcp.company.com 或 http://1.2.3.4:8765
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
