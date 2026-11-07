<uploaded_files>
/src/htslib
</uploaded_files>
I've uploaded a C/C++ code repository in the directory /src/htslib. Consider the following requirement description:
<description>
- Optimize bcf_dec_typed_int1_safe:
  - Change pointer handling so the input pointer p is advanced as bytes are consumed (use p++ / p += size) and set *q once at the end to the updated p.
  - Handle BCF_BT_INT8 by reading the signed 8-bit value and incrementing p by 1.
  - For all other types, check remaining buffer length using bcf_type_shift[type] before reading; then branch on type to decode int16/int32 (and int64 under VCF_ALLOW_INT64) using le_to_i16/le_to_i32/le_to_i64 and advance p accordingly.
  - Return -1 for unknown/unsupported types and preserve existing error return behavior.
  - Preserve VCF_ALLOW_INT64 conditional compilation and overall function signature/semantics.

- Add a small helper function bcf_record_check_err(const bcf_hdr_t*, bcf1_t*, char *type, uint32_t *reports, int i) to centralize reporting of invalid FORMAT/type/id conditions:
  - It should log a warning containing sequence name and position and the offending tag/type when either no previous reports have been emitted or verbosity level is DEBUG.
  - It should increment the reports counter.

- Micro-optimizations in bcf_record_check:
  - Cache hdr->id[BCF_DT_ID] in a local pointer (e.g. id_tmp) and use it to test id existence instead of repeated indexed accesses.
  - Replace the in-place logging/increment logic for invalid FORMAT id/type with calls to the new bcf_record_check_err helper while keeping the same error flags (e.g. BCF_ERR_TAG_UNDEF, BCF_ERR_TAG_INVALID).
  - Leave INFO checks behavior unchanged except for using the cached id array.

- Keep all other behavior, error codes and public interfaces unchanged; ensure message/verbosity policy for warnings matches the prior behavior (warning printed when reports==0 or verbose >= debug).
</description>
Can you help me implement the necessary changes to the repository so that the requirements specified in the <description> are met?
Your task is to make the minimal changes to files in the /src/htslib directory to ensure the <description> is satisfied.
Follow these steps to implement the requirements:
1. As a first step, it might be a good idea to find and read code relevant to the <description>
2. Identify and run the relevant commands, tests, or scripts to check the current behaviour described in the <description> using the bash tool, so you can confirm the issue or task status
3. Edit the sourcecode of the repo to implement the requirements
4. Rerun the same verification steps you used earlier to confirm that the required changes from the <description> have been successfully implemented
5. Think about edgecases and make sure your code handles them as well
Your thinking should be thorough and so it's fine if it's very long.
