<uploaded_files>
/src/libplist
</uploaded_files>
I've uploaded a C/C++ code repository in the directory /src/libplist. Consider the following requirement description:
<description>
- Add a helper function parse_decimal(const char* str, const char* str_end, char** endp) that parses an optional leading '-' and consecutive digits from str up to str_end, sets *endp to the first character after the parsed digits (never overrunning str_end), and returns the parsed value as a signed long long.

- Change numeric primitive parsing to operate directly on the token substring (no copying into a temporary buffer and no use of strtoll/atof on null-terminated buffers). Treat a token as numeric if it starts with a digit or starts with '-' followed by a digit.

- Use parse_decimal to read the integer part. If parsing reaches the token end, create an integer plist node (plist_new_uint cast from the parsed value).

- If the token contains a fractional part or an exponent, parse it as a floating-point value:
  - Initialize a double from the parsed integer part.
  - If there is a '.' followed by digits, parse fractional digits in-place by accumulating fraction digits with decreasing powers of ten and add/subtract the fraction to/from the double (respect sign).
  - If there is an exponent ('e' or 'E') optionally with a sign, parse the exponent digits in-place (use parse_decimal for the exponent) and multiply the double by pow(10, exponent).
  - Validate characters at each step; if unexpected characters are encountered, emit the same parsing error diagnostics with an offset relative to the input JSON pointer.
  - If the resulting double is infinite or NaN, emit an "unrepresentable floating point" error; otherwise create a real plist node (plist_new_real).

- Preserve existing null/primitive branch behavior and error reporting semantics; ensure all pointer arithmetic and bounds checks use the provided token start/end so parsing works with non-null-terminated JSON substrings.
</description>
Can you help me implement the necessary changes to the repository so that the requirements specified in the <description> are met?
Your task is to make the minimal changes to files in the /src/libplist directory to ensure the <description> is satisfied.
Follow these steps to implement the requirements:
1. As a first step, it might be a good idea to find and read code relevant to the <description>
2. Identify and run the relevant commands, tests, or scripts to check the current behaviour described in the <description> using the bash tool, so you can confirm the issue or task status
3. Edit the sourcecode of the repo to implement the requirements
4. Rerun the same verification steps you used earlier to confirm that the required changes from the <description> have been successfully implemented
5. Think about edgecases and make sure your code handles them as well
Your thinking should be thorough and so it's fine if it's very long.
