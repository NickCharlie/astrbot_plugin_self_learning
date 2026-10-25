# 远程服务器容器部署与 WebUI 连接指南

这份文档解决一个常见场景：**AstrBot 跑在远程服务器的 Docker 容器里，你人在本地，想打开 Self Learning 的管理界面**。内容覆盖端口映射、防火墙/安全组放行、密码策略，以及"打不开"时的逐段排查方法。

## 两种访问入口

| 入口 | 地址 | 端口 | 鉴权 | 适用场景 |
| --- | --- | --- | --- | --- |
| 内嵌插件页（推荐） | `http://服务器IP:6185` → 插件管理 → Self Learning → 插件页 | 6185（AstrBot 面板） | AstrBot 面板账号 | 只开一个端口就能用全部功能 |
| 独立 WebUI | `http://服务器IP:7833` | 7833（插件自带） | 免密（仅本机来源）或登录密码 | 功能预览/alpha 试验区，或不想经过 AstrBot 面板 |

内嵌插件页与独立 WebUI 功能基本对齐：黑话学习、表达学习、人格学习、影子模式、审查队列、学习内容、图谱、功能融合（世界书 / QQ 聊天记录 / MaiBot 导入）、监控与设置均可在内嵌页完成。独立 WebUI 保留为后续改动的 alpha 试验区，新能力会先在那里验证再同步过来。

## 端口速查表

| 端口 | 用途 | 是否必须暴露到公网 |
| --- | --- | --- |
| 6185 | AstrBot 管理面板（含内嵌插件页） | 需要远程访问时放行；建议限源 IP 或套反代/隧道 |
| 7833 | Self Learning 独立 WebUI | 非必须；更推荐 SSH 隧道访问 |
| 6186+ | 消息平台适配器（NapCat 等，按需） | 与本插件无关，按平台文档处理 |

## 第一步：容器部署

