# think-zh 安装手册（智能体执行版）

> **执行者**：AI 智能体。按步骤顺序执行。每步含【命令】【验证】【失败处理】。
> 全部步骤完成后执行「最终验收」，通过即安装完成，向用户报告。
> 约定：`<TZ>` = 本包解压根目录（含 app\ llama\ models\ 的那一层）。
> **本手册全部命令均为 PowerShell 语法**（Windows PowerShell 5.1+ 或 pwsh 7+；**不要在 cmd 里执行**——
> `cd /d`、`copy /y`、`set X=`、`start "" /min` 都是 cmd 语法，PowerShell 下无效）。
> 动手前先固定根目录变量，之后所有命令直接可用：
>
> ```powershell
> $TZ = "D:\tools\think-zh"   # ← 换成实际解压根目录
> ```

## 大件清单（先看清要下载什么，再动手）

| 大件 | 大小 | 必须？ | 获取处 |
|---|---|---|---|
| llama.cpp 引擎（exe + CUDA DLL） | ~1.7 GB | ✅ 必须 | GitHub `ggerganov/llama.cpp` Releases（win-cuda 包）——第 2 步 |
| 1.8B 翻译模型 GGUF | ~1.4 GB | ✅ 必须（实时层唯一模型） | HuggingFace `Hunyuan-MT GGUF`——第 3 步 |
| 7B 校正模型 GGUF | ~4.4 GB | ⭕ 可选（仅空闲挖矿层，默认停用，不装不影响主功能） | HuggingFace `Hunyuan-MT 7B GGUF`——第 3b 步 |

> 引擎与模型**不随包分发**（第三方公共品，许可见文末）。全部装完磁盘占用 ≈ **3.2 GB**（含 7B 则 ~7.6 GB）。

## 第 0 步：环境探测（先做，任何一条不过先解决再继续）

**平台硬前提（本项目按此交付，不满足则无法安装）**：
- Windows 10/11 x64（引擎与 CUDA DLL 均为 win-cuda x64 版）
- NVIDIA GPU：空闲显存 ≥ 3000 MiB，驱动支持 CUDA 12.4+（`nvidia-smi` 能正常出表）
- 无 N 卡没有官方回退路径（本项目不含 CPU 版引擎），请先解决硬件再继续

【命令】逐条运行并记录（PowerShell）：

```powershell
python --version
nvidia-smi --query-gpu=name,memory.free --format=csv
Get-NetTCPConnection -LocalPort 18765,8199 -ErrorAction SilentlyContinue   # 无输出 = 两端口空闲
```

【判据】
- Python ≥ 3.10
- 存在 NVIDIA GPU 且空闲显存 ≥ 3000 MiB
- 18765 与 8199 端口均未被占用
- 目标盘剩余空间 ≥ 10 GB（大件见上方清单）

【失败处理】
- 显存不足 → 提醒用户关闭大显存程序，或后续第 6 步改用 `-np 2`
- 端口被占 → 记下占用端口，第 6 步前修改 `app\watcher_service.py` 顶部 `PORT` / `MPORT`

## 第 1 步：安装 Python 依赖（唯一第三方库）

【命令】
```
pip install zstandard
```
【验证】`python -c "import zstandard; print(zstandard.__version__)"` 输出版本号
【失败处理】网络问题则 `pip install zstandard -i https://pypi.tuna.tsinghua.edu.cn/simple`

## 第 2 步：引擎 llama-server

若 `$TZ\llama\llama-server.exe` 已存在则跳过。否则先建目录，再下载：

```powershell
New-Item -ItemType Directory -Force "$TZ\llama" | Out-Null
```

