apt-get update
apt-get install -y build-essential cmake ninja-build git pkg-config \
    flex bison python3 python3-pip libglib2.0-dev libpcap-dev libgcrypt20-dev \
    zlib1g-dev libzstd-dev liblz4-dev libnghttp2-dev libbrotli-dev \
    libmaxminddb-dev libc-ares-dev libkrb5-dev libcap-dev libsystemd-dev \
    libssh-dev libgnutls28-dev libxml2-dev libminizip-dev libspeexdsp-dev
git checkout 8103dd92fcaffb35add2343bf6877c148640b1ca
rm -rf wireshark-build
mkdir wireshark-build
cd wireshark-build
cmake -G Ninja .. \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_wireshark=OFF \
  -DBUILD_qtgui=OFF \
  -DBUILD_tshark=ON \
  -DBUILD_TESTING=ON \
  -DENABLE_EXTCAP=ON
ninja -j"$(nproc)"
export WIRESHARK_EXTCAP_PATH="$(pwd)/run/extcap"
/usr/local/bin/python3.8 -m pip install --upgrade pip
/usr/local/bin/python3.8 -m pip install pytest
/usr/local/bin/python3.8 -m pip install "pytest-xdist>=3" pytest-forked
/usr/local/bin/python3.8 -m pytest -vv -rA