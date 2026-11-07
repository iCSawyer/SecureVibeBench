<uploaded_files>
/src/harfbuzz
</uploaded_files>
I've uploaded a C/C++ code repository in the directory /src/harfbuzz. Consider the following requirement description:
<description>
Requirements — Support unordered glyph lists when serializing Coverage and ClassDef

1. When building Coverage from a glyph list:
   - Detect if the glyph list is not strictly increasing (track an "unsorted" flag).
   - Track the maximum glyph id seen (separate from the last-in-input value).
   - Only choose Coverage format 1 (single glyph array) if the list is sorted and the format-1 heuristics still apply; otherwise use format 2.
   - When deciding whether to select a format that requires handling >0xFFFF glyph ids, use the tracked maximum glyph id, not the last input glyph value.

2. When building RangeRecord arrays for Coverage format 2 and ClassDef format 2:
   - Provide a comparator routine for RangeRecord suitable for qsort (compare by first, then last, then value).
   - Before finalizing/serializing the rangeRecord array, sort it using that comparator to handle unordered input glyph lists.

3. Apply the above changes both in Coverage format-2 construction and in ClassDef format-2 construction so unordered glyph input produces correct, sorted range records and correct format selection.

4. Keep the changes internal to the layout-common code (no API changes).
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