以官方镜像 `soulter/astrbot` 为例（详见 [AstrBot 官方 Docker 部署文档](https://github.com/AstrBotDevs/AstrBot/wiki/zh-deploy-astrbot-docker)）。

**docker run：**

```bash
docker run -d --name astrbot \
  -p 6185:6185 \
  -p 7833:7833 \
  -v ./astrbot_data:/AstrBot/data \
  soulter/astrbot
```

**docker-compose.yml：**

```yaml
services:
  astrbot:
    image: soulter/astrbot
    container_name: astrbot
    restart: unless-stopped
    ports:
      - "6185:6185"   # AstrBot 管理面板（内嵌插件页）
      - "7833:7833"   # Self Learning 独立 WebUI
    volumes:
      - ./astrbot_data:/AstrBot/data
```

要点：

- 插件安装在 `data/plugins/astrbot_plugin_self_learning`（挂载目录内），通过 AstrBot 面板的插件市场安装或手动放入均可。
- `-p 7833:7833` 只在想直接远程访问独立 WebUI 时需要；走 SSH 隧道可改为 `-p 127.0.0.1:7833:7833`（只绑宿主机回环，更安全）。
- **容器内配置陷阱**：独立 WebUI 默认 `web_interface_host=127.0.0.1`，只监听容器内回环。端口映射后从外部访问会直接连不上。在容器环境请把它改为 `0.0.0.0`（见下文[密码设置](#webui-密码设置)一节的配置位置）。

## 第二步：开放端口（防火墙/安全组）

远程访问需要**每一层都放行**，少一层都连不上。从外到内依次是：

1. 云厂商安全组（云服务器特有，最常被遗漏）
2. 服务器系统防火墙（ufw / firewalld / iptables）
3. Docker 端口映射（上一步的 `-p`）

### 云安全组（阿里云 / 腾讯云 / AWS 等）

在控制台找到实例的「安全组 / 防火墙规则」，添加入站规则：

| 协议 | 端口 | 来源 | 说明 |
| --- | --- | --- | --- |
| TCP | 6185 | 你的 IP/32（或 0.0.0.0/0） | AstrBot 面板 |
| TCP | 7833 | 你的 IP/32 | 独立 WebUI（若直接暴露） |

强烈建议「来源」填你自己的出口 IP 而不是全网开放。

### ufw（Ubuntu/Debian 常见）

```bash
sudo ufw allow 6185/tcp
sudo ufw allow 7833/tcp     # 仅当直接暴露独立 WebUI
sudo ufw status verbose
```

### firewalld（CentOS/Rocky 常见）

```bash
sudo firewall-cmd --permanent --add-port=6185/tcp
sudo firewall-cmd --permanent --add-port=7833/tcp
sudo firewall-cmd --reload
```

### iptables（通用兜底）

```bash
sudo iptables -I INPUT -p tcp --dport 6185 -j ACCEPT
sudo iptables -I INPUT -p tcp --dport 7833 -j ACCEPT
```

### ⚠️ Docker 会绕过 ufw

Docker 发布端口（`-p`）直接写 iptables 的 `DOCKER` 链，**不经过 ufw 规则**。也就是说 `ufw deny 7833` 拦不住已经 `-p 7833:7833` 映射出来的端口。处理方式二选一：

- 最简单：不映射公网端口，独立 WebUI 只绑宿主机回环 `-p 127.0.0.1:7833:7833`，用 SSH 隧道访问。
- 或使用 [ufw-docker](https://github.com/chaifeng/ufw-docker) 等方案让 ufw 接管 DOCKER 链。

## 第三步：访问

### 内嵌插件页（推荐）

浏览器打开 `http://服务器IP:6185`，登录 AstrBot 面板（首次默认账号/密码均为 `astrbot`，登录后请修改），进入「插件管理」→ 找到 Self Learning → 打开插件页。内嵌页通过 AstrBot 的登录态调用后端，不需要独立 WebUI 的密码，也不依赖 7833 端口。

### 独立 WebUI

浏览器打开 `http://服务器IP:7833`。注意免密模式的限制（见下节）：非本机来源的免密请求会被拒绝，直接用公网 IP 访问**必须先开启登录密码**。

## 更安全的访问姿势（不暴露公网端口）

### SSH 隧道（推荐，免密可直接用）

```bash
ssh -N -L 6185:127.0.0.1:6185 -L 7833:127.0.0.1:7833 user@你的服务器
```

保持该连接后，本地浏览器访问 `http://127.0.0.1:6185` 与 `http://127.0.0.1:7833` 即可。经隧道访问独立 WebUI 时，插件看到的来源是回环地址，**免密模式可直接使用**——这是远程使用免密 WebUI 的唯一推荐方式。此时容器端口可以只绑回环（`-p 127.0.0.1:7833:7833`），安全组也无需放行 7833。

### Nginx 反向代理 + HTTPS（需要开密码）

反代场景下请求来源是同机回环、但 `Host` 头是公网域名，免密校验不通过，**必须开启 WebUI 登录密码**。示例：

```nginx
server {
    listen 443 ssl;
    server_name astrbot.example.com;

    ssl_certificate     /etc/letsencrypt/live/astrbot.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/astrbot.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:6185;   # AstrBot 面板；独立 WebUI 换成 7833
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;   # 面板 WebSocket 必需
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

Caddy 用户等价配置（自动 HTTPS）：

```caddy
astrbot.example.com {
    reverse_proxy 127.0.0.1:6185
}
```

### frp / Tailscale 等内网穿透

原理相同：能形成"访问来源可信"的通道即可。穿透工具暴露的端口同样要注意套 TLS 和密码，不要裸奔公网。

## WebUI 密码设置

独立 WebUI 的密码在插件配置 `服务器与安全`（Server_Settings）组：

| 配置项 | 说明 |
| --- | --- |
| `enable_web_interface` | 独立 WebUI 总开关 |
| `web_interface_host` | 监听地址；**容器环境必须 `0.0.0.0`**，默认 `127.0.0.1` 只监听容器内回环，映射后无法访问 |
| `web_interface_port` | 默认 7833 |
| `enable_webui_password` | 开启后访问 WebUI 需登录密码 |
| `webui_initial_password` | 一次性初始密码；保存后写入哈希并清空，不回显 |

也可以用环境变量 `ASTRBOT_WEBUI_INITIAL_PASSWORD` 提供初始密码。免密模式的访问限制：只有"客户端来源为回环 **且** Host 头指向本机"的请求可用（SSH 隧道满足；公网/局域网直连、同机反代均不满足）。修改 host/port 后需重启插件。

## 常见问题排查

### 打不开/连接超时：三段式定位

逐段测试，在哪一段断掉问题就在哪一层：

```bash
# 1. 容器内：服务本身活着吗？
docker exec astrbot curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:7833/api/
docker exec astrbot curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:6185/

# 2. 宿主机：端口映射通了吗？
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:7833/
ss -lntp | grep -E "6185|7833"     # 确认监听 0.0.0.0 而非仅 127.0.0.1

# 3. 本地电脑：防火墙/安全组放行了吗？
curl -sS -m 5 http://服务器IP:7833/ || echo "被防火墙或安全组拦截"
```

第 1 段失败 → 服务未启动或监听地址不对（`web_interface_host` 是否为 `0.0.0.0`）；第 2 段失败 → 端口未映射（检查 `-p` / compose）；第 3 段失败 → 安全组或系统防火墙未放行。

### `docker: port is already allocated`

7833/6185 在宿主机上已被占用（可能是另一个容器或本机进程）。用 `ss -lntp | grep 7833` 找到占用者，或改映射端口：`-p 17833:7833` 后通过 17833 访问（容器内端口不变，`web_interface_port` 无需修改）。

### 7833 能连上但返回"仅允许本机调用"/拒绝访问

这是免密模式的本机限制在工作，不是故障。解决办法：开启 `enable_webui_password`，或改用 SSH 隧道访问。

### 内嵌页右上角"打开独立 WebUI"没反应/指向 127.0.0.1

内嵌页会把链接里的 `localhost/127.0.0.1` 主机名替换成你浏览器当前访问的主机（保留端口）。若仍打不开：

- 确认 7833 已映射并放行（见上文三段式排查）；
- 免密模式直连公网 IP 会被拒（见上一条），开密码或走隧道。

### 反代后面板一直转圈/实时日志不出

反代缺少 WebSocket 升级头。确认配置里包含 `proxy_set_header Upgrade $http_upgrade;` 和 `proxy_set_header Connection "upgrade";`（见上文 Nginx 示例）。

### HTTPS 站点里点开 http://IP:7833 被浏览器拦截

混合内容（mixed content）限制：HTTPS 页面不能加载 `http://` 资源。独立 WebUI 也走反代 + HTTPS，或单独开标签页直接访问。

### 修改了 compose 的 ports 但没生效

`docker compose up -d` 不会重建已有容器。执行 `docker compose up -d --force-recreate` 或先 `docker compose down` 再 up。

### IPv6 环境

若服务器只有 IPv6 公网地址，确认安全组规则同时覆盖 IPv6，且 `-p` 发布会同时绑定 v4/v6（Docker 默认双栈）。浏览器访问使用 `http://[IPv6地址]:6185` 格式。

## 安全建议清单

- 6185/7833 的安全组来源尽量限制为你的固定 IP，不要长期 0.0.0.0/0。
- 独立 WebUI 一旦对外（含反代），必须开启登录密码。
- 公网明文 HTTP 会暴露面板会话，优先反代 + HTTPS 或 SSH 隧道。
- 定期更新镜像与插件；AstrBot 面板默认密码 `astrbot/astrbot` 首次登录后立即修改。
