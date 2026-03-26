---
name: batch-npu-api-test
description: 
  批量处理 PyTorch API 的 NPU 功能测试生成任务。当输入是 api_manifest.csv
  或者用户要求批量生成/审查/修复 test/api_test 下的 API 测试文件时使用。
---

你负责执行完整的批处理流水线，不要要求用户分步下达指令。

输入：
- 一个 CSV 文件路径，CSV 至少包含：
  - canonical_name
  - file_name
  - status
  - notes

工作流：
1. 读取 CSV 中 status=pending 的行。
2. 对每一行启动一个 api_test_generator 子代理并行生成测试文件。
   - **重要**：如果 pipeline 提示了 api_context 目录，在启动 generator 前，
     读取 `api_context/{canonical_name 中 . 替换为 _}.json` 文件，将其中的
     `doc`（API 文档、签名、参数说明、示例代码）和 `test_references`（上游参考测试片段）
     作为上下文传递给 generator 子代理的 prompt。
3. 等待全部 generator 完成，收集生成结果。
4. 对新生成或修改过的测试文件启动 api_test_reviewer 子代理并行审查。
   - reviewer 同样应接收 API 上下文信息以判断覆盖完整性。
5. 对 reviewer 判定为不通过的文件，进行最小修复：
   - 启动 api_test_fixer 子代理处理单文件修复
   - 只修复失败项
   - 不重写已通过文件
   - 不改动 test/api_test 之外的业务代码
6. 对本次触达的测试文件运行 pytest。
7. 输出最终汇总：
   - 成功生成并通过的 API
   - 经修复后通过的 API
   - 仍失败 / skip 的 API 及原因
   - 明显未覆盖项

约束：
- 所有测试文件必须位于 test/api_test/
- 文件名必须使用 CSV 中的 file_name
- 测试必须运行在 NPU 上，使用 torch_npu
- 关注功能行为和接口覆盖，不做数值精度校验
- 异常场景必须使用 pytest.raises
- 禁止使用 pytest.xfail/pytest.skip 来掩盖测试失败
- **严禁**对"NPU 后端不支持某功能"使用 pytest.skip——让测试自然失败
- 文件头注释必须写明测试目的、API 名称、覆盖入参
  例如：
  ```
  """
  测试目的：验证 Tensor.new_zeros 在 NPU 上的接口可调用性、返回类型与异常分支，覆盖默认/显式参数、None/非 None、主要枚举、主要类型与边界场景。
  API 名称：Tensor.new_zeros
  覆盖参数维度：
  | 维度 | 覆盖方式 |
  | --- | --- |
  ...
  """

