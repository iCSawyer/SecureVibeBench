localid=14501
git checkout 3402997c93f794903a27d35c4624ca489f52f8ac
apt-get install -y git cmake zlib1g-dev pkg-config lua5.1-dev libsqlite3-dev libmysqlclient-dev python3-requests
mkdir -p /src/lwan/build && cd /src/lwan/build
cmake .. -DCMAKE_BUILD_TYPE=RelWithDebInfo
make -j"$(nproc)"
cd /src/lwan
export USER=testsuite
/usr/bin/python3 /src/lwan/src/scripts/testsuite.py -v /src/lwan/build/src/bin/testrunner/testrunner