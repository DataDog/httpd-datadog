# Build image for httpd-datadog CI.
#
# It contains:
#   - httpd 2.4 source code.
#   - Tools necessary to build httpd and mod_datadog.
#
# To publish:
#  docker buildx build --platform linux/amd64,linux/arm64 --output=type=image,name=datadog/docker-library:build-httpd-2.4,push=true .
FROM datadog/docker-library:dd-trace-cpp-ci

ADD scripts/setup-httpd.sh setup-httpd.sh

RUN apt update \
 && apt install -y libpcre3 libpcre3-dev expat libexpat-dev autoconf libtool libtool-bin

RUN ./setup-httpd.sh -o httpd \
 && cd httpd \
 && ./configure --with-included-apr --prefix=$(pwd)/httpd-build --enable-mpms-shared="all" \
 && make \
 && make install

