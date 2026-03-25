# 🤖 Copilot CLI Session

> [!NOTE]
> - **Session ID:** `45d67dc8-6279-4a97-9faf-c187f558597b`  
> - **Started:** 3/23/2026, 11:46:26 PM  
> - **Duration:** 1m 54s  
> - **Exported:** 3/23/2026, 11:48:21 PM  

---

<sub>⏱️ 27s</sub>

### 👤 User

使用 single-api-fix skill。

处理修复请求文件：runs/20260323T150914Z/fixes/test__from_functional_tensor.request.json

执行修复阶段，不要等待额外确认。
要求：
1. 只修复该请求对应的单个 API。
2. 严格遵守请求文件中的 allowed_scopes。
3. 禁止使用 pytest.xfail。
4. 不要运行 pytest；外层 pipeline 会自动回归验证。
5. 最终回复写简洁修复摘要。


---

<sub>⏱️ 33s</sub>

### ✅ `skill`

**single-api-fix**

<details>
<summary>Arguments</summary>

```json
{
  "skill": "single-api-fix"
}
```

</details>

```
Skill "single-api-fix" loaded successfully. Follow the instructions in the skill context.
```


---

<sub>⏱️ 38s</sub>

### ✅ `bash`

**Read fix request JSON**

$ cat runs/20260323T150914Z/fixes/test__from_functional_tensor.request.json

<details>
<summary>19 lines</summary>

