# inject-browser-sdk Library

Core library for determining the HTML document injection point for the Datadog RUM Browser SDK. Read the full [library reference here](https://datadoghq.dev/inject-browser-sdk/injectbrowsersdk/).

## Overview

This library provides the core functionality for parsing HTML documents and determining the injection point for the Datadog RUM Browser SDK. It is used by various web server modules (NGINX, Apache HTTP Server, IIS) to enable automatic RUM injection.

## Features

- Efficient streaming parser that works on chunked HTML responses
- Minimal memory footprint
- Cross-platform compatibility (Linux, Windows, macOS)
- Foreign Function Interface (FFI) for cross-language interoperability

## Project Structure

The library is organized into several components:

```
lib/
├── inject-browser-sdk/       # Core injection library
├── inject-browser-sdk-ffi/   # FFI bindings for C/C++
```