【命令】下载 llama.cpp Windows CUDA 发行版（GitHub `ggerganov/llama.cpp` Releases，
选 `llama-<ver>-bin-win-cuda-x64.zip`，**另需配套 `cudart-llama-bin-win-cuda-12.4-x64.zip`**；
实际版本示例：`llama-b10665-bin-win-cuda-12.4-x64.zip`），解压后把 `llama-server.exe` 与同目录 CUDA DLL
（cudart64*.dll、cublas*.dll）放入 `$TZ\llama\`

直连与镜像 URL（把 `<ver>` 换成实际版本号）：

```
官方直连：https://github.com/ggerganov/llama.cpp/releases/download/<ver>/llama-<ver>-bin-win-cuda-12.4-x64.zip
镜像加速：https://ghfast.top/https://github.com/ggerganov/llama.cpp/releases/download/<ver>/llama-<ver>-bin-win-cuda-12.4-x64.zip
```

【验证】`& "$TZ\llama\llama-server.exe" --version` 输出版本号
【失败处理】无 N 卡驱动报错 → 先装 NVIDIA 驱动；GitHub 直连慢/失败 → URL 前加 `https://ghfast.top/` 前缀，或让用户手动下载后放入

## 第 3 步：翻译模型（实时层必需，不装则系统无法翻译）

若 `$TZ\models\Hy-MT2-1.8B-Q6_K.gguf` 已存在则跳过。否则先建目录：

```powershell
New-Item -ItemType Directory -Force "$TZ\models" | Out-Null
```

【获取路径，按序尝试】
1. HuggingFace 搜 `Hunyuan-MT GGUF`——腾讯混元翻译模型（官方仓库 `tencent/Hunyuan-MT-1.8B`
   为 safetensors；GGUF 用社区量化版），挑 1.8B 的 Q4_K_M 或 Q6_K（~1.2~1.5GB）
2. HF 直连慢 → 域名换成镜像，路径不变：
   `https://huggingface.co/<仓库>/resolve/main/<文件名>` → `https://hf-mirror.com/<仓库>/resolve/main/<文件名>`
3. 实在没有 GGUF → 下载官方 safetensors 后用 llama.cpp 的 `convert_hf_to_gguf.py` 转换（进阶）

【命令】下载后重命名放入：`$TZ\models\Hy-MT2-1.8B-Q6_K.gguf`
【验证】`(Get-Item "$TZ\models\Hy-MT2-1.8B-Q6_K.gguf").Length -gt 1000000000` 输出 True
【说明】文件名与下载所得不一致时，同步修改 `watcher_service.py` 顶部 `MODEL_18B`
常量（或设环境变量 `TZ_MODEL_18B`），否则第 5 步模型起不来。

## 第 3b 步：7B 校正模型（完全可选，可跳过）

- **用途**：仅服务「空闲挖矿校正层」——用户离开电脑时用 7B 免费提质存量译文
- **不装的影响**：主功能（实时翻译 / 库命中 / DeepSeek 精修层）**完全不受影响**
- 【命令】HuggingFace 搜 `Hunyuan-MT 7B GGUF`（Q4_K_M，~4.4GB；直连慢用 `hf-mirror.com` 同路径）→ 放入
  `$TZ\models\Hy-MT2-7B-Q4_K_M.gguf`（文件名不同则改环境变量 `TZ_MODEL_7B`）
- 默认挖矿停用（`app\out\mining.off` 存在）；装好模型后想启用挖矿，删除该文件即可

## 第 4 步：导入种子库（强烈建议，跳过则空库起步）

【命令】
```powershell
New-Item -ItemType Directory -Force "$TZ\app\cache" | Out-Null
Copy-Item "$TZ\app\seed\tm-share.sqlite3" "$TZ\app\cache\tm.sqlite3" -Force
```
【验证】`$TZ\app\cache\tm.sqlite3` 存在且 ≈ 25.4 MB
【说明】该库含 75,353 句已精修译文（已剔敏）。导入后新推理句子大量直接命中。

## 第 5 步：启动观察器（常驻）

【命令】先后台自检一次（前台 30 秒看日志）：
```powershell
Set-Location "$TZ\app"
python -X utf8 -u watcher_service.py
```
日志应依次出现：`[tm] 规范索引构建: N 条` → `[http] http://127.0.0.1:18765 ...`
确认无异常后 Ctrl+C，改用生产模式（分离进程 + 隐藏窗口，随系统会话常驻）：

```powershell
Start-Process python -ArgumentList '-X','utf8','-u','watcher_service.py' -WorkingDirectory "$TZ\app" -WindowStyle Hidden
```

