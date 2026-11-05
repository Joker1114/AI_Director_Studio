# V1.1 重构记录（以交付源码实际实现为准）

## 结构变化

- `apps/desktop`：新增 Electron 主进程 + Preload + React/TS 渲染进程；桌面端完全不携带/启动 Python。
- `apps/api`：迁移 V1.0 FastAPI 服务、SQLAlchemy 数据、Qwen API、剧本解析、资产审批、分镜与提示词业务；接口主要暴露在 `/api/v1`。
- `app/api/v1`：放置业务接口与视频生成接口；旧 `/api` 路由仅作过渡兼容。
- `app/models`、`app/schemas`：模型与 Pydantic 契约分别归档；旧导入做兼容导出。
- `app/adapters/llm` 和 `app/adapters/video`：云端 Qwen 与远端 ComfyUI 通信适配器。
- `app/workers/generation.py`：生成任务领取、工作流参数编译、GPU 轮询、文件回收、重启恢复。
- `workflows/comfyui/manifests`：工作流参数映射，以配置的节点 ID 和字段值为准。
- `infra/compose/cloud.yml`：PostgreSQL + FastAPI + Worker 的云端容器配置。

## 已落地的变更

1. Electron API 服务地址从用户配置读取，支持在应用设置界面修改；无需重新打包。
2. 通过 Electron Main + 安全 Preload 的 IPC 访问 FastAPI HTTPS API，API Token 不交给 React。
3. 远端 GPU 节点通过 JSON 配置，ComfyUI 调用由 FastAPI Worker 完成；用户电脑无需访问 GPU。
4. 支持按镜头挑选多张参考图，顺序编译为 Picture 1..9 的提交清单。
5. 将项目画风送入 Qwen 调用参数；添加对明显左右颠倒、浮空雨伞、远景变近景的文本冲突拦截。
6. 新增视频任务表、SQLAlchemy 模型、Alembic 数据库迁移、任务状态查询/重试/下载接口。
7. 修复原 V1.0 的测试环境数据库初始化缺陷。

## 已做本地验证

- `pytest -q`：13/13 通过（内存数据库；Qwen 与 ComfyUI 使用模拟响应）。
- `alembic upgrade head`：全新 SQLite 数据库可迁移至 `20261105_jobs`。
- `compileall`：后端、迁移、测试代码可解析。
- Electron TypeScript/TSX 文件：TypeScript transpile 语法诊断为 0 错误。
- FastAPI：实测启动及 `/health`、`/api/v1/projects`、`/api/v1/gpu-nodes`、`/api/v1/workflows` HTTP 返回。
- Python Wheel：可构建（不联网安装依赖）。

## 尚未通过真实环境验收

- 当前环境无法下载安装 npm 包，未执行 Electron `pnpm desktop:typecheck` / `pnpm desktop:build` / Windows NSIS 安装包构建；请在有网络的 Windows 机器上按 README 验收。
- 无真实百炼 API Key，未做 Qwen3.8 计费调用。
- 未取得 API 格式 MiniMax H3 工作流，没有真实 GPU 渲染测试；工作流映射有意保持为可修改模板。
- 无 Docker 引擎与 PostgreSQL 服务，未做容器上线验收。
- 尚非多租户 SaaS：无正式 OIDC、RBAC、账号体系、分布式 GPU 租约或对象存储。
- 目前的空间约束冲突检查仍是规则级文本判定，不代表对生成图像/视频空间布局的视觉验证。
