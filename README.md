# AI Director Studio

AI Director Studio 是短剧创作工作台。桌面端管理剧本、资产、分镜和视频生成任务；云端 API 处理业务与 Qwen 调用；独立 Worker 将生成任务交给 ComfyUI。

当前版本：**1.1.0**。桌面端技术栈为 **Electron + Vue 3 + TypeScript**，云端为 **FastAPI + PostgreSQL**。桌面端不包含 Python，也不直接连接 GPU。

## 功能

- 创建项目并保存剧本历史版本；使用 Qwen 提取角色、场景、道具和剧情事件。
- 审核资产候选，管理锁定事实、参考图和生图提示词。
- 生成与编辑分镜，绑定参考图，检查空间约束，审核首帧及视频提示词。
- 提交 ComfyUI 视频任务，查看状态、重试失败任务并下载结果。

## 项目结构

| 路径 | 用途 |
| --- | --- |
| `apps/desktop/` | Electron 主进程、Preload 和 Vue 3 桌面界面 |
| `apps/api/` | FastAPI、数据库迁移和独立生成 Worker |
| `workflows/comfyui/` | ComfyUI 工作流和节点映射 |
| `infra/compose/cloud.yml` | PostgreSQL、API、Worker 的 Docker Compose 配置 |
| `docs/architecture/DEPLOYMENT.md` | 部署架构与生产环境扩展说明 |

桌面端通过 Electron 主进程向 FastAPI 发起请求。API 和 Worker 共享数据库及媒体目录；Worker 通过可路由的私有网络访问 ComfyUI。Qwen 密钥、数据库连接和 GPU 地址均配置在云端。

## 环境要求

| 组件 | 要求 |
| --- | --- |
| 桌面端开发 | Windows 10/11、Node.js 22、pnpm 9.15.9 |
| API 本地开发 | Python 3.11 或 3.12 |
| 云端部署 | Docker Compose、可访问的 ComfyUI GPU 服务（视频生成功能需要） |

## 快速开始

以下命令在仓库根目录的 PowerShell 中执行。

### 1. 启动桌面端

```powershell
corepack enable
corepack prepare pnpm@9.15.9 --activate
pnpm install
pnpm desktop:dev
```

桌面端可以先启动，再到「连接设置」填写 FastAPI **根地址**，例如 `http://127.0.0.1:8000` 或 `https://api.example.com`，以及服务端设置的 `APP_API_TOKEN`。地址不要包含 `/api/v1`。非本机地址必须使用 HTTPS。

### 2. 启动本地 API

在另一个 PowerShell 窗口中执行：

```powershell
Set-Location apps/api
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
Copy-Item .env.example .env
New-Item -ItemType Directory -Force data | Out-Null
```

编辑 `apps/api/.env`：本地不使用 PostgreSQL 时，将 `DATABASE_URL` 改为 `sqlite:///./data/director.db`；将示例 `APP_API_TOKEN` 换成自己的长随机令牌。需要使用 Qwen 功能时，再配置 `DASHSCOPE_API_KEY` 和 `DASHSCOPE_BASE_URL`。然后继续执行：

```powershell
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

访问 `http://127.0.0.1:8000/health` 检查服务，访问 `http://127.0.0.1:8000/docs` 查看 API 文档。视频生成需要在另一个终端、同一 `apps/api` 目录和虚拟环境中启动 Worker：

```powershell
python -m app.workers.generation
```

API 和 Worker 必须使用同一数据库及媒体目录。单机 SQLite 适合本地开发；云端部署使用 PostgreSQL。

## 云端部署

从仓库根目录复制并编辑环境文件：

```powershell
Copy-Item apps/api/.env.example apps/api/.env
```

至少设置独立的 `POSTGRES_PASSWORD`、长随机 `APP_API_TOKEN`，以及需要 Qwen 时使用的 `DASHSCOPE_API_KEY` 和 `DASHSCOPE_BASE_URL`。随后检查 `apps/api/config/gpu_nodes.json` 和 `workflows/comfyui/manifests/minimax_h3.json`，并导入实际可执行的 ComfyUI API 工作流。启动服务：

```powershell
docker compose --env-file apps/api/.env -f infra/compose/cloud.yml up -d --build
```

API 容器启动时自动执行数据库迁移。Compose 将 API 绑定到宿主机 `127.0.0.1:8000`；对外提供服务时需自行配置 HTTPS 反向代理和域名。ComfyUI 地址必须能从 Worker 所在网络访问，不应将未经认证的 ComfyUI 服务直接开放到公网。

## 配置说明

| 配置 | 位置 | 作用 |
| --- | --- | --- |
| FastAPI 地址和超时 | 桌面端「连接设置」；默认值在 `apps/desktop/src/main/defaults.json` | 决定桌面端连接哪个 API |
| 桌面端访问令牌 | 桌面端「连接设置」 | 由 Electron 主进程保管；系统加密可用时写入用户数据目录的 `token.bin` |
| 数据库、Qwen、鉴权和媒体目录 | `apps/api/.env`，参考 `apps/api/.env.example` | 配置 API 与 Worker |
| GPU 节点 | `apps/api/config/gpu_nodes.json` | 配置 ComfyUI 地址、支持的模型和启用状态 |
| 工作流节点映射 | `workflows/comfyui/manifests/minimax_h3.json` | 映射提示词、参考图、种子和输出节点 |
| 可执行工作流 | `workflows/comfyui/videos/minimax_h3/workflow_api.json` | 从 ComfyUI 导出的 **Workflow (API Format)** JSON |

仓库目前没有可执行的 `workflow_api.json`，示例 GPU 节点也默认禁用。完成工作流导出、节点映射和 GPU 配置之前，视频任务无法实际渲染。操作细节见 `workflows/comfyui/videos/minimax_h3/README.md`。

## 检查与打包

```powershell
# 仓库根目录
pnpm desktop:typecheck
pnpm desktop:build
pnpm desktop:dist:win
```

Windows 安装包输出到 `apps/desktop/release/`。后端测试在 `apps/api` 目录执行：

```powershell
python -m pytest -q
```

若本机因 Windows 符号链接权限无法解压打包工具，可先运行 `pnpm desktop:build`，再临时使用 `pnpm --filter @aidirector/desktop exec electron-builder --win nsis --config.win.signAndEditExecutable=false` 生成安装包；该选项会跳过可执行文件资源编辑。

## 当前限制

- 仅提供受控环境下的共享令牌认证，尚无多租户权限、账单隔离或完整审计体系。
- 尚无自动生图、视觉质检、2D 场景编辑和成片拼接。空间约束检查是规则级文本判定。
- Worker 初版按单实例顺序处理任务；多 Worker 的 GPU 容量管理和租约机制仍需完善。
- Vue 桌面端已通过类型检查、构建和基础界面启动检查；真实 Qwen 调用、ComfyUI 渲染、Docker/PostgreSQL 在线部署及 Windows 安装流程仍需在目标环境验收。

更多设计和部署说明见 `docs/architecture/DEPLOYMENT.md`。
