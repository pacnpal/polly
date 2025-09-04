"""
IP Blocking System
Manages blocked IPs and provides functionality to block repeat attackers.
"""

import time
import logging
from typing import Set, Dict
from collections import defaultdict
import threading

logger = logging.getLogger(__name__)


class IPBlocker:
    """
    Simple in-memory IP blocking system.
    In production, this should be backed by Redis or a database.
    """

    def __init__(self):
        self._blocked_ips: Set[str] = set()
        self._violation_counts: Dict[str, int] = defaultdict(int)
        self._violation_timestamps: Dict[str, float] = {}
        self._lock = threading.Lock()

        # Configuration
        self.max_violations = 5  # Block after 5 violations
        self.violation_window = 3600  # 1 hour window
        self.block_duration = 86400  # Block for 24 hours

    def is_blocked(self, ip: str) -> bool:
        """Check if an IP is currently blocked"""
        with self._lock:
            return ip in self._blocked_ips

    def record_violation(self, ip: str, severity: str = "MEDIUM") -> bool:
        """
        Record a security violation for an IP.
        Returns True if the IP should be blocked.
        """
        with self._lock:
            current_time = time.time()

            # Clean old violations outside the window
            if ip in self._violation_timestamps:
                if (
                    current_time - self._violation_timestamps[ip]
                    > self.violation_window
                ):
                    self._violation_counts[ip] = 0

            # Record the violation
            self._violation_counts[ip] += self._get_violation_weight(severity)
            self._violation_timestamps[ip] = current_time

            # Check if we should block this IP
            if self._violation_counts[ip] >= self.max_violations:
                self._blocked_ips.add(ip)
                logger.warning(
                    f"IP {ip} blocked after {self._violation_counts[ip]} violations"
                )
                return True

            return False

    def _get_violation_weight(self, severity: str) -> int:
        """Get the weight of a violation based on severity"""
        weights = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
        return weights.get(severity, 2)

    def unblock_ip(self, ip: str) -> bool:
        """Manually unblock an IP"""
        with self._lock:
            if ip in self._blocked_ips:
                self._blocked_ips.remove(ip)
                self._violation_counts[ip] = 0
                logger.info(f"IP {ip} manually unblocked")
                return True
            return False

    def get_blocked_ips(self) -> Set[str]:
        """Get all currently blocked IPs"""
        with self._lock:
            return self._blocked_ips.copy()

    def get_violation_count(self, ip: str) -> int:
        """Get violation count for an IP"""
        with self._lock:
            return self._violation_counts.get(ip, 0)

    def cleanup_old_blocks(self):
        """Clean up old blocks (should be called periodically)"""
        # For now, we'll keep blocks indefinitely
        # In production, you'd want to implement time-based expiration
        pass


# Global IP blocker instance
_ip_blocker = None


def get_ip_blocker() -> IPBlocker:
    """Get the global IP blocker instance"""
    global _ip_blocker
    if _ip_blocker is None:
        _ip_blocker = IPBlocker()
    return _ip_blocker
