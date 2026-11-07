<uploaded_files>
/src/harfbuzz
</uploaded_files>
I've uploaded a C/C++ code repository in the directory /src/harfbuzz. Consider the following requirement description:
<description>
- Add support for Lookup format 10 (variable-sized integer values) to the Lookup machinery:
  - Introduce a LookupFormat10<T> structure that stores format, valueSize, firstGlyph, glyphCount and an array of bytes for values.
  - Implement LookupFormat10::get_value_or_null(glyph_id) that returns the integer value constructed from valueSize bytes for the given glyph (big-endian), or Null(T) if glyph_id is out of range.
  - Implement LookupFormat10::sanitize(...) to validate the struct, enforce valueSize <= 4 and validate the backing byte array length.
  - Add a format10 member to the Lookup union and include it in Lookup::sanitize handling for case 10.
  - Update Lookup::get_value_or_null to return typename T::type and to dispatch to format10.get_value_or_null when the lookup format is 10. Preserve existing behavior for other formats.

- Change the return type of Lookup::get_value_or_null to be typename T::type (instead of const T&) to allow format 10 to return by-value.

- Update anchor lookup code that consumed Lookup::get_value_or_null:
  - Use get_value (which returns a pointer to an Offset) to obtain the Offset<HBUINT16,false> pointer for a glyph.
  - Check the pointer for null and return Null(Anchor) if null.
  - Dereference the Offset and pass the value to StructAtOffset to obtain anchors.
  - Preserve the existing bounds check against the buffer end.

- Expose an inner type alias (typedef Type type) on integer wrapper templates so callers can refer to the underlying C++ type:
  - Add typedef Type type to BEInt specializations (sizes 1..4).
  - Add typedef Type type to OT::IntType.
  - Add typedef Type type to Offset template.

- Ensure new structures are included in the existing size/serialization macros/definitions so they are considered by the library's size macros (DEFINE_SIZE_ARRAY/DEFINE_SIZE_UNION) consistent with other Lookup formats.
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
