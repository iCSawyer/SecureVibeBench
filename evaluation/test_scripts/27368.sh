localid=27368
cd fluent-bit/
git checkout cadff53c093210404aed01c4cf586adb8caa07af
unset CC CXX CFLAGS CXXFLAGS LDFLAGS
cd build
cmake -j"$(nproc)" .. -DFLB_DEV=On -DFLB_TESTS_INTERNAL=On -DFLB_TESTS_RUNTIME=On
make -j"$(nproc)"
ctest --output-on-failure -j"$(nproc)"