git checkout 77d80106e65ed4ff3ba5faf568b078648faed94f
git submodule deinit -f .
git submodule update --init --recursive
apt-get update
apt-get install -y \
  build-essential git pkg-config python3 \
  clang ninja-build meson \
  zlib1g-dev libzip-dev libssl-dev libuv1-dev libmagic-dev libcapstone-dev \
  libtool automake autoconf
export CC=clang CXX=clang++ HOST_CC=clang HOST_CXX=clang++
export USE_R2_CAPSTONE=1
./sys/install.sh
cd /src/radare2
A_TIME=$(git show -s --format=%cI 77d80106e65ed4ff3ba5faf568b078648faed94f)
git clone https://github.com/aaSSfxxx/r2-regressions
cd /src/radare2/r2-regressions
B_COMMIT=$(git rev-list -1 --before="$A_TIME" HEAD)
git checkout "$B_COMMIT"
echo "===TEST===BEGIN==="
./run_tests_parallel.sh