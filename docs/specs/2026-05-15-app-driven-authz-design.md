# 应用驱动授权 — 设计文档

- **状态**：已实施
- **日期**：2026-05-15
- **范围**：把服务×应用的授权关系从「服务侧手动授权」改为「应用侧勾选服务」单向驱动；API Key 去掉 user 归属
- **取代**：`2026-05-08-v1a-access-control-and-ratelimit-design.md` §3.1、§4–§6 关于授权管理的部分（限流与 default-deny 语义仍然有效）
- **不变**：`service_permissions` 仍是底层白名单表；网关的 `PolicyCache` / 默认拒绝 / 失效广播机制不变

## 1. 动机

V1-A 设计的「服务详情页手动授权应用」在使用中暴露两个问题：

1. **入口割裂**：运营要先在 Service 详情页给 App 授权，再到 API Key 列表为同一个 App 签发 Key。两个页面要回看两遍才知道一个应用能调什么。
2. **签发流程歧义**：API Key 同时支持 `owner_type=user` 和 `owner_type=application`，而只有 application 类型的 Key 受 `service_permissions` 约束 —— user 类型的 Key 设计上「永远默认拒绝」，等于一种死代码。

应用驱动模型把「这个应用能调什么服务」做成应用的**自有属性**：在创建应用时勾选，在应用详情页随时改。服务详情页的「授权应用」由此自动同步，纯只读。Key 签发只需要选应用，因为权限来源完全是应用的服务列表。

## 2. 概念变化

| 旧模型 (V1-A) | 新模型 |
| --- | --- |
| 服务详情页「授权应用」中手动 grant / revoke 行 | 应用详情页「可调用服务」勾选，自动维护 `service_permissions` |
| API Key 可归属 user 或 application | API Key 只能归属 application |
| `service_permissions.note` 记录授权理由 | 删除该字段（自动同步的行不需要人写备注） |
| 审计动作：`service_permission.grant` / `service_permission.revoke` | 审计动作：`application.create` / `application.update`，`after.service_ids` 反映完整集合 |

底层不变：`service_permissions` 仍是 `(application_id, service_id)` 白名单；网关命中规则仍是 `application_id ∈ allow_set_for_service`。

## 3. API 变化

### 3.1 Applications

- **POST `/api/v1/applications`**：请求体新增 `service_ids: list[int]`。返回体新增 `service_ids` 和 `created_at`。
- **GET `/api/v1/applications/{id}`**（新增）：返回应用详情含 `service_ids`。
- **PATCH `/api/v1/applications/{id}`**（新增）：支持改 `name` / `team` / `description` / `service_ids`。
  - `service_ids` 字段语义：**省略 = 不动；给出 = 作为新的完整集合**（含 `[]` 清空）。
  - Diff 计算后只对 `added ∪ removed` 的 `service_id` 发送 `policy:invalidate`，无变化则不广播。
- **GET `/api/v1/applications`**：返回的每个 item 含 `service_ids`（一条 SQL 批量回填，无 N+1）。

### 3.2 API Keys

- **POST `/api/v1/api-keys`**：请求体把 `owner_type` + `owner_id` 替换为单字段 `application_id`。内部固定写 `owner_type=application`、`owner_id=application_id`。
- 响应仍含 `owner_type` / `owner_id`（列保留，便于前端兼容显示历史 user 类型的已吊销 Key）。

### 3.3 Permissions

仅剩两个只读端点：
- `GET /api/v1/services/{slug}/permissions` — 某服务被哪些应用授权
- `GET /api/v1/applications/{id}/permissions` — 某应用能调哪些服务

**删除**：`POST /api/v1/services/{slug}/permissions`、`DELETE /api/v1/services/{slug}/permissions/{application_id}`。

## 4. 数据迁移（alembic 0005）

```sql
-- 1. 历史 user-owned key 全部吊销（不再支持的归属类型）
UPDATE api_keys SET revoked_at = now()
WHERE owner_type = 'user' AND revoked_at IS NULL;

-- 2. 删除 service_permissions.note
ALTER TABLE service_permissions DROP COLUMN note;
```

不动：`api_keys.owner_type` 列、`apikeyownertype` 枚举（PG 删除枚举值代价高；应用层禁止再签发 user 类型即可）。

## 5. 不变式

- **V1-A.1（保留）**：`policy:invalidate` 必须在事务 commit **之后**发布。在 `applications.py` 中：`flush → audit_log → commit → publish_policy_invalidate` 的顺序。
- **V1-A.2（保留）**：默认拒绝。`service_permissions` 没有 `(app, svc)` 行即拒绝。
- **新增**：当 PATCH 的 `service_ids` 与现状相同（diff 为空），**不**发布失效广播。避免无意义的缓存刷新。
- **新增**：API Key 永远归属应用。`POST /api/v1/api-keys` 不再接受 `owner_type=user`。Schema 层移除 `owner_type` / `owner_id` 字段，只接 `application_id`。

## 6. 审计

| 动作 | 何时写 | `before` | `after` |
| --- | --- | --- | --- |
| `application.create` | 创建应用（含 service_ids） | `None` | 标量列 + `service_ids: [...]` |
| `application.update` | PATCH 应用（标量或 service_ids 任一） | 改前完整快照（含 `service_ids`） | 改后完整快照（含 `service_ids`） |

不再写 `service_permission.grant` / `service_permission.revoke` 行。历史这两类事件在 `audit_events` 中仍可查（用 audit 列表筛选「修改应用」也能看到等价信息）。

## 7. UI 变化

- **应用列表**：创建弹窗加多选「可调用服务」；列表加「可调服务 N 个」列。
- **应用详情**：增可编辑的「可调用服务」面板（admin / operator 可改，viewer 只读）。下方还有一张「已授权服务」表，链接到服务详情。
- **API Key 签发**：删掉「归属类型」单选和「用户 ID」输入，只留「所属应用」下拉。
- **API Key 列表**：归属列直接显示应用名（链接到应用详情），历史 user Key 显示「用户 #N（已弃用）」灰字。
- **服务详情 → 授权应用**：删掉「授权」按钮、授权弹窗、撤销按钮。变成纯只读列表 + 「在对应应用详情页修改」提示。Tab 标题带上数量。
- **审计列表**：动作下拉新增「修改应用」。

## 8. 不在此次范围

- tool 级权限（仍为 V1 之后的工作）
- 应用归属用户的转移、应用的软删除
- API Key 与应用以外主体的绑定（如服务账号 / SSO 联邦身份）

旧的 `bootstrap_permissions.py` 脚本保留为可选的"全量授权"工具（已配合 schema 变化去掉 `note` 字段写入）。
