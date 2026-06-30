"""CRM 售后工单查询工具（按 SN）。"""

from mcpserver import auth, config


async def _fetch(sn: str) -> dict:
    return await auth.post_with_jwt(config.SEARCH_SN_IN_SALES_POST_ORDER_URL, {"sn": sn})


def register(mcp):
    @mcp.tool()
    async def search_sn_in_sales_post_order_count(sn: str) -> int:
        """统计某台机器在 CRM 系统中的售后维修/服务工单总数。

        适用场景：用户想知道"这台机器修过几次"、"维修次数"、"返修频率"、
        "有没有售后记录"等只关心数量、不关心具体内容的问题。
        如果用户想看维修详情，请改用 search_sn_in_sales_post_order_data。

        Args:
            sn: 机器序列号（Serial Number），通常为厂商出厂时打在机身上的
                唯一编号。直接传入用户提供的原始字符串即可，不要做大小写
                转换或去除连字符。示例："SN20240315001"、"A1B2-C3D4"。

        Returns:
            该 SN 对应的售后维修工单数量（整数）。无记录时返回 0。
        """
        return (await _fetch(sn)).get("count", 0)

    @mcp.tool()
    async def search_sn_in_sales_post_order_data(sn: str) -> list:
        """查询某台机器在 CRM 系统中的详细信息。

        适用场景：用户输入了一个sn号或者想了解"某个机器的相关信息"、"某台机器的详细信息"等需要看具体内容的问题。
        如果只是想知道维修次数，请改用 search_sn_in_sales_post_order_count。

        Args:
            sn: 机器序列号（Serial Number），厂商出厂的唯一编号。直接传入
                用户提供的原始字符串，不要做大小写转换或去除连字符。
                示例："SN20240315001"、"A1B2-C3D4"。

        Returns:
            包含一条机器全部信息字段的列表，典型字段含工单号、报修日期、故障
            描述、维修状态、客户信息等。无记录时返回空列表 []。
        """
        return (await _fetch(sn)).get("data", [])
