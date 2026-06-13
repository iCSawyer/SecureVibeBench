git checkout 4e9c96f00614d829347dce7f183c3bedc2b35829
apt install -y \
  build-essential autoconf automake libtool pkg-config \
  python3 python3-pip python3-setuptools \
  libssl-dev libcap-ng-dev \
  netcat-openbsd curl graphviz \
  iproute2 procps

python3 -m pip install --user --upgrade "pip<21" "setuptools<50" "wheel<0.35"
pip3 install --user "pyftpdlib<2.0" "tftpy<0.9" "flake8<4"

./boot.sh
./configure
make -j"$(nproc)"
make -j"$(nproc)" check