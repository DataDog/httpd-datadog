# Datadog RUM Auto-Instrumentation

This project enables automatic injection of the Datadog RUM Browser SDK into HTML responses without requiring changes to your application code. It works by intercepting HTML responses and inserting the SDK snippet before the closing `</head>` tag.

[Browser Monitoring Auto-Instrumentation (Server-Side)](https://docs.datadoghq.com/real_user_monitoring/browser/setup/server/) public documentation.

## Design Considerations

- **Zero Code Changes**: No need to modify your application code
- **Low Performance Impact**: Minimal impact on response times
- **Flexible Configuration**

## Architecture

The project consists of several components:

1. **[Core Injection Library](lib/)**: Written in Rust, handling the HTML parsing and determining appropriate injection location
2. **Web Server Module**: Native module for IIS (Other proxies/web servers may live in different repos)
3. **Installer Scripts**: For easy deployment and configuration

## Contributing

We welcome contributions to the project! Please see our [Contributing Guide](CONTRIBUTING.md) for more information.

## License

This project is licensed under the Apache 2.0 License - see the [LICENSE](LICENSE) file for details.

## Support

For support, please [open an issue](https://github.com/DataDog/inject-browser-sdk/issues/new) or contact [Datadog support](https://docs.datadoghq.com/help/).
