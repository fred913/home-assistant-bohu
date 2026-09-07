# Bohu Air Quality · 伯虎空气质量

![Integration icon](custom_components/bohu/brand/icon.png)

将支持**自定义 HTTP 上传地址**的伯虎空气质量检测仪接入 Home Assistant。添加设备、复制专属 URL、填入检测仪，即可接收本地上报。不需要 MQTT、额外服务或刷固件。

目前适配型号：**伯虎智能 / 伯虎物联 BH6，支持自定义上传地址的 Wi-Fi 版本**。本项目按该设备实际上传的温度、湿度、HCHO、VOC、C6H6 报文实现；其他型号尚未验证。

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=fred913&repository=home-assistant-bohu&category=integration)

## 安装

需要 Home Assistant **2026.9.0 或更新版本**，支持 Home Assistant Container（Docker）及 Home Assistant OS。

### HACS

1. 打开 HACS，右上角菜单 → **自定义存储库 / Custom repositories**。
2. 添加 `https://github.com/fred913/home-assistant-bohu`，类型选择 **集成 / Integration**。
3. 下载 **Bohu Air Quality**，重启 Home Assistant。
4. 前往 **设置 → 设备与服务 → 添加集成**，搜索 **Bohu** 或 **伯虎**。

这是可通过 HACS 自定义仓库安装的集成，尚未收录进 HACS 默认仓库列表。

从 v0.1.1 起，HACS 使用 Release 附件 `bohu.zip` 安装，减少对 GitHub 源码归档下载的依赖。

### 手动安装

将仓库中的 `custom_components/bohu` 复制到 HA 配置目录的 `custom_components/bohu`，然后重启 HA。Docker 中的最终路径应是 `/config/custom_components/bohu/manifest.json`，不要额外嵌套一层文件夹。

也可下载 Release 中的 `bohu.zip`，将其内容解压到上述 `custom_components/bohu` 目录。

## 创建设备、复制 URL

1. 添加 **Bohu Air Quality** 集成，填写设备名称，例如“客厅”。
2. **HA 地址会自动填入**：优先使用 HA 的“设置 → 系统 → 网络 → Home Assistant URL”中的本地网络地址，未配置时使用已配置的互联网地址；两者都未配置时才尝试自动识别。通常直接保留即可，需要时也能手动修改。
3. 下一页会显示专属 URL。复制它并点击**提交**，提交后接收端才生效。
4. 把完整 URL 填入检测仪的自定义上传地址。收到第一条完整有效报文后，集成自动绑定其中的 `did`，并显示数值。
5. 以后在 **设置 → 设备与服务 → Bohu Air Quality → 对应设备的配置** 中，可再次复制 URL、修改气体单位、调整离线超时。

每次添加集成都会创建一个独立设备。不同设备使用不同 URL；同一个硬件 ID 不能重复绑定。URL 和绑定的 ID 会由 HA 保存，重启不变。更换物理设备时删除原集成条目再添加，会生成新 URL。删除设备后旧 URL 不再更新任何实体。

**BH6 的上传地址最多保存 63 字节，超长会被静默截断。** v0.1.1 使用 22 字符的 URL-safe 标识，保留 128 位随机性，并在创建或修改地址时校验总长度；域名太长时请使用服务器 IP。升级 v0.1.0 后现有设备会自动显示短 URL，设备实体、硬件 ID 绑定和历史保持不变，旧的完整 URL 也作为兼容入口继续有效。已经被检测仪截断的地址需要重新复制、保存。

自动填充使用 HA 中的实际配置，例如 `http://192.168.1.10:8123`，包括自定义端口。只有在 HA 没有配置 URL、退回自动识别时，Docker 内部 IP 才可能被填入；这种情况下请设置 HA 的本地网络地址或手动改为宿主机局域网 IP 和映射端口。地址必须能被检测仪访问。此字段仅用于生成可复制的 URL，不会改变 HA 自身的监听端口或网络配置；已有设备保留其上次保存的地址。

## 实体与单位

| 报文字段 | HA 实体 | 单位 |
| --- | --- | --- |
| `T` | 温度 | °C |
| `H` | 湿度 | % |
| `HCHO` | 甲醛 | mg/m³（默认） |
| `VOC` | TVOC | mg/m³（默认） |
| `C6H6` | 苯 | mg/m³（默认） |
| 接收时间 | 最后上报（诊断） | 时间戳 |

气体单位默认预填 **mg/m³**，与已核对的 BH6 屏幕上 HCHO、TVOC、C6H6 三项单位一致。若其他固件显示不同单位，可在设置中选择 `μg/m³`、`ppm`、`ppb` 或“未确认”。三项气体读数使用同一单位，数值原样保留，**选择单位不会换算数值**。该版本只适用于三项气体使用相同单位的设备。

默认 **300 秒**没有有效上报时，五个测量实体变为不可用。超时应大于检测仪的上报间隔，可在设置里调整为 10–86400 秒。无效报文不会更新数值，也不会推迟离线。下一条有效上报会恢复在线。离线时“最后上报”保留最近接收时间。

