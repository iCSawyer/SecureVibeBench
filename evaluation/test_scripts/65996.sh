cd /src/mruby
git checkout 69cf074778f2e08c565f03e4251aaef38879ca69

apt install -y build-essential ruby rake git bison gperf

rake -j"$(nproc)"
rake test --verbose