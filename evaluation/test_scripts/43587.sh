localid=43587
git checkout db9ab417b11eaf96722b6cfb22f8ead5e22513c9
mkdir build && cd build
cmake .. 
make -j"$(nproc)"
cd ..
python3 test/spec_tests.py -p ./build/md2html/md2html -s test/spec.txt