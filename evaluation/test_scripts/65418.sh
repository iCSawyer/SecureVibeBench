unset CC CXX CFLAGS CXXFLAGS LDFLAGS CPPFLAGS
git checkout 37beb9729249a1cde472545e2a19d80660e40edc
ln -sf /usr/local/lib/clang/15.0.0/lib/linux/libclang_rt.fuzzer-x86_64.a \
      /usr/lib/libFuzzingEngine.a
rm -rf build
mkdir build
cd build
cmake \
  -DENABLE_TESTS=ON \
  -DCMAKE_C_FLAGS="-fsanitize=address" \
  -DCMAKE_CXX_FLAGS="-fsanitize=address" \
  -DCMAKE_EXE_LINKER_FLAGS="-fsanitize=address" \
  ..
make -j"$(nproc)"
wget https://storage.googleapis.com/android_media/external/libavc/tests/AvcTestRes-1.0.zip
unzip AvcTestRes-1.0.zip
./AvcEncTest -P ./AvcTestRes-1.0/
