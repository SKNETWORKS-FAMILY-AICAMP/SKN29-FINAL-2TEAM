"""MCP endpoint URL 검사 — SSRF 1차 방어선 (11_MCP_설계 §4-1).

사용자가 **임의 URL을 등록하는 구조**다. 막지 않으면 우리 서버가 내부망을
대신 두드려 준다 — `http://169.254.169.254/`(클라우드 메타데이터), `http://
localhost:5432`(우리 DB), 사내 대시보드 어디든.

**등록 시와 호출 시 모두 검사한다.** 등록 때만 보면 DNS 리바인딩으로 뚫린다 —
등록 시점에는 공인 IP를 주고 호출 시점에 사설 IP를 주는 도메인을 막을 수 없다.
그래서 호출 직전에 이름을 다시 풀어 확인한다.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


class UnsafeEndpoint(ValueError):
    """등록하거나 호출해서는 안 되는 주소."""


#: 이름으로도 막는다. IP 검사를 통과해도 의미가 분명한 내부 호스트는 거절한다.
_BLOCKED_HOSTNAMES = frozenset(
    {"localhost", "localhost.localdomain", "metadata", "metadata.google.internal"}
)

#: 이 접미사로 끝나는 이름은 내부망 규약이다.
_BLOCKED_SUFFIXES = (".local", ".internal", ".localdomain", ".cluster.local")


def validate(url: str) -> str:
    """등록 시 검사. 통과하면 정규화된 URL 을 돌려준다.

    이름 풀이(DNS)까지 여기서 한다. 풀리지 않는 이름을 등록해 두면 나중에
    호출할 때야 실패하는데, 그때는 사용자가 무엇을 잘못 적었는지 모른다.
    """

    parsed = urlparse((url or "").strip())

    if parsed.scheme != "https":
        # http 를 허용하면 토큰이 평문으로 나간다. 예외를 두지 않는다 —
        # 로컬 개발용 http 서버는 설정으로 여는 순간 운영에서도 열린다.
        raise UnsafeEndpoint("MCP 주소는 https 여야 합니다.")
    if not parsed.hostname:
        raise UnsafeEndpoint("MCP 주소에 호스트가 없습니다.")
    if parsed.username or parsed.password:
        # `https://user:pass@내부호스트@evil.com` 같은 혼동을 애초에 없앤다.
        raise UnsafeEndpoint("주소에 인증 정보를 넣을 수 없습니다.")

    _check_hostname(parsed.hostname)
    for address in _resolve(parsed.hostname):
        _check_address(address, parsed.hostname)

    return parsed.geturl()


def recheck(url: str) -> None:
    """호출 직전 재검사. **DNS 리바인딩 대비라 생략하면 안 된다.**

    등록 때 공인 IP 를 주고 호출 때 사설 IP 를 주는 도메인이 있다. 등록 검사만
    하면 그 창이 그대로 열린다.
    """

    validate(url)


def _check_hostname(hostname: str) -> None:
    name = hostname.lower().rstrip(".")
    if name in _BLOCKED_HOSTNAMES or name.endswith(_BLOCKED_SUFFIXES):
        raise UnsafeEndpoint(f"내부 호스트에는 연결할 수 없습니다: {hostname}")


def _resolve(hostname: str) -> list[str]:
    """이름이 가리키는 주소 전부. **하나라도 사설이면 막는다.**

    A 레코드가 여러 개인 도메인이 공인 IP 하나와 사설 IP 하나를 함께 주면,
    첫 번째만 보고 통과시켰을 때 실제 연결이 사설 쪽으로 갈 수 있다.
    """

    try:
        infos = socket.getaddrinfo(hostname, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeEndpoint(f"주소를 확인할 수 없습니다: {hostname}") from exc
    return [info[4][0] for info in infos]


def _check_address(address: str, hostname: str) -> None:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError as exc:
        raise UnsafeEndpoint(f"올바르지 않은 주소입니다: {address}") from exc

    # `is_global` 하나로 사설(10./172.16-31./192.168.)·루프백(127.)·
    # 링크로컬(169.254. — 클라우드 메타데이터)·멀티캐스트·예약 대역이 전부
    # 걸린다. 대역을 손으로 나열하면 IPv6 쪽에서 빠지는 것이 생긴다.
    if not ip.is_global:
        raise UnsafeEndpoint(f"내부 주소에는 연결할 수 없습니다: {hostname} → {address}")
