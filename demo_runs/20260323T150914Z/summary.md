# 流水线摘要：20260323T150914Z

- 输入：`apis.txt`
- 进度 CSV：`runs/20260323T150914Z/manifest.csv`
- 修复模式：`tests`
- 运行命令：`/usr/local/python3.11.14/bin/python -m scripts.pipeline run --input apis.txt --fix-mode tests --cli-backend copilot --report-dir /home/l00913161/projects/pta_testcase/runs`
- API 总数：`53`
- 结果 JSON：`runs/20260323T150914Z/results.json`
- 结果 CSV：`runs/20260323T150914Z/results.csv`
- 汇总表 CSV：`runs/20260323T150914Z/summary_table.csv`
- **最终交付报告**：`runs/20260323T150914Z/final_verdict.md`
- 最终交付 CSV：`runs/20260323T150914Z/final_verdict.csv`
- 生成摘要：`runs/20260323T150914Z/generation_summary.md`
- 分析摘要：`runs/20260323T150914Z/analysis_summary.md`

## 状态统计
- `analyzed`: 3
- `fixed`: 3
- `pytest_passed`: 47

## 失败类别
- `NONE`: 50
- `UNKNOWN`: 3

## 已修复 API
- `Tensor.new_zeros`: 初始分类 `TEST_BUG` -> `test/api_test`；重跑结果 `pytest_passed`；变更文件：test/api_test/test_Tensor_new_zeros.py
- `torch.nn.Parameter.device`: 初始分类 `TEST_BUG` -> `test/api_test`；重跑结果 `pytest_passed`；变更文件：test/api_test/test_nn_Parameter_device.py
- `torch._from_functional_tensor`: 初始分类 `TEST_BUG` -> `test/api_test`；重跑结果 `pytest_passed`；变更文件：test/api_test/test__from_functional_tensor.py

## 仍有问题的 API
- 无

## 跳过的 API
- 无

## 通过的 API
- 数量：50

## 需要人工介入
> 在 `summary_table.csv` 中筛选 `Intervention Type == human_required` 即可获得此列表。
- `torch.nn.Parameter.device.type`：原因=`unknown_failure` 类别=`UNKNOWN`
- `torch._dynamo.compiled_autograd.compiled_autograd_enabled_force_eager`：原因=`unknown_failure` 类别=`UNKNOWN`
- `torch._dynamo.config.skip_fsdp_hooks`：原因=`unknown_failure` 类别=`UNKNOWN`

## 建议 AI 代理重试
> 在 `summary_table.csv` 中筛选 `Intervention Type == agent_retry` 即可获得此列表。
- 无