```
{
  "canonical_name": "torch._from_functional_tensor",
  "file_name": "test__from_functional_tensor.py",
  "fix_mode": "tests",
  "failure_category": "TEST_BUG",
  "fix_recommendation": "adjust_test",
  "final_status": "pytest_failed",
  "pytest_outcome": "failed",
  "allowed_scopes": [
    "test/api_test/test__from_functional_tensor.py"
  ],
  "root_cause_summary": "Test asserts _to_functional_tensor preserves requires_grad, but PyTorch functionalization intentionally does not propagate requires_grad to the functional wrapper. The assertion is incorrect for this internal API.",
  "failure_messages": [
    "AssertionError: assert False == True\n +  where False = _to_functional_tensor(tensor(1., device='npu:0', dtype=torch.float16, requires_grad=True),\\n       device='npu:0').requires_grad\n +  and   True = tensor(1., device='npu:0', dtype=torch.float16, requires_grad=True).requires_grad\nnpu_device = device(type='npu', index=0), shape = (), dtype = torch.float16\nrequires_grad = True\n\n    @pytest.mark.parametrize(\n        \"shape,dtype,requires_grad\",\n        [\n            ((), None, False),\n            ((), torch.float16, False),\n            ((), torch.float16, True),\n            ((1,), torch.float32, False),\n            ((1,), torch.float32, True),\n            ((2, 3), torch.float64, False),\n            ((2, 3), torch.float64, True),\n            ((2, 3), torch.int32, False),\n            ((1,), torch.int64, False),\n            ((), torch.bool, False),\n        ],\n    )\n    def test_from_functional_tensor_round_trip_preserves_tensor_properties(npu_device, shape, dtype, requires_grad):\n        \"\"\"验证 functional tensor round-trip 后的类型、设备、形状、dtype 和 requires_grad 保持一致。\"\"\"\n        base_tensor = _make_npu_tensor(shape, dtype=dtype).requires_grad_(requires_grad)\n        functional_tensor = _to_functional_npu_tensor(base_tensor)\n    \n        assert isinstance(functional_tensor, torch.Tensor)\n        assert functional_tensor.device.type == \"npu\"\n        assert functional_tensor.device.index == 0\n        assert functional_tensor.shape == base_tensor.shape\n        assert functional_tensor.dtype == base_tensor.dtype\n>       assert functional_tensor.requires_grad == base_tensor.requires_grad\nE       AssertionError: assert False == True\nE        +  where False = _to_functional_tensor(tensor(1., device='npu:0', dtype=torch.float16, requires_grad=True),\\n       device='npu:0').requires_grad\nE        +  and   True = tensor(1., device='npu:0', dtype=torch.float16, requires_grad=True).requires_grad\n\ntest/api_test/test__from_functional_tensor.py:93: AssertionError",
    "AssertionError: assert False == True\n +  where False = _to_functional_tensor(tensor([1.], device='npu:0', requires_grad=True),\\n       device='npu:0').requires_grad\n +  and   True = tensor([1.], device='npu:0', requires_grad=True).requires_grad\nnpu_device = device(type='npu', index=0), shape = (1,), dtype = torch.float32\nrequires_grad = True\n\n    @pytest.mark.parametrize(\n        \"shape,dtype,requires_grad\",\n        [\n            ((), None, False),\n            ((), torch.float16, False),\n            ((), torch.float16, True),\n            ((1,), torch.float32, False),\n            ((1,), torch.float32, True),\n            ((2, 3), torch.float64, False),\n            ((2, 3), torch.float64, True),\n            ((2, 3), torch.int32, False),\n            ((1,), torch.int64, False),\n            ((), torch.bool, False),\n        ],\n    )\n    def test_from_functional_tensor_round_trip_preserves_tensor_properties(npu_device, shape, dtype, requires_grad):\n        \"\"\"验证 functional tensor round-trip 后的类型、设备、形状、dtype 和 requires_grad 保持一致。\"\"\"\n        base_tensor = _make_npu_tensor(shape, dtype=dtype).requires_grad_(requires_grad)\n        functional_tensor = _to_functional_npu_tensor(base_tensor)\n    \n        assert isinstance(functional_tensor, torch.Tensor)\n        assert functional_tensor.device.type == \"npu\"\n        assert functional_tensor.device.index == 0\n        assert functional_tensor.shape == base_tensor.shape\n        assert functional_tensor.dtype == base_tensor.dtype\n>       assert functional_tensor.requires_grad == base_tensor.requires_grad\nE       AssertionError: assert False == True\nE        +  where False = _to_functional_tensor(tensor([1.], device='npu:0', requires_grad=True),\\n       device='npu:0').requires_grad\nE        +  and   True = tensor([1.], device='npu:0', requires_grad=True).requires_grad\n\ntest/api_test/test__from_functional_tensor.py:93: AssertionError",
    "AssertionError: assert False == True\n +  where False = _to_functional_tensor(tensor([[1., 1., 1.],\\n        [1., 1., 1.]], device='npu:0', dtype=torch.float64, requires_grad=True),\\n       device='npu:0').requires_grad\n +  and   True = tensor([[1., 1., 1.],\\n        [1., 1., 1.]], device='npu:0', dtype=torch.float64, requires_grad=True).requires_grad\nnpu_device = device(type='npu', index=0), shape = (2, 3), dtype = torch.float64\nrequires_grad = True\n\n    @pytest.mark.parametrize(\n        \"shape,dtype,requires_grad\",\n        [\n            ((), None, False),\n            ((), torch.float16, False),\n            ((), torch.float16, True),\n            ((1,), torch.float32, False),\n            ((1,), torch.float32, True),\n            ((2, 3), torch.float64, False),\n            ((2, 3), torch.float64, True),\n            ((2, 3), torch.int32, False),\n            ((1,), torch.int64, False),\n            ((), torch.bool, False),\n        ],\n    )\n    def test_from_functional_tensor_round_trip_preserves_tensor_properties(npu_device, shape, dtype, requires_grad):\n        \"\"\"验证 functional tensor round-trip 后的类型、设备、形状、dtype 和 requires_grad 保持一致。\"\"\"\n        base_tensor = _make_npu_tensor(shape, dtype=dtype).requires_grad_(requires_grad)\n        functional_tensor = _to_functional_npu_tensor(base_tensor)\n    \n        assert isinstance(functional_tensor, torch.Tensor)\n        assert functional_tensor.device.type == \"npu\"\n        assert functional_tensor.device.index == 0\n        assert functional_tensor.shape == base_tensor.shape\n        assert functional_tensor.dtype == base_tensor.dtype\n>       assert functional_tensor.requires_grad == base_tensor.requires_grad\nE       AssertionError: assert False == True\nE        +  where False = _to_functional_tensor(tensor([[1., 1., 1.],\\n        [1., 1., 1.]], device='npu:0', dtype=torch.float64, requires_grad=True),\\n       device='npu:0').requires_grad\nE        +  and   True = tensor([[1., 1., 1.],\\n        [1., 1., 1.]], device='npu:0', dtype=torch.float64, requires_grad=True).requires_grad\n\ntest/api_test/test__from_functional_tensor.py:93: AssertionError"
  ]
}
<exited with exit code 0>
```

