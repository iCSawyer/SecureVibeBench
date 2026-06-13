git checkout 79e921d904d46fc9edc292e02a48f1aa54567a7d
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