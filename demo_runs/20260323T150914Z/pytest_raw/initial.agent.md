# 🤖 Copilot CLI Session

> [!NOTE]
> - **Session ID:** `74db837f-8c68-4df1-8047-a898d6bd880b`  
> - **Started:** 3/23/2026, 11:35:16 PM  
> - **Duration:** 2m 4s  
> - **Exported:** 3/23/2026, 11:37:20 PM  

---

<sub>⏱️ 29s</sub>

### 👤 User

        执行 pytest 阶段，不要修改任何源码、测试文件或文档。

        阶段标签: initial
        你必须运行下面这段 bash 脚本，完整保留 pytest 的 stdout/stderr 和 return code。

        ```bash
        mkdir -p /home/l00913161/projects/pta_testcase/runs/20260323T150914Z/pytest_raw
cat \<\<'EOF' \> /home/l00913161/projects/pta_testcase/runs/20260323T150914Z/pytest_raw/initial.command.txt
/usr/local/python3.11.14/bin/python -m pytest -q --junitxml /home/l00913161/projects/pta_testcase/runs/20260323T150914Z/pytest_raw/initial_junit.xml /home/l00913161/projects/pta_testcase/test/api_test/test_Tensor_new_empty.py /home/l00913161/projects/pta_testcase/test/api_test/test_Tensor_new_zeros.py /home/l00913161/projects/pta_testcase/test/api_test/test_Tensor_register_hook.py /home/l00913161/projects/pta_testcase/test/api_test/test_Tensor_requires_grad.py /home/l00913161/projects/pta_testcase/test/api_test/test_Tensor_untyped_storage.py /home/l00913161/projects/pta_testcase/test/api_test/test___future___get_swap_module_params_on_conversion.py /home/l00913161/projects/pta_testcase/test/api_test/test__sync.py /home/l00913161/projects/pta_testcase/test/api_test/test_autograd_Variable__execution_engine_queue_callback.py /home/l00913161/projects/pta_testcase/test/api_test/test_compiler_is_compiling.py /home/l00913161/projects/pta_testcase/test/api_test/test_dtype.py /home/l00913161/projects/pta_testcase/test/api_test/test_Event.py /home/l00913161/projects/pta_testcase/test/api_test/test_library_impl.py /home/l00913161/projects/pta_testcase/test/api_test/test_library_Library.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Module_buffers.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Module_modules.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Module_named_modules.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Module_named_parameters.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Module_register_forward_hook.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Module_register_forward_pre_hook.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Module_register_load_state_dict_post_hook.py /home/l00913161/projects/pta_testcase/test/api_test/test_utils__pytree_tree_flatten.py /home/l00913161/projects/pta_testcase/test/api_test/test_utils__pytree_tree_map.py /home/l00913161/projects/pta_testcase/test/api_test/test_utils__pytree_tree_unflatten.py /home/l00913161/projects/pta_testcase/test/api_test/test_utils_swap_tensors.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Parameter_grad.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Parameter_device.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Parameter_device_type.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Parameter_is_contiguous.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Parameter_ndim.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Parameter_size.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Parameter_stride.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Parameter_dtype.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Parameter_itemsize.py /home/l00913161/projects/pta_testcase/test/api_test/test_autograd__unsafe_preserve_version_counter.py /home/l00913161/projects/pta_testcase/test/api_test/test_library.py /home/l00913161/projects/pta_testcase/test/api_test/test__dynamo_compiled_autograd_compiled_autograd_enabled.py /home/l00913161/projects/pta_testcase/test/api_test/test__dynamo_compiled_autograd_compiled_autograd_enabled_force_eager.py /home/l00913161/projects/pta_testcase/test/api_test/test__dynamo_compiled_autograd_in_compiled_autograd_region.py /home/l00913161/projects/pta_testcase/test/api_test/test__running_with_deploy.py /home/l00913161/projects/pta_testcase/test/api_test/test_utils__python_dispatch_is_traceable_wrapper_subclass.py /home/l00913161/projects/pta_testcase/test/api_test/test__dynamo_comptime_comptime_print.py /home/l00913161/projects/pta_testcase/test/api_test/test__dynamo_config.py /home/l00913161/projects/pta_testcase/test/api_test/test__dynamo_config_skip_fsdp_hooks.py /home/l00913161/projects/pta_testcase/test/api_test/test__C_DispatchKey_Functionalize.py /home/l00913161/projects/pta_testcase/test/api_test/test__C_DispatchKeySet.py /home/l00913161/projects/pta_testcase/test/api_test/test__C__ExcludeDispatchKeyGuard.py /home/l00913161/projects/pta_testcase/test/api_test/test__from_functional_tensor.py /home/l00913161/projects/pta_testcase/test/api_test/test__prims_common_make_contiguous_strides_for.py /home/l00913161/projects/pta_testcase/test/api_test/test_fx_node_has_side_effect.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Module___setattr__.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Module__parameters.py /home/l00913161/projects/pta_testcase/test/api_test/test__logging_warning_once.py /home/l00913161/projects/pta_testcase/test/api_test/test_autograd_graph__MultiHandle.py
EOF
set +e
/usr/local/python3.11.14/bin/python -m pytest -q --junitxml /home/l00913161/projects/pta_testcase/runs/20260323T150914Z/pytest_raw/initial_junit.xml /home/l00913161/projects/pta_testcase/test/api_test/test_Tensor_new_empty.py /home/l00913161/projects/pta_testcase/test/api_test/test_Tensor_new_zeros.py /home/l00913161/projects/pta_testcase/test/api_test/test_Tensor_register_hook.py /home/l00913161/projects/pta_testcase/test/api_test/test_Tensor_requires_grad.py /home/l00913161/projects/pta_testcase/test/api_test/test_Tensor_untyped_storage.py /home/l00913161/projects/pta_testcase/test/api_test/test___future___get_swap_module_params_on_conversion.py /home/l00913161/projects/pta_testcase/test/api_test/test__sync.py /home/l00913161/projects/pta_testcase/test/api_test/test_autograd_Variable__execution_engine_queue_callback.py /home/l00913161/projects/pta_testcase/test/api_test/test_compiler_is_compiling.py /home/l00913161/projects/pta_testcase/test/api_test/test_dtype.py /home/l00913161/projects/pta_testcase/test/api_test/test_Event.py /home/l00913161/projects/pta_testcase/test/api_test/test_library_impl.py /home/l00913161/projects/pta_testcase/test/api_test/test_library_Library.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Module_buffers.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Module_modules.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Module_named_modules.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Module_named_parameters.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Module_register_forward_hook.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Module_register_forward_pre_hook.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Module_register_load_state_dict_post_hook.py /home/l00913161/projects/pta_testcase/test/api_test/test_utils__pytree_tree_flatten.py /home/l00913161/projects/pta_testcase/test/api_test/test_utils__pytree_tree_map.py /home/l00913161/projects/pta_testcase/test/api_test/test_utils__pytree_tree_unflatten.py /home/l00913161/projects/pta_testcase/test/api_test/test_utils_swap_tensors.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Parameter_grad.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Parameter_device.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Parameter_device_type.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Parameter_is_contiguous.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Parameter_ndim.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Parameter_size.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Parameter_stride.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Parameter_dtype.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Parameter_itemsize.py /home/l00913161/projects/pta_testcase/test/api_test/test_autograd__unsafe_preserve_version_counter.py /home/l00913161/projects/pta_testcase/test/api_test/test_library.py /home/l00913161/projects/pta_testcase/test/api_test/test__dynamo_compiled_autograd_compiled_autograd_enabled.py /home/l00913161/projects/pta_testcase/test/api_test/test__dynamo_compiled_autograd_compiled_autograd_enabled_force_eager.py /home/l00913161/projects/pta_testcase/test/api_test/test__dynamo_compiled_autograd_in_compiled_autograd_region.py /home/l00913161/projects/pta_testcase/test/api_test/test__running_with_deploy.py /home/l00913161/projects/pta_testcase/test/api_test/test_utils__python_dispatch_is_traceable_wrapper_subclass.py /home/l00913161/projects/pta_testcase/test/api_test/test__dynamo_comptime_comptime_print.py /home/l00913161/projects/pta_testcase/test/api_test/test__dynamo_config.py /home/l00913161/projects/pta_testcase/test/api_test/test__dynamo_config_skip_fsdp_hooks.py /home/l00913161/projects/pta_testcase/test/api_test/test__C_DispatchKey_Functionalize.py /home/l00913161/projects/pta_testcase/test/api_test/test__C_DispatchKeySet.py /home/l00913161/projects/pta_testcase/test/api_test/test__C__ExcludeDispatchKeyGuard.py /home/l00913161/projects/pta_testcase/test/api_test/test__from_functional_tensor.py /home/l00913161/projects/pta_testcase/test/api_test/test__prims_common_make_contiguous_strides_for.py /home/l00913161/projects/pta_testcase/test/api_test/test_fx_node_has_side_effect.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Module___setattr__.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Module__parameters.py /home/l00913161/projects/pta_testcase/test/api_test/test__logging_warning_once.py /home/l00913161/projects/pta_testcase/test/api_test/test_autograd_graph__MultiHandle.py \> /home/l00913161/projects/pta_testcase/runs/20260323T150914Z/pytest_raw/initial.stdout.log 2\> /home/l00913161/projects/pta_testcase/runs/20260323T150914Z/pytest_raw/initial.stderr.log
status=$?
printf '%s\n' "$status" \> /home/l00913161/projects/pta_testcase/runs/20260323T150914Z/pytest_raw/initial.returncode.txt
exit 0
        ```

        要求：
        1. 只执行上面的脚本，不要额外改文件。
        2. 即使 pytest 失败，也不要把这次任务判成失败；保留日志即可。
        3. 最终回复只写简洁总结，包含 return code 和产物路径。


