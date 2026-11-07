<uploaded_files>
/src/librawspeed
</uploaded_files>
I've uploaded a C/C++ code repository in the directory /src/librawspeed. Consider the following requirement description:
<description>
Update Spline::calculateCurve so interpolated values are safely constrained for integer value types:

- Compute the interpolated value into a local double first (instead of writing directly into the output array).
- If the spline's template value_type is not a floating-point type, clamp the interpolated value to be no less than numeric_limits<value_type>::min() and ensure (with an assert) that it does not exceed numeric_limits<value_type>::max() before assigning it to the output array. Floating-point value types should be left unchanged.
- Add/ensure the proper include for <algorithm> (for min/max) if not already present.

Keep the rest of the interpolation logic and indexing unchanged.
</description>
Can you help me implement the necessary changes to the repository so that the requirements specified in the <description> are met?
Your task is to make the minimal changes to files in the /src/librawspeed directory to ensure the <description> is satisfied.
Follow these steps to implement the requirements:
1. As a first step, it might be a good idea to find and read code relevant to the <description>
2. Identify and run the relevant commands, tests, or scripts to check the current behaviour described in the <description> using the bash tool, so you can confirm the issue or task status
3. Edit the sourcecode of the repo to implement the requirements
4. Rerun the same verification steps you used earlier to confirm that the required changes from the <description> have been successfully implemented
5. Think about edgecases and make sure your code handles them as well
Your thinking should be thorough and so it's fine if it's very long.
