"""
Dynamic port allocation for Docker containers.

This module provides utilities to find available ports dynamically,
preventing port conflicts when running multiple containers or specs.
"""

import socket
import logging
from typing import Optional, Set
from contextlib import closing

logger = logging.getLogger(__name__)


class PortAllocator:
    """
    Manages dynamic port allocation for Docker containers.

    Ensures that each container gets a unique, available port
    to prevent conflicts when running multiple specs or containers.
    """

    # Default port range for container allocation
    DEFAULT_START_PORT = 8000
    DEFAULT_END_PORT = 8100

    # Ports currently in use by this allocator instance
    _allocated_ports: Set[int] = set()

    def __init__(
        self,
        start_port: int = DEFAULT_START_PORT,
        end_port: int = DEFAULT_END_PORT
    ):
        """
        Initialize the port allocator.

        Args:
            start_port: Minimum port number to allocate
            end_port: Maximum port number to allocate
        """
        self.start_port = start_port
        self.end_port = end_port

    @staticmethod
    def is_port_available(port: int, host: str = "127.0.0.1") -> bool:
        """
        Check if a port is available on the given host.

        Args:
            port: Port number to check
            host: Host to check (default: localhost)

        Returns:
            True if port is available, False otherwise
        """
        try:
            with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
                sock.settimeout(1)
                # Try to bind to the port
                result = sock.connect_ex((host, port))
                # If connection fails (port not in use), it's available
                return result != 0
        except socket.error as e:
            logger.warning(f"Error checking port {port}: {e}")
            return False

    def find_available_port(
        self,
        preferred_port: Optional[int] = None,
        host: str = "127.0.0.1"
    ) -> int:
        """
        Find an available port, optionally starting with a preferred port.

        Args:
            preferred_port: Port to try first (if None, start from start_port)
            host: Host to check availability on

        Returns:
            An available port number

        Raises:
            RuntimeError: If no available port is found in the range
        """
        # Try preferred port first if specified
        if preferred_port is not None:
            if (self.start_port <= preferred_port <= self.end_port and
                preferred_port not in self._allocated_ports and
                self.is_port_available(preferred_port, host)):
                self._allocated_ports.add(preferred_port)
                logger.info(f"Allocated preferred port {preferred_port}")
                return preferred_port
            else:
                logger.warning(
                    f"Preferred port {preferred_port} not available, "
                    f"searching for alternative"
                )

        # Search for available port in range
        for port in range(self.start_port, self.end_port + 1):
            if port in self._allocated_ports:
                continue

            if self.is_port_available(port, host):
                self._allocated_ports.add(port)
                logger.info(f"Allocated port {port}")
                return port

        # No port available
        raise RuntimeError(
            f"No available ports found in range {self.start_port}-{self.end_port}"
        )

    def allocate_ports(
        self,
        count: int,
        preferred_ports: Optional[list[int]] = None,
        host: str = "127.0.0.1"
    ) -> list[int]:
        """
        Allocate multiple ports at once.

        Args:
            count: Number of ports to allocate
            preferred_ports: List of preferred ports (can be shorter than count)
            host: Host to check availability on

        Returns:
            List of allocated port numbers

        Raises:
            RuntimeError: If unable to allocate the requested number of ports
        """
        allocated = []
        preferred_ports = preferred_ports or []

        try:
            # Try to allocate preferred ports first
            for i in range(min(count, len(preferred_ports))):
                port = self.find_available_port(
                    preferred_port=preferred_ports[i],
                    host=host
                )
                allocated.append(port)

            # Allocate remaining ports
            for _ in range(count - len(allocated)):
                port = self.find_available_port(host=host)
                allocated.append(port)

            logger.info(f"Allocated {count} ports: {allocated}")
            return allocated

        except Exception as e:
            # Rollback: release any ports we allocated
            for port in allocated:
                self.release_port(port)
            raise RuntimeError(f"Failed to allocate {count} ports: {e}") from e

    def release_port(self, port: int) -> None:
        """
        Release a previously allocated port.

        Args:
            port: Port number to release
        """
        if port in self._allocated_ports:
            self._allocated_ports.discard(port)
            logger.info(f"Released port {port}")
        else:
            logger.warning(f"Attempted to release unallocated port {port}")

    def release_all_ports(self) -> None:
        """Release all allocated ports."""
        count = len(self._allocated_ports)
        self._allocated_ports.clear()
        logger.info(f"Released all {count} allocated ports")

    @property
    def allocated_ports(self) -> list[int]:
        """Get list of currently allocated ports."""
        return sorted(list(self._allocated_ports))


# Global singleton instance for convenience
_global_allocator = PortAllocator()


def get_global_allocator() -> PortAllocator:
    """Get the global port allocator instance."""
    return _global_allocator


def find_available_port(preferred_port: Optional[int] = None) -> int:
    """
    Convenience function to find an available port using the global allocator.

    Args:
        preferred_port: Port to try first

    Returns:
        An available port number
    """
    return _global_allocator.find_available_port(preferred_port)


def allocate_ports(
    count: int,
    preferred_ports: Optional[list[int]] = None
) -> list[int]:
    """
    Convenience function to allocate multiple ports using the global allocator.

    Args:
        count: Number of ports to allocate
        preferred_ports: List of preferred ports

    Returns:
        List of allocated port numbers
    """
    return _global_allocator.allocate_ports(count, preferred_ports)


def release_port(port: int) -> None:
    """
    Convenience function to release a port using the global allocator.

    Args:
        port: Port number to release
    """
    _global_allocator.release_port(port)


def release_all_ports() -> None:
    """Convenience function to release all ports using the global allocator."""
    _global_allocator.release_all_ports()
