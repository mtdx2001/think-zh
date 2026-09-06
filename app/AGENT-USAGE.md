# 本机智能体使用 think-zh 翻译服务

> 本文件面向**同机运行的其他智能体**。观察器对思考流的翻译是旁路自动的（无需配置）；
> 本文件主要说明**主动调用**方式。

## 服务信息

- 端点：`http://127.0.0.1:18765/v1/chat/completions`（OpenAI 兼容）
- model：`think-zh`
- 库：75,000+ 句 DeepSeek 精修翻译记忆（命中 2ms，零云端调用）
- 未命中：本地 1.8B 实时翻译兜底（显存常驻，断网可用）
- 隐私：代码/路径/密钥在翻译前即被摘成 `⟦P001⟧` 占位符，数据不出本机

## 主动调用（PowerShell 示例）

```powershell
$body = @{ model = "think-zh"; messages = @(@{ role = "user"; content = "Let me check the watcher pipeline." }) } | ConvertTo-Json -Depth 5
Invoke-RestMethod http://127.0.0.1:18765/v1/chat/completions -Method Post -ContentType application/json -Body $body
# 返回 choices[0].message.content = 中文译文
```

Python：

```python
import json, urllib.request
req = urllib.request.Request("http://127.0.0.1:18765/v1/chat/completions",
    data=json.dumps({"model": "think-zh", "messages": [{"role": "user", "content": ENGLISH_TEXT}]}).encode(),
    headers={"Content-Type": "application/json"})
zh = json.loads(urllib.request.urlopen(req, timeout=30).read())["choices"][0]["message"]["content"]
```

## 行为说明

- 优先命中本地库（2ms）；未命中走本地 1.8B（0.2~1s）并入库，空闲时段 7B 自动校正升级
- 代码块、文件路径、命令行自动保留原文
- 服务未启动时：连接拒绝——可检查观察器是否运行（`start_watcher.cmd`）
- 观察页（给人看）：`http://127.0.0.1:18765`

## UI 直显（可选，仅 DSH 版本）

```powershell
dsh plugin --profile desktop add dsh-think-translate
Copy-Item D:\think-zh\app\plugin-config\dsh-think-translate.config.json `
    "$env:DSH_HOME\profiles\desktop\node_modules\dsh-think-translate\lib\config.json" -Force
# 重启 DSH 生效
```
