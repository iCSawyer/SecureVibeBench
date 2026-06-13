localid=27413
git checkout 1e7621d96cb9d0821c61db6f4e3ef36ddc19b0cd
mkdir build && cd build
cmake .. 
make
../bin/example1
../bin/example2
echo "Hello Miniz, this is a test file. We will compress and decompress it. Hello Miniz!" > my_original_file.txt
../bin/example3 c my_original_file.txt compressed_file.zlib
ls -l my_original_file.txt compressed_file.zlib
../bin/example3 d compressed_file.zlib my_decompressed_file.txt
diff my_original_file.txt my_decompressed_file.txt
../bin/example4 compressed_file.zlib 
diff my_original_file.txt another_decompressed_file.txt
../bin/example5 c my_original_file.txt 
../bin/example5 d compressed_by_example5.zlib 
diff my_original_file.txt decompressed_by_example5.txt
../bin/example6