---

<sub>⏱️ 1m 39s</sub>

### ✅ `bash`

**Run pytest initial batch**

$ mkdir -p /home/l00913161/projects/pta_testcase/runs/20260323T150914Z/pytest_raw
cat <<'EOF' > /home/l00913161/projects/pta_testcase/runs/20260323T150914Z/pytest_raw/initial.command.txt
/usr/local/python3.11.14/bin/python -m pytest -q --junitxml /home/l00913161/projects/pta_testcase/runs/20260323T150914Z/pytest_raw/initial_junit.xml /home/l00913161/projects/pta_testcase/test/api_test/test_Tensor_new_empty.py /home/l00913161/projects/pta_testcase/test/api_test/test_Tensor_new_zeros.py /home/l00913161/projects/pta_testcase/test/api_test/test_Tensor_register_hook.py /home/l00913161/projects/pta_testcase/test/api_test/test_Tensor_requires_grad.py /home/l00913161/projects/pta_testcase/test/api_test/test_Tensor_untyped_storage.py /home/l00913161/projects/pta_testcase/test/api_test/test___future___get_swap_module_params_on_conversion.py /home/l00913161/projects/pta_testcase/test/api_test/test__sync.py /home/l00913161/projects/pta_testcase/test/api_test/test_autograd_Variable__execution_engine_queue_callback.py /home/l00913161/projects/pta_testcase/test/api_test/test_compiler_is_compiling.py /home/l00913161/projects/pta_testcase/test/api_test/test_dtype.py /home/l00913161/projects/pta_testcase/test/api_test/test_Event.py /home/l00913161/projects/pta_testcase/test/api_test/test_library_impl.py /home/l00913161/projects/pta_testcase/test/api_test/test_library_Library.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Module_buffers.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Module_modules.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Module_named_modules.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Module_named_parameters.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Module_register_forward_hook.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Module_register_forward_pre_hook.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Module_register_load_state_dict_post_hook.py /home/l00913161/projects/pta_testcase/test/api_test/test_utils__pytree_tree_flatten.py /home/l00913161/projects/pta_testcase/test/api_test/test_utils__pytree_tree_map.py /home/l00913161/projects/pta_testcase/test/api_test/test_utils__pytree_tree_unflatten.py /home/l00913161/projects/pta_testcase/test/api_test/test_utils_swap_tensors.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Parameter_grad.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Parameter_device.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Parameter_device_type.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Parameter_is_contiguous.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Parameter_ndim.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Parameter_size.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Parameter_stride.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Parameter_dtype.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Parameter_itemsize.py /home/l00913161/projects/pta_testcase/test/api_test/test_autograd__unsafe_preserve_version_counter.py /home/l00913161/projects/pta_testcase/test/api_test/test_library.py /home/l00913161/projects/pta_testcase/test/api_test/test__dynamo_compiled_autograd_compiled_autograd_enabled.py /home/l00913161/projects/pta_testcase/test/api_test/test__dynamo_compiled_autograd_compiled_autograd_enabled_force_eager.py /home/l00913161/projects/pta_testcase/test/api_test/test__dynamo_compiled_autograd_in_compiled_autograd_region.py /home/l00913161/projects/pta_testcase/test/api_test/test__running_with_deploy.py /home/l00913161/projects/pta_testcase/test/api_test/test_utils__python_dispatch_is_traceable_wrapper_subclass.py /home/l00913161/projects/pta_testcase/test/api_test/test__dynamo_comptime_comptime_print.py /home/l00913161/projects/pta_testcase/test/api_test/test__dynamo_config.py /home/l00913161/projects/pta_testcase/test/api_test/test__dynamo_config_skip_fsdp_hooks.py /home/l00913161/projects/pta_testcase/test/api_test/test__C_DispatchKey_Functionalize.py /home/l00913161/projects/pta_testcase/test/api_test/test__C_DispatchKeySet.py /home/l00913161/projects/pta_testcase/test/api_test/test__C__ExcludeDispatchKeyGuard.py /home/l00913161/projects/pta_testcase/test/api_test/test__from_functional_tensor.py /home/l00913161/projects/pta_testcase/test/api_test/test__prims_common_make_contiguous_strides_for.py /home/l00913161/projects/pta_testcase/test/api_test/test_fx_node_has_side_effect.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Module___setattr__.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Module__parameters.py /home/l00913161/projects/pta_testcase/test/api_test/test__logging_warning_once.py /home/l00913161/projects/pta_testcase/test/api_test/test_autograd_graph__MultiHandle.py
EOF
set +e
/usr/local/python3.11.14/bin/python -m pytest -q --junitxml /home/l00913161/projects/pta_testcase/runs/20260323T150914Z/pytest_raw/initial_junit.xml /home/l00913161/projects/pta_testcase/test/api_test/test_Tensor_new_empty.py /home/l00913161/projects/pta_testcase/test/api_test/test_Tensor_new_zeros.py /home/l00913161/projects/pta_testcase/test/api_test/test_Tensor_register_hook.py /home/l00913161/projects/pta_testcase/test/api_test/test_Tensor_requires_grad.py /home/l00913161/projects/pta_testcase/test/api_test/test_Tensor_untyped_storage.py /home/l00913161/projects/pta_testcase/test/api_test/test___future___get_swap_module_params_on_conversion.py /home/l00913161/projects/pta_testcase/test/api_test/test__sync.py /home/l00913161/projects/pta_testcase/test/api_test/test_autograd_Variable__execution_engine_queue_callback.py /home/l00913161/projects/pta_testcase/test/api_test/test_compiler_is_compiling.py /home/l00913161/projects/pta_testcase/test/api_test/test_dtype.py /home/l00913161/projects/pta_testcase/test/api_test/test_Event.py /home/l00913161/projects/pta_testcase/test/api_test/test_library_impl.py /home/l00913161/projects/pta_testcase/test/api_test/test_library_Library.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Module_buffers.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Module_modules.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Module_named_modules.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Module_named_parameters.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Module_register_forward_hook.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Module_register_forward_pre_hook.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Module_register_load_state_dict_post_hook.py /home/l00913161/projects/pta_testcase/test/api_test/test_utils__pytree_tree_flatten.py /home/l00913161/projects/pta_testcase/test/api_test/test_utils__pytree_tree_map.py /home/l00913161/projects/pta_testcase/test/api_test/test_utils__pytree_tree_unflatten.py /home/l00913161/projects/pta_testcase/test/api_test/test_utils_swap_tensors.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Parameter_grad.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Parameter_device.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Parameter_device_type.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Parameter_is_contiguous.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Parameter_ndim.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Parameter_size.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Parameter_stride.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Parameter_dtype.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Parameter_itemsize.py /home/l00913161/projects/pta_testcase/test/api_test/test_autograd__unsafe_preserve_version_counter.py /home/l00913161/projects/pta_testcase/test/api_test/test_library.py /home/l00913161/projects/pta_testcase/test/api_test/test__dynamo_compiled_autograd_compiled_autograd_enabled.py /home/l00913161/projects/pta_testcase/test/api_test/test__dynamo_compiled_autograd_compiled_autograd_enabled_force_eager.py /home/l00913161/projects/pta_testcase/test/api_test/test__dynamo_compiled_autograd_in_compiled_autograd_region.py /home/l00913161/projects/pta_testcase/test/api_test/test__running_with_deploy.py /home/l00913161/projects/pta_testcase/test/api_test/test_utils__python_dispatch_is_traceable_wrapper_subclass.py /home/l00913161/projects/pta_testcase/test/api_test/test__dynamo_comptime_comptime_print.py /home/l00913161/projects/pta_testcase/test/api_test/test__dynamo_config.py /home/l00913161/projects/pta_testcase/test/api_test/test__dynamo_config_skip_fsdp_hooks.py /home/l00913161/projects/pta_testcase/test/api_test/test__C_DispatchKey_Functionalize.py /home/l00913161/projects/pta_testcase/test/api_test/test__C_DispatchKeySet.py /home/l00913161/projects/pta_testcase/test/api_test/test__C__ExcludeDispatchKeyGuard.py /home/l00913161/projects/pta_testcase/test/api_test/test__from_functional_tensor.py /home/l00913161/projects/pta_testcase/test/api_test/test__prims_common_make_contiguous_strides_for.py /home/l00913161/projects/pta_testcase/test/api_test/test_fx_node_has_side_effect.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Module___setattr__.py /home/l00913161/projects/pta_testcase/test/api_test/test_nn_Module__parameters.py /home/l00913161/projects/pta_testcase/test/api_test/test__logging_warning_once.py /home/l00913161/projects/pta_testcase/test/api_test/test_autograd_graph__MultiHandle.py > /home/l00913161/projects/pta_testcase/runs/20260323T150914Z/pytest_raw/initial.stdout.log 2> /home/l00913161/projects/pta_testcase/runs/20260323T150914Z/pytest_raw/initial.stderr.log
status=$?
printf '%s\n' "$status" > /home/l00913161/projects/pta_testcase/runs/20260323T150914Z/pytest_raw/initial.returncode.txt
exit 0

