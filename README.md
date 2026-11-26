# CampusEvent · 校园活动报名与管理系统

实验二 change-v2。单机运行、无需注册登录：学生端用页面右上角切换演示学生身份，管理端固定开放。

**在线地址**：<https://iouyun07.pythonanywhere.com>（部署步骤见文末「部署说明」；线上目前仍是 baseline-v1，change-v2 未重新部署）

## 功能

| 编号 | 功能 | 说明 |
|---|---|---|
| P2-F01 | 活动浏览 | 列表展示标题、分类、时间、地点、名额、已通过人数、我的状态；支持关键词搜索 |
| P2-F02 | 报名 | 直接报名（名额未满即通过）与审核报名（进入待审核）两种策略 |
| P2-F03 | 名额控制 | 按「已通过」人数计算剩余名额；满员拒绝；审批时事务内复查 |
| P2-F04 | 审批 | 管理端查看待审核列表，通过 / 拒绝，并给学生发消息 |
| P2-F05 | 取消报名 | 学生可取消待审核或已通过的报名，保留历史记录 |
| P2-F06 | 我的报名 | 查看本人全部报名记录及状态 |
| P2-F07 | 消息通知 | 报名提交、通过、拒绝、取消时生成站内消息；同一事件去重，可逐条或全部已读 |
| P2-F08 | 活动管理 | 管理端新增、编辑、删除活动；有报名记录的活动禁止删除 |
| CR-01 | 年级限定报名 | 新增 `grade_limited` 策略：仅大二、大三可直接报名，其他年级给出明确原因；名额、开始时间、重复报名规则不变 |
| CR-02 | 模拟邮件通知 | 报名通过 / 审核通过 / 拒绝时，在站内消息之外增加模拟邮件；失败只记录、不回滚；同一事件不重复发送 |

业务规则：名额只统计「已通过」；「待审核」不占名额；同一活动同一学生只能有一条有效报名（待审核/已通过）；活动开始后禁止报名；通知失败只写日志、不回滚业务。

## 技术栈

- Python 3.13、Flask 3.1.3、Jinja2 服务端渲染（无前端框架、无 JavaScript 依赖）
- SQLite（标准库 `sqlite3`），数据文件 `instance/campus_event.db`
- pytest 9.2.0

## 目录结构

```
CampusEvent/
├── app.py                     # 应用工厂、配置、演示数据
├── schema.sql                 # 表结构（含部分唯一索引）
├── requirements.txt
├── pytest.ini
├── campus/
│   ├── db.py                  # 连接、事务上下文管理器
│   ├── models.py              # 领域模型与常量
│   ├── repositories.py        # 数据访问
│   ├── capacity.py            # 名额计算
│   ├── policies.py            # 报名策略（策略模式，含年级限定）
│   ├── events.py              # 事件总线（观察者模式）
│   ├── notifications.py       # 消息观察者 + 邮件通知观察者（幂等）
│   ├── mock_email.py         # 模拟邮件发送器（可注入失败）
│   ├── migrations.py          # 结构迁移（v1 → v2，版本表幂等）
│   ├── services.py            # 应用服务（事务边界）
│   └── views.py               # 路由与页面
├── templates/                 # Jinja2 模板
├── static/style.css
├── tests/                     # pytest 用例（覆盖 C1–C10 及规则）
└── docs/                      # 需求分析、用例、类图、时序图、设计决策与评审记录
```

## 快速开始

