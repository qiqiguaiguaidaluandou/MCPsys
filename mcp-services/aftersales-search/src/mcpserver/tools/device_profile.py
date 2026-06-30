"""设备档案信息查询工具（按 SN）。

请求体为简单的 {"sn": ...}，鉴权只需 JWT（token 直接放 Authorization 头），
与 CRM 售后查询一致，不需要票据——票据是 MES 独有的。
"""

from mcpserver import auth, config


async def _fetch_device_profile(sn: str) -> dict:
    return await auth.post_with_jwt(config.GET_DEVICE_PROFILE_URL, {"sn": sn})


def register(mcp):
    @mcp.tool()
    async def get_device_profile_by_sn(sn: str) -> dict:
        """根据 SN 号查询某台设备的档案信息（出厂、客户、产品型号、保修等）。

        适用场景：用户输入了 sn 号或者想了解"这台设备是什么型号"、"属于哪个客户/项目"、
        "什么时候生产/验收的"、"保修期/是否在保"等关于**设备静态档案**的问题。

        与其他工具的区别：
        - 本工具：设备档案（型号、客户、项目、生产/验收日期、保修等静态信息）
        - get_repair_process_status_by_sn：MES 中实时的当前工序
        - search_sn_in_sales_post_order_count / _data：CRM 中的售后工单信息

        Args:
            sn: 机器序列号（Serial Number），厂商出厂的唯一编号。直接传入
                用户提供的原始字符串，不要做大小写转换或去除连字符。
                示例："MC705"、"SN20240315001"。

        Returns:
            字典，包含字段：
            - sn (str): 设备序列号。
            - new_productgroup (str): 产品组。
            - new_account (str): 所属客户/账户。
            - new_productmodel (str): 产品型号。
            - new_salesorder (str): 关联销售订单。
            - new_project_id (str): 项目 ID。
            - new_projectcode (str): 项目编号。
            - new_produceddate (str): 生产日期。
            - new_acceptance_date (str): 验收日期。
            - new_warrantyperiod (str): 保修期。
            - new_warranty (str): 保修信息/是否在保。
            若该 SN 不存在或无记录，返回空字典 {}。
        """
        return await _fetch_device_profile(sn)