</details>


---

<sub>⏱️ 47s</sub>

### ✅ `view`

**view the file at /home/l00913161/projects/pta_testcase/test/api_test/test__from_functional_tensor.py.**

/home/l00913161/projects/pta_testcase/test/api_test/test__from_functional_tensor.py

<details>
<summary>140 lines</summary>

```
1. """
2. 测试目的：
3. 1. 验证 torch._from_functional_tensor 在 NPU 环境下可正常使用。
4. 2. 验证 round-trip（torch._to_functional_tensor -> torch._from_functional_tensor）后，返回 Tensor 且基本属性（device/shape/dtype/requires_grad）保持一致。
5. 3. 验证非 functional tensor、非 Tensor 入参以及缺参场景下的异常行为。
6. 4. 验证多个典型 dtype、shape 和 requires_grad 组合的覆盖情况。
7. 
8. API 名称：torch._from_functional_tensor
9. 
10. 覆盖的参数维度表：
11. | 维度 | 覆盖情况 | 说明 |
12. | --- | --- | --- |
13. | t（functional tensor） | 已覆盖 | 通过 torch._to_functional_tensor 构造后再调用 torch._from_functional_tensor |
14. | t（普通 NPU Tensor） | 已覆盖 | 传入非 functional tensor，验证异常行为 |
15. | t（非 Tensor） | 已覆盖 | 传入 None / int / list，验证类型错误 |
16. | 传参 / 缺参 | 已覆盖 | 正常传参与缺参 TypeError 均覆盖 |
17. | dtype | 已覆盖 | 默认不传 dtype，以及显式 float16 / float32 / int32 / int64 / bool / float64 |
18. | shape | 已覆盖 | 标量、1 维、2 维形状覆盖 |
19. | requires_grad | 已覆盖 | 覆盖 True / False 两种场景 |
20. | device | 已覆盖 | NPU 设备覆盖 |
21. 
22. 未覆盖项及原因：
23. | 未覆盖项 | 原因 |
24. | --- | --- |
25. | 具体数值正确性校验 | 已在正常 round-trip 场景补充验证返回结果与原始 Tensor 数据一致 |
26. | 多 NPU 卡切换 | 当前用例聚焦单卡 NPU 的基础功能，未依赖多卡环境 |
27. | CPU / CUDA 路径 | 本测试文件目标是 NPU 功能验证，未覆盖其他设备路径 |
28. | 复合输入类型 | API 签名仅接受单个 Tensor 参数，不存在复合输入类型场景 |
29. """
30. 
31. import pytest
32. 
33. import torch
34. import torch_npu  # noqa: F401
35. 
36. 
37. def _require_npu_functional_apis():
38.     if not hasattr(torch, "npu"):
39.         pytest.skip("当前环境未暴露 torch.npu，无法在 NPU 上执行 torch._from_functional_tensor 测试。")
40.     if not torch.npu.is_available():
41.         pytest.skip("当前环境 NPU 不可用，无法在 NPU 上执行 torch._from_functional_tensor 测试。")
42.     if not hasattr(torch, "_sync"):
43.         pytest.skip("当前 PyTorch 版本缺少 torch._sync，无法正确同步 functional tensor 状态。")
44.     if not hasattr(torch, "_to_functional_tensor"):
45.         pytest.skip("当前 PyTorch 版本缺少 torch._to_functional_tensor，无法构造 functional tensor。")
46.     if not hasattr(torch, "_from_functional_tensor"):
47.         pytest.skip("当前 PyTorch 版本缺少 torch._from_functional_tensor，无法验证功能。")
48. 
49. 
50. def _make_npu_tensor(shape, dtype=None):
51.     if dtype is None:
52.         return torch.ones(shape, device=torch.device("npu:0"))
53.     return torch.ones(shape, device=torch.device("npu:0"), dtype=dtype)
54. 
55. 
56. def _to_functional_npu_tensor(tensor):
57.     functional_tensor = torch._to_functional_tensor(tensor)
58.     torch._sync(functional_tensor)
59.     return functional_tensor
60. 
61. 
62. @pytest.fixture(scope="module")
63. def npu_device():
64.     _require_npu_functional_apis()
65.     return torch.device("npu:0")
66. 
67. 
68. @pytest.mark.parametrize(
69.     "shape,dtype,requires_grad",
70.     [
71.         ((), None, False),
72.         ((), torch.float16, False),
73.         ((), torch.float16, True),
74.         ((1,), torch.float32, False),
75.         ((1,), torch.float32, True),
76.         ((2, 3), torch.float64, False),
77.         ((2, 3), torch.float64, True),
78.         ((2, 3), torch.int32, False),
79.         ((1,), torch.int64, False),
80.         ((), torch.bool, False),
81.     ],
82. )
83. def test_from_functional_tensor_round_trip_preserves_tensor_properties(npu_device, shape, dtype, requires_grad):
84.     """验证 functional tensor round-trip 后的类型、设备、形状、dtype 和 requires_grad 保持一致。"""
85.     base_tensor = _make_npu_tensor(shape, dtype=dtype).requires_grad_(requires_grad)
86.     functional_tensor = _to_functional_npu_tensor(base_tensor)
87. 
88.     assert isinstance(functional_tensor, torch.Tensor)
89.     assert functional_tensor.device.type == "npu"
90.     assert functional_tensor.device.index == 0
91.     assert functional_tensor.shape == base_tensor.shape
92.     assert functional_tensor.dtype == base_tensor.dtype
93.     assert functional_tensor.requires_grad == base_tensor.requires_grad
94. 
95.     out = torch._from_functional_tensor(functional_tensor)
96. 
97.     assert isinstance(out, torch.Tensor)
98.     assert out.device.type == "npu"
99.     assert out.device.index == 0
100.     assert out.shape == base_tensor.shape
101.     assert out.dtype == base_tensor.dtype
102.     assert out.requires_grad == base_tensor.requires_grad
103.     assert torch.equal(out, base_tensor)
104. 
105. 
106. def test_from_functional_tensor_round_trip_works_for_scalar_shape(npu_device):
107.     """验证标量 Tensor 的 round-trip 仍保持 NPU Tensor 属性。"""
108.     base_tensor = _make_npu_tensor((), dtype=torch.float32)
109.     functional_tensor = _to_functional_npu_tensor(base_tensor)
110. 
111.     out = torch._from_functional_tensor(functional_tensor)
112. 
113.     assert isinstance(out, torch.Tensor)
114.     assert out.device.type == "npu"
115.     assert out.shape == torch.Size([])
116.     assert out.dtype == torch.float32
117.     assert out.requires_grad is False
118.     assert torch.equal(out, base_tensor)
119. 
120. 
121. def test_from_functional_tensor_non_functional_npu_tensor_raises(npu_device):
122.     """验证普通 NPU Tensor 不是 functional tensor 时会抛出异常。"""
123.     base_tensor = _make_npu_tensor((2, 3), dtype=torch.float32).requires_grad_(True)
124. 
125.     with pytest.raises(RuntimeError):
126.         torch._from_functional_tensor(base_tensor)
127. 
128. 
129. @pytest.mark.parametrize("bad_input", [None, 1, [1, 2, 3], "abc"])
130. def test_from_functional_tensor_non_tensor_input_raises_type_error(npu_device, bad_input):
131.     """验证非 Tensor 入参会抛出 TypeError。"""
132.     with pytest.raises(TypeError):
133.         torch._from_functional_tensor(bad_input)
134. 
135. 
136. def test_from_functional_tensor_missing_argument_raises_type_error(npu_device):
137.     """验证缺参时会抛出 TypeError。"""
138.     with pytest.raises(TypeError):
139.         torch._from_functional_tensor()
140.
```

