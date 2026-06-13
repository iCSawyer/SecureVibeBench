apt-get update
apt-get install -y \
  build-essential cmake pkg-config flex bison python3 python3-pip \
  libglib2.0-dev libpcap-dev libgnutls28-dev libgcrypt20-dev \
  qtbase5-dev qttools5-dev qttools5-dev-tools qtmultimedia5-dev libqt5svg5-dev \
  locales libnghttp2-dev zlib1g-dev libssh-dev libssh-4 libpcap0.8-dev zlib1g-dev

# locale（保留你的设置）
sed -i 's/^# *en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen || true
locale-gen en_US.UTF-8
update-locale LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8
export LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 LC_CTYPE=en_US.UTF-8 PYTHONIOENCODING=UTF-8

# 干净源码 + 切换提交
git clean -fdx
git checkout f55cb116a002ae0097564522abf49e2498a7380a

# out-of-tree 构建
rm -rf build && mkdir build && cd build
unset CFLAGS CXXFLAGS CPPFLAGS LDFLAGS FUZZING_CFLAGS FUZZING_CXXFLAGS ASAN_OPTIONS UBSAN_OPTIONS MSAN_OPTIONS
cmake .. \
  -DBUILD_wireshark=ON \
  -DENABLE_PCAP=ON -DENABLE_GNUTLS=ON \
  -DUSE_qt6=OFF \
  -DBUILD_tests=ON \
  -DCMAKE_EXE_LINKER_FLAGS="-Wl,--no-as-needed -pthread" \
  -DCMAKE_SHARED_LINKER_FLAGS="-Wl,--no-as-needed -pthread" \
  -DCMAKE_MODULE_LINKER_FLAGS="-Wl,--no-as-needed -pthread"
cmake --build . -- -j"$(nproc)"

# 先把单元测试可执行文件补齐
cmake --build . --target test-programs -- -j"$(nproc)"

# 非 root 用户跑测试 + 跳过抓包测试
useradd -m -r -s /bin/bash ws 2>/dev/null || true
chown -R ws:ws /src/wireshark
su -s /bin/bash ws -c 'cd /src/wireshark/build && \
  PYTEST_ADDOPTS="--disable-capture -n auto" ctest --force-new-ctest-process -j 4 --verbose'

# 如需手动运行 GUI/CLI 做冒烟验证：
# ./run/wireshark &
# ./run/tshark -v