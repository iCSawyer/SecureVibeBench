git checkout 5c36f6166c30b586be3e6cc600f58e1eb5830eb7
apt-get install -y libpcap-dev qtbase5-dev qttools5-dev qttools5-dev-tools qtmultimedia5-dev libqt5svg5-dev libgnutls28-dev libgcrypt20-dev
unset CC CXX CFLAGS CXXFLAGS LDFLAGS
git clean -fdx
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