```bat
cd /d D:\install\software\CampusEvent
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

浏览器打开 <http://127.0.0.1:5001>。

- 学生端：右上角下拉可切换演示学生（张伟 2023001 大二 / 李娜 2023002 大三 / 王强 2023003 大一）
- 管理端：<http://127.0.0.1:5001/admin>

首次启动会自动建库并写入 3 名学生与 4 个演示活动（其中「高数冲刺讲座」为年级限定）；旧库（baseline-v1）启动时会自动迁移到 v2 结构，无需删库。删除 `instance/` 目录即可重置数据。

## 测试

```bat
.venv\Scripts\python.exe -m pytest -q
```

当前结果：`30 passed`。包含 baseline 的 C1–C10 回归用例（19 条），以及 change-v2 新增用例：CR1-01～05（年级判定、拒绝提示、名额规则复用）、CR2-01～04（邮件渠道、审核通过/拒绝、失败隔离、重复事件去重）与 2 条迁移用例（旧库升级、幂等）。

## 页面路由

| 路径 | 方法 | 说明 |
|---|---|---|
| `/` | GET | 活动列表（`?keyword=` 搜索） |
| `/activities/<id>` | GET | 活动详情、名额统计、我的报名历史 |
| `/activities/<id>/register` | POST | 报名 |
| `/registrations/<id>/cancel` | POST | 取消报名 |
| `/my/registrations` | GET | 我的报名 |
| `/messages` | GET | 消息中心 |
| `/messages/<id>/read`、`/messages/read-all` | POST | 标记已读 |
| `/admin` | GET | 活动管理列表 |
| `/admin/activities/new`、`/admin/activities/<id>/edit` | GET/POST | 新增 / 编辑活动 |
| `/admin/activities/<id>/delete` | POST | 删除活动 |
| `/admin/approvals` | GET | 待审核列表 |
| `/admin/approvals/<id>/approve`、`/reject` | POST | 审批 |

## 设计要点

- **策略模式**：`RegistrationPolicy` 有两个实现（直接报名 / 审核报名），活动通过 `policy_type` 选择；新增策略只需注册到 `POLICIES`。change-v2 的 `GradeLimitedPolicy` 继承 `DirectRegistrationPolicy`，先判年级再复用父类的名额检查，容量逻辑仍只有一处。
- **观察者模式**：`EventBus` 发布报名领域事件，`NotificationObserver` 写站内消息，`EmailNotifier` 发模拟邮件；通知在业务事务提交后发布，失败写 `instance/notification_failures.log`，不影响业务结果。
- **名额一致性**：名额只统计「已通过」；审批在 `BEGIN IMMEDIATE` 事务内重新读取并复查名额，避免并发超卖。
- **幂等通知**：消息表、邮件表各自的 `dedupe_key` 唯一，重复事件不会重复通知；邮件先占位再发送，重复事件直接跳过。
- **结构迁移**：SQLite 无法修改 CHECK 约束，v2 迁移通过重建 `activities` 表完成（外键临时关闭、事务内复制数据），`schema_version` 保证只执行一次。

## 部署说明（PythonAnywhere）

线上实例部署在 PythonAnywhere 免费账号（用户名 `iouyun07`），代码来自 GitHub 仓库 `iouyun07/CampusEvent`。

1. 登录 PythonAnywhere，打开 **Consoles → Bash**，克隆代码：

   ```bash
   cd ~
   git clone https://github.com/iouyun07/CampusEvent.git
   cd CampusEvent
   ```

2. 创建虚拟环境并安装依赖：

   ```bash
   mkvirtualenv --python=/usr/bin/python3.13 campusevent
   pip install -r requirements.txt
   python -m pytest -q
   ```

3. 打开 **Web → Add a new web app → Manual configuration → Python 3.13**。
4. **Code** 区块：Source code 与 Working directory 都填 `/home/iouyun07/CampusEvent`。
5. **Virtualenv** 填 `/home/iouyun07/.virtualenvs/campusevent`。
6. **Static files**：URL 填 `/static/`，Directory 填 `/home/iouyun07/CampusEvent/static`。
7. 编辑 WSGI 文件 `/var/www/iouyun07_pythonanywhere_com_wsgi.py`：

   ```python
   import sys
   path = "/home/iouyun07/CampusEvent"
   if path not in sys.path:
       sys.path.insert(0, path)
   from app import app as application
   ```

8. 点 **Reload**，访问 <https://iouyun07.pythonanywhere.com>。

数据保存在 `/home/iouyun07/CampusEvent/instance/campus_event.db`，重启服务不丢；更新代码后在 Bash 里执行 `cd ~/CampusEvent && git pull`，再点 Reload 即可生效。

## 已知限制

- 无登录鉴权：学生身份通过页面切换，管理端任何人可访问，仅用于课程演示。
- 年级规则目前固定为大二、大三（`GradeLimitedPolicy.allowed_grades`），未做后台配置。
- 邮件为模拟发送：只写入 `emails` 表并记录状态，不真正投递；可用 `MOCK_EMAIL_FAIL_FOR=2023001` 演示失败分支。
- SQLite 单文件数据库，不支持多实例并发部署。
- 未实现分页，活动数量按课程规模（数十条）设计。