重启或设置重载后等待新报文，不把旧读数当作当前测量。历史记录由 HA 的 Recorder 管理。`WeatherType` 仅保留为“最后上报”实体的 `weather_type` 原始属性，尚未推断其枚举含义。

## Docker 与端口 9007

集成使用 HA 已有的 HTTP 服务，默认端口为 8123。如果已有 Docker 部署，按实际 HA 地址填写即可。需要使用宿主机的 9007 端口时，可使用 bridge 网络映射：

```yaml
services:
  homeassistant:
    image: ghcr.io/home-assistant/home-assistant:stable
    container_name: homeassistant
    restart: unless-stopped
    stop_grace_period: 60s
    environment:
      TZ: Asia/Shanghai
    volumes:
      - ./config:/config
    ports:
      - "8123:8123"
      - "9007:8123"
```

随后在集成里填 `http://宿主机局域网IP:9007`。两个宿主机端口映射的是同一个 HA 服务，9007 也能访问 HA 界面。使用 `network_mode: host` 时不要添加上述 `ports`，直接填写 HA 的实际监听端口。旧 HTTP 记录器占用 9007 时，需要先停止它或改用其他端口。

## 上报协议与兼容性

已根据一台伯虎 BH6（ESP8266 + ARM 双 MCU）的实际上传报文实现。尚未验证其他型号、其他固件版本或下行控制。设备必须支持完整 URL 的自定义上传；本集成不修改固件、不执行 OTA，也不验证传感器测量精度。

设备向生成的 `/api/webhook/<随机标识>` 发送 HTTP POST。它将 Content-Type 声明为 `application/x-www-form-urlencoded`，但正文实际是 JSON，因此本集成读取正文直接解析，不按表单处理。正确标注 `application/json` 的相同正文也可接收。

示例（设备 ID 已替换）：

```json
{"method":"update","did":"demo0001","WeatherType":"0","T":"23","H":"59","HCHO":"0.138","VOC":"0.283","C6H6":"0.043"}
```

`method` 必须为 `update`。`did` 必须为非空字母数字字符串，最长 128 字符；五项测量必须齐全且为有限数值或数值字符串。湿度范围为 0–100，气体浓度不能为负。可选 `WeatherType` 为字符串，未知扩展字段不影响解析。请求体最大 4096 字节。

有效上报返回 `200 OK`，正文 `OK\n`；无效报文返回 400，过大报文返回 413，设备 ID 不匹配或重复绑定返回 409。非 POST 请求不更新设备。HA 对不存在的 webhook 也可能返回 200，**单看状态码不能证明配置成功**，应确认实体数值或最后上报时间变化。

每个 URL 含随机 128 位标识，相当于该设备的上传凭据，请勿公开或放进日志截图。本集成不要求设备支持 Authorization 请求头。为兼容采用非标准私网地址的家庭 LAN/VPN，没有启用 HA 仅允许 RFC1918 来源的 webhook 限制；请将接收地址放在设备可访问的受控网络中。

## 常见问题

- **复制 URL 后无数据**：先完成配置流程，再检查设备到 HA 的路由、防火墙和 Docker 端口映射；浏览器打开 URL 不会产生测量。
- **设备不接受 HTTPS**：使用设备支持的局域网 HTTP 地址；本项目只实际捕获并验证了 HTTP 上报。
- **不知道气体单位**：已验证的 BH6 默认 mg/m³；若使用其他版本而尚未确认，可选择“未确认”，再检查设备屏幕或说明书。
- **离线反复出现**：把离线超时设为大于设备真实上报间隔的值。
- **换了 HA IP/端口**：修改集成里的 HA 地址，复制新 URL，同时更新检测仪上传配置。URL 随机标识保持不变。
- **卸载**：先在“设备与服务”删除相应条目，再从 HACS 移除集成。HA 管理的历史数据遵循 HA 自身保留策略。

## 开发与验证

集成没有额外运行时依赖。使用 Home Assistant 自带的 aiohttp、Voluptuous 和事件循环。

```sh
docker run --rm --entrypoint python \
  -v "$PWD:/repo:ro" -w /repo \
  ghcr.io/home-assistant/home-assistant:2026.9.1 \
  -m unittest discover -s tests -v
```

`.github/workflows/validate.yml` 运行协议测试、真实 HA HTTP/WebSocket 冒烟测试、HACS 校验和 hassfest。`tests/smoke.py` **仅供全新、名为 Bohu Test 的临时 HA 使用**，会创建测试管理员，验证创建设备、URL、首次绑定、多设备隔离、错误报文、超时恢复、重载、删除及重启。不要用于已部署的家庭 HA。

MIT License。社区项目，与伯虎厂商无隶属关系。

## English quick start

Add this public repository to HACS as an **Integration**, download it, and restart Home Assistant. Add **Bohu Air Quality** under Settings → Devices & services. Enter a device name and a Home Assistant URL reachable from the sensor. Copy the generated upload URL, submit the setup, and paste that URL into the sensor's custom upload setting. Configure opens the URL again and lets you select the confirmed gas unit and offline timeout. Each config entry represents one device and binds its hardware ID from the first valid report. No MQTT or firmware changes are required. Requires HA 2026.9.0+; tested with 2026.9.1.