【验证】`(Invoke-RestMethod http://127.0.0.1:18765/api/stats).model_up` 为 `True`（首次加载模型需 10~30 秒，可轮询等待）
【失败处理】
- `model_up: false` → 检查第 2/3 步路径；显存不足则编辑 `watcher_service.py` 将 `-np 4` 改 `-np 2` 后重启
- 端口冲突 → 改 `PORT`/`MPORT` 常量后重启（后续步骤同步改端口）

## 第 6 步：显示层插件（仅 DSH 用户需要；其他工具跳到「通用接入」）

【命令】
```
npm i dsh-think-translate
```
> 插件中心标准方式亦可：`dsh plugin --profile desktop add dsh-think-translate`（无论哪种方式，装完都需要下面的 config.json 补丁——原版默认连 Ollama）。

编辑 DSH 桌面 profile 的 `package.json`，`dependencies` 加 `"dsh-think-translate": "^1.0.10"`。

> **版本锚点**：本步基于插件 **1.0.10** 验证。`^1.0.10` 自动接受 1.x 次版本更新；若插件发布
> 2.x 大版本（config 结构或 provider 协议变更），按下方「版本漂移处理」回退。

**关键配置补丁**（原版默认连 Ollama，必须改连观察器）：

先定位 DSH 桌面 profile（`<DSH_profile>` 即含 `node_modules\` 的那一层 profile 目录），按序探测：

```powershell
if ($env:DSH_HOME) { $dp = Join-Path $env:DSH_HOME "profiles\desktop" }
else { $dp = Join-Path $HOME ".dsh\profiles\desktop" }
if (-not (Test-Path "$dp\node_modules")) {
    # 判据落空 → 列出全部候选，挑 node_modules 下装有 dsh-think-translate 的那个
    $root = if ($env:DSH_HOME) { $env:DSH_HOME } else { Join-Path $HOME ".dsh" }
    Get-ChildItem (Join-Path $root "profiles") -Directory
    # 逐个验证：Test-Path "<候选>\node_modules\dsh-think-translate" 为 True 的即 $dp
}
Test-Path "$dp\node_modules\dsh-think-translate"   # True = 定位成功
```

> `<DSH_profile>` 没有写死的通用值：优先 `%DSH_HOME%\profiles\desktop`，兜底 `~\.dsh\profiles\desktop`，
> 最终以 `profiles\desktop\node_modules` 真实存在为准（各机器安装位置不同）。

```powershell
Copy-Item "$TZ\app\plugin-config\dsh-think-translate.config.json" `
    "$dp\node_modules\dsh-think-translate\lib\config.json" -Force
```
然后重启 DSH 桌面端。

**版本漂移处理**（插件大版本升级导致本步失效时）：

1. **观察器端点契约永不变**：`POST http://127.0.0.1:18765/v1/chat/completions`、`model: "think-zh"`
   是本项目的稳定接口（OpenAI 行业标准格式）。无论插件怎么改，任何支持自定义 OpenAI
   provider 的显示层都能接回你的精修库——**接口由本项目定义，客户端来适配**。
2. **回退已知良好配置**：本仓库 `app\plugin-config\dsh-think-translate.config.json` 永远是经
   1.0.10 验证的配置锚点——新版插件 config 结构变化时，对照它手工迁移字段。
3. **零插件兜底**：显示层完全装不上也不影响翻译资产——浏览器直开 `http://127.0.0.1:18765`
   观察页（实时翻译流 + 统计），核心功能与插件无关。
4. 插件 config 结构变化较大时，以其 npm 页官方 README 为准重新生成配置；欢迎提 issue
   反馈，本手册跟进更新。

【验证】`(Invoke-RestMethod http://127.0.0.1:18765/api/stats)` 的 `hits` 或 `misses` 在用户对话后开始增长

## 通用接入（非 DSH 工具用这个；无需第 6 步）

观察器暴露 OpenAI 兼容端点，任何工具/智能体直接调用。**PowerShell 下不要用 curl 内联 JSON**
（`\"` 转义在 PowerShell 必炸），用 `ConvertTo-Json` 构造请求体：

```powershell
$body = @{ model = "think-zh"; messages = @(@{ role = "user"; content = "Let me check the pipeline." }) } | ConvertTo-Json -Depth 5
Invoke-RestMethod -Uri "http://127.0.0.1:18765/v1/chat/completions" -Method Post -ContentType "application/json" -Body $body
```