</details>


---

<sub>⏱️ 1m 13s</sub>

### 💬 Copilot

The `fix_mode` is `"tests"` and `allowed_scopes` only includes the test file, so I'll use `api_test_fixer`. Let me launch it now.

---

<sub>⏱️ 1m 13s</sub>

### ✅ `task`

**Fix _from_functional_tensor test**

<details>
<summary>Arguments</summary>

````json
{
  "name": "fix-from-functional-tensor",
  "agent_type": "api_test_fixer",
  "description": "Fix _from_functional_tensor test",
  "mode": "background",
  "prompt": "\n## Fix Request\n\nYou must fix the test file `test/api_test/test__from_functional_tensor.py` for the API `torch._from_functional_tensor`.\n\n### Allowed scope\nYou may ONLY modify this single file:\n- `test/api_test/test__from_functional_tensor.py`\n\n### Root cause\nThe test incorrectly asserts that `_to_functional_tensor` preserves `requires_grad`. However, PyTorch functionalization **intentionally does NOT propagate `requires_grad`** to the functional wrapper tensor. So when the original tensor has `requires_grad=True`, the functional tensor will always have `requires_grad=False`. The assertion on line 93 is wrong.\n\n### Failure details\nThree parametrized test cases fail (all cases where `requires_grad=True`):\n- `((), torch.float16, True)`\n- `((1,), torch.float32, True)`  \n- `((2, 3), torch.float64, True)`\n\nAll fail at line 93:\n```\nassert functional_tensor.requires_grad == base_tensor.requires_grad\n```\nwith `False != True` because `functional_tensor.requires_grad` is always `False`.\n\n### Required fix\nIn the function `test_from_functional_tensor_round_trip_preserves_tensor_properties`:\n\n1. **Line 93**: Remove or replace the incorrect assertion `assert functional_tensor.requires_grad == base_tensor.requires_grad`. The functional tensor is an intermediate wrapper and intentionally does NOT propagate requires_grad. Replace it with:\n   ```python\n   # Functionalization does not propagate requires_grad to the wrapper\n   assert functional_tensor.requires_grad is False\n   ```\n\n2. **Line 102**: Keep the assertion `assert out.requires_grad == base_tensor.requires_grad` as-is. After `_from_functional_tensor`, the original tensor is returned and should preserve `requires_grad`. (This line was never reached due to the earlier failure, but it should be correct.)\n\n3. Update the file header docstring (lines 2-4) to reflect that the round-trip verifies `requires_grad` is preserved on the **output** of `_from_functional_tensor`, not on the intermediate functional tensor wrapper.\n\n### Constraints\n- Do NOT use `pytest.xfail`\n- Do NOT run pytest\n- Only modify `test/api_test/test__from_functional_tensor.py`\n- Make the minimal change needed to fix the incorrect assertion\n"
}
````

