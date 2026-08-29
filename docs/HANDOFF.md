# think-zh 交接文档（HANDOFF）

> **给新会话**：原会话因一次 `read_image` 误用（glm-5.3-flash 纯文本模型不支持图片输入，图片已持久化进历史导致会话锁死）弃用。本文档承载全部关键上下文，读完即可无缝继续。
> **交接时间**：2026-08-29 18:1x｜**原会话进度**：turn132，审计报告已产出，第 4 项修复已完成，观察页已验证。

## 一、项目是什么

**dsh-think-translate（think-zh）**：DSH 的思维链中译插件/服务。npm 包 `dsh-think-translate`（latest = 1.0.10，已核实 `^1.0.10` 有效）。核心：`watcher_service.py` 内嵌观察页 UI，服务监听 `127.0.0.1:18765`，打开 `http://127.0.0.1:18765` 即"think-zh 思维链中译"观察页（已实测 HTTP 200、实时日志流正常）。

## 二、目录地图（两个工作副本的分工）

| 路径 | 角色 |
|---|---|
| `D:\think-zh\` | **发布工作区**：`app\`（发布面，已精简）、`docs\`（截图与验证结论）、`llama\`、`models\`、`.git` |
| `D:\think-zh\app\` | 发布面现状（**第 4 项已完成**）：仅剩 6 个必需文件 `watcher_service.py / core.py / tm_store.py / review.py / backfill.py / terms.json` + `plugin-config\`、`tools\`、`seed\` 目录 |
| `E:\DSH011rc1\workspace\think-zh\` | **开发工作区**：源码副本、`方案设计.md`、`观察页-嵌入.html` |
| `E:\DSH011rc1\workspace\think-zh\out\` | 产物与脚本：`probe_form.py`、`shot_observer.py`（截图脚本）、`survey_channels.py`（社区渠道调研）、`gh_*.py`（GitHub 发布脚本）、`sentences.jsonl`（语料）、`tm-share.sqlite3`（翻译记忆）、`对照报告.md` |
| `E:\DSH011rc1\workspace\think-zh\out\dev-scripts\` | 从发布面移出的 **7 个开发残留留档**（acceptance_phase2 / extract_all / extract_sample / run_review_scheduled / translate_sample / upgrade_now / verify_quality） |
| `D:\think-zh\docs\screenshot-observer.png` | 观察页截图（1800x1400，已拍好） |
| `D:\think-zh\docs\screenshot-observer.ocr.md` | **截图 OCR 验证结论**（观察页正常，机翻痕迹清单） |

## 三、审计报告（修复清单原文）

### 🔴 必修（翻车级）

1. **手册全是 cmd 语法**：第 5 步、精修层、第 4 步的 `cd /d`、`start "" /min`、`set XXX=`、`copy /y` 在 PowerShell 无效；`curl --data "{...}"` 内联转义在 PowerShell 必炸。需全面改 PowerShell 写法（`Set-Location` 等），并给 curl JSON 转义提供临时文件替代写法。
2. **`<DSH_profile>` 幽灵路径**：需给探测判据——先 `%DSH_HOME%` → 兜底 `~/.dsh` → 找 `profiles\desktop\node_modules`（本机实际在 `E:\DSH011rc1\home\profiles\desktop`）。
3. **README 数字与包内容不符**：74,573 句 → 实际 **75,353**；7.6 MB → **7.8 MB**；≈24 MB → **25.4 MB**。
4. ~~开发残留脚本进发布包~~ → **已完成**：7 个残留移至 `workspace\think-zh\out\dev-scripts\`，发布面已精简。

### 🟡 快修（5-9）

| # | 问题 |
|---|---|
| 5 | 无 LICENSE 文件（README 声称 MIT） |
| 6 | 零截图零演示 → **截图已拍好**（`docs\screenshot-observer.png`），待嵌入 README/发布物 |
| 7 | 平台限制未声明（Windows + NVIDIA 硬前提） |
| 8 | zip 解压后无 `llama\`、`models\` 目录说明（第 2/3 步缺 mkdir） |
| 9 | llama.cpp 下载需给镜像 URL（HF 用 hf-mirror，GitHub 用 ghfast.top） |

### 🟢 产品决策（10）

10. **观察页要不要进包** → **已验证、建议保留进包**：页面随 watcher_service 内嵌即开即用，实时日志流工作正常，对调试翻译质量有直接价值；存在机翻痕迹（"剧作家"=Playwright、破折号误译成"一"），属质量问题非功能问题，可后续迭代。证据：`docs\screenshot-observer.ocr.md`。

### 附加摩擦项（审计中一并列出）

无"两行代码"快速上手示例、端口安全声明（仅监听 127.0.0.1）未写。

## 四、待办顺序（建议）

1. 第 1-3 项（README 语法/路径/数字）——纯文档修，工作量小收益大；
2. 第 5-9 项快修；
3. 第 10 项：把观察页与截图写进 README（"装完打开 http://127.0.0.1:18765 即是中文推理观察页"）；
4. 重新打包前：数字三处复核、敏感扫描（`E:\DSH011rc1` 硬编码已随残留移出，复查一遍）、UTF-8 校验。

## 五、本机环境红线（务必遵守）

1. **禁止调用 `read_image`**：本会话模型 glm-5.3-flash 是纯文本模型，图片会锁死会话（原会话就是这么死的）。看图一律用本机 OCR：
   ```
   "E:\DSH011rc1\tools\ocr\python\python.exe" -X utf8 "E:\DSH011rc1\tools\ocr\tool\dsh_ocr.py" ocr "<图片绝对路径>" --json
   ```
2. **命令一律 PowerShell 语法**（`cd /d`、`start "" /min` 等/cmd 语法不可用）——这正是审计第 1 条要修的坑，自己别再踩。
3. 模型旁如有 off/low 档位选择器：低要求任务选 off 省时省 token。

## 六、2026-08-29 修复会话记录（待办已清）

1. **第 1-3 项完成**：INSTALL.md 全部命令改 PowerShell（`$TZ` 变量约定、`Set-Location`/`Copy-Item`/`Start-Process`/`Invoke-RestMethod`，curl JSON 改 `ConvertTo-Json` 构造并注明临时文件替代写法）；`<DSH_profile>` 探测判据落进第 6 步（`%DSH_HOME%` → 兜底 `~\.dsh` → 以 `profiles\desktop\node_modules` 为准）；数字三处修正并实测（75,353 句 / 种子库 25.4 MB / 包 8.3 MB）。
2. **第 5-9 项完成**：新增根目录 `LICENSE`（MIT）；README 新增「平台要求」节（Windows+NVIDIA 硬前提 + 仅监听 127.0.0.1）与「装完第一件事：打开观察页」节（嵌 `docs/screenshot-observer.png`）；第 2/3 步补 `New-Item -ItemType Directory`；第 2 步给 ghfast.top 镜像 URL、第 3 步给 hf-mirror.com 同路径写法。
3. **额外发现并修复**：发布面 `app\tools\` 三脚本（scan_sensitive / watch_review / export_clean）残留 `E:\DSH011rc1`、`D:\think-zh` 硬编码路径，已全部改为随包相对定位（`__file__` 推导）。
4. **用户新增要求**：发布面不提费用——README 与 COMMUNITY-POST 中 0.0004 元/条、~26 元、谷价、买断、扣费、零成本等表述全部中性化（INSTALL 的 DeepSeek 付费安全提示与踩坑实录保留，属防呆性质）。
5. **重新打包完成**：`think-zh-portable.zip` 重打（Python zipfile、`/` 分隔、白名单 16 项：文档 4 + LICENSE + app 六必需 + plugin-config + tools 3 + seed 库 + `out\mining.off`），旧包残留 7 个开发脚本已不在包内；实测 8,289,240 字节 ≈ 8.3 MB。
6. **校验全过**：种子库 75,353 条剔敏复扫零命中；发布面 13 个文本 UTF-8 无 BOM；zip CRC 全过；硬编码 grep 零残留。复核脚本留档 `workspace\think-zh\out\pre_release_check.py`、打包脚本 `repack.py`。
7. ~~**未做（待用户确认）**~~ → **已完成（见第 9 条）**。
8. **演示截图（第二张）完成**：`docs/screenshot-reasoning.png`（14 块满窗、全库命中、骨架保留），已嵌 README 并入包，包更新为 17 项 ≈ 8.5 MB。制作要点：观察页流只能来自会话文件监听（API 翻译不入流）；canon 规范化是**块级**的（多句拼块会改变占位符编号导致查库不中，须一句一块）；watcher 用 `DSH_SESSION_JSONL` 指向构造文件即回放（TailDecoder 多帧 zstd，事件格式 `{"type":"reasoning-chunks","data":{"texts":[...],"turn":<数字>}}`）；演示后已恢复 watcher 至真实会话监听并清理临时文件。注意：本会话智能体思考为中文，进英→中管线必然乱翻，演示素材必须取英文推理句（库内 review-% 精修句最佳）。
9. **发布完成（2026-08-29 晚）**：commit `d3fd518`（20 文件，+293/-597）已 push 至 `github.com/mtdx2001/think-zh` main；Release v1.0.0 的 asset 已替换为新包 8,492,782 bytes（远端=本地校验一致），body 补充截图与 PowerShell 手册说明。**同轮修复 watcher 会话切换缺陷**：`watcher_loop` 每 20 秒重探测最新会话文件（显式 `DSH_SESSION_JSONL` 时不自动切换），切换后从新文件尾部继续、120 秒防抖；发布面与开发工作区副本已同步。**发布脚本坑位备忘**：本机全局 gitconfig 的 `url.ghfast.top.insteadOf` 重写会让一切 push 认证失败（ghfast 只加速下载不支持 push）——push 须用剔除该段的临时 GIT_CONFIG_GLOBAL（脚本 `out/make_push_config.py`）；`gh_update_asset.py` 上传 URL 参数不可含未编码空格（曾致旧 asset 已删新 asset 未传的中间态，去掉 label 参数后恢复）。
10. **机翻坏句治理（2026-08-29 深夜，commit `10d5db7`）**：「剧作家」坏句 33 条全在本机 cache 库（本会话现翻产物，含中文思考混英文词的句；发布 seed 库零命中），已 REPLACE 为 "Playwright" 清零。`terms.json` 补 8 词（playwright/headless/smoke test/dry run/workaround/edge case/rollback/race condition），match_terms 为词边界正则、短语键可用；术语只注入现翻提示词，管不到已入库译文——库坏句须直接改库，命中即显示。1.8B 对个别术语遵循度有限（如 smoke test 未按词表翻），属模型能力边界。git 推送再次踩 ghfast 重写坑（第二次了），以后**凡 push 必套 `make_push_config.py` 临时配置**。〔更新：此规矩已被全局 gitconfig 的 `pushInsteadOf` 方案取代（2026-08-29 深夜，原配置备份 `.gitconfig.bak-20260829`）——下载继续走 ghfast 加速、push 经 pushInsteadOf 直连 github.com，push --dry-run 已实测打通；`make_push_config.py` 降级为备用。配置同步副本：`E:\DSH011rc1\home\gitconfig.bak`（C 盘文件为唯一生效源，E 盘仅备份，改 C 盘后须手动同步）。〕
11. **翻译闸门 + 积压治理（2026-08-29 深夜，commit `76bcfe3`，优化方针：更快/更好/更低占用）**：`publish_block` 双闸——中文块（`zh_ratio>=0.25`）与纯符号块（剥占位符后 4+ 字母词 ≤1 且剩余 <40 字符）原样直通入展示流，不调模型不入库；`openai_translate` 对插件 POST 的中文文本同样直通。清理 cache 积压垃圾 1,760 条（中文乱翻 + 符号块），`upgrade_pending` 2,095→**337**（全为真英文叙述句，7B 校正价值真实化）。经验：闸门验证一律写 python 脚本（`verify_gates.py`），PowerShell 内联含反引号/中文必炸（踩坑第三次，纪律已 pinned）；命中路径会返回历史坏译文（如旧符号句"提交"），清理后才闭环。

12. **插件源码仓库单列发布（2026-08-29 深夜）**：npm 包 dsh-think-translate 的 repository 指向陌生账号 UncleK（凭据不在本机、无法修正），为归位生态入口，新建公开仓库 https://github.com/mtdx2001/dsh-think-translate （commit ddcb90a：lib/ 插件主体 + 9 语种 README + demo + docs + 补 MIT LICENSE + package.json 指向修正 + README 增加 think-zh 联动章节与源码主仓声明），topics 含 dsh-plugin；hub #20 已留言告知。发布前完成内容审查（文本敏感扫描 3 命中均为虚惊；demo gif 24 帧 OCR 审查——demo1 为发布 1.0.6 思考流翻译演示含 UncleK 公开 commit hash 与 npm 现状一致，demo2 为设置面板纯 UI，无凭据/路径/身份泄露）。工具：out/publish_plugin_repo.py、scan_tarball.py、extract_gif_frames.py、ocr_all_frames.py（注意批量 OCR 须用 tools\ocr 专用 python，字段名 items[].text）。