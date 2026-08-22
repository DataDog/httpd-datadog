FROM debian:stable-slim

# Install dependencies (only baseline system tools)
RUN apt-get update && \
    apt-get install -y apache2 curl unzip && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Enable required Apache modules
RUN a2enmod rewrite proxy proxy_http

# Download and install mod_datadog directly
RUN cd /tmp && \
    # Get latest release info using curl and basic text processing
    RELEASE_DATA=$(curl -s https://api.github.com/repos/DataDog/httpd-datadog/releases/latest) && \
    # Extract download URL for the zip file using grep and cut
    DOWNLOAD_URL=$(echo "$RELEASE_DATA" | grep -o '"browser_download_url": *"[^"]*mod_datadog_artifact.zip"' | cut -d '"' -f 4) && \
    # Download and install
    curl -Lf -o mod_datadog_artifact.zip "$DOWNLOAD_URL" && \
    unzip -j mod_datadog_artifact.zip -d /usr/lib/apache2/modules/ && \
    rm mod_datadog_artifact.zip

# Enable datadog module
RUN echo "LoadModule datadog_module /usr/lib/apache2/modules/mod_datadog.so" > /etc/apache2/mods-available/datadog.load && \
    a2enmod datadog

# Copy Apache configuration
COPY apache-config.conf /etc/apache2/sites-available/000-default.conf

# Update ports configuration to listen on 8888 and 81
RUN sed -i 's/Listen 80/Listen 8888\nListen 81/' /etc/apache2/ports.conf

# Create app directory
RUN mkdir -p /app

# Create startup script
RUN echo '#!/bin/bash\napachectl -D FOREGROUND' > /app/start.sh && \
    chmod +x /app/start.sh

WORKDIR /app

EXPOSE 8888 81

CMD ["./start.sh"]