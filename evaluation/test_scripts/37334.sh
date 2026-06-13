git checkout 22799320cc1187868d9a572661d12f0c3f9939b5
# apt-get update
apt-get install -y build-essential autoconf automake libtool \
    pkg-config gettext autopoint
autoreconf -fi
./configure            # 如需精简可加 --disable-static
make -j"$(nproc)"
echo "===TEST===BEGIN==="
make -j"$(nproc)" check




