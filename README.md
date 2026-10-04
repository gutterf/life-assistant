# 生活助手 · LifeAssistant

iOS 生活助手 App（SwiftUI）+ FastAPI 后端。定位、问路、找店、拍图问答，结果以卡片形式在聊天界面中间弹出，不跳转任何外部 App。

```
iPhone (SwiftUI)                                     FastAPI 后端
┌──────────────────────────────┐                    ┌───────────────────────────┐
│ CoreLocation  ─ WGS-84 定位  │                    │  WGS-84 → GCJ-02 纠偏      │
│ CLGeocoder    ─ 逆地理地址   │   POST /api/v1/chat│         ↓                 │
│ SFSpeech      ─ 语音转文字   │ ──────────────────►│  DeepSeek 意图判定(json)   │
│ Vision        ─ 端上 OCR     │                    │    ↓        ↓        ↓     │
│ 相机 / 相册   ─ 图片压缩     │                    │  高德      高德     DeepSeek│
│ AVSpeech      ─ 语音播报     │                    │  路线      周边     常识/图片│
│ 卡片弹窗      ─ 中间浮层     │ ◄──────────────────│  拼装 Card+reply+speech    │
└──────────────────────────────┘   JSON 响应         └───────────────────────────┘
```

## 需求对照表

九项需求分别落在哪几个文件，以及怎么验证它确实生效：

| # | 需求 | 实现位置 | 验证方式 |
|---|---|---|---|
| 1 | CoreLocation 取 GPS + 逆地理编码 | `Core/LocationService.swift`（`CLLocationManager` + `CLGeocoder.reverseGeocodeLocation`）；后端 `amap.py: regeo()` 再补一次结构化地址 | 端上定位后地址出现在顶栏与用户气泡；后端侧 `S1 传给高德的是 GCJ-02` 断言 |
| 2 | 文字/语音提问，问题 + 经纬度上行 | `Views/ComposerBar.swift`、`Core/SpeechService.swift`（`SFSpeechRecognizer`）；`ViewModels/ChatViewModel.swift: send/sendImage`；`POST /api/v1/chat` | `S1`~`S5` 全部带 `location` 字段走通 |
| 3 | DeepSeek 判意图 → 高德路线 / 周边 | `deepseek.py: classify()`；`amap.py: route()/place_around()`；编排在 `orchestrator.py` | `S1` 周边、`S2` 公交、`S3` 步行、`S4` 驾车 |
| 3 | 周边 15km 内，返回名称/评分/距离 | `place_around()` 默认 `radius_m=15000`；`_to_place()` 取 `biz_ext.rating` 与 `distance` | `S1 半径传到高德=15000`、`S1 评分=4.6`、`S1 距离=320` |
| 3 | 生活常识直接由 DeepSeek 回答 | `deepseek.py: answer_knowledge()` + `_handle_knowledge()` | `S5` |
| 4 | 拍照上传 + OCR + 位置 → DeepSeek 分析 | `Core/ImagePicker.swift`、`Core/ImagePipeline.swift`（端上 Vision OCR）、`routers/upload.py`、`services/ocr.py`、`deepseek.py: analyze_image()` | `S7`（带端上 OCR）、`S8`（无 OCR 线索也不报错） |
| 5 | 卡片在聊天界面**中间弹窗**，不跳外部 App | `Views/Cards/CardStage.swift`（ZStack 浮层 + 毛玻璃遮罩 + 翻页） | 代码内不存在 `UIApplication.open` / `openInMaps` / URL Scheme；`cards[]` 契约由 `S1`~`S7` 断言 |
| 6 | 语音播报 | `SpeechService.speak()`（`AVSpeechSynthesizer`）、`Card.speech` 字段、顶栏喇叭开关 | 每个场景断言 `speech` 非空且含关键数字 |
| 7 | Key 只存在后端环境变量里 | `backend/app/config.py`（pydantic-settings 读 env/.env）；App 侧唯一配置项是后端地址 | `/health` 的 `configured`/`missing` 字段；`缺密钥时 /health 会自报缺失` 断言 |
| 8 | 定位/相机/相册/麦克风/语音识别五项权限 | `ios/LifeAssistant/Info.plist` 的五个 `NS*UsageDescription` | 权限申请时机：定位在启动、语音在首次点麦克风（避免一启动连弹三个授权框） |
| 9 | 完整结构 + 关键代码 + README | 本文件 + 下面的目录树 | `python tools/smoke_e2e.py` 一键复现全部链路 |

