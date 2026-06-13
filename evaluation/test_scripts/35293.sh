git checkout dbf8653bf9c654c42406dab4b55c024f0d879cd8
git submodule update --init --recursive
apt update
apt install -y \
  build-essential git cmake pkg-config ninja-build \
  libbrotli-dev \
  libjpeg-turbo8-dev libpng-dev libgif-dev libopenexr-dev libwebp-dev
apt-get remove -y libjpeg-dev libjpeg8-dev libjpeg-turbo8-dev || true
apt-get install -y libjpeg-turbo8-dev
rm -rf build && mkdir build && cd build
cmake -G Ninja .. \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_TESTING=ON \
  -DJPEGXL_ENABLE_VIEWERS=OFF \
  -DJPEGXL_WARNINGS_AS_ERRORS=OFF \
  -DCMAKE_DISABLE_FIND_PACKAGE_JPEG=ON \
  -DCMAKE_EXE_LINKER_FLAGS="-pthread" \
  -DCMAKE_SHARED_LINKER_FLAGS="-pthread"
ninja -j"$(nproc)"
echo "===TEST===BEGIN==="
ctest --output-on-failure -j"$(nproc)"