git checkout c8e24f5c55cb37b9a311e5226923d291892de892
apt-get install -y libpcap-dev qtbase5-dev qttools5-dev qttools5-dev-tools qtmultimedia5-dev libqt5svg5-dev libgnutls28-dev libgcrypt20-dev locales
unset CC CXX CFLAGS CXXFLAGS LDFLAGS
git clean -fdx
sed -i 's/^# *en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen || true
locale-gen en_US.UTF-8
update-locale LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8
export LC_CTYPE=en_US.UTF-8
export PYTHONIOENCODING=UTF-8
rm -rf build && mkdir build && cd build
cmake .. \
  -DENABLE_PCAP=ON \
  -DENABLE_QT=ON \
  -DBUILD_wireshark=ON \
  -DENABLE_GNUTLS=ON \
  -DTEST_EXTRA_ARGS=--disable-capture \
  -DBUILD_tests=ON
cmake --build . -- -j"$(nproc)"
make -j"$(nproc)" exntest oids_test reassemble_test tvbtest wmem_test
cmake --build . --target run
useradd -m -r -s /bin/bash ws 2>/dev/null || true
chown -R ws:ws /src/wireshark
su -s /bin/bash ws -c 'cd /src/wireshark/build && ctest --force-new-ctest-process -j 4 --verbose'