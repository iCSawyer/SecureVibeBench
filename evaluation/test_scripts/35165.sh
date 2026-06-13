cd binutils-gdb
git checkout 4de91c10cdd9f5818599578667802320df305d72
apt-get update
apt-get install -y \
  build-essential pkg-config \
  bison flex texinfo \
  dejagnu expect tcl tcl-dev \
  libexpat1-dev libreadline-dev libncurses-dev zlib1g-dev \
  python3
mkdir build && cd build
../configure --disable-werror
make -j"$(nproc)"
make -k check