// This is an HTTP server that listens on port 8080 and responds to all
// requests with some text, including the request headers as JSON.

require('dd-trace').init({ logInjection: true });

const http = require('http');
const process = require('process');
const { createLogger, format, transports } = require('winston');

const logger = createLogger({
  level: 'info',
  format: format.json(),       // JSON required for auto-injection
  transports: [new transports.Console()]
});

// In order for the span(s) associated with an HTTP request to be considered
// finished, the body of the response corresponding to the request must have
// ended.
const ignoreRequestBody = request => {
  request.on('data', () => {});
  request.on('end', () => {});
}

const requestListener = function (request, response) {
  ignoreRequestBody(request);
  const responseBody = JSON.stringify({
    "service": "http",
    "headers": request.headers
  }, null, 2);
  
  // Log with Winston for automatic trace injection
  logger.info('HTTP request processed', {
    method: request.method,
    url: request.url,
    userAgent: request.headers['user-agent']
  });
  
  response.end(responseBody);
}

console.log('http node.js web server is running');
const server = http.createServer(requestListener);
server.listen(8080);

process.on('SIGTERM', function () {
  console.log('Received SIGTERM');
  server.close(function () { process.exit(0); });
});
