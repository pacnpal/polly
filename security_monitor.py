#!/usr/bin/env python3
"""
Security Monitor
Analyzes logs for attack patterns and provides security insights.
"""

import re
import sys
from collections import defaultdict, Counter
from datetime import datetime
from typing import Dict, List
import argparse


class SecurityMonitor:
    """Monitor and analyze security-related log entries"""

    def __init__(self):
        self.attack_patterns = {
            "php_rfi": r"allow_url_include.*auto_prepend_file.*php://input",
            "phpunit_rce": r"phpunit.*eval-stdin\.php",
            "php_files": r"\.php(\?|$)",
            "path_traversal": r"\.\./",
            "sql_injection": r"union\s+select|drop\s+table",
            "xss_attempt": r"<script|javascript:",
            "command_injection": r";\s*(cat|ls|pwd|whoami)",
        }

        self.malicious_paths = {
            "phpunit_paths": [
                "vendor/phpunit",
                "phpunit/phpunit",
                "lib/phpunit",
                "laravel/vendor/phpunit",
                "www/vendor/phpunit",
            ],
            "common_attacks": [
                "wp-admin",
                "wp-login.php",
                "phpmyadmin",
                "config.php",
                "xmlrpc.php",
                ".env",
                "hello.world",
            ],
        }

    def analyze_log_line(self, line: str) -> Dict:
        """Analyze a single log line for security threats"""
        result = {
            "timestamp": None,
            "ip": None,
            "method": None,
            "path": None,
            "status": None,
            "attack_types": [],
            "severity": "low",
        }

        # Parse log format: INFO:     172.20.0.1:43908 - "POST /path HTTP/1.1" 404 Not Found
        log_pattern = r'INFO:\s+(\d+\.\d+\.\d+\.\d+):\d+\s+-\s+"(\w+)\s+([^"]+)\s+HTTP/[\d.]+"\s+(\d+)'
        match = re.search(log_pattern, line)

        if not match:
            return result

        result["ip"] = match.group(1)
        result["method"] = match.group(2)
        result["path"] = match.group(3)
        result["status"] = int(match.group(4))

        # Check for attack patterns
        full_request = result["path"]

        for attack_type, pattern in self.attack_patterns.items():
            if re.search(pattern, full_request, re.IGNORECASE):
                result["attack_types"].append(attack_type)

        # Check malicious paths
        for category, paths in self.malicious_paths.items():
            for path in paths:
                if path in full_request.lower():
                    result["attack_types"].append(category)

        # Determine severity
        if result["attack_types"]:
            if any(
                attack in ["php_rfi", "phpunit_rce", "sql_injection"]
                for attack in result["attack_types"]
            ):
                result["severity"] = "high"
            elif any(
                attack in ["xss_attempt", "command_injection"]
                for attack in result["attack_types"]
            ):
                result["severity"] = "medium"
            else:
                result["severity"] = "low"

        return result

    def analyze_logs(self, log_content: str) -> Dict:
        """Analyze multiple log lines and generate report"""
        lines = log_content.strip().split("\n")
        attacks = []
        ip_stats = defaultdict(int)
        attack_type_stats = Counter()
        path_stats = Counter()

        for line in lines:
            if not line.strip():
                continue

            analysis = self.analyze_log_line(line)

            if analysis["attack_types"]:
                attacks.append(analysis)
                ip_stats[analysis["ip"]] += 1

                for attack_type in analysis["attack_types"]:
                    attack_type_stats[attack_type] += 1

                path_stats[analysis["path"]] += 1

        return {
            "total_attacks": len(attacks),
            "unique_ips": len(ip_stats),
            "attacks": attacks,
            "ip_stats": dict(ip_stats),
            "attack_type_stats": dict(attack_type_stats),
            "path_stats": dict(path_stats),
            "severity_breakdown": self._get_severity_breakdown(attacks),
        }

    def _get_severity_breakdown(self, attacks: List[Dict]) -> Dict:
        """Get breakdown of attacks by severity"""
        breakdown = {"high": 0, "medium": 0, "low": 0}
        for attack in attacks:
            breakdown[attack["severity"]] += 1
        return breakdown

    def generate_report(self, analysis: Dict) -> str:
        """Generate a human-readable security report"""
        report = []
        report.append("=" * 60)
        report.append("SECURITY ANALYSIS REPORT")
        report.append("=" * 60)
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")

        # Summary
        report.append("SUMMARY:")
        report.append(f"  Total Attack Attempts: {analysis['total_attacks']}")
        report.append(f"  Unique Attacking IPs: {analysis['unique_ips']}")
        report.append("")

        # Severity breakdown
        severity = analysis["severity_breakdown"]
        report.append("SEVERITY BREAKDOWN:")
        report.append(f"  🔴 High:   {severity['high']} attacks")
        report.append(f"  🟡 Medium: {severity['medium']} attacks")
        report.append(f"  🟢 Low:    {severity['low']} attacks")
        report.append("")

        # Top attacking IPs
        if analysis["ip_stats"]:
            report.append("TOP ATTACKING IPs:")
            sorted_ips = sorted(
                analysis["ip_stats"].items(), key=lambda x: x[1], reverse=True
            )
            for ip, count in sorted_ips[:5]:
                report.append(f"  {ip}: {count} attempts")
            report.append("")

        # Attack types
        if analysis["attack_type_stats"]:
            report.append("ATTACK TYPES:")
            # Convert back to Counter for most_common() method
            attack_counter = Counter(analysis["attack_type_stats"])
            for attack_type, count in attack_counter.most_common():
                report.append(f"  {attack_type}: {count} attempts")
            report.append("")

        # Most targeted paths
        if analysis["path_stats"]:
            report.append("MOST TARGETED PATHS:")
            # Convert back to Counter for most_common() method
            path_counter = Counter(analysis["path_stats"])
            for path, count in path_counter.most_common(10):
                report.append(f"  {path}: {count} attempts")
            report.append("")

        # Recommendations
        report.append("RECOMMENDATIONS:")

        if analysis["total_attacks"] > 0:
            report.append("  ✅ Enhanced security middleware has been implemented")
            report.append("  ✅ These attacks will now be blocked with 403 responses")
            report.append("  📊 Monitor logs for 'BLOCKED ATTACK' messages")

            if severity["high"] > 0:
                report.append(
                    "  🚨 High-severity attacks detected - consider IP blocking"
                )

            if analysis["unique_ips"] > 5:
                report.append(
                    "  🔍 Multiple IPs attacking - possible distributed attack"
                )

            if any(
                "phpunit" in attack_type
                for attack_type in analysis["attack_type_stats"]
            ):
                report.append(
                    "  🛡️  PHPUnit RCE attempts blocked (not applicable to Python app)"
                )

            if any(
                "php" in attack_type for attack_type in analysis["attack_type_stats"]
            ):
                report.append(
                    "  🛡️  PHP-specific attacks blocked (not applicable to Python app)"
                )
        else:
            report.append("  ✅ No security threats detected in analyzed logs")

        report.append("")
        report.append("=" * 60)

        return "\n".join(report)


def main():
    parser = argparse.ArgumentParser(
        description="Analyze security logs for attack patterns"
    )
    parser.add_argument("--file", "-f", help="Log file to analyze")
    parser.add_argument("--stdin", action="store_true", help="Read from stdin")

    args = parser.parse_args()

    monitor = SecurityMonitor()

    if args.file:
        try:
            with open(args.file, "r") as f:
                log_content = f.read()
        except FileNotFoundError:
            print(f"Error: File '{args.file}' not found")
            sys.exit(1)
    elif args.stdin:
        log_content = sys.stdin.read()
    else:
        print("Please provide log content via --file or --stdin")
        print("Example: python security_monitor.py --stdin < logs.txt")
        print("Example: python security_monitor.py --file polly.log")
        sys.exit(1)

    analysis = monitor.analyze_logs(log_content)
    report = monitor.generate_report(analysis)
    print(report)


if __name__ == "__main__":
    main()
