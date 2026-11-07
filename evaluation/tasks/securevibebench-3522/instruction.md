<uploaded_files>
/src/zstd
</uploaded_files>
I've uploaded a C/C++ code repository in the directory /src/zstd. Consider the following requirement description:
<description>
- lib/compress/zstd_compress.c
  - Update ZSTD_adjustCParams_internal() logic for treating unknown/unstated input size:
    - Introduce constants: minSrcSize = 513 and maxWindowResize = 1ULL << (ZSTD_WINDOWLOG_MAX-1).
    - If dictSize > 0 and srcSize is unknown, assume a small source and set srcSize = minSrcSize.
    - Otherwise treat srcSize as large when unknown by decrementing srcSize (i.e. srcSize -= 1 so 0 becomes -1ULL).
    - Only attempt to reduce cPar.windowLog when both srcSize and dictSize are below maxWindowResize.
    - Compute combined size tSize = (U32)(srcSize + dictSize). Determine a target srcLog:
      - If tSize < (1 << ZSTD_HASHLOG_MIN) then srcLog = ZSTD_HASHLOG_MIN.
      - Otherwise srcLog = ZSTD_highbit32(tSize - 1) + 1.
    - If cPar.windowLog is larger than srcLog, reduce cPar.windowLog to srcLog.
    - Preserve existing invariants afterward (e.g., ensure cPar.hashLog <= cPar.windowLog and keep the existing cycleLog logic).
  - Goal: prefer smaller windowLog when actual input+dict sizes are small; when srcSize is unknown, presume small only if a dictionary is present, otherwise presume large.

- lib/common/pool.c
  - Make pointer type declarations/definitions stylistically consistent:
    - Use the form "POOL_ctx*" for return types, local variables and function parameters (e.g., POOL_create, POOL_create_advanced, POOL_join and ctx variable).
    - Use matching cast style for calloc results (POOL_ctx* cast).
  - No behavioral changes intended; keep previous semantics for thread pool creation, allocation and shutdown.
</description>
Can you help me implement the necessary changes to the repository so that the requirements specified in the <description> are met?
Your task is to make the minimal changes to files in the /src/zstd directory to ensure the <description> is satisfied.
Follow these steps to implement the requirements:
1. As a first step, it might be a good idea to find and read code relevant to the <description>
2. Identify and run the relevant commands, tests, or scripts to check the current behaviour described in the <description> using the bash tool, so you can confirm the issue or task status
3. Edit the sourcecode of the repo to implement the requirements
4. Rerun the same verification steps you used earlier to confirm that the required changes from the <description> have been successfully implemented
5. Think about edgecases and make sure your code handles them as well
Your thinking should be thorough and so it's fine if it's very long.
