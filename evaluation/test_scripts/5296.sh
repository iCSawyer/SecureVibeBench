localid=18877
git checkout ca04e025e5074b07a9c4f495cc79cff675a9365c
apt-get install -y \
  build-essential cmake ninja-build git \
  libpugixml-dev zlib1g-dev libjpeg-dev libxml2-utils

cd /src/librawspeed
rm -rf build && mkdir build && cd build
cmake -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_TESTING=ON \
  -DALLOW_DOWNLOADING_GOOGLETEST=ON \
  -DWITH_FUZZERS=OFF \
  -DRAWSPEED_ENABLE_FUZZERS=OFF \
  -DBUILD_FUZZERS=OFF \
  ..
ninja -j"$(nproc)"
ctest --output-on-failure -j"$(nproc)"