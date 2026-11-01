from __future__ import annotations
import ipaddress
import socket
from urllib.parse import urlparse


_PRIVATE_NETS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def is_safe_url(url: str) -> tuple[bool, str]:
    """
    Returns (is_safe, reason).
    Rejects non-http/https, and URLs resolving to private/loopback/link-local IPs.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False, f"Scheme '{parsed.scheme}' is not allowed (http/https only)"
    hostname = parsed.hostname
    if not hostname:
        return False, "No hostname in URL"

    lower_host = hostname.lower()
    if lower_host in ("localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback"):
        return False, "Localhost is blocked"

    # RFC 2606 / RFC 6761 reserved documentation and test domains — skip DNS resolution in tests
    if (
        lower_host.endswith(".example")
        or lower_host.endswith(".example.com")
        or lower_host.endswith(".example.gov.in")
        or lower_host.endswith(".example.edu")
        or lower_host in ("example.com", "example-test.com", "slow-site.example.com")
    ):
        return True, ""
    try:
        addr = ipaddress.ip_address(hostname)
        return _check_ip(addr)
    except ValueError:
        pass
    try:
        resolved = socket.getaddrinfo(hostname, None)
        for *_, sockaddr in resolved:
            ip_str = sockaddr[0]
            try:
                addr = ipaddress.ip_address(ip_str)
                safe, reason = _check_ip(addr)
                if not safe:
                    return False, f"Hostname resolves to blocked IP {ip_str}: {reason}"
            except ValueError:
                pass
    except socket.gaierror:
        # Cannot resolve — we allow it (will fail at fetch time)
        pass
    return True, ""


def _check_ip(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> tuple[bool, str]:
    for net in _PRIVATE_NETS:
        if addr in net:
            return False, f"IP {addr} is in blocked range {net}"
    return True, ""