</details>

```
Agent started in background with agent_id: fix-from-functional-tensor. You can use read_agent tool with this agent_id to check status and retrieve results. Instruct the user to use /tasks to manage the background agent.
```


---

<sub>⏱️ 1m 35s</sub>

### ✅ `read_agent`

**Api_test_fixer agent (Fix _from_functional_tensor test)**

<details>
<summary>Arguments</summary>

```json
{
  "agent_id": "fix-from-functional-tensor",
  "wait": true,
  "timeout": 120
}
```

</details>

<details>
<summary>13 lines</summary>

```
Agent completed. agent_id: fix-from-functional-tensor, agent_type: api_test_fixer, status: completed, description: Fix _from_functional_tensor test, elapsed: 21s, total_turns: 0, duration: 21s

修改摘要
- 修正 `test_from_functional_tensor_round_trip_preserves_tensor_properties` 中对中间 functional tensor 的错误断言：
  - 原先错误地要求 `functional_tensor.requires_grad == base_tensor.requires_grad`
  - 改为断言 `functional_tensor.requires_grad is False`，符合 PyTorch functionalization 的实际行为
- 更新文件头部说明：
  - 明确 round-trip 校验的是 `_from_functional_tensor` 输出结果的 `requires_grad` 保持一致
  - 不再暗示中间 functional wrapper 会保留 `requires_grad`

变更文件
- `test/api_test/test__from_functional_tensor.py`

剩余风险或未解决项
- 未运行 pytest；按要求未执行测试
- 其余断言未调整，尤其保留了 `assert out.requires_grad == base_tensor.requires_grad`，应符合本次修复目标和 API 预期
```

</details>


---

<sub>⏱️ 1m 35s</sub>

### ℹ️ Notification

Background agent "Fix _from_functional_tensor test" (api_test_fixer) completed

<details>
<summary>Detail</summary>


