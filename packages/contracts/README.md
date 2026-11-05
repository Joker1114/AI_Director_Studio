# Shared contracts

运行时唯一接口契约来源是 FastAPI 的 OpenAPI：`https://<API_DOMAIN>/openapi.json`。
客户端 `src/renderer/lib/api.ts` 定义当前桌面版本所需的类型。
生产项目应在 CI 中自动从 OpenAPI 生成 TypeScript 类型，并以契约兼容性检查阻止不兼容 API 变更。

当前版本使用 `/api/v1`，原 `/api` 保留为临时兼容路径。
