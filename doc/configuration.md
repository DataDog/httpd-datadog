# Configuring the Datadog module for Apache HTTP Server

> [!TIP]
> Server directives should be set only once per server or virtual server. On the other hand, directory configuration gives you the flexibility to fine-tune settings for each specific direction.

- [Tracing](#configuring-tracing)
- [Real User Monitoring (RUM)](#configuring-real-user-monitoring)

# Configuring Tracing
## `DatadogServiceName` directive

   - **Description**: Set the service name
   - **Syntax:** DatadogServiceName *name*
   - **Mandatory:** No, but highly recommended
   - **Context:** Server config

Set the application name. 

Overriden by the `DD_SERVICE` environment variable.

## `DatadogServiceVersion` directive

   - **Description**: Set the service version
   - **Syntax**: DatadogServiceVersion *version*
   - **Mandatory**: No, but highly suggested
   - **Context**: Server config

Set the application version.

Overriden by the `DD_VERSION` environment variable.

Exemple values: `1.2.3`, `6c44da20`, `2020.02.13`.

## `DatadogServiceEnvironment` directive
   - **Description**: Set the service environment
   - **Syntax**: DatadogServiceEnvironment *env_name*
   - **Mandatory**: No, but highly recommended
   - **Context**: Server config

Set the name of the environment within which `httpd` is running.
Overriden by the `DD_ENV` environment variable.

Example: `prod`, `pre-prod`, `staging`.

## `DatadogAgentUrl` directive
   - **Description**: Set the datadog agent url
   - **Syntax**: DatadogAgentUrl *url*
   - **Default**: http://localhost:8126
   - **Mandatory**: No
   - **Context**: Server config

Set a URL at which the Datadog Agent can be reached.
The following formats are supported:

 - http://\<domain or IP>:\<port>
 - http://\<domain or IP>
 - http+unix://\<path to socket>
 - unix://\<path to socket>
  
The port defaults to 8126 if it is not specified.

Overriden by the `DD_TRACE_AGENT_URL` environment variable.

## `DatadogTracing` directive
   - **Description**: Enable or disable the module
   - **Syntax**: DatadogTracing *On\|Off*
   - **Default**: On
   - **Mandatory**: No
   - **Context**: Directory config

Directive to enable or disable the module.

## `DatadogSamplingRate` directive
   - **Description**: Set the trace sampling rate
   - **Syntax**: DatadogSamplingRate *rate*
   - **Default**: 1.0
   - **Mandatory**: No
   - **Context**: Directory config

Set the sampling rate on traces started from `httpd`. The value should be between `0.0` and `1.0`.

Overriden by `DD_TRACE_SAMPLING_RULES`, `DD_TRACE_SAMPLE_RATE`
and `DD_TRACE_RATE_LIMIT` environment variables.

## `DatadogPropagationStyle` directive
   - **Description**: Set the propagation style
   - **Syntax**: DatadogPropagationStyle *style1* ... *styleN*
   - **Default**: datadog tracecontext
   - **Mandatory**: No
   - **Context**: Directory config

Set one or more trace propagation styles that will use to extract trace context from incoming requests and to inject trace context into outgoing requests.

When extracting trace context from an incoming request, the specified styles will be tried in order, stopping at the first style that yields trace context.

When injecting trace context into an outgoing request, all of the specified styles will be used.

The following styles are supported:
   - `datadog` is the Datadog style.
   - `traceontext` is the W3C (OpenTelemetry) style.
   - `b3` is the Zipking multi-header style.

## `DatadogTrustInboundSpan` directive
   - **Description**: Extract or not span from incoming requests
   - **Syntax**: DatadogTrustInboundSpan *On|Off*
   - **Default**: On
   - **Mandatory**: No
   - **Context**: Directory config

If `on`, attempt to extract trace context from incoming requests. This way, nginx need not be the beginning of the trace — it can inherit a parent span from the incoming request.

If `off`, trace context will not be extracted from incoming requests. Nginx will start a new trace. This might be desired if extracting trace information from untrusted clients is deemed a security concern.

## `DatadogAddTag` directive
   - **Description**: Add custom tag
   - **Syntax**: DatadogAddTag *key* *value*
   - **Mandatory**: No
   - **Context**: Directory config

To enhance trace data, you can set key/value pairs that will serve as tags on all traces. Each invocation of `DatadogAddTag` adds the specified key/value pair to the current context.

For clarity, consider the following example:

````
# Both tags will apply to the </hello> endpoint.
<Location "/hello">
   DatadogAddTag "foo" "bar"
   DatadogAddTag "beep" "boop"
</Location>

# Only the "data=dog" tag will apply to the </world> endpoint.
<Location "/world">
   DatadogAddTag "data" "dog"
</Location>
````

Additionally, tags inherit from the parent scope:

````
# In the httpd.conf file
DatadogAddTag "team" "apm/proxy"
<Location "/foo">
   DatadogAddTag "location" "/foo"
</Location>
````

When calling the `</foo>` endpoint, both the team and location tags will be added.

## `DatadogDelegateSampling` directive
   - **Description**: Add custom tag
   - **Syntax**: DatadogDelegateSampling *On|Off*
   - **Mandatory**: No
   - **Context**: Directory config

If `on`, and if `httpd` is making the trace sampling decision (i.e. if `httpd` is the first service in the trace), then delegate the sampling decision to the upstream service. nginx will make a provisional sampling decision, and convey it along with the intention to delegate to the upstream. The upstream service might then make its own sampling decision and convey that decision back in the response. If the upstream does so, then nginx will use the upstream's sampling decision instead of the provisional decision.

Sampling delegation exists to allow `httpd` to act as a reverse proxy for multiple different services, where the trace sampling decision can be better made within the service than it can within `httpd`.

# Configuring Real User Monitoring

> [!IMPORTANT]
> 🚧 RUM SDK Injection is currently in Private Beta! 🚧
>
> Interested in early access? [Apply to join the beta program today!](https://www.datadoghq.com/private-beta/rum-sdk-auto-injection/)

## `DatadogRum` directive
   - **Description**: Enable or disable the RUM Injection
   - **Syntax:** DatadogRum *On\|Off*
   - **Default:** Off
   - **Context:** Server and Directory

Directive to enable or disable RUM SDK Injection.

## `DatadogRumSettings` section
- **Description**: Container for Datadog RUM settings
   - **Syntax:**:
   ```xml
   <DatadogRumSettings>
     DatadogRumOption "applicationId" "my-app-id"
     ...
     DatadogRumOption "sessionSampleRate" "100"
   </DatadogRumSettings>
   ```

## `DatadogRumOption` directive

> [!NOTE]
> `DatadogRumOption` must be set only in `DatadogRumSettings` sections.

- **Description**: Set options on the RUM SDK
   - **Syntax:** DatadogRumOption *key* *value1* ... *valueN*
   - **Mandatory:** Depends. See table below.
   - **Context:** DatadogRumSettings

Set options on the RUM SDK that will be injected. As of now, here is the list of settings supported:

| Setting | Description | Mandatory | Example |
| ------- | ----------- | --------- | ------- |
| `applicationId` | RUM Application ID. Defined in the Datadog UI. | Yes | |
| `clientToken` | Datadog Client Token. Defined in the Datadog UI. | Yes | |
| `site` | Datadog site parameter for your organization. | Yes | `datadoghq.com` |
| `service` | Service name for your application | No | `my-web-application` |
| `env` | Application's environment | No | `prod`, `pre-prod`, `staging` |
| `version` | Application's version | No | `1.2.3`, `6c44da20`, `2020.02.13` |
| `trackUserInteractions` | Enables autonatic collection of users actions. | No | `true` or `false` |
| `trackResources` | Enables collection of resource events. | No | `true` or `false` |
| `trackLongTasks` | Enables collection of long task events. | No | `true` or `false` |
| `defaultPrivacyLevel` | See Session reaply Privacy Options. | No | `true` or `false` |
| `sessionSampleRate` | The percentage of sessions to track: `100` for all, `0` for none. | No | `100`, `50`, `0` |
| `sessionReplaySampleRate` | The percentage of tracked sessions to capture: `100` for all, `0` for none. | No | `100`, `50`, `0` |
| `allowedTracingUrls` | A list of request URLs used to inject tracing headers. For more information, see [Connect RUM and Traces](https://docs.datadoghq.com/real_user_monitoring/platform/connect_rum_and_traces/?tab=browserrum). | No | "https://api.example.com" "https:\/\/.*\.my-api-domain\.com/" |

Example:
```
<DatadogRumSettings>
    DatadogRumOption "applicationId" "<APP-ID>"
    DatadogRumOption "clientToken" "<CLIENT-TOKEN>"
    DatadogRumOption "site" "datadoghq.com"
    DatadogRumOption "service" "httpd-injection"
    DatadogRumOption "env" "demo"
    DatadogRumOption "version" "1.0.0"
    DatadogRumOption "sessionSampleRate" "100"
    DatadogRumOption "sessionReplaySampleRate" "100"
    DatadogRumOption "trackResources" "true"
    DatadogRumOption "trackLongTasks" "true"
    DatadogRumOption "trackUserInteractions" "true"
    DatadogRumOption "allowedTracingUrls" "https://api.example.com" "https://backend.example.org" "https://staging.backend.example.org"
</DatadogRumSettings>
```

## RUM Configuration Example
`httpd.conf`
```
LoadModule status_module mod_status.so
LoadModule datadog_module mod_datadog.so

DatadogRum On
<DatadogRumSettings>
    DatadogRumOption "applicationId" "<DATADOG_APPLICATION_ID>"
    DatadogRumOption "clientToken" "<DATADOG_CLIENT_TOKEN>"
    DatadogRumOption "site" "<DATADOG_SITE>"
    DatadogRumOption "service" "my-web-application"
    DatadogRumOption "env" "production"
    DatadogRumOption "version" "1.0.0"
    DatadogRumOption "sessionSampleRate" 10
    DatadogRumOption "sessionReplaySampleRate" 100
    DatadogRumOption "trackResources" true
    DatadogRumOption "trackLongTasks" true
    DatadogRumOption "trackUserInteractions" true
</DatadogRumSettings>

<Location "/proxy">
    <DatadogRumSettings>
        DatadogRumOption "applicationId" "<DATADOG_APPLICATION_ID>"
        DatadogRumOption "clientToken" "<DATADOG_CLIENT_TOKEN>"
        DatadogRumOption "site" "<DATADOG_SITE>"
        DatadogRumOption "service" "proxied-website"
        DatadogRumOption "env" "dev"
        DatadogRumOption "version" "0.2.0"
        DatadogRumOption "sessionSampleRate" "100"
        DatadogRumOption "trackResources" "true"
        DatadogRumOption "trackUserInteractions" "true"
    </DatadogRumSettings>
    ProxyPass "http://localhost:8081/"
</Location>

<Location "/health">
    DatadogRum Off
    SetHandler server-status
</Location>
```
