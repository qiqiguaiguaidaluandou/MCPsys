# HTTPS / 证书问题排查指南

> 背景：访问 MCP 管理系统域名（如 `https://mcp.jptoe.com`）时，浏览器和 RAG 服务正常，
> 但 MCP 服务（及 curl / openssl）报证书错误。本文记录完整的排查过程、根因与解决方案，
> 供后续遇到同类问题时直接参考。

---

## TL;DR（结论先行）

- **根因**：服务端只发了**叶子证书**，漏发了**中间证书**（DigiCert/GeoTrust 链），导致客户端无法接上信任链。
  - openssl 报 `Verify return code: 21 (unable to verify the first certificate)`
  - curl 报 `unable to get local issuer certificate` / `unknown CA`
- **不是**自签名、不是内部 CA、不是网络/转发问题——证书本身是正规 DigiCert 签发的好证书。
- **为什么浏览器和 RAG 正常**：浏览器和部分客户端会**自动联网补全中间证书**（AIA fetching），
  而 Python(httpx)/Node/Go/curl/openssl 这类客户端**不会**，于是暴露了服务端缺链的问题。
- **正确修法**：服务端配置 **fullchain**（叶子 + 中间证书），一次性修复所有客户端。
- **次选**：客户端补中间证书（验证仍开启）。**最后手段**：跳过验证（仅内网临时用）。

---

## 一、关键概念

### 1.1 证书是「连接级」的，不是「路径级」的

HTTPS 请求顺序：

```
https://mcp.jptoe.com/your/api/xxx
        └──── 域名:443 ────┘ └─ 路径 ─┘
   ① 建立 TCP 连接 → ② TLS 握手 + 证书验证 → ③ 加密通道里才传路径和数据
```

- 证书验证发生在 **TLS 握手**阶段，**早于**任何 HTTP 路径的发送。
- 证书绑定的是**域名（host）**，覆盖该域名下所有路径。
- 因此：无论在 URL 后拼接什么路径，都走**同一道证书验证**，失败方式完全一样。
  握手过不去，路径根本没机会发出去。

### 1.2 「跳过证书验证」≠「不用 SSL / 改走 HTTP」

| 操作 | 端口 | 是否加密 | 是否校验证书 |
|------|------|---------|-------------|
| `https://host`（正常） | 443 | ✅ | ✅ |
| `https://host` + 跳过验证 | **443** | **✅ 仍加密** | ❌ |
| `http://host` | 80 | ❌ 明文 | — |

- **端口由 URL 决定**（`https://`→443，`http://`→80，或显式 `:端口`），**跟 verify 开关无关**。
- 跳过验证只关掉了「校验证书是否可信」这一步，**TLS 照样建立、数据照样加密、端口照样 443**。

### 1.3 AIA fetching（自动补中间证书）

当服务端漏发中间证书时，部分客户端会根据叶子证书里的 `Authority Information Access` 扩展，
**自动联网下载缺失的中间证书**，从而补全信任链。这是**底层 TLS 栈 / 操作系统**的能力，
**不是应用或 MCP 库本身的能力**。

---

## 二、排查流程（按顺序执行）

### 步骤 1：去掉静默、加超时、开详细日志

`curl -sI` 的 `-s` 会把错误一起静默掉，导致「没反应」。改用：

```bash
curl -v --connect-timeout 5 --max-time 10 -I https://mcp.jptoe.com
```

根据停在哪一步定位：

| 停/卡在哪 | 含义 |
|-----------|------|
| `Could not resolve host` | DNS 没解析出来 |
| 停在 `Trying <IP>...` 后超时 | TCP 连不上——443 没开放或被防火墙挡 |
| 卡在 `TLS handshake` | 端口通，但 HTTPS/证书有问题 |
| 正常打印 `HTTP/...` 状态码 | 其实是通的，只是被 `-s` 静默了 |

### 步骤 2：确认是「证书验证失败」而非「连不上」

典型错误输出：

```
* Connected to mcp.jptoe.com (10.111.71.77) port 443     ← 端口通了
* TLSv1.3 (IN), TLS handshake, Certificate (11):          ← 证书发过来了
* TLSv1.3 (OUT), TLS alert, unknown CA (560):
* SSL certificate problem: unable to get local issuer certificate
curl: (60) SSL certificate problem: unable to get local issuer certificate
```

