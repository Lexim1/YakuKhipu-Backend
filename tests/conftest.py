"""Las pruebas unitarias/HTTP no crean ni borran tablas. Integración usa conexión explícita."""
import ipaddress
import socket
import pytest

@pytest.fixture(autouse=True)
def bloquear_red_externa(monkeypatch):
    """La suite solo puede conectar a infraestructura local; jamás gastar inferencia externa."""
    connect=socket.socket.connect
    def local_only(sock,address):
        if isinstance(address,tuple):
            host=address[0]
            try:allowed=ipaddress.ip_address(host).is_loopback
            except ValueError:allowed=host=='localhost'
            if not allowed:raise RuntimeError('La suite bloquea conexiones de red externas')
        return connect(sock,address)
    monkeypatch.setattr(socket.socket,'connect',local_only)
