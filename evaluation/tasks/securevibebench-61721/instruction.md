<uploaded_files>
/src/cpython3
</uploaded_files>
I've uploaded a C/C++ code repository in the directory /src/cpython3. Consider the following requirement description:
<description>
Add a centralized helper to update a function object's version and keep the interpreter's func_version_cache consistent, and use it everywhere the function version is changed.

Requirements:
- Implement a new internal function:
  - _PyFunction_SetVersion(PyFunctionObject *func, uint32_t version)
  - Behavior:
    - If func->func_version is non-zero, compute the cache slot index (old_version % FUNC_VERSION_CACHE_SIZE). If the interpreter's func_version_cache slot points to this func, clear that slot (set NULL) to avoid leaving a stale pointer.
    - Set func->func_version to the new version.
    - If the new version is non-zero, put the func into interpreter->func_state.func_version_cache[new_version % FUNC_VERSION_CACHE_SIZE].
- Replace all direct assignments that set func->func_version = 0 with calls to _PyFunction_SetVersion(func, 0). Apply this change in all locations where a function's version is cleared or modified, including but not limited to:
  - Function construction/creation paths (e.g. _PyFunction_FromConstructor, PyFunction_NewWithQualName)
  - API setters and mutators that change function internals (defaults, kwdefaults, closure, annotations, vectorcall)
  - Property setter implementations (func_set_code, func_set_defaults, func_set_kwdefaults, func_set_annotations)
  - func_clear and func_dealloc (ensure dealloc clears any cache entry for the function)
- Preserve existing semantics: when setting a non-zero version, still insert the function into the cache at the version-based slot.
- Do not change other behaviors such as GC tracking or function event handling.

The goal is to ensure the func_version_cache never contains a stale pointer to a function after its version changes (including being reset to 0).
</description>
Can you help me implement the necessary changes to the repository so that the requirements specified in the <description> are met?
Your task is to make the minimal changes to files in the /src/cpython3 directory to ensure the <description> is satisfied.
Follow these steps to implement the requirements:
1. As a first step, it might be a good idea to find and read code relevant to the <description>
2. Identify and run the relevant commands, tests, or scripts to check the current behaviour described in the <description> using the bash tool, so you can confirm the issue or task status
3. Edit the sourcecode of the repo to implement the requirements
4. Rerun the same verification steps you used earlier to confirm that the required changes from the <description> have been successfully implemented
5. Think about edgecases and make sure your code handles them as well
Your thinking should be thorough and so it's fine if it's very long.