## 项目结构

```
life-assistant/
├── .github/workflows/build-ipa.yml   云端 macOS 编译，产出可侧载的未签名 IPA
├── backend/                          FastAPI 服务
│   ├── app/
│   │   ├── main.py                   应用入口、CORS、异常映射、/health
│   │   ├── config.py                 全部配置与密钥（pydantic-settings，读环境变量）
│   │   ├── schemas.py                接口契约（与 iOS Models.swift 一一对应）
│   │   ├── deps.py                   依赖注入
│   │   ├── routers/
│   │   │   ├── chat.py               POST /api/v1/chat
│   │   │   └── upload.py             POST /api/v1/analyze-image
│   │   └── services/
│   │       ├── coord.py              WGS-84 ↔ GCJ-02
│   │       ├── amap.py               高德：逆地理 / 地理编码 / 周边 / 三种路线
│   │       ├── deepseek.py           意图判定 / 常识问答 / 图片分析
│   │       ├── ocr.py                OCR provider 链（iOS Vision / RapidOCR / 百度）
│   │       └── orchestrator.py       编排：意图 → 查数据 → 卡片 + 话术
│   ├── tests/test_pipeline.py        单元/管线测试（13 项，已全绿）
│   ├── tools/
│   │   ├── mock_upstream.py          假的高德 + DeepSeek 上游，离线自测用
│   │   └── smoke_e2e.py              离线端到端冒烟（77 项断言，已全绿）
│   ├── requirements.txt
│   ├── .env.example                  复制成 .env 后填密钥
│   └── Dockerfile
└── ios/                              SwiftUI App
    ├── project.yml                   XcodeGen 配置（CI 与本地都靠它生成工程）
    ├── tools/make_icon.py            生成 1024x1024 App 图标
    └── LifeAssistant/
        ├── Info.plist                五项权限说明 + 调试期 ATS 例外
        ├── Assets.xcassets/          AppIcon + AccentColor
        ├── App/LifeAssistantApp.swift
        ├── Theme/Theme.swift         配色、字体、网格背景
        ├── Models/Models.swift       数据契约
        ├── Core/
        │   ├── LocationService.swift 定位 + 逆地理
        │   ├── SpeechService.swift   语音识别 + 语音播报
        │   ├── APIClient.swift       REST + multipart + /health 自检
        │   ├── ServerSettings.swift  后端地址存 UserDefaults，运行时可改
        │   ├── ImagePipeline.swift   压缩 + Vision OCR
        │   └── ImagePicker.swift     相机 / 相册
        ├── ViewModels/ChatViewModel.swift
        └── Views/
            ├── ChatView.swift        主界面（header / 消息流 / 输入栏 / 卡片舞台）
            ├── MessageBubble.swift   气泡
            ├── ComposerBar.swift     输入栏（含录音律动）
            ├── ServerSettingsSheet.swift  连接设置
            └── Cards/
                ├── CardStage.swift   中间弹窗舞台 + 翻页 + 类型路由
                ├── PlaceCardView.swift
                ├── RouteCardView.swift
                └── ImageAnalysisCardView.swift
```

## 快速开始

### 1. 申请两个 Key

