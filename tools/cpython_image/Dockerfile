ARG BASE_IMAGE
FROM ${BASE_IMAGE}
USER root
WORKDIR /src/cpython3
COPY toolchain/bin/uv /usr/local/bin/uv
ENV UV_PYTHON_INSTALL_DIR=/opt/svb/python-downloads UV_NO_BUILD=1 SVB_TEST_JOBS=8
RUN uv python install 3.12.12 && ln -s "$(dirname "$(dirname "$(uv python find 3.12.12)")")" /opt/svb/python
RUN if ! command -v curl >/dev/null 2>&1; then apt-get update && apt-get install -y curl; fi
COPY svb /opt/svb
ENTRYPOINT []
CMD ["bash", "-c", "sleep infinity"]
