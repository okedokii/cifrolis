#!/usr/bin/env python3
import os
import shlex
from urllib.parse import urlsplit


def java_proxy_properties():
    properties = {}
    for protocol in ('http', 'https'):
        value = os.environ.get(protocol.upper() + '_PROXY') or os.environ.get(protocol + '_proxy')
        if not value:
            continue
        parsed = urlsplit(value if '://' in value else 'http://' + value)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname:
            raise ValueError('Java proxy setup expects an HTTP(S) proxy URL')
        if parsed.username is not None or parsed.password is not None:
            raise ValueError('Authenticated proxy URLs need separate Java authentication configuration; credentials are not copied into logs or properties')
        properties[protocol + '.proxyHost'] = parsed.hostname
        properties[protocol + '.proxyPort'] = str(parsed.port or (443 if parsed.scheme == 'https' else 80))
    if properties:
        hosts = ['localhost', '127.*', '[::1]']
        for value in (os.environ.get('NO_PROXY') or os.environ.get('no_proxy') or '').split(','):
            value = value.strip()
            if not value or '/' in value:
                continue
            if value.startswith('.'):
                hosts.extend((value[1:], '*' + value))
            else:
                hosts.append(value)
        properties['http.nonProxyHosts'] = '|'.join(dict.fromkeys(hosts))
    for option in shlex.split(os.environ.get('JAVA_TOOL_OPTIONS', '')):
        if option.startswith('-D') and '=' in option:
            key, value = option[2:].split('=', 1)
            if key in properties or key in ('http.proxyHost', 'http.proxyPort', 'https.proxyHost', 'https.proxyPort', 'http.nonProxyHosts'):
                properties[key] = value
    return properties


if __name__ == '__main__':
    existing = os.environ.get('JAVA_TOOL_OPTIONS', '')
    keys = {part[2:].split('=', 1)[0] for part in shlex.split(existing) if part.startswith('-D')}
    additions = [f'-D{key}={value}' for key, value in java_proxy_properties().items() if key not in keys]
    print(' '.join([existing, *additions]).strip())