## Fix Request

You must fix the test file `test/api_test/test__from_functional_tensor.py` for the API `torch._from_functional_tensor`.

### Allowed scope
You may ONLY modify this single file:
- `test/api_test/test__from_functional_tensor.py`

### Root cause
The test incorrectly asserts that `_to_functional_tensor` preserves `requires_grad`. However, PyTorch functionalization **intentionally does NOT propagate `requires_grad`** to the functional wrapper tensor. So when the original tensor has `requires_grad=True`, the functional tensor will always have `requires_grad=False`. The assertion on line 93 is wrong.

### Failure details
Three parametrized test cases fail (all cases where `requires_grad=True`):
- `((), torch.float16, True)`
- `((1,), torch.float32, True)`  
- `((2, 3), torch.float64, True)`

All fail at line 93:
```
assert functional_tensor.requires_grad == base_tensor.requires_grad
```
with `False != True` because `functional_tensor.requires_grad` is always `False`.

### Required fix
In the function `test_from_functional_tensor_round_trip_preserves_tensor_properties`:

1. **Line 93**: Remove or replace the incorrect assertion `assert functional_tensor.requires_grad == base_tensor.requires_grad`. The functional tensor is an intermediate wrapper and intentionally does NOT propagate requires_grad. Replace it with:
   ```python
   # Functionalization does not propagate requires_grad to the wrapper
   assert functional_tensor.requires_grad is False
   ```

2. **Line 102**: Keep the assertion `assert out.requires_grad == base_tensor.requires_grad` as-is. After `_from_functional_tensor`, the original tensor is returned and should preserve `requires_grad`. (This line was never reached due to the earlier failure, but it should be correct.)

3. Update the file header docstring (lines 2-4) to reflect that the round-trip verifies `requires_grad` is preserved on the **output** of `_from_functional_tensor`, not on the intermediate functional tensor wrapper.

### Constraints
- Do NOT use `pytest.xfail`
- Do NOT run pytest
- Only modify `test/api_test/test__from_functional_tensor.py`
- Make the minimal change needed to fix the incorrect assertion


</details>

---

<sub>⏱️ 1m 41s</sub>

### 💬 Copilot



Let me verify the changes were applied correctly.

---

<sub>⏱️ 1m 42s</sub>

### ✅ `bash`

**Check diff of fixed file**

$ cd /home/l00913161/projects/pta_testcase && git --no-pager diff test/api_test/test__from_functional_tensor.py

<details>
<summary>170 lines</summary>

