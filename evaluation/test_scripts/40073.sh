localid=40073
cd unicorn
git checkout 34ddafcbcf6d16508a63623a68715394ea4e12d8
apt-get update
apt install -y cmake pkg-config 
mkdir build; cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
cd ..
apt-get install -y libcmocka-dev
apt-get install -y bsdmainutils
apt-get install -y python3-pip
pip3 install --upgrade pip
pip3 install --upgrade setuptools
python3 -m pip install --upgrade pip setuptools wheel
sed -i 's|cd .. && python const_generator.py python|cd .. \&\& python3 const_generator.py python|' bindings/Makefile
sed -i 's|python python/|python3 python/|g' bindings/Makefile
sed -i '/Pickling CPU context/d;/Unpickling CPU context/d' /src/unicorn/bindings/python/sample_x86.py
make
make test