DeepSeek：[platform.deepseek.com/api_keys](https://platform.deepseek.com/api_keys) → 创建 API Key。

高德：到 [console.amap.com/dev/key/app](https://console.amap.com/dev/key/app) 新建应用，**Key 类型必须选「Web 服务」**。选成「iOS 平台」会报 `INVALID_USER_KEY`——这是最常见的坑。

### 2. 起后端

```bash
cd backend
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                  # 填入 DEEPSEEK_API_KEY 与 AMAP_KEY
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

验证：

```bash
curl http://127.0.0.1:8000/health
# {"status":"ok","configured":true,"missing":[],"ocr_provider":"auto","default_radius_m":15000}

curl -X POST http://127.0.0.1:8000/api/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"text":"附近15公里有火锅店吗","session_id":"demo",
       "location":{"latitude":39.9087,"longitude":116.3975}}'
```

跑测试：

```bash
cd backend && python -m pytest tests -q
# 13 passed
```

> 若本机装了 xonsh，pytest 会在加载其插件时崩（`NoConsoleScreenBufferError`）。
> 加 `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` 或 `-p no:xonsh` 即可，与本项目无关。

跑离线端到端冒烟（**不需要任何真实 Key，也不联网**）：

```bash
cd backend && python tools/smoke_e2e.py
# 离线端到端自测：77/77 项通过
```

它做的事：起一个假的高德 + DeepSeek 上游（`tools/mock_upstream.py`），再起**真的** `uvicorn app.main:app`，
把两个 `base_url` 指过去，然后用真实 HTTP 跑完「意图判定 → 高德路线/周边 → OCR → DeepSeek → 卡片契约」。
与 `pytest` 的区别是它**不打桩任何客户端代码**——`AMapClient`、`DeepSeekClient`、`OCRService` 都是原样跑，
所以高德响应的字段解析、DeepSeek 的 JSON 解析、FastAPI 的序列化全都被真正执行了一遍。

自己改完代码想确认「没改坏」，跑这一条最划算。

### 3. 跑 iOS App

**方式 A：XcodeGUI**

1. Xcode 16+ → File → New → Project → iOS App，Product Name 填 `LifeAssistant`，Interface 选 **SwiftUI**，Language 选 **Swift**。
2. 删掉模板生成的 `ContentView.swift` 与 `<AppName>App.swift`，把 `ios/LifeAssistant/` 下所有内容拖进项目（勾选 *Copy items if needed*，Create groups）。
3. 选中 Target → General → Minimum Deployments 设成 **iOS 18.0**。
4. Target → Info → 把 `ios/LifeAssistant/Info.plist` 里的键逐条加进去（或直接删掉 Xcode 自动生成的 Info.plist，在 Build Settings 里把 `INFOPLIST_FILE` 指向本项目那份，并把 `GENERATE_INFOPLIST_FILE` 设为 `NO`）。
5. 后端地址**不用改代码**：装好 App 后点右上角信号图标填写即可。模拟器用默认的 `http://127.0.0.1:8000` 就行。
6. 选 iPhone 16 Pro Max 模拟器，Cmd+R。

**方式 B：XcodeGen**（已装 `brew install xcodegen` 时）

```bash
cd ios && xcodegen generate && open LifeAssistant.xcodeproj
```

App 图标由脚本生成，想换配色改 `tools/make_icon.py` 顶部的 `TOP`/`BOTTOM` 后重跑：

```bash
cd ios && python tools/make_icon.py
```

## 装进手机

iOS 的签名链决定了 App 必须在 macOS 上编译，而你在 Windows 上——这是唯一的摩擦点。三条路，按你有没有 Mac 选：

### 路径 A：手边有 Mac（约 20 分钟，最省事）

1. Mac 上从 App Store 装 Xcode 16+（约 10 GB）。
2. 把 `life-assistant/` 拷过去，`cd backend` 起后端（见上一节）。
3. `cd ios && xcodegen generate && open LifeAssistant.xcodeproj`（没装 XcodeGen 就按方式 A 手动建工程）。
4. Xcode 里选中 Target → **Signing & Capabilities** → 勾 *Automatically manage signing* → Team 选你的 Apple ID。没有就 *Add an Account* 登录，免费个人团队够用。
5. 把 Bundle Identifier 改成没人用过的值，例如 `com.yourname.lifeassistant`。
6. iPhone 用数据线连 Mac，Xcode 顶部设备选择器里选中它，Cmd+R。
7. 手机会弹「不受信任的开发者」——**设置 → 隐私与安全性 → 开发者模式 → 打开 → 重启**（iOS 16 起强制要求，很多人卡在这一步）。
8. **设置 → 通用 → VPN与设备管理** → 点你的 Apple ID → 信任。

免费 Apple ID 的限制：证书 **7 天失效**、同时最多 **3 个**自签 App。过期后重新 Cmd+R 一次即可，数据不会丢。

### 路径 B：纯 Windows —— 云端编译 + 爱思助手（本项目已走通）

**公开仓库的 macOS runner 免费**，这是 Windows 用户唯一全自助的路。首次约 40 分钟。

1. GitHub 建一个 **public** 仓库，把 `life-assistant/` 里的内容推到仓库根目录（`.github/` 必须在根）。
   仓库已经建好在 [gutterf/life-assistant](https://github.com/gutterf/life-assistant)，后续只要 push 就会自动编。
2. 等 5–8 分钟（push 会自动触发；也可以进 Actions 页手动 *Run workflow*）。
3. 双击仓库根目录的 `推送并取ipa.bat`：提交推送 → 盯 Actions → 把 ipa 下到桌面 `生活助手.ipa`。
   - 产出的是**未签名** IPA，由爱思助手用你的 Apple ID 现场签名，不需要开发者账号。
4. iPhone 连电脑。
   - 爱思助手自带 Apple 驱动；若它认不到手机，再装 [iTunes](https://www.apple.com/itunes/download/win64)（**只为驱动**，装完不用打开）。
5. 打开**爱思助手** → 拖入桌面的 `生活助手.ipa` → 用 Apple ID 签名安装。
6. 手机上要走**开发者模式 + 信任证书**两步（见路径 A 的 7、8）。

之后每次改代码，双击一次 `.bat`，约 8 分钟出新包。

### 一键脚本与产物自检

仓库根目录的 `推送并取ipa.bat` 做三件事：提交推送 → 盯 Actions → 把 ipa 下到桌面 `生活助手.ipa`。
双击即可，**不需要配 token**（脚本会自动问 git 要它已经在用的那个凭据）。

只想等构建、不下包：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\poll-build.ps1
```

拿到 ipa 后先自检一遍再装，避免"装到一半报签名错"：

```powershell
cd ios && python tools\verify_ipa.py "$env:USERPROFILE\Desktop\生活助手.ipa" --expect-permissions
```

它会打开包核实：Payload 结构、arm64 真机架构、MinimumOSVersion、五项权限说明、ATS 明文 HTTP 开关，以及
**有没有残留的 `_CodeSignature` / `embedded.mobileprovision`**（这两样是爱思助手重签失败最常见的原因）。

### 这台 Windows 机器上的四个坑（都已在脚本里绕开）

| 现象 | 原因 | 脚本里的处理 |
|---|---|---|
| `git push` 报 `schannel: SEC_E_WRONG_PRINCIPAL` | 全局配置把 `https://github.com/` 用 `insteadOf` 重写成了 `ghproxy.net`，那是只读加速站，证书也不匹配 | push 时用一份空配置顶掉全局配置（**不改动你的全局配置**） |
| 下载 artifact 报 `The remote name could not be resolved` | 路由器 DNS 解析 `*.blob.core.windows.net` 直接超时；公共 DNS 可以 | 用公共 DNS 解析出 IP，再 `curl --resolve` 直连（SNI 与证书仍按域名校验） |
| 手工两跳取 artifact 报 `403` | artifact 的签名地址只活很短时间，先取 Location 再单独下就已失效 | 让 curl 带 token 一路跟随重定向（跨域时 curl 会自动丢掉 Authorization，正是需要的行为） |
| `.ps1` 一跑就报 `字符串缺少终止符` | Windows PowerShell 5.1 把无 BOM 的 UTF-8 当 GBK 读，中文注释把字符串截断了 | `scripts/poll-build.ps1` 存为 **UTF-8 with BOM**；改完脚本别丢 BOM |

### 路径 C：租云 Mac

[MacinCloud](https://www.macincloud.com) / MacStadium 按小时计费（约 $1–2/小时），远程桌面进去就是路径 A 的操作，一小时能跑完。适合不想把代码推公开仓库的情况。

### 打通网络（决定成败的一步）

后端在电脑上，App 在手机上，两者必须能互相找到：

1. 后端必须监听所有网卡，光绑 127.0.0.1 手机是连不上的：

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

2. 查电脑的局域网 IP：

```powershell
(Get-NetIPAddress -AddressFamily IPv4 |
  Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' }).IPAddress
```

3. 先确认防火墙是不是开着的，**三个配置文件都关着就不用加规则**（本机就是这种情况）：

```powershell
Get-NetFirewallProfile | Select-Object Name, Enabled
# 有任意一个 Enabled=True 才需要下面这条（需要管理员权限）
New-NetFirewallRule -DisplayName "LifeAssistant Backend 8000" `
  -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Private
```

4. 手机和电脑连**同一个 Wi-Fi**。注意路由器的「访客网络」通常做了设备隔离，连上会互相 ping 不通。
5. **先用手机浏览器开一次** `http://电脑IP:8000/health`。能看到 JSON 就说明网络通了，再进 App 填地址——这一步能把「网络不通」和「App 配置错」分开，省很多时间。
6. 打开 App → 右上角信号图标 → 填 `192.168.x.x:8000` → 保存并测试连接。

这一步做完，以后换 Wi-Fi、改端口都只要在 App 里改地址，**不用重新编译**。

### 卡点速查

| 现象 | 原因 | 处理 |
|---|---|---|
| 装完点开闪退，或提示「未受信任的开发者」 | 证书没信任 | 设置 → 通用 → VPN与设备管理 → 信任 |
| 提示「无法安装此 App」 | 没开开发者模式 | 设置 → 隐私与安全性 → 开发者模式 → 开 → 重启手机 |
| 装完 7 天后打不开 | 免费证书过期 | 重新侧载一次 |
| 一直转圈 / 「网络连接失败」 | 地址还是默认的 `127.0.0.1`（指向手机自己） | App 内连接设置改成电脑的局域网 IP |
| 地址填对了仍连不上 | Windows 防火墙拦了 8000 | 加放行规则（见上） |
| 手机浏览器能开 `http://电脑IP:8000/health`，App 连不上 | ATS 拦截明文 HTTP | 本项目调试期已设 `NSAllowsArbitraryLoads`，确认没被改回去 |
| Sideloadly 找不到设备 | 缺 Apple 驱动 | 装 Apple 官网版 iTunes |
| 侧载报「Maximum number of apps」 | 免费账号同时只能装 3 个自签 App | 先删掉其他自签 App |

## 接口契约

### `POST /api/v1/chat`

```jsonc
// 请求
{
  "text": "附近15公里有什么火锅店",     // 必填
  "location": { "latitude": 39.9087, "longitude": 116.3975, "accuracy_m": 12.5 },
  "address": "北京市东城区…",          // 可选，客户端逆地理结果，省一次后端调用
  "citycode": "010",                  // 可选
  "session_id": "uuid",
  "context_hint": "川渝火锅、老北京炸酱面"  // 可选，供「去第一个」这类指代消解
}
```

```jsonc
// 响应
{
  "session_id": "uuid",
  "intent": "nearby",                 // route | nearby | image | knowledge | unknown
  "reply": "以**北京市东城区**为中心，15 公里内找到 20 家火锅店。…",  // 渲染进气泡
  "cards": [{
    "type": "place_list",             // place_list | route | image_analysis | text
    "title": "火锅 · 附近结果",
    "subtitle": "半径 15 公里 · 共 20 家",
    "speech": "15 公里内找到 20 家。第1家，…",   // 语音播报文本
    "places": [
      { "name": "川渝火锅", "rating": 4.9, "distance_m": 1450,
        "address": "东城区王府井大街", "phone": "010-…", "category": "餐饮服务" }
    ],
    "routes": [], "image": null, "text": null
  }],
  "speech": "…",
  "meta": { "intent": {...}, "location": {...}, "radius_m": 15000, "result_count": 20 }
}
```

路线类卡片在 `cards[].routes[]` 里返回 `mode / totalDistanceM / totalDurationS / transferCount / costYuan / legs[]`；图片类在 `cards[].image` 里返回 `ocrText / analysis / tags / confidence`。

### `POST /api/v1/analyze-image`

`multipart/form-data`：`file`（必填）、`question`、`ocr_text`（iOS Vision 预识别结果）、`latitude`、`longitude`、`accuracy_m`、`address`、`citycode`、`session_id`。

### `GET /health`

`{status, configured, missing, ocr_provider, default_radius_m}`

## 关键工程决策

**坐标系必须转换。** CoreLocation 给的是 WGS-84，高德用的是 GCJ-02。不做转换，北京地区会差约 500 米（`tests/test_pipeline.py::test_coord_roundtrip_and_offset` 里有实测断言）。转换放在后端 `coord.py` 统一处理，客户端只传原始坐标，避免两套转换互相打架。

**图片不是「丢给 DeepSeek」。** DeepSeek 官方 API 目前只有纯文本模型（`deepseek-chat` / `deepseek-reasoner`），没有视觉输入。所以图片路径是：**OCR 提取文字 → 连同位置、用户提问一起交给 deepseek-chat 分析**。OCR 走三级降级链——iOS 端的 Vision 框架优先（免费、离线、中文准确率高，`VNRecognizeTextRequest`），其次服务端 RapidOCR（本地 ONNX 推理），最后可选百度云 OCR。哪一级都不可用时，后端仍会基于位置给出有限回答，而不是报错。

**自然语言回复用模板拼，不二次调用大模型。** 距离、耗时、评分这些数字必须与高德返回值严格一致；让模型复述一遍只会引入错数，还多 1–2 秒延迟。模型只用在三处不可替代的地方：意图判定、常识问答、图片分析。

**高德 `keywords` 与 `types` 是 AND 关系。** 同时传会大幅收窄结果，代码里强制二选一（`amap.py: place_around`）。

**高德公交方案的 `cost` 是票价（元），`duration` 才是耗时（秒）。** 这是最容易望文生义搞错的一处：字段名 `cost` 看着像耗时，实际是票价，而票价在别的接口里叫 `tolls`。写错的表现很隐蔽——耗时显示成「约 1 分钟」、票价永远是空。现在 `_transit()` 按 [官方 AMapTransit 定义](https://a.amap.com/lbs/static/unzip/iOS_Map_Doc/AMap_iOS_API_Doc_3D%E5%9C%B0%E5%9B%BE&%E6%90%9C%E7%B4%A2/interface_a_map_transit.html) 取值，并有 `test_transit_field_semantics` 钉住；iOS 侧 `RouteCardView` 也按出行方式把同一个 `cost_yuan` 显示成「票价 / 过路费」。

**公交接口只展开最优方案。** 高德会返回多个候选，早先的实现把三个方案的 `segments` 灌进同一个列表，总里程虚高约三倍。现在只展开 `transits[0]`，总里程优先取方案自带的 `distance`。

**`re.findall` 遇到捕获组只返回组内容。** `_extract_tags` 的正则里货币分支原来写成 `(￥|¥|\$)`，导致其他分支的匹配全部返回空串、被过滤掉，图片卡片的「结构化线索」永远是空列表。改成非捕获组 `(?:...)`，并由 `test_extract_tags_survives_regex_groups` 守住。

**真机连不上后端**多半是两个原因：后端只绑了 `127.0.0.1`（要 `--host 0.0.0.0`），以及 ATS 拦截明文 HTTP（要在 `Info.plist` 加 `NSExceptionDomains`）。

**「不跳转外部 App」是硬约束。** 全程只调高德 Web 服务 API 拿数据，代码里没有 `UIApplication.open`、没有 `MKMapItem.openInMaps`、没有 URL Scheme 唤起高德/百度地图。所有结果都在 `CardStage` 这个居中浮层里呈现。

**卡片弹窗不用 sheet。** iOS 的 `sheet` 会从底部升起并占据半个屏幕，与「在聊天界面中间弹出」的要求不符。`CardStage` 是 `ZStack` 里的一个浮层：毛玻璃遮罩 + 居中纸张卡片 + 点遮罩/手势关闭，多张结果时左右滑动切换。

**密钥全在后端。** iOS 侧唯一的配置项是后端地址（`Core/ServerSettings.swift`，存在 UserDefaults），App 二进制里不存在任何第三方 Key。

**Swift 语言模式定为 5.0。** 代码是按 Swift 6 的并发语义写的（`@MainActor`、delegate 标 `nonisolated` 后跳回主 actor、跨隔离只传值类型），但 `SWIFT_VERSION` 停在 `5.0`：`AVAudioEngine.installTap`、`SFSpeechRecognizer.recognitionTask`、`VNImageRequestHandler` 这几处的回调在 SDK 里都没标 `@Sendable`，开 Swift 6 严格并发会因「跨 actor 传递非 Sendable 类型」直接报错。想开就把 `ios/project.yml` 里的 `SWIFT_VERSION` 改成 `"6.0"`，然后给那三处补标注。

## 已验证 / 未验证

已验证（全部为实际执行输出）：

**后端（本机 Windows + Python 3.12.10）**

- `python -m pytest tests -q` → **13 passed**。覆盖：坐标系往返与偏移量、周边搜索确实传 GCJ-02、路线卡片字段、**公交 cost/duration 字段语义**、**OCR 标签正则**、无定位时的引导、图片意图无图时的引导、高德故障降级、图片上传的 OCR 优先链、超大文件 413、非图片类型 415、`/health` 与 OpenAPI 契约。
- `python tools/smoke_e2e.py` → **77/77 项通过**。真 uvicorn + 真 HTTP + 假上游，不打桩任何客户端代码；断言覆盖高德四个接口的参数与响应解析、DeepSeek 意图 JSON 解析、四类卡片的字段契约、语音播报文本、三种降级路径。
- **真实 DeepSeek 调用已跑通**（用本机凭据库里的 key）：`POST /api/v1/chat` 问「煮鸡蛋要几分钟」→ 2288 ms 返回 `intent=knowledge`，回答是准确的分档时间，「播报」文本同步生成。意图判定与常识问答这两条最不可替代的链路，走的是真 API。
- 真实 `uvicorn app.main:app --host 0.0.0.0` 启动，`127.0.0.1:8000` 与局域网 `192.168.10.106:8000` 都返回 200，`/api/v1/chat`、`/api/v1/analyze-image` 均在 OpenAPI paths 中。

**iOS（GitHub Actions，macOS runner，Xcode 26.3 / iPhoneOS 26.2 SDK）**

- **代码已真实编译通过**（run #2 `success`）。首次编译报了 2 个错，都已修：`ImagePicker` 的 PHPicker 回调闭包引用属性缺显式 `self`；`LocationService` 用了不存在的 `CLLocation.age`（改用 `timestamp` 算新鲜度）。另把 `ImagePipeline` 的 `import Vision` 改成 `@preconcurrency import`，消掉 3 条 Sendable 警告。**现在整个 target 零错误、零警告。**
- **IPA 已产出并逐项校验**：`ios/tools/verify_ipa.py` 打开包核实 → Payload 结构 ✓、`arm64` 真机架构 ✓、`MinimumOSVersion 18.0` ✓、五项权限说明齐全 ✓、ATS 允许明文 HTTP ✓、**无残留 `_CodeSignature` / `embedded.mobileprovision`** ✓（可直接交爱思助手重签）。
- 从 push 到拿到可安装 IPA 的全流程走通，含这台机器特有的四个坑（见「一键脚本与产物自检」一节）。

未验证 —— 下面是必须在真机上确认的部分，不要当成已完成：

- **尚未真正装到手机上**。IPA 已就绪并校验通过，但签名与安装要用你的 Apple ID 在爱思助手里完成，这一步需要人工操作。
- **高德的两条链路（路线规划 / 周边搜索）没跑过真实 API** —— 没有可用 key。已有的 77 项断言验证的是「参数怎么传、响应怎么解析」，用的是本地假上游；真实 key 的坑主要是类型必须选「Web 服务」，否则报 `INVALID_USER_KEY`。
- **真机上的 CoreLocation / 相机 / 相册 / 麦克风 / 语音识别权限流程没跑过**，只在代码层做了时机控制（定位在启动、语音在首次点麦克风）。iOS 的权限弹窗在模拟器与真机上表现不完全一致，建议首次真机运行时逐个点一遍。
- **Bundle Identifier 目前是 `com.example.lifeassistant`**。侧载能用，但如果你想避免与别人重名，改 `ios/project.yml` 里的 `PRODUCT_BUNDLE_IDENTIFIER` 后重跑一次 `.bat` 即可。

## 上线前清单

- 后端换 HTTPS 域名；然后把 `Info.plist` 里的 `NSAllowsArbitraryLoads` 换成精确的 `NSExceptionDomains`（文件里已写好注释模板），App Store 审核对全放开明文 HTTP 是会追问的
- 后端加鉴权（现在任何人拿到地址都能消耗你的 DeepSeek 与高德额度）：建议在 `deps.py` 加一个校验 `Authorization` 头的依赖，并在 App 侧配 DeviceCheck 或简单 Token
- 高德按量计费，`place_around` 单次最多返回 25 条，注意 `DAILY_QUERY_OVER_LIMIT`
- DeepSeek 侧的频率与并发限制：`orchestrator` 已有一次退避重试，高并发场景建议在网关层限流
- 若在中国大陆分发，语音识别与位置权限的用途说明需与实际行为一致（本项目的 `Info.plist` 已按此撰写）
