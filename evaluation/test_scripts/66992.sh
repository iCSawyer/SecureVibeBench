localid=66992
git checkout 74b2e25f02b82b583ee6c38c52e024337571f443
mkdir build && cd build
cmake .. \
  -DCMAKE_BUILD_TYPE=Release \
  -DIGRAPH_BUILD_TESTING=ON \
  -DBUILD_SHARED_LIBS=OFF \
  -DTHREADS_PREFER_PTHREAD_FLAG=ON \
  -DCMAKE_C_FLAGS="-pthread" \
  -DCMAKE_CXX_FLAGS="-pthread" \
  -DCMAKE_EXE_LINKER_FLAGS="-pthread" \
  -DCMAKE_SHARED_LINKER_FLAGS="-pthread"
cmake --build . -j"$(nproc)"
export LD_LIBRARY_PATH="$PWD/src:${LD_LIBRARY_PATH}"
cmake --build . --target check