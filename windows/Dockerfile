# Utiliser une image de base officielle Ubuntu
FROM datadog/docker-library:httpd-datadog-ci-2.4
# Définir l'option non interactive pour éviter les prompts
ENV DEBIAN_FRONTEND=noninteractive

RUN git clone https://github.com/DataDog/httpd-datadog.git
RUN cd httpd-datadog && git submodule update --init --recursive

# Mettre à jour les paquets et installer MinGW et les outils nécessaires
RUN apt-get update && \
    apt-get install -y mingw-w64 && \
    apt-get clean

RUN export TARGET=x86_64-w64-mingw32 \
    && export CC=$TARGET-gcc \
    && export CXX=$TARGET-g++ \
    && export AR=$TARGET-ar \
    && export RANLIB=$TARGET-ranlib \
    && export STRIP=$TARGET-strip \
    && export WINDRES=$TARGET-windres 

RUN git clone --branch 1.7.4 --depth 1 https://github.com/apache/apr.git

WORKDIR /apr
RUN ./buildconf
RUN ./configure --host=$TARGET --prefix=/install/apr
RUN make -j12 
RUN make install

WORKDIR /

RUN git clone --branch 1.6.3 --depth 1 https://github.com/apache/apr-util.git
WORKDIR /apr-util
RUN ./buildconf
RUN ./configure --host=$TARGET --prefix=/install/apr-util
RUN make -j12 
RUN make install

WORKDIR /

RUN git clone --branch 1.1.x --depth 1 https://github.com/apache/apr-iconv.git
WORKDIR /apr-iconv
RUN ./buildconf
RUN ./configure --host=$TARGET --prefix=/install/apr-iconv
RUN make -j12
RUN make install


RUN wget https://sourceforge.net/projects/pcre/files/pcre/8.45/pcre-8.45.tar.gz
RUN tar -xzf pcre-8.45.tar.gz
RUN rm pcre-8.45.tar.gz