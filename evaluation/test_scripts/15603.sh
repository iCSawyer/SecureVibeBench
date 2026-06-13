cd /src/mruby
git checkout 23783a44300a39efbbc312a6ca22fe61d94db857
apt install -y build-essential ruby rake git bison gperf
rake -j"$(nproc)"
rake test --verbose