# VLESS Configuration Improvement Plan

## Analysis Summary

### Current Architecture
```
gateway_manager.py
├── XrayManager (config generation)
│   ├── generate_config()
│   ├── _build_vless_outbound()
│   └── _build_stream_settings()
└── GatewayMonitor (key rotation)
    ├── load_key_pool()
    ├── check_connection()
    └── run() - monitoring loop
```

### Identified Issues

#### 1. VLESS Key Parsing (`config/vless.py`)
**Current**: Only extracts UUID, address, port, security, sni, flow, pbk, sid
**Missing**: type, host, path, headers, alpn, fp, allowInsecure, mode, extra, packetEncoding, headerType

#### 2. Stream Settings Gaps
- **XHTTP**: Missing `xhttpSettings` with `path`, `host`, `mode`, `extra`
- **WebSocket**: Missing `wsSettings` with `path`, `headers`
- **gRPC**: Missing `grpcSettings` with `serviceName`, `multiMode`
- **TLS**: Missing `allowInsecure`, `alpn`, `fingerprint`
- **REALITY**: Missing `fingerprint`

#### 3. XrayManager Architecture
- `_build_vless_outbound()` re-invents outbound building
- `_build_stream_settings()` duplicates `config/builder` logic
- `generate_config()` doesn't use `XrayConfigBuilder`

#### 4. Monitoring Issues
- No latency-based key selection from `latency_ms` in keys.json
- No quality scoring for servers

---

## Implementation Plan

### Phase 1: Enhanced VLESS Key Parsing (`config/vless.py`)

#### 1.1 Update `VLESSInfo` Dataclass
```python
@dataclass
class VLESSInfo:
    uuid: str
    address: str
    port: int
    encryption: str = "none"
    security: str = "tls"
    sni: Optional[str] = None
    flow: Optional[str] = None
    
    # New parameters
    network: str = "tcp"  # type parameter
    host: Optional[str] = None
    path: Optional[str] = None
    headers: Optional[Dict[str, List[str]]] = None
    alpn: Optional[List[str]] = None
    fingerprint: Optional[str] = None
    reality_public_key: Optional[str] = None
    reality_short_id: Optional[str] = None
    reality_spider_x: Optional[str] = None
    allow_insecure: bool = False
    packet_encoding: Optional[str] = None
    mode: Optional[str] = None
    extra: Optional[Dict[str, Any]] = None
    header_type: Optional[str] = None
```

#### 1.2 Update `_parse_params()` Method
- Parse `alpn` as comma-separated list
- Parse `extra` as JSON object
- Normalize `allowinsecure` / `insecure` → `allow_insecure`

#### 1.3 Update `to_outbound_config()` Method
Build complete stream settings per network:
- XHTTP: `xhttpSettings` with all fields
- WebSocket: `wsSettings` with path, headers
- gRPC: `grpcSettings` with serviceName, multiMode
- TLS/REALITY: complete settings with fingerprints

### Phase 2: Update `StreamSettings` (`config/builder.py`)

Add missing fields:
```python
@dataclass
class StreamSettings:
    network: str = "tcp"
    security: str = "tls"
    sni: Optional[str] = None
    alpn: Optional[List[str]] = None
    fp: Optional[str] = None
    pbk: Optional[str] = None
    sid: Optional[str] = None
    spiderx: Optional[str] = None
    path: Optional[str] = None
    headers: Optional[Dict[str, List[str]]] = None
    allow_insecure: bool = False  # NEW
    host: Optional[str] = None  # NEW
    mode: Optional[str] = None  # NEW
    extra: Optional[Dict[str, Any]] = None  # NEW
    packet_encoding: Optional[str] = None  # NEW
    header_type: Optional[str] = None  # NEW
```

### Phase 3: Refactor `XrayManager` (`gateway_manager.py`)

Replace manual outbound building with `XrayConfigBuilder`:
```python
stream_settings = StreamSettings(
    network=vless_info.network,
    security=vless_info.security,
    sni=vless_info.sni,
    alpn=vless_info.alpn,
    fp=vless_info.fingerprint,
    pbk=vless_info.reality_public_key,
    sid=vless_info.reality_short_id,
    spiderx=vless_info.reality_spider_x,
    path=vless_info.path,
    headers=vless_info.headers,
    host=vless_info.host,
    mode=vless_info.mode,
    extra=vless_info.extra,
    allow_insecure=vless_info.allow_insecure,
)

outbound_config = OutboundConfig(
    tag=tag,
    protocol="vless",
    settings=vless_settings,
    stream_settings=stream_settings,
)
builder.add_outbound(outbound_config)
```

### Phase 4: Enhanced Monitoring

Add latency-based key selection from keys.json:
```python
def get_best_key_from_keys_json(keys_path: str) -> Optional[str]:
    # Parse all keys with latency info
    # Sort by latency_ms
    # Return lowest latency key
```

---

## Test Scenarios

1. **XHTTP + Reality**: Parse full config from keys.json
2. **WebSocket + TLS**: Verify host header and path
3. **TCP + none**: Simple direct connection
4. **Multi-mode XHTTP**: Parse extra JSON and mode parameter

---

## Priority

| Priority | Task | Impact |
|----------|------|--------|
| 1 | Update `VLESSInfo` dataclass | High |
| 2 | Update `_parse_params()` | High |
| 3 | Update `to_outbound_config()` | High |
| 4 | Update `StreamSettings` | Medium |
| 5 | Update `XrayManager` | High |
| 6 | Add latency selection | Medium |

---

## Notes

- XHTTP `extra` field is a JSON object containing:
  - `scMaxEachPostBytes`
  - `scMaxConcurrentPosts`
  - `scMinPostsIntervalMs`
  - `xPaddingBytes`
  - `noGRPCHeader`
- `alpn` is comma-separated: `h2,http/1.1`
- `allowinsecure` and `insecure` are aliases
- `mode` for XHTTP: `auto`, `stream-one`, `multiMode`
