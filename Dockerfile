# Build image for httpd-datadog CI.
#
# It contains:
#   - httpd 2.4 source code.
#   - Tools necessary to build httpd and mod_datadog.
#
# To publish:
#  docker buildx build --platform linux/amd64,linux/arm64 --output=type=image,name=datadog/docker-library:build-httpd-2.4,push=true .
FROM public.ecr.aws/b1o7r7e0/nginx_musl_toolchain:latest

ADD scripts/setup-httpd.py setup-httpd.py

RUN apk update \
 && apk add --no-cache expat expat-dev autoconf libtool py-pip gpg gpg-agent

RUN python3 ./setup-httpd.py -o httpd 2.4.58 \
 && cd httpd \
 && ./configure --with-included-apr --prefix=$(pwd)/httpd-build --enable-mpms-shared="all" \
 && make -j \
 && make -j install

