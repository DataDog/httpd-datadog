# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Docker Compose-based demonstration project for testing distributed tracing with Apache httpd-datadog module. The project consists of three main services:

- **apache**: Reverse proxy with Datadog tracing module, proxies requests to the HTTP service
- **httpjs**: Simple Node.js HTTP server with Datadog APM tracing
- **datadog**: Datadog Agent for collecting traces and logs

## Architecture

```
Client → apache (port 8888) → httpjs (port 8080) → Datadog Agent (port 8126)
```

The Apache service loads the `mod_datadog.so` to enable APM tracing for proxy requests. The Node.js HTTP service uses the dd-trace library to instrument HTTP handlers.

## Prerequisites

Before running any commands, ensure the Datadog API key is set. You can either:

**Option 1: Export environment variable**
```bash
export DD_API_KEY=<your_api_key>
```

**Option 2: Use envchain (recommended for security)**
```bash
# Store API key in keychain (run once)
envchain --set datadog DD_API_KEY

# Use envchain when running docker-compose commands
envchain datadog docker-compose up -d
```

The runtime environment must be linux/amd64 for the Datadog Apache module to work properly.

## Common Commands

### Start the application
```bash
# With exported environment variable
docker-compose up -d

# Or with envchain
envchain datadog docker-compose up -d
```

### Make a test request (generates traces)
```bash
curl localhost:8888
```

### Load testing
```bash
make stress
```
This uses vegeta to send 1000 req/s for 60 seconds to test the tracing under load.

### View logs
```bash
docker-compose logs -f [service_name]
```

### Rebuild and restart services (required after config changes)
```bash
# With exported environment variable
docker-compose down && docker-compose build && docker-compose up -d

# Or with envchain
envchain datadog docker-compose down && envchain datadog docker-compose build && envchain datadog docker-compose up -d
```

### Stop and clean up
```bash
docker-compose down
```

## Service Details

### apache (Port 8888)
- Uses httpd:2.4 base image with mod_datadog module
- Dynamically downloads latest mod_datadog module from GitHub releases
- Proxies all requests to the `api` service
- **Enhanced logging**: Includes Datadog trace and span IDs for correlation
- Log format: `dd.trace_id="%{datadog_trace_id}e" dd.span_id="%{datadog_span_id}e"`
- Exposes Apache server-status endpoint on port 81 for Datadog monitoring
- Configuration: `apache/httpd.conf`

### httpjs (Port 8080)
- Simple Node.js HTTP server with Datadog APM tracing via dd-trace
- Returns JSON response with service name and request headers
- Uses Alpine Linux base image with Node.js and npm
- Automatically instruments HTTP requests with dd-trace/init
- Listens on port 8080 and handles SIGTERM gracefully

### datadog
- Official Datadog Agent 7 image
- Configured for APM, logs, and metrics collection
- Connects to containers via Docker socket for autodiscovery

## File Structure

- `docker-compose.yml`: Main orchestration configuration
- `apache/`: Apache configuration and Dockerfile
- `httpjs/`: Node.js HTTP service with Dockerfile and http.js server
- `Makefile`: Contains stress testing command
- `doc/`: Documentation and trace sample images