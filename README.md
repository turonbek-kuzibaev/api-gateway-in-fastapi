# API Gateway in FastAPI

A production-ready, Kong API gateway built with FastAPI featuring plugin architecture, load balancing, circuit breaker, health checks, and an Admin API.

## Features

### Core Features
- **Request Proxying**: Route requests to backend services with path-based routing
- **Load Balancing**: Multiple algorithms (round-robin, least-connections, IP-hash, weighted, random)
- **Circuit Breaker**: Automatic failure detection and recovery
- **Health Checks**: Active health monitoring for upstream targets
- **Retry Logic**: Configurable retry with exponential backoff

### Plugin System
- **JWT Authentication**: Validate JWT Bearer tokens
- **API Key Authentication**: Authenticate via API keys
- **Rate Limiting**: Token bucket algorithm with multiple time windows
- **CORS**: Cross-origin resource sharing configuration
- **Request Transformer**: Modify requests before proxying
- **Response Transformer**: Modify responses before returning
- **IP Restriction**: Whitelist/blacklist IP addresses
- **Request Size Limiting**: Limit request body size
- **Logging**: Structured JSON logging with HTTP endpoint support

### Admin API
- Runtime configuration management
- Upstream and target management
- Health status monitoring
- Plugin information

## Installation

```bash
pip install -r requirements.txt
```

## Quick Start

```bash
# Start the gateway
uvicorn main:app --reload

# Or run directly
python main.py
```

The gateway will start on `http://localhost:8000` with the Admin API on `http://localhost:8000/admin`.

## Configuration

Configuration is defined in `config.yaml`:

### Gateway Settings

```yaml
gateway:
  host: "0.0.0.0"
  port: 8000
  admin_port: 8001
  admin_enabled: true
```

### Upstreams

Upstreams define pools of backend servers with load balancing:

```yaml
upstreams:
  - name: "users-upstream"
    algorithm: "round-robin"  # round-robin, least-connections, ip-hash, weighted, random
    targets:
      - host: "localhost"
        port: 8081
        weight: 100
      - host: "localhost"
        port: 8082
        weight: 50
    health_check:
      enabled: true
      type: "http"
      path: "/health"
      interval: 10
      timeout: 5
      healthy_threshold: 2
      unhealthy_threshold: 3
    circuit_breaker:
      enabled: true
      failure_threshold: 5
      success_threshold: 2
      timeout: 30
    retry:
      enabled: true
      max_retries: 3
      retry_on_status: [502, 503, 504]
```

### Services and Routes

Services connect routes to upstreams:

```yaml
services:
  - name: "users-service"
    upstream: "users-upstream"
    path: ""
    enabled: true
    routes:
      - name: "users-route"
        paths: ["/api/users", "/api/users/*"]
        methods: ["GET", "POST", "PUT", "DELETE"]
        strip_path: false
        plugins:
          - name: "jwt-auth"
            config:
              secret: "your-secret-key"
```

### Global Plugins

Plugins applied to all routes:

```yaml
plugins:
  - name: "cors"
    config:
      origins: ["*"]
      methods: ["GET", "POST", "PUT", "DELETE", "OPTIONS"]

  - name: "rate-limiting"
    config:
      minute: 60
      limit_by: "ip"
```

## Plugins

### jwt-auth

JWT authentication plugin.

```yaml
- name: "jwt-auth"
  config:
    secret: "your-secret-key"
    algorithm: "HS256"
    header_names: ["Authorization"]
    claims_to_verify: ["exp"]
    anonymous: null  # Optional: allow anonymous access
```

### key-auth

API key authentication plugin.

```yaml
- name: "key-auth"
  config:
    key_names: ["X-API-Key", "apikey"]
    key_in_header: true
    key_in_query: true
    hide_credentials: true
    keys:
      "api-key-1": "user1"
      "api-key-2": { "username": "user2", "custom_id": "u2" }
```

### rate-limiting

Rate limiting with multiple time windows.

```yaml
- name: "rate-limiting"
  config:
    second: null
    minute: 60
    hour: 1000
    day: null
    limit_by: "ip"  # ip, consumer, credential, header
    policy: "local"
    hide_client_headers: false
```

### cors

CORS handling.

```yaml
- name: "cors"
  config:
    origins: ["https://example.com"]
    methods: ["GET", "POST"]
    headers: ["Authorization", "Content-Type"]
    exposed_headers: []
    credentials: true
    max_age: 86400
```

### request-transformer

Transform requests before proxying.

```yaml
- name: "request-transformer"
  config:
    add:
      headers:
        X-Custom-Header: "value"
    remove:
      headers: ["X-Remove-Me"]
    rename:
      headers:
        Old-Header: "New-Header"
```

### response-transformer

Transform responses before returning.

```yaml
- name: "response-transformer"
  config:
    add:
      headers:
        X-Gateway: "true"
      json:
        gateway_processed: true
    remove:
      headers: ["Server"]
```

### ip-restriction

IP whitelist/blacklist.

```yaml
- name: "ip-restriction"
  config:
    allow: ["192.168.1.0/24", "10.0.0.1"]
    deny: ["192.168.1.100"]
    status: 403
    message: "IP not allowed"
```

