PROXY INSTALLER
===============
Necessary components to install the proxy / web server module.
It consists of an sh script, plus a go binary (configurator) that performs the actual installation.
Running this installer results in the NGINX/httpd module being installed locally and RUM injection configured.

Shell script
------------
Verifies connectivity to the Datadog Agent. Detects the architecture, downloads 
the configurator for the specific architecture and invokes it.

Configurator
------------
Does the bulk of the installation.
1. Validates parameters
2. Validates the proxy installation
3. Downloads the appropriate proxy module
4. Makes neccessary config modifications
5. Validates the modified configurations

# Build

Compile the go binary
```bash
env GOOS=linux go -C configurator build -o ../proxy-configurator
```

# Unit Testing

```bash
go test -C configurator -v
```

# Integration Testing

Start the docker-compose file provided. It boots up a proxy / web server
instance and a Datadog Agent within a network.

Select the desired Dockerfile from those provided with `PROXY_DOCKERFILE`, and the 
matching proxy kind with `PROXY_KIND`. Example:
```bash
DOCKER_DEFAULT_PLATFORM=linux/amd64 PROXY_DOCKERFILE=nginx.bookworm.Dockerfile PROXY_KIND=nginx DD_API_KEY=<YOUR_API_KEY> docker compose -f test/docker-compose.yml up --exit-code-from proxy
```

# Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `proxyKind` | string | Yes | - | Proxy kind to install (`nginx` or `httpd`). |
| `appId` | string | Yes | - | Application ID. |
| `site` | string | Yes | - | Site. |
| `clientToken` | string | Yes | - | Client Token. |
| `sessionSampleRate` | int | Yes | - | Session Sample Rate (0-100). |
| `sessionReplaySampleRate` | int | Yes | - | Session Replay Sample Rate (0-100). |
| `remoteConfigId` | string | Yes | - | Remote Configuration ID. |
| `arch` | string | Yes | - | Architecture (`amd64` or `arm64`). |
| `agentUri` | string | No | `http://localhost:8126` | Datadog Agent URI. |
| `skipVerify` | bool | No | `false` | Skip verifying downloads. |
| `verbose` | bool | No | `false` | Verbose output. |
| `dryRun` | bool | No | `false` | Dry run (no changes made). |
| `skipDownload` | bool | No | `false` | Skip the download of this installer and use a local binary instead. |
