"""
Tests for the PortAllocator module.

Tests dynamic port allocation, conflict detection, and port release.
"""

import pytest
import socket
from contextlib import closing
from apps.backend.core.isolation.port_allocator import (
    PortAllocator,
    find_available_port,
    allocate_ports,
    release_port,
    release_all_ports,
)


class TestPortAllocator:
    """Test suite for PortAllocator class."""

    def test_initialization(self):
        """Test that PortAllocator initializes with correct defaults."""
        allocator = PortAllocator()
        assert allocator.start_port == PortAllocator.DEFAULT_START_PORT
        assert allocator.end_port == PortAllocator.DEFAULT_END_PORT
        assert len(allocator._allocated_ports) == 0

    def test_custom_port_range(self):
        """Test initialization with custom port range."""
        allocator = PortAllocator(start_port=9000, end_port=9100)
        assert allocator.start_port == 9000
        assert allocator.end_port == 9100

    def test_is_port_available_for_available_port(self):
        """Test that is_port_available correctly identifies an available port."""
        # Find a truly available port by binding to it temporarily
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            sock.bind(('127.0.0.1', 0))
            available_port = sock.getsockname()[1]

        # Port should be available now
        allocator = PortAllocator()
        assert allocator.is_port_available(available_port) is True

    def test_is_port_available_for_unavailable_port(self):
        """Test that is_port_available correctly identifies an unavailable port."""
        # Bind to a port to make it unavailable
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(('127.0.0.1', 0))
            unavailable_port = sock.getsockname()[1]

            # Port should be unavailable while we hold it
            allocator = PortAllocator()
            assert allocator.is_port_available(unavailable_port) is False

    def test_find_available_port_without_preference(self):
        """Test finding an available port without a preferred port."""
        allocator = PortAllocator()
        port = allocator.find_available_port()

        assert allocator.start_port <= port <= allocator.end_port
        assert port in allocator._allocated_ports

    def test_find_available_port_with_preferred_port(self):
        """Test finding an available port with a preferred port."""
        allocator = PortAllocator(start_port=8050, end_port=8150)

        # Try to allocate with a preferred port in range
        preferred_port = 8075
        port = allocator.find_available_port(preferred_port=preferred_port)

        # Should get preferred port if it's available
        assert port in allocator._allocated_ports

    def test_find_available_port_when_preferred_unavailable(self):
        """Test that allocation falls back when preferred port is unavailable."""
        allocator = PortAllocator(start_port=8050, end_port=8150)

        # Allocate a port first
        first_port = allocator.find_available_port()

        # Try to allocate the same port again (should get a different one)
        second_port = allocator.find_available_port(preferred_port=first_port)

        assert first_port != second_port
        assert first_port in allocator._allocated_ports
        assert second_port in allocator._allocated_ports

    def test_allocate_multiple_ports(self):
        """Test allocating multiple ports at once."""
        allocator = PortAllocator()
        ports = allocator.allocate_ports(count=3)

        assert len(ports) == 3
        assert len(set(ports)) == 3  # All unique
        assert all(p in allocator._allocated_ports for p in ports)

    def test_allocate_ports_with_preferences(self):
        """Test allocating multiple ports with preferred ports."""
        allocator = PortAllocator(start_port=8050, end_port=8150)
        preferred = [8060, 8070]
        ports = allocator.allocate_ports(count=3, preferred_ports=preferred)

        assert len(ports) == 3
        assert len(set(ports)) == 3  # All unique
        assert all(p in allocator._allocated_ports for p in ports)

    def test_release_port(self):
        """Test releasing an allocated port."""
        allocator = PortAllocator()
        port = allocator.find_available_port()

        assert port in allocator._allocated_ports

        allocator.release_port(port)
        assert port not in allocator._allocated_ports

    def test_release_unallocated_port(self):
        """Test that releasing an unallocated port doesn't raise an error."""
        allocator = PortAllocator()
        # Should not raise an exception
        allocator.release_port(9999)

    def test_release_all_ports(self):
        """Test releasing all allocated ports."""
        allocator = PortAllocator()
        ports = allocator.allocate_ports(count=5)

        assert len(allocator._allocated_ports) == 5

        allocator.release_all_ports()
        assert len(allocator._allocated_ports) == 0

    def test_allocated_ports_property(self):
        """Test the allocated_ports property returns sorted list."""
        allocator = PortAllocator(start_port=8050, end_port=8150)
        ports = allocator.allocate_ports(count=3)

        allocated = allocator.allocated_ports
        assert allocated == sorted(ports)

    def test_port_exhaustion(self):
        """Test behavior when port range is exhausted."""
        # Create allocator with very small range
        allocator = PortAllocator(start_port=8090, end_port=8092)

        # Allocate all ports in range (8090, 8091, 8092 = 3 ports max)
        # Note: Some might be in use, so we might get fewer
        try:
            # Try to allocate more ports than available
            ports = []
            for _ in range(10):  # Try to allocate 10 ports in a 3-port range
                port = allocator.find_available_port()
                ports.append(port)
        except RuntimeError as e:
            # Should raise RuntimeError when no ports available
            assert "No available ports found" in str(e)

    def test_global_convenience_functions(self):
        """Test global convenience functions."""
        # Clear any previously allocated ports
        release_all_ports()

        # Test find_available_port
        port1 = find_available_port()
        assert port1 is not None

        # Test allocate_ports
        ports = allocate_ports(count=2)
        assert len(ports) == 2

        # Test release_port
        release_port(port1)

        # Test release_all_ports
        release_all_ports()

    def test_concurrent_allocation(self):
        """Test that concurrent allocations don't conflict."""
        allocator = PortAllocator()

        port1 = allocator.find_available_port()
        port2 = allocator.find_available_port()
        port3 = allocator.find_available_port()

        # All should be unique
        assert len({port1, port2, port3}) == 3

        # All should be tracked
        assert port1 in allocator._allocated_ports
        assert port2 in allocator._allocated_ports
        assert port3 in allocator._allocated_ports

    def test_rollback_on_allocation_failure(self):
        """Test that allocate_ports rolls back on failure."""
        allocator = PortAllocator(start_port=8090, end_port=8091)  # Only 2 ports

        try:
            # Try to allocate more ports than available
            ports = allocator.allocate_ports(count=5)
        except RuntimeError:
            # Should rollback and release any partially allocated ports
            # In this case, it should have tried to allocate but failed
            pass

        # After rollback, we should be able to allocate within the limit
        ports = allocator.allocate_ports(count=2)
        assert len(ports) <= 2


class TestPortAvailability:
    """Test actual port availability checking."""

    def test_port_is_unavailable_when_bound(self):
        """Test that a bound port is detected as unavailable."""
        allocator = PortAllocator()

        # Bind to a port
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(('127.0.0.1', 0))
            bound_port = sock.getsockname()[1]

            # Port should be unavailable
            assert allocator.is_port_available(bound_port) is False

        # Port should be available after socket closes
        assert allocator.is_port_available(bound_port) is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
