git checkout 6c6878ce4cdc5ac58e5115553656e05c9695544e
unset CC CXX CFLAGS CXXFLAGS LDFLAGS CPPFLAGS
apt-get update
apt-get install -y build-essential libtalloc-dev libkqueue-dev \
                    libssl-dev libpcap-dev libreadline-dev pkg-config \
                    libldap2-dev libmysqlclient-dev libpq-dev libpam0g-dev \
                     libperl-dev libsnmp-dev asciidoctor
export PKG_CONFIG_LIBDIR=/usr/lib/x86_64-linux-gnu/pkgconfig:/usr/share/pkgconfig
unset PKG_CONFIG_PATH
export CPPFLAGS="-I/usr/include"
export LDFLAGS="-L/usr/lib/x86_64-linux-gnu"
[ -x /usr/local/bin/openssl ] && mv /usr/local/bin/openssl /usr/local/bin/openssl.bak
[ -d /usr/local/include/openssl ] && mv /usr/local/include/openssl /usr/local/include/openssl.bak
hash -r
which openssl         # 应该是 /usr/bin/openssl
openssl version       # 应该显示 OpenSSL 1.1.1f 31 Mar 2020
cd /src/freeradius-server
rm -f config.cache
./configure --prefix=/usr/local
make -j"$(nproc)"
make install
cd /usr/local/etc/raddb/certs
make clean all
/usr/local/sbin/radiusd -XC