含义：**连接和握手都正常，纯粹是客户端不信任 / 接不上这张证书的信任链。**

### 步骤 3：先确认服务本身正常（忽略证书）

```bash
curl -k -I https://mcp.jptoe.com
```

能返回状态码 → 服务完全正常，问题 100% 在证书信任，而非应用本身。

### 步骤 4：查看证书签发者和证书链张数（决定性）

```bash
echo | openssl s_client -connect mcp.jptoe.com:443 -servername mcp.jptoe.com -showcerts 2>/dev/null \
  | grep -E "^ *s:|^ *i:|Verify return"

# 只数服务端发了几张证书
echo | openssl s_client -connect mcp.jptoe.com:443 -servername mcp.jptoe.com -showcerts 2>/dev/null \
  | grep -c "BEGIN CERTIFICATE"
```

判读：

| 现象 | 结论 |
|------|------|
| `issuer` 与 `subject` 相同 | 自签名证书 |
| `issuer` 是内部机构名 | 私有 / 内部 CA |
| **`issuer` 是公共 CA（DigiCert 等）+ 只发 1 张证书 + `Verify return code: 21`** | **缺中间证书（本案例）** |
| `Verify return code: 0 (ok)` | 证书链正常 |

> **本案例实测**：两个服务（RAG 与 MCP）的 `issuer` 都是
> `C=US, O=DigiCert, Inc., CN=GeoTrust G2 TLS CN RSA4096 SHA256 2022 CA1`，
> 且都是 `Verify return code: 21 (unable to verify the first certificate)`。
> → 两个服务端**都**漏发了中间证书，只是 RAG 的调用方恰好能自动补链才"看起来正常"。

---

## 三、为什么「浏览器/RAG 正常，MCP 不正常」

服务端缺链是客观存在的，差别只在**不同客户端是否会自动补中间证书（AIA）**：

| 客户端 / 运行时 | 缺中间证书时是否能补 |
|----------------|---------------------|
| 浏览器（Chrome/Edge/Safari、Firefox 75+） | ✅ 会 AIA 抓取 |
| Windows 应用（Schannel/CryptoAPI） | ✅ 系统级自动补并缓存 |
| macOS 应用（Security.framework） | ✅ |
| Java（JSSE） | ⚠️ 默认**不会**，需 `-Dcom.sun.security.enableAIAcaIssuers=true` |
| .NET | Windows ✅ / Linux ❌ |
| **OpenSSL / curl（Linux）** | ❌ |
| **Python（requests/httpx/aiohttp）** | ❌（certifi 只含根证书） |
| **Node.js** | ❌ |
| **Go（crypto/tls，Linux）** | ❌ |
| **Rust（rustls）** | ❌ |

### MCP 各语言 SDK 的实际表现

AIA 能力取决于底层 TLS 栈，**MCP SDK 本身不提供**。Linux 上主流 SDK 基本都不会自动补链：

| MCP SDK | 底层栈 | 自动补中间证书 |
|---------|--------|---------------|
| Python SDK（`mcp`，httpx） | OpenSSL | ❌ |
| TypeScript/JS SDK（Node） | Node + OpenSSL/BoringSSL | ❌ |
| Go SDK | Go crypto/tls | ❌ |
| Rust SDK（`rmcp`，rustls） | rustls | ❌ |
| Java/Kotlin SDK | JSSE | ⚠️ 需开开关 |
| C#/.NET SDK | Schannel(Win)/OpenSSL(Linux) | Win ✅ / Linux ❌ |

**结论**：不要指望客户端自动补链，它不可移植、换客户端/换机器就挂。

---

## 四、解决方案（按推荐度排序）

### 方案 A：修服务端 fullchain ⭐ 首选（根治）

把「叶子证书 + 中间证书」拼成 fullchain，所有客户端一次性通。

1. 拿到中间证书 `GeoTrust G2 TLS CN RSA4096 SHA256 2022 CA1`（签发时一般附带 `chain.pem`，或从 DigiCert 官网下载）。
2. 拼接（**顺序：叶子在上，中间在下**）：
   ```bash
   cat your_domain.crt intermediate.crt > fullchain.crt
   ```
