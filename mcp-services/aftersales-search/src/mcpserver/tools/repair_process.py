"""MES 生产/维修流程查询工具（按 SN）。"""

from mcpserver import auth, config


async def _fetch_repair_process(sn: str) -> dict:
    ticket, inv_org_id = await auth.get_ticket()
    body = {
        "ApiType": "AiController",
        "Parameters": [{"Value": {"Sn": sn}}],
        "Method": "GetSN",
        "Context": {"Ticket": ticket, "InvOrgId": inv_org_id},
    }
    data = await auth.post_with_jwt(config.GETSN_URL, body)
    if not data.get("Success"):
        # 票据可能已失效；作废后下次调用会重新登录换取
        auth.invalidate_ticket()
        raise RuntimeError(f"GetSN failed: {data.get('Message')}")
    return data.get("Result", {})


def register(mcp):
    @mcp.tool()
    async def get_repair_process_status_by_sn(sn: str) -> dict:
        """根据 SN 号查询某台机器在MES系统中的当前工序（维修状态）和最近更新时间。

        适用场景：用户输入了sn号或者想知道"这台机器现在的维修状态"、"当前在什么工序"、
        等关于**实时状态**的问题。返回的是机器在MES系统中的当前工序（如"装箱"、
        "上料"、"质检"等）。

        与售后查询的区别：
        - 本工具：MES系统中实时的当前工序
        - search_sn_in_sales_post_order_count / _data：CRM 系统中的机器详细信息

        Args:
            sn: 机器序列号（Serial Number），厂商出厂的唯一编号。直接传入
                用户提供的原始字符串，不要做大小写转换或去除连字符。
                示例："MC705"、"SN20240315001"。

        Returns:
            字典，包含字段：
            - Sn (str): 机器序列号，回显输入。
            - CurrentProcess (str): 当前流程节点名称，如"装箱"。
            - UpdateDate (str): 最近一次状态更新时间，ISO 8601 格式带时区，
              如 "2022-03-15T09:24:41+08:00"。
            若该 SN 不存在或无记录，返回空字典 {}。
        """
        return await _fetch_repair_process(sn)
