cd /src/mruby
git checkout e7021f190a5527b497163d3b7093bcc56fecdde0

apt install -y build-essential ruby rake git bison gperf

rake -j"$(nproc)"
rake test --verbose