git checkout c33cb2d8935002f8ba942028a1f0871d075345a1
apt-get install -y git curl build-essential clang lld binutils

curl -L https://github.com/bazelbuild/bazelisk/releases/latest/download/bazelisk-linux-amd64 \
  -o /usr/local/bin/bazel && chmod +x /usr/local/bin/bazel
export USE_BAZEL_VERSION=6.3.2
bazel shutdown || true
bazel clean --expunge || true
bazel build //tcmalloc/testing:hello_main
bazel run   //tcmalloc/testing:hello_main
bazel query 'kind(".*_test", //tcmalloc:all)'
bazel test //tcmalloc:cpu_cache_test --test_output=errors -s --verbose_failures
TESTS=$(bazel query 'kind(".*_test", //tcmalloc:all)')
bazel test $TESTS --test_output=errors --keep_going -s --verbose_failures