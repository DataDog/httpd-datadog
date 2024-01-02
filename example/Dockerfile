FROM httpd:2.4

ADD https://github.com/DataDog/httpd-datadog/blob/dmehala/add-trace/install_module.sh /datadog/install.sh

COPY ./httpd.conf /usr/local/apache2/conf/httpd.conf

RUN /datadog/install.sh
