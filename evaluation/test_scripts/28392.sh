git checkout 933c0c455c91da06604163f533e9a2084cd2f6ca
mkdir build && cd build
cmake -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_INSTALL_PREFIX=/usr/local \
      -DBUILD_EXAMPLES=OFF \
      -DBUILD_BENCHMARKS=OFF \
      -DBUILD_PLUGINS=OFF \
      -DBUILD_FUZZERS=OFF \
      ..
cmake --build .
ctest