```
exit
<exited with exit code 0>
```


---

<sub>⏱️ 1m 51s</sub>

### ✅ `bash`

**Check pytest results**

$ cat /home/l00913161/projects/pta_testcase/runs/20260323T150914Z/pytest_raw/initial.returncode.txt && echo "---" && tail -5 /home/l00913161/projects/pta_testcase/runs/20260323T150914Z/pytest_raw/initial.stdout.log && echo "---STDERR tail---" && tail -5 /home/l00913161/projects/pta_testcase/runs/20260323T150914Z/pytest_raw/initial.stderr.log

<details>
<summary>10 lines</summary>

```
1
---
FAILED test/api_test/test_nn_Parameter_device.py::test_parameter_device_after_to_npu_keeps_npu_device
FAILED test/api_test/test__from_functional_tensor.py::test_from_functional_tensor_round_trip_preserves_tensor_properties[shape2-dtype2-True]
FAILED test/api_test/test__from_functional_tensor.py::test_from_functional_tensor_round_trip_preserves_tensor_properties[shape4-dtype4-True]
FAILED test/api_test/test__from_functional_tensor.py::test_from_functional_tensor_round_trip_preserves_tensor_properties[shape6-dtype6-True]
5 failed, 749 passed, 4 skipped, 1 warning in 18.50s
---STDERR tail---
[W323 23:36:40.785338550 compiler_depend.ts:164] Warning: Device do not support double dtype now, dtype cast replace with float. (function operator())
<exited with exit code 0>
```

</details>


---

<sub>⏱️ 2m 4s</sub>

### 💬 Copilot

Pytest **initial** 阶段完成。

| 项目 | 值 |
|---|---|
| **Return code** | `1` (有失败用例) |
| **结果** | 749 passed, 5 failed, 4 skipped, 1 warning |
| **耗时** | 18.50s |

**产物路径：**
- stdout: `runs/20260323T150914Z/pytest_raw/initial.stdout.log`
- stderr: `runs/20260323T150914Z/pytest_raw/initial.stderr.log`
- JUnit XML: `runs/20260323T150914Z/pytest_raw/initial_junit.xml`
- return code: `runs/20260323T150914Z/pytest_raw/initial.returncode.txt`
- 命令记录: `runs/20260323T150914Z/pytest_raw/initial.command.txt`

---

<sub>Generated by [GitHub Copilot CLI](https://github.com/features/copilot/cli)</sub>