### request-size-limiting

Limit request body size.

```yaml
- name: "request-size-limiting"
  config:
    allowed_payload_size: 10
    size_unit: "megabytes"  # bytes, kilobytes, megabytes, gigabytes
```

### logging

Structured logging.

```yaml
- name: "logging"
  config:
    http_endpoint: "http://log-server/logs"
    content_type: "application/json"
    include_request: true
    include_response: true
    include_latencies: true
    include_consumer: true
```

## Admin API

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/` | Gateway status |
| GET | `/admin/status` | Detailed status |
| GET | `/admin/upstreams` | List upstreams |
| GET | `/admin/upstreams/{name}` | Get upstream |
| POST | `/admin/upstreams` | Create upstream |
| DELETE | `/admin/upstreams/{name}` | Delete upstream |
| GET | `/admin/upstreams/{name}/targets` | List targets |
| POST | `/admin/upstreams/{name}/targets` | Add target |
| GET | `/admin/upstreams/{name}/health` | Health status |
| GET | `/admin/services` | List services |
| GET | `/admin/routes` | List routes |
| GET | `/admin/plugins` | List available plugins |

### Example: Add a Target

```bash
curl -X POST http://localhost:8000/admin/upstreams/users-upstream/targets \
  -H "Content-Type: application/json" \
  -d '{"host": "localhost", "port": 8083, "weight": 100}'
```

### Example: Check Health

```bash
curl http://localhost:8000/admin/upstreams/users-upstream/health
```

## Load Balancing Algorithms

| Algorithm | Description |
|-----------|-------------|
| `round-robin` | Distributes requests sequentially |
| `least-connections` | Sends to target with fewest active connections |
| `ip-hash` | Routes based on client IP hash (sticky sessions) |
| `weighted` | Weighted round-robin based on target weights |
| `random` | Random selection with optional weighting |

## Circuit Breaker

The circuit breaker protects against cascading failures:

- **Closed**: Normal operation, requests pass through
- **Open**: Failures exceeded threshold, requests fail fast
- **Half-Open**: Testing if service recovered

Configuration:
- `failure_threshold`: Failures before opening circuit (default: 5)
- `success_threshold`: Successes to close circuit (default: 2)
- `timeout`: Seconds before trying again (default: 30)

## Headers

### Request Headers Added

| Header | Description |
|--------|-------------|
| `X-Forwarded-For` | Client IP address |
| `X-Forwarded-Proto` | Original protocol |
| `X-Forwarded-Host` | Original host |
| `X-Consumer-Username` | Authenticated consumer username |
| `X-Consumer-Custom-ID` | Consumer custom ID |
| `X-User-ID` | User ID from JWT |

### Rate Limit Headers

| Header | Description |
|--------|-------------|
| `X-RateLimit-Limit-{period}` | Limit for period |
| `X-RateLimit-Remaining-{period}` | Remaining requests |
| `Retry-After` | Seconds until reset |

## Project Structure

```
api_gateway_in_fastapi/
├── main.py                 # Application entry point
├── config.yaml             # Gateway configuration
├── config.py               # Legacy config loader
├── requirements.txt        # Dependencies
├── admin/
│   ├── __init__.py
│   └── api.py              # Admin API endpoints
├── core/
│   ├── __init__.py
│   ├── gateway.py          # Main gateway logic
│   ├── router.py           # Route matching
│   └── plugin_chain.py     # Plugin execution
├── models/
│   ├── __init__.py
│   └── config.py           # Pydantic models
├── plugins/
│   ├── __init__.py
│   ├── base.py             # Plugin base classes
│   ├── registry.py         # Plugin registry
│   └── builtin/
│       ├── __init__.py
│       ├── jwt_auth.py
│       ├── key_auth.py
│       ├── rate_limiting.py
│       ├── cors.py
│       ├── request_transformer.py
│       ├── response_transformer.py
│       ├── ip_restriction.py
│       ├── request_size_limiting.py
│       └── logging.py
├── upstream/
│   ├── __init__.py
│   ├── manager.py          # Upstream management
│   ├── balancer.py         # Load balancing
│   ├── circuit_breaker.py  # Circuit breaker
│   ├── health_checker.py   # Health checks
│   └── target.py           # Target model
├── middleware/             # Legacy middleware
│   ├── __init__.py
│   ├── auth.py
│   └── rate_limit.py
└── proxy/                  # Legacy proxy
    ├── __init__.py
    └── handler.py
```

## Error Responses

| Status | Description |
|--------|-------------|
| 401 | Authentication failed |
| 403 | Forbidden (IP restriction, etc.) |
| 404 | No matching route |
| 413 | Request body too large |
| 429 | Rate limit exceeded |
| 502 | Bad gateway |
| 503 | Service unavailable / Circuit open |
| 504 | Gateway timeout |

## Generating JWT Tokens

```python
from jose import jwt
import time

payload = {
    "sub": "user123",
    "name": "John Doe",
    "exp": int(time.time()) + 3600  # 1 hour
}
token = jwt.encode(payload, "your-secret-key", algorithm="HS256")
print(token)
```

## License

MIT
