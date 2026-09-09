"""Explicit local/LAN modes with a same-origin boundary, not a hard-coded IP list."""
import ipaddress
import os
import socket
from urllib.parse import urlsplit


def lan_enabled():
    return os.environ.get('PMC_LAN', '').lower() in {'1', 'true'}


def local_names():
    names={'localhost','127.0.0.1','::1'}
    for name in {socket.gethostname(),socket.getfqdn()}:
        if name:
            names.add(name.lower().rstrip('.'))
            try:
                names.update(row[4][0].split('%')[0].lower() for row in socket.getaddrinfo(name,None))
            except OSError:
                pass
    return names


def authority(value):
    try:
        parsed=urlsplit('//'+value)
        if not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
            return None
        return parsed.hostname.lower().rstrip('.'),parsed.port or 80
    except ValueError:
        return None


def host_allowed(value, test_client=False):
    parsed=authority(value)
    if not parsed:return False
    host,port=parsed
    if test_client and host=='testserver' and port==80:return True
    if port!=8765:return False
    if host in {'localhost','127.0.0.1','::1'}:return True
    return lan_enabled() and host in local_names()


def same_origin(origin,scheme,host):
    try:
        parsed=urlsplit(origin)
        if parsed.scheme!=scheme or parsed.path or parsed.query or parsed.fragment:
            return False
        return authority(parsed.netloc)==authority(host) and authority(host) is not None
    except ValueError:
        return False


def endpoints():
    urls=['http://127.0.0.1:8765']
    if lan_enabled():
        for name in sorted(local_names()):
            try:
                address=ipaddress.ip_address(name)
                if address.version==4 and not address.is_loopback and not address.is_unspecified:
                    urls.append(f'http://{name}:8765')
            except ValueError:
                pass
        urls.append(f'http://{socket.gethostname().lower()}:8765')
    return dict(mode='lan' if lan_enabled() else 'local',urls=list(dict.fromkeys(urls)))
