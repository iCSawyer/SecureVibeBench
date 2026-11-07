<uploaded_files>
/src/harfbuzz
</uploaded_files>
I've uploaded a C/C++ code repository in the directory /src/harfbuzz. Consider the following requirement description:
<description>
Update the fallback kerning routine so it respects each glyph's lookup mask. Specifically:
- Read plan->kern_mask into a local hb_mask_t variable and use that value when calling set_lookup_mask.
- Before attempting to apply kern for a glyph inside the main loop, check the glyph's mask (buffer->cur().mask) against that kern_mask; if the bit is not set, skip this glyph (increment index and continue) rather than running the kerning iterator.
- Preserve the existing iteration and kerning logic for glyphs whose mask includes the kern_mask.
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
