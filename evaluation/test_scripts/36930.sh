cd /src/mruby
git checkout 1315e8751e70937e4cf43ba9225ea0cfaa67689d

apt install -y build-essential ruby rake git bison gperf

rake -j"$(nproc)"
rake test --verbose