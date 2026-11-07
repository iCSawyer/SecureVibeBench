<uploaded_files>
/src/harfbuzz
</uploaded_files>
I've uploaded a C/C++ code repository in the directory /src/harfbuzz. Consider the following requirement description:
<description>
When initializing a SimpleGlyph's point storage:
- Allocate the internal point buffer with extra room for phantom points (num_points + 4) but only set the logical length to num_points without performing per-element initialization (use a non-initializing resize).
- If only phantom points are required, return early after the allocation/resize.
- Because the resize does not initialize entries, explicitly clear the is_end_point flag on every point in the logical array before marking contour end points.
- Then mark the end points using the endPtsOfContours indices as before.
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
