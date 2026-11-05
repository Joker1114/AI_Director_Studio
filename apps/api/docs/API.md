# 云端 REST API V1.1

接口前缀：`/api/v1`。旧版 `/api` 仅为过渡期兼容，不作为新客户端契约。

鉴权：除 health 之外，添加 `X-API-Token: <APP_API_TOKEN>`。正式云端强制 HTTPS。

| 方法 | 地址 | 功能 |
|---|---|---|
| GET | `/health` | 健康状态（不需要令牌） |
| POST | `/projects` | 创建项目 |
| GET | `/projects` | 获取项目列表 |
| POST | `/projects/{id}/scripts` | 保存新版本剧本 |
| POST | `/scripts/{id}/extract` | 调用 Qwen 抽取资产候选 |
| GET | `/scripts/{id}/extraction` | 获取候选/事件 |
| POST | `/candidates/{id}/approve` | 审核候选为正式资产 |
| GET | `/projects/{id}/assets` | 获取角色场景道具 |
| PATCH | `/assets/{id}` | 保存资产事实与锁定字段 |
| POST | `/assets/{id}/image-prompts` | 调用 Qwen 润色生图提示词 |
| POST | `/assets/{id}/references` | 上传参考图 multipart/form-data |
| POST | `/references/{id}/review` | 审核参考图 |
| POST | `/scripts/{id}/storyboard` | Qwen 生成结构化分镜 |
| PATCH | `/shots/{id}` | 修改镜头与参考图绑定 `reference_ids` |
| GET | `/shots/{id}/validate` | 检查结构化空间约束 |
| POST | `/shots/{id}/prompts` | 润色首帧/H3 视频提示词 |
| POST | `/prompts/{id}/review` | 审核提示词 |
| GET | `/gpu-nodes` | 当前已配置 GPU 节点 |
| GET | `/workflows` | 工作流准备状态 |
| POST | `/generation-jobs` | 提交视频生成任务 |
| GET | `/projects/{id}/generation-jobs` | 项目视频任务列表 |
| GET | `/generation-jobs/{id}` | 查询单任务 |
| POST | `/generation-jobs/{id}/retry` | 重试失败任务 |
| GET | `/generation-jobs/{id}/files/{index}` | 下载生成结果 |

参数及响应字段请以 FastAPI `/openapi.json`、`/docs` 为准。