返回 JSON 的 `choices[0].message.content` 即中文译文。（确需用 `curl.exe` 时，把 JSON 写入临时文件后
`curl -X POST ... -d "@body.json"`，不要内联转义。）也可用 Python 直接查库
（`app\tm_store.py`，SQLite 三张表：tm / canon / terms）。

## 最终验收（全部做完必做）

【命令】
```powershell
$body = @{ model = "think-zh"; messages = @(@{ role = "user"; content = "Actually, wait. Let me reconsider the fallback path." }) } | ConvertTo-Json -Depth 5
(Invoke-RestMethod -Uri "http://127.0.0.1:18765/v1/chat/completions" -Method Post -ContentType "application/json" -Body $body).choices[0].message.content
```
【判据】HTTP 200，输出为中文（库命中应包含「回退」等词）。
【交付报告】向用户报告：环境探测结果、种子库条数、最终验收响应、观察页地址
`http://127.0.0.1:18765/`。

---

## 踩坑实录（开发期真实代价，每条都踩过，勿重蹈）

> **两条元教训（比下面 20 条更重要）**：
> 1. **装任何组件前，先读它自带的 README**——默认值的设计意图都写在里面
>    （本项目的"插件默认连 Ollama"坑，其 README 第 26/71 行其实早已写明）
> 2. **二手信息（新闻稿/转述/博客）必须用官方文档原文校验后再执行**
>    （峰谷定价的"周末全天谷"只存在于官方脚注，二手转述全部漏掉——差点多花一倍）

### 安装/环境坑

| # | 坑 | 症状 | 解法 |
|---|---|---|---|
| 1 | DSH 会话文件是**多帧 zstd** | 单帧解码读到一半断流/魔数错误 | 必须跨帧连续解码（`read_across_frames=True`），尾部用魔数重同步的 Tail 模式 |
| 2 | PowerShell 写 JSON 带 BOM | 插件解析配置报 `Unexpected token '﻿'` | 用 `[System.Text.UTF8Encoding]::new($false)` 写文件 |
| 2b | PowerShell 读 UTF-8 日志不指定编码 | 中文全成"杩涘害"式乱码（UTF-8 字节被按 GBK 配对） | `Get-Content -Encoding UTF8`；或干脆用 python 读 |
| 3 | PowerShell 5.1 的 Start-Process 无 -Environment | 参数报错 | 环境变量靠当前会话 `$env:` 继承，先设再 Start-Process |
| 4 | 内联 `python -c` 复杂引号 | 引号地狱各种报错 | 逻辑超过一行就写临时 .py 文件执行 |
| 5 | 端口漂移 | DSH 桌面重启后端口变化，写死的端口连不上 | 依赖端口的脚本动态探测（扫 Listen 端口试 /_xlate/models） |
| 6 | 模型放 C 盘 | C 盘仅剩 0.1GB 系统告警 | 模型/库一律放数据盘 |
| 7 | HuggingFace 下载慢/失败 | 模型拉不下来 | hf-mirror.com 同路径 |
| 8 | 会话文件散在多个 home | 找不到最新会话 | 优先 `DSH_HOME` 环境变量，兜底 `~/.dsh`，还要考虑 AppData harness-home |
| 9 | npm 原版插件默认连 Ollama | 装完插件翻译静默失败 | 第 6 步的 config.json 补丁（已写明） |
| 9b | **PowerShell 里 `cd /d` 无效**（那是 cmd 语法） | 脚本在错误目录执行——本项目曾因此把 `git add -A` 跑进错误仓库（幸无 commit 无 remote，零泄漏） | PowerShell 用 `Set-Location`；**git 操作永远加 `-C <路径>`** 显式指定仓库，不依赖当前目录 |

### 运行期坑

