git checkout 861ba79f31393dec0a0782ca11cf32cebb6f6610
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