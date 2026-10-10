"""Pytest plugin: reject external connections, permit asyncio's local socketpair."""
import ipaddress
import socket

_CONNECT = socket.socket.connect
_CONNECT_EX = socket.socket.connect_ex
BLOCKED_ATTEMPTS = []


def checked_address(address):
    if not isinstance(address, tuple):
        BLOCKED_ATTEMPTS.append(str(address))
        raise TypeError("Offline tests require a loopback socket address")
    try:
        loopback = ipaddress.ip_address(address[0]).is_loopback
    except ValueError:
        loopback = False
    if not loopback:
        BLOCKED_ATTEMPTS.append(str(address))
        raise AssertionError("External network access is forbidden in revision66 tests")


def connect(sock, address):
    checked_address(address)
    return _CONNECT(sock, address)


def connect_ex(sock, address):
    checked_address(address)
    return _CONNECT_EX(sock, address)


def pytest_sessionstart(session):
    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex


def pytest_sessionfinish(session, exitstatus):
    socket.socket.connect = _CONNECT
    socket.socket.connect_ex = _CONNECT_EX
    if BLOCKED_ATTEMPTS:
        session.exitstatus = 1
        print("Offline guard rejected external connection attempts:", len(BLOCKED_ATTEMPTS))