| # | 坑 | 症状 | 解法 |
|---|---|---|---|
| 10 | 后台长任务被宿主/终端回收 | 跑到一半进程消失（"unknown job"） | 长任务一律 `Start-Process -WindowStyle Hidden` 分离 + 日志文件轮询，绝不用交互终端挂后台 |
| 11 | 1.8B 单槽串行 | 推理快时中文滞后 2~4 秒 | `-np 4` 并行 + `-c 1024`（实测 4 句并发 1.3s） |
| 12 | 术语表改了不生效 | terms.json 更新但译文仍旧 | 术语表启动时加载，改完必须重启 watcher |
| 13 | 1.8B 常驻 + 7B 校正同时起 | 显存 OOM | 7B 校正专用小配置（np=1, ctx=2048），且挖矿有活动让路机制 |
| 14 | 多进程写库锁死 | watcher 与精修同时写 SQLite | WAL 模式 + `timeout=15`；只读巡检用 `mode=ro` URI |
| 15 | 库的 created 字段是建库日 | 按日统计全堆在同一天 | 铺量写入不携带句子真实时间，别拿它做时间序列 |

### DeepSeek 付费坑（每条都是真金白银）

| # | 坑 | 代价 | 解法 |
|---|---|---|---|
| 16 | v4-flash 默认开思考链 | 500 条预估 0.32 元实收 **2.73 元**（输出 93% 是默想 token） | 请求体加 `"thinking":{"type":"disabled"}`——省 13 倍且快 14 倍 |
| 17 | 模型名想当然 | deepseek-chat 已下线，404 | 跑前 `GET /v1/models` 实测可用模型名 |
| 18 | 直接全量跑批 | 费率错误时损失放大 | 永远先 `--dry-run` 零成本预览 + 首批小批量实测费率核对 |
| 19 | 峰谷价差 2 倍 | 峰时全量多花一倍 | `--valley-only` 防呆锁；周末全天谷（官方脚注 UTC 口径） |
| 20 | sk- 密钥泄漏进库 | 库里扫出 8 条真实 key 明文 | core.py 保护规则补 `sk-` 模式；发布前强制剔敏复扫 |

## 失败处理速查

| 症状 | 处理 |
|---|---|
| 中文有滞后感 | 确认 `-np 4` 生效；命中句 2ms，未命中 0.2~1s |
| 显存不足 | `-np` 降 2；或换 Q4_K_M 量化模型 |
| 命中率低 | 属正常，库随使用收敛；确认第 4 步种子库已导入 |
| 观察页乱码 | 用浏览器访问，勿用 PowerShell 重定向读日志 |
| 精修/进阶 | 见下两节 |

## DeepSeek 精修层（可选，付费，默认不做）

```powershell
Set-Location "$TZ\app"
python -X utf8 review.py --dry-run --all          # 零成本预览
$env:DEEPSEEK_API_KEY = "sk-xxx"                   # 凭据只走环境变量（当前会话有效）
python -X utf8 review.py --all --yes --valley-only # 谷价自动防呆
```
- 模型 deepseek-v4-flash，已内置关思考参数（省 13 倍费用）
- 谷时段：工作日 UTC 1-4、6-10 以外全部；周末全天谷
- 断点续跑；精修过的条目永不重复扣费
- **未经用户逐次确认不得调用付费接口**

## 隐私红线

- API key 只走环境变量，绝不入库、入脚本、入日志、入 Git
- 再分发库副本前必须跑 `app\tools\export_clean.py` 剔敏并复扫
- `app\tools\scan_sensitive.py` 随时全库复扫

## 参数速查

| 参数 | 值 | 位置 |
|---|---|---|
| 1.8B 并行槽 | `-np 4` | watcher_service.py ensure_model |
| 单句上下文 | `-c 1024` | 同上 |
| 观察页/API 端口 | 18765 | PORT |
| 模型端口 | 8199（1.8B）/ 8198（7B） | MPORT / PRESETS |
| 挖矿开关 | app\out\mining.off 文件存在=停 | 删除即启用 |

## 许可证

- 本项目代码与文档：**MIT**（见根目录 `LICENSE`）
- llama.cpp 引擎：MIT（第三方公共品，第 2 步自行获取）
- Tencent Hunyuan-MT 模型：许可见腾讯官方仓库（第 3 步自行获取）
- NVIDIA CUDA 运行时 DLL：NVIDIA 最终用户许可（随引擎分发包提供）
- 种子库 `tm-share.sqlite3`：随本项目分发，发布前已剔敏复扫
