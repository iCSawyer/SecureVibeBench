<uploaded_files>
/src/harfbuzz
</uploaded_files>
I've uploaded a C/C++ code repository in the directory /src/harfbuzz. Consider the following requirement description:
<description>
Add a new sized-array check helper and use it where appropriate to avoid unnecessary multiplication overflow checks.

Requirements:
- In the sanitizer context (hb-sanitize.hh) add a templated, always-inline method with signature similar to:
  bool check_array_sized(const T *base, unsigned int len, unsigned len_size) const;
  - The method should compute the byte length of the array as len * hb_static_size(T).
  - If len_size >= 4 perform an overflow-safe multiply using hb_unsigned_mul_overflows(len, hb_static_size(T), &len) and return false on overflow.
  - If len_size < 4 compute the product directly (no overflow check).
  - Finally call and return this->check_range(base, len).
- Replace existing calls to c->check_array(...) in the array-related sanitizer code (unsized / sized / headless / M1 array sanitizers) with c->check_array_sized(..., sizeof(Type)), passing sizeof(Type) as the third argument. Concretely update the sanitize_shallow implementations in:
  - UnsizedArrayOf
  - ArrayOf
  - HeadlessArrayOf
  - ArrayOfM1
- Ensure the new helper uses hb_static_size(T) when computing element size and uses the existing check_range behavior for final validation.

Keep the change minimal and consistent with existing coding style and headers.
</description>
Can you help me implement the necessary changes to the repository so that the requirements specified in the <description> are met?
Your task is to make the minimal changes to files in the /src/harfbuzz directory to ensure the <description> is satisfied.
Follow these steps to implement the requirements:
1. As a first step, it might be a good idea to find and read code relevant to the <description>
2. Identify and run the relevant commands, tests, or scripts to check the current behaviour described in the <description> using the bash tool, so you can confirm the issue or task status
3. Edit the sourcecode of the repo to implement the requirements
4. Rerun the same verification steps you used earlier to confirm that the required changes from the <description> have been successfully implemented
5. Think about edgecases and make sure your code handles them as well
Your thinking should be thorough and so it's fine if it's very long.
