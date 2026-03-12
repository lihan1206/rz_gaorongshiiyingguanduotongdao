# 高融石英管多通道液位同步检测系统

## 🛠 技术栈
- Frontend: React + Vite + Ant Design + ECharts
- Backend: FastAPI + SQLAlchemy + Pydantic
- Database: MySQL 8.0

## 🚀 启动指南 (How to Run)
1. 确保 Docker Desktop 已启动。
2. 在根目录执行：`docker compose up --build`
3. 等待容器启动完成。

## 🔗 服务地址 (Services)
- Frontend: http://localhost:3000
- Backend Swagger: http://localhost:8000/docs
- Database: localhost:3306 (user: root / pass: root)

## 🧪 测试账号
- Admin: admin / 123456

## 📦 轻量打包
- 执行：`./scripts/package_release.sh`
- 特性：打包过程不执行自动测试，自动排除 `node_modules`、`dist`、`.git`、`venv`、`target`、测试脚本/测试用例等无关文件。
- 输出：`release/*.tar.gz`

## 功能说明
- 登录鉴权：进入系统需先登录，账号来自数据库种子数据。
- 多通道配置管理：支持新建、编辑、删除通道（删除含 UI 二次确认）。
- 同步采样录入：一次性提交多通道液位，实时写入数据库。
- 自动报警判定：采样值超过阈值自动生成报警，支持人工确认处理。
- 实时监控总览：展示通道状态、实时统计和趋势图。
- 历史数据报表：按通道和时间范围查询，并导出 CSV。

## 目录结构
```text
.
├── backend
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app
├── frontend
│   ├── Dockerfile
│   ├── nginx.conf
│   └── src
├── docker-compose.yml
└── README.md
```

## 说明
- 系统启动时会自动建表并写入种子数据（用户、8 路通道、历史采样数据）。
- 前端不使用任何 Mock 数据，所有页面直接调用后端 API。
- 后端采用标准日志输出，可通过 `docker compose logs -f backend` 查看运行日志。
