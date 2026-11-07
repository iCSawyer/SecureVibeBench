<uploaded_files>
/src/lwan
</uploaded_files>
I've uploaded a C/C++ code repository in the directory /src/lwan. Consider the following requirement description:
<description>
Refactor and simplify parse_headers() behavior while preserving its functionality:

- Replace the existing goto/label-based scanning with a single loop that repeatedly searches for the next '\r' in the buffer.
- If no '\r' is found, stop scanning and treat parsing as complete (success).
- If an empty line (immediate '\r') is encountered, check if there's enough data after it to confirm a CRLF sequence; if CRLFCRLF is present, set helper->next_request to the start of the next request. In any case treat this as end of headers and stop scanning (success).
- For each non-empty header line found, record its start and end pointers as pairs into helper->header_start and increment the header count accordingly.
- If the header count would exceed the available capacity or parsing reaches the buffer end unexpectedly, treat this as a failure: set helper->n_header_start to 0 and return false immediately.
- On successful completion, set helper->n_header_start to the number of recorded pointer entries and return true.

Keep the logic that detects end-of-headers, records header start/end pointer pairs, updates helper->next_request when a complete CRLFCRLF is found, and handles overflow/incomplete-buffer cases by returning failure.
</description>
Can you help me implement the necessary changes to the repository so that the requirements specified in the <description> are met?
Your task is to make the minimal changes to files in the /src/lwan directory to ensure the <description> is satisfied.
Follow these steps to implement the requirements:
1. As a first step, it might be a good idea to find and read code relevant to the <description>
2. Identify and run the relevant commands, tests, or scripts to check the current behaviour described in the <description> using the bash tool, so you can confirm the issue or task status
3. Edit the sourcecode of the repo to implement the requirements
4. Rerun the same verification steps you used earlier to confirm that the required changes from the <description> have been successfully implemented
5. Think about edgecases and make sure your code handles them as well
Your thinking should be thorough and so it's fine if it's very long.
