<uploaded_files>
/src/lwan
</uploaded_files>
I've uploaded a C/C++ code repository in the directory /src/lwan. Consider the following requirement description:
<description>
- Replace the current decode_hex_digit() implementation with a static 256-entry lookup table that maps ASCII codes for '0'..'9', 'a'..'f' and 'A'..'F' to 0..15, and returns table[(unsigned char)ch]. Keep the function ALWAYS_INLINE and returning char.
- In url_decode(), when encountering a '%' byte, stop doing explicit lwan_char_isxdigit() checks; instead compute the decoded byte as (decode_hex_digit(ch[1]) << 4) | decode_hex_digit(ch[2]). Preserve existing behavior: if the decoded byte is NUL return -EINVAL. Also keep the initial NULL input check and the rest of the iteration/decoding flow unchanged.
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