3. 服务端指向 fullchain：
   - **nginx**：`ssl_certificate /path/fullchain.crt;` → `nginx -s reload`
   - **应用自带 HTTPS**：证书文件换成 fullchain 后重启
4. 验证修复：
   ```bash
   echo | openssl s_client -connect mcp.jptoe.com:443 -servername mcp.jptoe.com 2>/dev/null | grep "Verify return"
   # 期望：Verify return code: 0 (ok)，且 -showcerts 数证书变成 2 张
   ```

> 建议 RAG 也一并补 fullchain，否则换个严格客户端同样会挂。

### 方案 B：客户端补中间证书（改不动服务端时的正解）

**验证保持开启**，只把缺失的中间证书提供给客户端：

- **Python (httpx/requests)**：把「中间证书 + 根」拼成 bundle，`verify="/path/bundle.pem"`
- **Node**：`NODE_EXTRA_CA_CERTS=/path/intermediate.pem`
- **Java**：`-Dcom.sun.security.enableAIAcaIssuers=true`，或 keytool 导入中间证书

### 方案 C：跳过证书验证 ⚠️ 仅内网临时应急

技术上可行，但**关掉的是对中间人攻击（MITM）的防护**：连接仍加密，但无法确认对端身份。
内网风险相对低但不为零（ARP 欺骗、被入侵节点、DNS 投毒）。

如确需临时使用，务必：

1. **做成配置开关，默认开启验证**（生产环境绝不能默认关）。
2. **只针对特定 host 关闭**，不要全局关
   （Node 不要设 `NODE_TLS_REJECT_UNAUTHORIZED=0`，Python 不要全局禁用——否则**所有**外部 HTTPS 调用都失去保护）。
3. 代码里留 `TODO` 注释，说明这是绕过"服务端缺中间证书"的临时措施。

> 注意：本项目代码会迁移到独立生产服务器，需按生产级标准编写。
> `verify=False` 跟随代码进生产是隐患，优先用方案 A / B。

---

## 五、速查命令

```bash
# 域名解析到哪个 IP（含 CNAME 链）
dig +short mcp.jptoe.com
dig mcp.jptoe.com CNAME

# IP 归属（判断是否 CDN / 云 LB）
whois <IP> | grep -iE "orgname|netname|descr"

# HTTPS 探活（带超时，看连接全过程）
curl -v --connect-timeout 5 --max-time 10 -I https://mcp.jptoe.com

# 忽略证书探活（确认服务本身正常）
curl -k -I https://mcp.jptoe.com

# 看证书签发者 / 链 / 验证结果
echo | openssl s_client -connect mcp.jptoe.com:443 -servername mcp.jptoe.com -showcerts 2>/dev/null \
  | grep -E "^ *s:|^ *i:|Verify return"

# 数服务端发了几张证书（1=缺链，≥2=完整）
echo | openssl s_client -connect mcp.jptoe.com:443 -servername mcp.jptoe.com -showcerts 2>/dev/null \
  | grep -c "BEGIN CERTIFICATE"

# 看证书有效期 / subject
echo | openssl s_client -connect mcp.jptoe.com:443 -servername mcp.jptoe.com 2>/dev/null \
  | openssl x509 -noout -subject -issuer -dates

# 单纯测 443 端口是否开放
timeout 5 bash -c "</dev/tcp/mcp.jptoe.com/443" && echo "443 通" || echo "443 不通"
```

---

## 六、错误码对照

| 错误 | 含义 | 通常原因 |
|------|------|---------|
| `unable to get local issuer certificate` | 找不到签发该证书的 CA | 缺中间证书 / 内部 CA 未信任 |
| openssl `Verify return code: 21` | 无法验证第一张证书 | **缺中间证书**（本案例） |
| openssl `Verify return code: 19` | 自签名证书在链中 | 自建 CA |
| openssl `Verify return code: 18` | 自签名证书 | 自签名 |
| `unknown CA` (TLS alert) | 客户端不信任对端 CA | 同上 |
| `Could not resolve host` | DNS 解析失败 | 域名未配解析 |
