localid=21916
git checkout 83946a28db3d13ffe8184bdae23287a81c09fd7f
apt-get update
apt-get install -y git cmake build-essential python3
mkdir build && cd build
env -i PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
  CC=/usr/bin/gcc CXX=/usr/bin/g++ \
  cmake .. \
    -DJSONCPP_WITH_TESTS=ON \
    -DBUILD_SHARED_LIBS=OFF \
    -DCMAKE_C_FLAGS= \
    -DCMAKE_CXX_FLAGS= \
    -DCMAKE_EXE_LINKER_FLAGS=
cmake --build . -j