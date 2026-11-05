# MiniMax H3 工作流配置

这里**未附带可执行的 `workflow_api.json`**：此前提供的是 ComfyUI 编辑器格式 JSON，不能直接传给 `/prompt`。
请在可正常运行的 ComfyUI 中导出 **Workflow (API Format)**，保存为本目录 `workflow_api.json`。

再核对 `../../manifests/minimax_h3.json` 中的：
- `prompt_node` 及 `prompt_field`：接收最终 H3 提示词的节点输入。
- `image_load_nodes`：按 `<Picture 1>`、`<Picture 2>`、`<Picture 3>` 顺序所连的 LoadImage 节点 ID。
- `seed_bindings`：实际可编辑的种子输入。
- `output_nodes`：实际写出 MP4/视频文件的节点 ID。

导出节点 ID/字段可能与编辑器版不同，需以 API JSON 为准。未完成映射时提交将明确报错，不应把它标记为可执行。
