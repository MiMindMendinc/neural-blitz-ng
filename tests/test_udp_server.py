"""UDP server integration tests."""

import asyncio

import pytest

from neural_blitz.udp_server import EchoServerProtocol


@pytest.mark.integration
async def test_echo_server_receives_packets():
    loop = asyncio.get_running_loop()
    transport, protocol = await loop.create_datagram_endpoint(EchoServerProtocol, local_addr=("127.0.0.1", 0))
    port = transport.get_extra_info("sockname")[1]

    client_transport, _ = await loop.create_datagram_endpoint(asyncio.DatagramProtocol, local_addr=("127.0.0.1", 0))
    received = asyncio.get_running_loop().create_future()

    class Client(asyncio.DatagramProtocol):
        def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
            if not received.done():
                received.set_result(data)

    client_transport.close()
    client_transport, _ = await loop.create_datagram_endpoint(Client, local_addr=("127.0.0.1", 0))
    payload = b"ping-test-payload-123456789012345"
    client_transport.sendto(payload, ("127.0.0.1", port))
    echoed = await asyncio.wait_for(received, timeout=2.0)
    assert echoed == payload
    assert protocol.packet_count >= 1
    client_transport.close()
    transport.close()
