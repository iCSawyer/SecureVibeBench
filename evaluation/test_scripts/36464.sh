cd /src/mruby
git checkout 47fca90069be44594d75eca69f1d978f5d9b4d65

apt install -y build-essential ruby rake git bison gperf

rake -j"$(nproc)"
rake test --verbose