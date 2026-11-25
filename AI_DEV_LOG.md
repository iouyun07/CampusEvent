# AI 开发日志（CampusEvent）

记录重要提示词、关键设计决策、发现的问题及人工判断；不粘贴完整对话。

## 2026-11-19 需求分析与设计

- **输入**：实验二 SRS（CampusEvent，2 周，baseline-v1 + change-v2）。
- **AI 承担**：提取 SRS 要点、整理初始 SRS 分析、用例说明、类图与时序图、设计模式决策报告、自评审记录。
- **关键决策**（详见 `docs/设计模式决策报告.md`）：
  - 报名流程用**策略模式**（直接报名 / 审核报名），名额检查不放在策略内，由服务层统一调用 `CapacityChecker`——名额是全局约束，不是策略差异。
  - 报名状态变化用**观察者模式**发布领域事件，通知在事务提交后发送，失败只写日志不回滚。
  - 消息写入用 `dedupe_key` 唯一约束做幂等。
  - 审批用 `BEGIN IMMEDIATE` 事务内复查名额，避免并发超卖。
  - 有报名记录的活动禁止删除（SRS 要求二选一，选更保守的策略）。
- **人工判断**：确认「待审核不占名额」「同一活动同一学生只能一条有效报名」等口径；确认设计评审自评审即可、无需签名。

## 2026-11-20 baseline-v1 实现与测试

- **AI 承担**：按设计实现 `schema.sql`、`campus/` 领域层与服务层、路由与模板、pytest 用例。
- **实现摘要**：4 张表（students / activities / registrations / messages），部分唯一索引 `ux_registrations_active` 保证有效报名唯一；`campus/` 按 db→repositories→policies/events→services→views 分层。
- **发现的问题与修复**：
  1. **通知事件类型错误**：直接报名自动通过后仍发 `submitted` 事件，学生收到「等待审核」的消息。冒烟测试发现后改为按报名结果状态选择 `EVENT_APPROVED` 或 `EVENT_SUBMITTED`。
  2. **测试环境临时目录**：本机沙箱下 pytest 创建 0o700 临时目录后无法访问，`PermissionError`。非代码缺陷，通过本机 `sitecustomize` 环境补丁绕过，不影响项目代码与 README 的标准运行方式。
  3. **测试辅助函数参数**：`create_activity(client, conn, ...)` 需要连接对象查 ID，初版用例漏传，统一修正。
- **验证**：`python -m pytest -q` → `19 passed`，覆盖验收 C1–C10 及额外业务规则。
- **人工判断**：追加「切换演示学生」下拉，仅为演示名额与审批流程，不属于新增业务功能。

## 2026-11-25 推送到 GitHub 与部署到 PythonAnywhere

- **AI 承担**：整理推送与部署步骤；核对本地 git 状态；部署后核验线上页面；更新 README 的在线地址与部署说明。
- **过程**：
  - 用户在 GitHub 创建空仓库 `iouyun07/CampusEvent`，本人执行 `git remote add origin` + `git push -u origin main`（53 个对象、39.89 KiB，main 分支建立并设置上游）。
  - 释放 PythonAnywhere 实验一的 Web 应用名额；在 Bash console 中克隆仓库、创建 `campusevent` 虚拟环境、安装 12 个依赖，服务器端 `pytest -q` → `19 passed in 9.37s`。
  - Web 标签用 Manual configuration 配置 Source code、Virtualenv、`/static/` 映射与 WSGI 文件，Reload 后线上可访问。
- **验证**：线上 <https://iouyun07.pythonanywhere.com> 返回 200，活动列表显示 3 个预置活动（校园歌手大赛 / 编程马拉松 / 篮球友谊赛）、剩余名额与演示学生切换正常。
- **人工判断**：部署形态选 PythonAnywhere 免费版而非临时磁盘的 PaaS，原因是 SQLite 数据需要持久化；实验一的在线地址随 Web 应用删除而下线，其代码与仓库保留。
