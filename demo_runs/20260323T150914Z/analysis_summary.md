# 分析摘要：20260323T150914Z

- 修复模式：`tests`
- 输入文件：`runs/20260323T150914Z/analysis_inputs.json`
- 分诊 JSON：`runs/20260323T150914Z/analysis_triage.json`
- AI 代理备注：`runs/20260323T150914Z/analysis_agent.md`

## 可自动修复候选
- `Tensor.new_zeros`: `TEST_BUG` -> `adjust_test`; Test expects TypeError for device=123 but NPU runtime raises RuntimeError (invalid device ID). The pytest.raises(TypeError) catches the wrong exception type.
- `torch.nn.Parameter.device`: `TEST_BUG` -> `adjust_test`; Test asserts param.to(npu_device) returns nn.Parameter, but PyTorch Parameter.to() returns a plain Tensor (with grad_fn) when moving to a different device. The isinstance check is an incorrect assumption about .to() semantics.
- `torch._from_functional_tensor`: `TEST_BUG` -> `adjust_test`; Test asserts _to_functional_tensor preserves requires_grad, but PyTorch functionalization intentionally does not propagate requires_grad to the functional wrapper. The assertion is incorrect for this internal API.

## 仅报告（不自动修复）失败
- 无
