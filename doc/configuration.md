# Configuring Datadog Tracing in Apache HTTP Server 

## `DatadogServiceName` directive

   - **Description:** Set the service name
   - **Syntax:** DatadogServiceName *name*
   - **Mandatory:** Yes
   - **Context:** Server config

Set the application name. 

Overriden by the `DD_SERVICE` environment variable.

## `DatadogServiceVersion` directive

   - Description: Set the service version
   - Syntax: DatadogServiceVersion *version*
   - Mandatory: No, but highly suggested
   - Context: server config

Set the application version.

Overriden by the `DD_VERSION` environment variable.

Exemple values: `1.2.3`, `6c44da20`, `2020.02.13`.

## `DatadogServiceEnvironment` directive
   - Description: Set the service environment
   - Syntax: DatadogServiceEnvironment *env_name*
   - Mandatory: No, but highly suggested
   - Context: server config

Set the name of the environment within which `httpd` is running.
Overriden by the `DD_ENV` environment variable.

Example: `prod`, `pre-prod`, `staging`.

## `DatadogAgentUrl` directive
   - Description: Set the datadog agent url
   - Syntax: DatadogAgentUrl *url*
   - Default: http://localhost:8126
   - Mandatory: No
   - Context: server config

Set a URL at which the Datadog Agent can be reached.
The following formats are supported:

 - http://\<domain or IP>:\<port>
 - http://\<domain or IP>
 - http+unix://\<path to socket>
 - unix://\<path to socket>
  
The port defaults to 8126 if it is not specified.

Overriden by the `DD_TRACE_AGENT_URL` environment variable.

## `DatadogEnable` directive

   - Description: Enable or disable the module
   - Syntax: DatadogEnable *On\|Off*
   - Default: On
   - Mandatory: No
   - Context: directory config

Directive to enable or disable the module.

## `DatadogSamplingRate` directive

   - description: Set the sampling rate
   - syntax: DatadogEnable *rate*
   - default: 1.0
   - Mandatory: No
   - Context: directory config

Set the sampling rate on traces started from `httpd`. 

Overriden by `DD_TRACE_SAMPLING_RULES`, `DD_TRACE_SAMPLE_RATE`
and `DD_TRACE_RATE_LIMIT` environment variables.

### `DatadogPropagationStyle`

   - description: Set the propagation style
   - syntax: DatadogPropagationStyle *style1* ... *styleN*
   - default: datadog tracecontext
   - Mandatory: No
   - Context: directory config

Set one or more trace propagation styles that will use to extract trace context from incoming requests and to inject trace context into outgoing requests.

When extracting trace context from an incoming request, the specified styles will be tried in order, stopping at the first style that yields trace context.

When injecting trace context into an outgoing request, all of the specified styles will be used.

The following styles are supported:
   - `datadog` is the Datadog style.
   - `traceontext` is the W3C (OpenTelemetry) style.
   - `b3` is the Zipking multi-header style.

## `DatadogTrustInboundSpan` directive

   - Description: Extract or not span from incoming requests
   - Syntax: DatadogTrustInboundSpan *On|Off*
   - Default: On
   - Mandatory: No
   - Context: directory config

If `on`, attempt to extract trace context from incoming requests. This way, nginx need not be the beginning of the trace — it can inherit a parent span from the incoming request.

If `off`, trace context will not be extracted from incoming requests. Nginx will start a new trace. This might be desired if extracting trace information from untrusted clients is deemed a security concern.

## `DatadogAddTag` directive

   - Description: Add custom tag
   - Syntax: DatadogAddTag *key* *value*
   - Mandatory: No
   - Context: directory config

Add tag. TODO: behavior when merging with context.
