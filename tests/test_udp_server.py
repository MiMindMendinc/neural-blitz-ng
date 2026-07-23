"""UDP server integration tests."""

import asyncio
from unittest import mock
from unittest.mock import Mock

import pytest

from neural_blitz.constants import HEADER_STRUCT
from neural_blitz.errors import NeuralBlitzError
from neural_blitz.latency import build_packet
from neural_blitz.udp_server import EchoServerProtocol, run_server


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
    payload = build_packet(1, 64)
    client_transport.sendto(payload, ("127.0.0.1", port))
    echoed = await asyncio.wait_for(received, timeout=2.0)
    assert echoed == payload
    assert protocol.packet_count >= 1
    client_transport.close()
    transport.close()


@pytest.mark.unit
def test_echo_server_drops_invalid_datagrams():
    protocol = EchoServerProtocol(max_packet_size=64)
    protocol.datagram_received(b"invalid", ("127.0.0.1", 1234))
    assert protocol.packet_count == 0
    assert protocol.dropped_packets == 1


@pytest.mark.unit
def test_echo_server_drops_unsupported_packet_version():
    transport = Mock()
    protocol = EchoServerProtocol()
    protocol.transport = transport
    malformed_version = HEADER_STRUCT.pack(2, 1, 1, 1) + b"\x00" * 32

    protocol.datagram_received(malformed_version, ("127.0.0.1", 1234))

    assert protocol.packet_count == 0
    assert protocol.dropped_packets == 1
    transport.sendto.assert_not_called()


@pytest.mark.unit
def test_echo_server_does_not_count_valid_packet_without_transport():
    protocol = EchoServerProtocol()

    protocol.datagram_received(build_packet(1, 64), ("127.0.0.1", 1234))

    assert protocol.packet_count == 0
    assert protocol.dropped_packets == 0


@pytest.mark.unit
def test_echo_server_connection_made_skips_missing_socket():
    protocol = EchoServerProtocol()
    transport = Mock()
    transport.get_extra_info.side_effect = lambda name: None if name == "socket" else ("127.0.0.1", 9000)

    protocol.connection_made(transport)

    assert protocol.transport is transport
    transport.get_extra_info.assert_any_call("sockname")


@pytest.mark.unit
def test_echo_server_connection_made_logs_buffer_tuning_error(caplog):
    protocol = EchoServerProtocol()
    sock = Mock()
    sock.setsockopt.side_effect = OSError("not permitted")
    transport = Mock()
    transport.get_extra_info.side_effect = lambda name: sock if name == "socket" else ("127.0.0.1", 9000)

    with caplog.at_level("DEBUG", logger="neural_blitz"):
        protocol.connection_made(transport)

    assert "Socket buffer tuning for server failed" in caplog.text
    sock.setsockopt.assert_called_once()


@pytest.mark.unit
def test_echo_server_enforces_rate_limit_for_valid_packets():
    transport = Mock()
    protocol = EchoServerProtocol(rate_limit=1)
    protocol.transport = transport
    packet = build_packet(1, 64)
    protocol.datagram_received(packet, ("127.0.0.1", 1234))
    protocol.datagram_received(packet, ("127.0.0.1", 1234))
    transport.sendto.assert_called_once_with(packet, ("127.0.0.1", 1234))
    assert protocol.packet_count == 1
    assert protocol.dropped_packets == 1


@pytest.mark.unit
def test_echo_server_logs_socket_and_connection_errors(caplog):
    protocol = EchoServerProtocol()

    with caplog.at_level("INFO", logger="neural_blitz"):
        protocol.error_received(OSError("socket failed"))
        protocol.connection_lost(ConnectionError("network down"))

    assert "Echo server socket error: socket failed" in caplog.text
    assert "Echo server connection lost: network down" in caplog.text
    assert "Echo server shut down after 0 packets" in caplog.text


@pytest.mark.unit
async def test_run_server_wraps_bind_error():
    loop = asyncio.get_running_loop()
    with (
        mock.patch.object(loop, "create_datagram_endpoint", side_effect=OSError("address in use")),
        pytest.raises(NeuralBlitzError, match="Unable to start UDP echo server on 127.0.0.1:9000: address in use"),
    ):
        await run_server("127.0.0.1", 9000)


@pytest.mark.unit
async def test_run_server_handles_unsupported_signals_and_cancellation(caplog):
    loop = asyncio.get_running_loop()
    transport = Mock()

    with (
        mock.patch.object(loop, "create_datagram_endpoint", return_value=(transport, EchoServerProtocol())),
        mock.patch.object(loop, "add_signal_handler", side_effect=NotImplementedError),
        caplog.at_level("DEBUG", logger="neural_blitz"),
    ):
        task = asyncio.create_task(run_server("127.0.0.1", 9000))
        await asyncio.sleep(0)
        task.cancel()
        await task

    assert "Signal handlers not supported on this platform" in caplog.text
    assert "Server cancelled" in caplog.text
    assert transport.close.call_count == 1