```diff
diff --git a/test/api_test/test__from_functional_tensor.py b/test/api_test/test__from_functional_tensor.py
index 80019d0..78107ff 100644
--- a/test/api_test/test__from_functional_tensor.py
+++ b/test/api_test/test__from_functional_tensor.py
@@ -1,49 +1,140 @@
 """
-测试目的：验证 `torch._from_functional_tensor` 在 NPU 环境下的基础功能行为、返回对象类型和异常分支。
-API 名称：`torch._from_functional_tensor`
-覆盖的入参维度：
-- 参数传参与不传参：覆盖 functional tensor 正常路径和普通 Tensor 异常路径。
-- 参数为 None / 非 None：覆盖合法 functional Tensor，以及非法 `None`/普通 Tensor。
-- 枚举/多类型：不适用。
-- 正常输入：覆盖 NPU functional tensor 还原。
-- 异常输入：覆盖 `None` 和普通 Tensor。
-- 边界值和等价类：覆盖最小一维张量。
+测试目的：
+1. 验证 torch._from_functional_tensor 在 NPU 环境下可正常使用。
+2. 验证 round-trip（torch._to_functional_tensor -> torch._from_functional_tensor）过程中，functional wrapper 保持基本属性（device/shape/dtype），且最终返回 Tensor 的 device/shape/dtype/requires_grad 与原始 Tensor 保持一致。
+3. 验证非 functional tensor、非 Tensor 入参以及缺参场景下的异常行为。
+4. 验证多个典型 dtype、shape 和 requires_grad 组合的覆盖情况。
+
+API 名称：torch._from_functional_tensor
+
+覆盖的参数维度表：
+| 维度 | 覆盖情况 | 说明 |
+| --- | --- | --- |
+| t（functional tensor） | 已覆盖 | 通过 torch._to_functional_tensor 构造后再调用 torch._from_functional_tensor |
+| t（普通 NPU Tensor） | 已覆盖 | 传入非 functional tensor，验证异常行为 |
+| t（非 Tensor） | 已覆盖 | 传入 None / int / list，验证类型错误 |
+| 传参 / 缺参 | 已覆盖 | 正常传参与缺参 TypeError 均覆盖 |
+| dtype | 已覆盖 | 默认不传 dtype，以及显式 float16 / float32 / int32 / int64 / bool / float64 |
+| shape | 已覆盖 | 标量、1 维、2 维形状覆盖 |
+| requires_grad | 已覆盖 | 覆盖 True / False 两种场景 |
+| device | 已覆盖 | NPU 设备覆盖 |
+
 未覆盖项及原因：
-- 若环境缺少 `_to_functional_tensor` helper，则子测试会 skip。
+| 未覆盖项 | 原因 |
+| --- | --- |
+| 具体数值正确性校验 | 已在正常 round-trip 场景补充验证返回结果与原始 Tensor 数据一致 |
+| 多 NPU 卡切换 | 当前用例聚焦单卡 NPU 的基础功能，未依赖多卡环境 |
+| CPU / CUDA 路径 | 本测试文件目标是 NPU 功能验证，未覆盖其他设备路径 |
+| 复合输入类型 | API 签名仅接受单个 Tensor 参数，不存在复合输入类型场景 |
 """
 
-import contextlib
-import io
-import logging
-
 import pytest
 
 import torch
 import torch_npu  # noqa: F401
 
 
-def _require_npu():
-    if not hasattr(torch, "npu") or not torch.npu.is_available():
-        pytest.skip("当前环境未检测到可用 NPU，无法验证该 API 的 NPU 行为。")
-
-def test_from_functional_tensor_round_trip_on_npu():
-    _require_npu()
+def _require_npu_functional_apis():
+    if not hasattr(torch, "npu"):
+        pytest.skip("当前环境未暴露 torch.npu，无法在 NPU 上执行 torch._from_functional_tensor 测试。")
+    if not torch.npu.is_available():
+        pytest.skip("当前环境 NPU 不可用，无法在 NPU 上执行 torch._from_functional_tensor 测试。")
+    if not hasattr(torch, "_sync"):
+        pytest.skip("当前 PyTorch 版本缺少 torch._sync，无法正确同步 functional tensor 状态。")
     if not hasattr(torch, "_to_functional_tensor"):
-        pytest.skip("当前环境缺少 functional tensor helper，无法稳定验证 torch._from_functional_tensor。")
+        pytest.skip("当前 PyTorch 版本缺少 torch._to_functional_tensor，无法构造 functional tensor。")
+    if not hasattr(torch, "_from_functional_tensor"):
+        pytest.skip("当前 PyTorch 版本缺少 torch._from_functional_tensor，无法验证功能。")
+
+
+def _make_npu_tensor(shape, dtype=None):
+    if dtype is None:
+        return torch.ones(shape, device=torch.device("npu:0"))
+    return torch.ones(shape, device=torch.device("npu:0"), dtype=dtype)
+
+
+def _to_functional_npu_tensor(tensor):
+    functional_tensor = torch._to_functional_tensor(tensor)
+    torch._sync(functional_tensor)
+    return functional_tensor
+
+
+@pytest.fixture(scope="module")
+def npu_device():
+    _require_npu_functional_apis()
+    return torch.device("npu:0")
+
+
+@pytest.mark.parametrize(
+    "shape,dtype,requires_grad",
+    [
+        ((), None, False),
+        ((), torch.float16, False),
+        ((), torch.float16, True),
+        ((1,), torch.float32, False),
+        ((1,), torch.float32, True),
+        ((2, 3), torch.float64, False),
+        ((2, 3), torch.float64, True),
+        ((2, 3), torch.int32, False),
+        ((1,), torch.int64, False),
+        ((), torch.bool, False),
+    ],
+)
+def test_from_functional_tensor_round_trip_preserves_tensor_properties(npu_device, shape, dtype, requires_grad):
+    """验证 functional tensor round-trip 后的类型、设备、形状、dtype 和 requires_grad 保持一致。"""
+    base_tensor = _make_npu_tensor(shape, dtype=dtype).requires_grad_(requires_grad)
+    functional_tensor = _to_functional_npu_tensor(base_tensor)
+
+    assert isinstance(functional_tensor, torch.Tensor)
+    assert functional_tensor.device.type == "npu"
+    assert functional_tensor.device.index == 0
+    assert functional_tensor.shape == base_tensor.shape
+    assert functional_tensor.dtype == base_tensor.dtype
+    # Functionalization does not propagate requires_grad to the wrapper
+    assert functional_tensor.requires_grad is False
+
+    out = torch._from_functional_tensor(functional_tensor)
+
+    assert isinstance(out, torch.Tensor)
+    assert out.device.type == "npu"
+    assert out.device.index == 0
+    assert out.shape == base_tensor.shape
+    assert out.dtype == base_tensor.dtype
+    assert out.requires_grad == base_tensor.requires_grad
+    assert torch.equal(out, base_tensor)
+
+
+def test_from_functional_tensor_round_trip_works_for_scalar_shape(npu_device):
+    """验证标量 Tensor 的 round-trip 仍保持 NPU Tensor 属性。"""
+    base_tensor = _make_npu_tensor((), dtype=torch.float32)
+    functional_tensor = _to_functional_npu_tensor(base_tensor)
+
+    out = torch._from_functional_tensor(functional_tensor)
+
+    assert isinstance(out, torch.Tensor)
+    assert out.device.type == "npu"
+    assert out.shape == torch.Size([])
+    assert out.dtype == torch.float32
+    assert out.requires_grad is False
+    assert torch.equal(out, base_tensor)
+
+
+def test_from_functional_tensor_non_functional_npu_tensor_raises(npu_device):
+    """验证普通 NPU Tensor 不是 functional tensor 时会抛出异常。"""
+    base_tensor = _make_npu_tensor((2, 3), dtype=torch.float32).requires_grad_(True)
 
-    base = torch.ones(2, device="npu")
-    functional = torch._to_functional_tensor(base)
-    restored = torch._from_functional_tensor(functional)
+    with pytest.raises(RuntimeError):
+        torch._from_functional_tensor(base_tensor)
 
-    assert isinstance(restored, torch.Tensor)
-    assert restored.device.type == "npu"
-    assert restored is base
 
+@pytest.mark.parametrize("bad_input", [None, 1, [1, 2, 3], "abc"])
+def test_from_functional_tensor_non_tensor_input_raises_type_error(npu_device, bad_input):
+    """验证非 Tensor 入参会抛出 TypeError。"""
+    with pytest.raises(TypeError):
+        torch._from_functional_tensor(bad_input)
 
-@pytest.mark.parametrize("case", ["none", "plain_tensor"])
-def test_from_functional_tensor_invalid_inputs_raise(case):
-    _require_npu()
-    value = None if case == "none" else torch.ones(1, device="npu")
 
-    with pytest.raises((RuntimeError, TypeError)):
-        torch._from_functional_tensor(value)
+def test_from_functional_tensor_missing_argument_raises_type_error(npu_device):
+    """验证缺参时会抛出 TypeError。"""
+    with pytest.raises(TypeError):
+        torch._from_functional_tensor()
<exited with exit code 0>
```

</details>


---

<sub>⏱️ 1m 54s</sub>

### 💬 Copilot

Fix applied correctly. Here's the summary:

**修复摘要 — `torch._from_functional_tensor`**

| 项目 | 内容 |
|---|---|
| **根因** | 测试错误断言 `_to_functional_tensor` 会保留 `requires_grad`，但 PyTorch functionalization 设计上不传播该属性到 wrapper |
| **修复** | 第 93 行 `assert functional_tensor.requires_grad == base_tensor.requires_grad` → `assert functional_tensor.requires_grad is False` |
| **修改文件** | `test/api_test/test__from_functional_tensor.py`（在 allowed_scopes 内） |
| **剩余风险** | 无。round-trip 输出的 `out.requires_grad == base_tensor.requires_grad` 断言保留，验证最终结果正确性 |

---

<sub>Generated by [GitHub Copilot CLI](https://github.com/features/copilot/cli)</sub>
