# AI Director Studio 1.1 — Electron 客户端 + 云端 FastAPI + 独立 ComfyUI

## 架构说明

- `apps/desktop`: **Electron + React + TypeScript** 桌面端。运行在用户 Windows 电脑；**不嵌入 Python**。通过 Electron 主进程的安全 HTTP 代理访问 FastAPI。
- `apps/api`: **FastAPI + Qwen3.8 云端适配 + PostgreSQL + 分镜/资产/提示词业务**。部署于任意可到达的云服务器。
- `apps/api/app/workers/generation.py`: **独立云端 Worker**，从 PostgreSQL 领取生成任务，通过服务器配置的 ComfyUI 地址访问 GPU。
- `workflows/comfyui`: 工作流 API JSON 及节点输入清单，图像序号由服务端严格映射；不要求桌面客户端直接访问 GPU。
- `infra/compose/cloud.yml`: PostgreSQL、FastAPI、Worker 的容器部署配置。

**所有网络地址都来自配置，不在业务代码内硬编码。** Electron 地址可在「连接设置」修改，云端 Qwen、数据库、GPU 地址由环境变量及 GPU 配置文件控制。

## 1. 云端 FastAPI 启动（本地开发方式）

建议 Python 3.11/3.12。以下命令均在 `apps/api/` 目录执行：

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# Linux: source .venv/bin/activate
pip install -e '.[test]'
cp .env.example .env     # Windows 使用 Copy-Item .env.example .env
# 配置 DATABASE_URL、DASHSCOPE_BASE_URL、DASHSCOPE_API_KEY、APP_API_TOKEN
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

测试：`GET http://127.0.0.1:8000/health`；业务文档 `http://127.0.0.1:8000/docs`。

使用独立终端启动 Worker（必须与 API 使用同一数据库与媒体目录）：

```bash
python -m app.workers.generation
```

生产环境将 API 置于 HTTPS 反向代理后方，配置长随机 `APP_API_TOKEN`，使用 PostgreSQL，不要开启 `APP_ALLOW_LOCAL_NO_TOKEN`，不要将 API 的开发模式直接暴露公网。

## 2. 云端 Docker 部署

```bash
cp apps/api/.env.example apps/api/.env
# 修改 .env、apps/api/config/gpu_nodes.json、以及工作流映射文件
# 在 apps/api/.env 中另行配置 POSTGRES_PASSWORD 或通过 shell 提供
# 以下命令从仓库根目录执行：
docker compose --env-file apps/api/.env -f infra/compose/cloud.yml up -d --build
```

`infra/compose/cloud.yml` 仅在 `127.0.0.1:8000` 绑定 HTTP API，供同机 Nginx/Caddy 反向代理。ComfyUI 需要是 FastAPI/Worker **能够路由访问的地址**：同 VPC、专网或 VPN。切勿直接开放未经认证的 ComfyUI 8188 到公网。

示例 API URL：`https://api.my-company.com`。证书、反向代理和 DNS 由部署者配置。

## 3. Electron 客户端开发

建议 Node.js 22、Windows 10/11。仓库根目录：

```powershell
corepack enable
corepack prepare pnpm@9.15.9 --activate
pnpm install
pnpm desktop:dev
```

启动后打开「连接设置」，填写云端 FastAPI 根地址（**不要带 `/api/v1`**），以及云端 `APP_API_TOKEN`；无需在客户端填写百炼 API Key、数据库或 ComfyUI IP。

打包 Windows 安装程序：

```powershell
pnpm desktop:dist:win
```

生成到 `apps/desktop/release/`。初始默认配置在 `apps/desktop/src/main/defaults.json`，首次运行可在设置界面覆盖。Electron 的 `nodeIntegration=false`、`contextIsolation=true`、`sandbox=true`；文件/网络能力仅通过 Preload 暴露的固定 IPC 白名单。

**本交付环境无法联网安装 npm 依赖，因此只完成 Electron TypeScript/TSX 语法解析，没有真实执行 `pnpm install`、打包或 Windows 兼容性验收。**

## 4. 配置文件清单

| 所在端 | 配置 | 作用 |
|---|---|---|
| Electron | `%APPDATA%/AI Director Studio/settings.json` | FastAPI 根地址、请求超时 |
| Electron | `%APPDATA%/AI Director Studio/token.bin` | Windows 可加密存储的访问令牌；不暴露给 React |
| FastAPI | `apps/api/.env` | PostgreSQL、Qwen、鉴权、目录等 |
| FastAPI Worker | `apps/api/config/gpu_nodes.json` | GPU 节点 ID、ComfyUI HTTP 地址、支持的模型 |
| FastAPI Worker | `workflows/comfyui/manifests/minimax_h3.json` | 参考图、提示词、种子和视频输出节点映射 |
| ComfyUI Workflow | `workflows/comfyui/videos/minimax_h3/workflow_api.json` | 从 ComfyUI 导出的实际可执行 API JSON |

**注意**：已提供工作流映射模板，但未收到有效的 `workflow_api.json`，无法在服务器上执行真实 MiniMax H3 渲染；该接口会阻止缺少工作流的任务提交。

## 5. 已实现的业务路径

1. 新建项目、保存剧本历史版本。
2. Qwen3.8 抽取角色/场景/道具及剧情事件；人工审核资产候选。
3. 手动管理资产、锁定事实、上传/审核参考图、生成资产生图提示词。
4. 生成分镜、编辑镜头/空间约束、单镜头选多张参考图、生成/审核首帧和 H3 视频提示词。
5. 选择已审核的 H3 视频提示词，提交云端视频生成任务、读取状态、失败重试、下载云端文件。
6. 使用外部配置的 GPU 服务器，运行独立 Worker 执行 ComfyUI `/upload/image`、`/prompt`、`/history/{id}` 和 `/view`。

## 6. 自动化测试与限制

从 `apps/api/` 执行 `pytest -q`。测试使用独立内存数据库和模拟 Qwen/ComfyUI，没有真实调用付费接口。`alembic upgrade head` 可在空 SQLite 库完成迁移。

**当前边界**：
- 此版本为单团队/受控环境使用的共享令牌认证；**不具备商业多租户 RBAC/账单隔离**。
- 尚无自动生图、图像视频视觉质检、2D 场景编辑器、自动拼接成片。
- 仅实现基础文本冲突拦截，不等于图像物理一致性保证。
- Worker 初版按单实例顺序处理任务；跨多个 Worker 的 GPU 容量管理、心跳锁与任务超时治理仍需强化。
- 未实际验证真实 Qwen3.8 调用、ComfyUI H3 工作流运行、Docker/PostgreSQL 在线部署或 Electron Windows 安装程序。

更多参见 `docs/architecture/DEPLOYMENT.md`。
