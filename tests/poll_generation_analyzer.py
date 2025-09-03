#!/usr/bin/env python3
"""
🔍 Snazzy Poll Generation Log Analyzer
=====================================

A comprehensive, critical analyzer for poll generation logs that provides:
- Deep performance analysis with visualizations
- Error pattern detection and categorization
- Memory usage tracking and optimization recommendations
- Timing analysis with bottleneck identification
- Critical assessment of system behavior
- Actionable insights and recommendations

Usage:
    # Analyze the latest log file
    uv run tests/poll_generation_analyzer.py
    
    # Analyze a specific log file
    uv run tests/poll_generation_analyzer.py --log-file poll_generation_20250903_133045.log
    
    # Generate detailed report with charts
    uv run tests/poll_generation_analyzer.py --detailed --charts
    
    # Export analysis to JSON
    uv run tests/poll_generation_analyzer.py --export analysis_report.json
    
    # Compare multiple log files
    uv run tests/poll_generation_analyzer.py --compare log1.log log2.log log3.log
"""

import argparse
import json
import re
import sys
from collections import defaultdict, Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import statistics
import glob

# Optional dependencies for enhanced analysis
try:
    import matplotlib.pyplot as plt
    import seaborn as sns
    import pandas as pd
    HAS_PLOTTING = True
except ImportError:
    HAS_PLOTTING = False
    print("📊 Install matplotlib, seaborn, and pandas for enhanced visualizations:")
    print("   pip install matplotlib seaborn pandas")

class LogEntry:
    """Represents a single log entry with parsed components"""
    
    def __init__(self, raw_line: str):
        self.raw_line = raw_line.strip()
        self.timestamp = None
        self.memory_mb = None
        self.cpu_percent = None
        self.thread_id = None
        self.logger_name = None
        self.level = None
        self.message = None
        self.parse_line()
    
    def parse_line(self):
        """Parse a log line into components"""
        # Pattern: 2025-01-03 13:30:45.123 | 45.2MB | 12.5% | T12345 | logger_name | INFO | message
        pattern = r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}) \| ([\d.]+MB) \| ([\d.]+%) \| (T\d+) \| ([^|]+) \| (\w+) \| (.+)'
        
        match = re.match(pattern, self.raw_line)
        if match:
            self.timestamp = datetime.strptime(match.group(1), '%Y-%m-%d %H:%M:%S.%f')
            self.memory_mb = float(match.group(2).replace('MB', ''))
            self.cpu_percent = float(match.group(3).replace('%', ''))
            self.thread_id = match.group(4)
            self.logger_name = match.group(5).strip()
            self.level = match.group(6)
            self.message = match.group(7)
        else:
            # Fallback for simpler log formats
            simple_pattern = r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ - ([^-]+) - (\w+) - (.+)'
            simple_match = re.match(simple_pattern, self.raw_line)
            if simple_match:
                self.timestamp = datetime.strptime(simple_match.group(1), '%Y-%m-%d %H:%M:%S')
                self.logger_name = simple_match.group(2).strip()
                self.level = simple_match.group(3)
                self.message = simple_match.group(4)

class PollGenerationAnalyzer:
    """Comprehensive analyzer for poll generation logs"""
    
    def __init__(self, log_files: List[str]):
        self.log_files = log_files
        self.entries: List[LogEntry] = []
        self.analysis_results = {}
        self.critical_issues = []
        self.recommendations = []
        
        # Analysis categories
        self.performance_metrics = {}
        self.error_analysis = {}
        self.memory_analysis = {}
        self.timing_analysis = {}
        self.operation_analysis = {}
        
        print(f"🔍 Initializing analyzer for {len(log_files)} log file(s)")
    
    def load_logs(self):
        """Load and parse all log files"""
        print("📖 Loading log files...")
        
        for log_file in self.log_files:
            if not Path(log_file).exists():
                print(f"❌ Log file not found: {log_file}")
                continue
                
            print(f"   📄 Processing {log_file}")
            with open(log_file, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    if line.strip():
                        entry = LogEntry(line)
                        if entry.timestamp:  # Only add successfully parsed entries
                            self.entries.append(entry)
        
        print(f"✅ Loaded {len(self.entries)} log entries")
        
        if not self.entries:
            print("❌ No valid log entries found!")
            return False
        
        # Sort entries by timestamp
        self.entries.sort(key=lambda x: x.timestamp)
        return True
    
    def analyze_performance(self):
        """Analyze overall performance metrics"""
        print("⚡ Analyzing performance metrics...")
        
        # Extract timing data
        poll_creation_times = []
        memory_usage = []
        cpu_usage = []
        
        for entry in self.entries:
            if entry.memory_mb:
                memory_usage.append(entry.memory_mb)
            if entry.cpu_percent:
                cpu_usage.append(entry.cpu_percent)
            
            # Look for poll creation timing patterns
            if "Created poll" in entry.message and "seconds" in entry.message:
                time_match = re.search(r'(\d+\.?\d*)\s*seconds', entry.message)
                if time_match:
                    poll_creation_times.append(float(time_match.group(1)))
        
        # Calculate statistics
        self.performance_metrics = {
            'total_entries': len(self.entries),
            'duration': (self.entries[-1].timestamp - self.entries[0].timestamp).total_seconds() if len(self.entries) > 1 else 0,
            'memory_stats': {
                'min': min(memory_usage) if memory_usage else 0,
                'max': max(memory_usage) if memory_usage else 0,
                'avg': statistics.mean(memory_usage) if memory_usage else 0,
                'median': statistics.median(memory_usage) if memory_usage else 0,
                'std_dev': statistics.stdev(memory_usage) if len(memory_usage) > 1 else 0
            },
            'cpu_stats': {
                'min': min(cpu_usage) if cpu_usage else 0,
                'max': max(cpu_usage) if cpu_usage else 0,
                'avg': statistics.mean(cpu_usage) if cpu_usage else 0,
                'median': statistics.median(cpu_usage) if cpu_usage else 0,
                'std_dev': statistics.stdev(cpu_usage) if len(cpu_usage) > 1 else 0
            },
            'poll_creation_times': poll_creation_times
        }
        
        # Performance assessment
        if self.performance_metrics['memory_stats']['max'] > 500:
            self.critical_issues.append("🚨 HIGH MEMORY USAGE: Peak memory usage exceeded 500MB")
        
        if self.performance_metrics['cpu_stats']['max'] > 80:
            self.critical_issues.append("🚨 HIGH CPU USAGE: Peak CPU usage exceeded 80%")
        
        if poll_creation_times and statistics.mean(poll_creation_times) > 5:
            self.critical_issues.append("🚨 SLOW POLL CREATION: Average poll creation time exceeds 5 seconds")
    
    def analyze_errors(self):
        """Analyze error patterns and categorize them"""
        print("🔍 Analyzing error patterns...")
        
        error_entries = [e for e in self.entries if e.level in ['ERROR', 'CRITICAL']]
        warning_entries = [e for e in self.entries if e.level == 'WARNING']
        
        # Categorize errors
        error_categories = defaultdict(list)
        error_patterns = {
            'discord_connection': [r'Discord.*connection', r'bot.*connect', r'Discord.*failed'],
            'database_errors': [r'database', r'SQL', r'sqlite', r'connection.*database'],
            'validation_errors': [r'validation.*failed', r'invalid.*data', r'validation.*error'],
            'image_processing': [r'image.*failed', r'image.*error', r'Failed to load image'],
            'network_errors': [r'network', r'timeout', r'connection.*refused', r'HTTP.*error'],
            'permission_errors': [r'permission', r'access.*denied', r'forbidden'],
            'rate_limiting': [r'rate.*limit', r'too many requests', r'throttle'],
            'memory_errors': [r'memory', r'out of memory', r'allocation.*failed'],
            'unknown_errors': []
        }
        
        for entry in error_entries:
            categorized = False
            for category, patterns in error_patterns.items():
                if category == 'unknown_errors':
                    continue
                for pattern in patterns:
                    if re.search(pattern, entry.message, re.IGNORECASE):
                        error_categories[category].append(entry)
                        categorized = True
                        break
                if categorized:
                    break
            
            if not categorized:
                error_categories['unknown_errors'].append(entry)
        
        self.error_analysis = {
            'total_errors': len(error_entries),
            'total_warnings': len(warning_entries),
            'error_categories': {cat: len(errors) for cat, errors in error_categories.items()},
            'error_details': error_categories,
            'error_rate': len(error_entries) / len(self.entries) * 100 if self.entries else 0
        }
        
        # Critical error assessment
        if self.error_analysis['error_rate'] > 10:
            self.critical_issues.append(f"🚨 HIGH ERROR RATE: {self.error_analysis['error_rate']:.1f}% of operations failed")
        
        if error_categories['discord_connection']:
            self.critical_issues.append("🚨 DISCORD CONNECTION ISSUES: Multiple Discord connection failures detected")
        
        if error_categories['database_errors']:
            self.critical_issues.append("🚨 DATABASE ISSUES: Database errors detected - check database integrity")
    
    def analyze_memory_patterns(self):
        """Analyze memory usage patterns and detect leaks"""
        print("🧠 Analyzing memory patterns...")
        
        memory_entries = [e for e in self.entries if e.memory_mb is not None]
        
        if len(memory_entries) < 10:
            self.memory_analysis = {'insufficient_data': True}
            return
        
        # Calculate memory trend
        memory_values = [e.memory_mb for e in memory_entries]
        
        # Simple linear regression to detect memory leaks
        n = len(memory_values)
        sum_x = sum(range(n))
        sum_y = sum(memory_values)
        sum_xy = sum(i * memory_values[i] for i in range(n))
        sum_x2 = sum(i * i for i in range(n))
        
        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x) if (n * sum_x2 - sum_x * sum_x) != 0 else 0
        
        # Memory spikes detection
        memory_spikes = []
        avg_memory = statistics.mean(memory_values)
        std_memory = statistics.stdev(memory_values) if len(memory_values) > 1 else 0
        threshold = avg_memory + 2 * std_memory
        
        for entry in memory_entries:
            if entry.memory_mb > threshold:
                memory_spikes.append(entry)
        
        self.memory_analysis = {
            'trend_slope': slope,
            'memory_leak_detected': slope > 0.1,  # MB per operation
            'memory_spikes': len(memory_spikes),
            'spike_threshold': threshold,
            'memory_efficiency': avg_memory / max(memory_values) if memory_values else 0
        }
        
        # Memory-related recommendations
        if self.memory_analysis['memory_leak_detected']:
            self.critical_issues.append("🚨 MEMORY LEAK DETECTED: Memory usage trending upward")
            self.recommendations.append("🔧 Investigate memory cleanup in poll creation operations")
        
        if len(memory_spikes) > len(memory_entries) * 0.1:
            self.critical_issues.append("🚨 FREQUENT MEMORY SPIKES: Unstable memory usage pattern")
    
    def analyze_timing_patterns(self):
        """Analyze timing patterns and identify bottlenecks"""
        print("⏱️ Analyzing timing patterns...")
        
        # Extract operation timings
        operation_times = defaultdict(list)
        
        # Look for timing patterns in messages
        timing_patterns = {
            'poll_creation': r'Created poll.*(\d+\.?\d*)\s*seconds',
            'database_operation': r'Database.*(\d+\.?\d*)\s*ms',
            'image_processing': r'Image.*processed.*(\d+\.?\d*)\s*seconds',
            'validation': r'Validation.*(\d+\.?\d*)\s*ms',
            'discord_operation': r'Discord.*(\d+\.?\d*)\s*seconds'
        }
        
        for entry in self.entries:
            for operation, pattern in timing_patterns.items():
                match = re.search(pattern, entry.message, re.IGNORECASE)
                if match:
                    time_value = float(match.group(1))
                    operation_times[operation].append(time_value)
        
        # Calculate timing statistics
        timing_stats = {}
        for operation, times in operation_times.items():
            if times:
                timing_stats[operation] = {
                    'count': len(times),
                    'min': min(times),
                    'max': max(times),
                    'avg': statistics.mean(times),
                    'median': statistics.median(times),
                    'p95': sorted(times)[int(len(times) * 0.95)] if len(times) > 20 else max(times)
                }
        
        self.timing_analysis = {
            'operation_times': operation_times,
            'timing_stats': timing_stats,
            'bottlenecks': []
        }
        
        # Identify bottlenecks
        for operation, stats in timing_stats.items():
            if stats['avg'] > 2.0:  # Operations taking more than 2 seconds on average
                self.timing_analysis['bottlenecks'].append({
                    'operation': operation,
                    'avg_time': stats['avg'],
                    'severity': 'high' if stats['avg'] > 5.0 else 'medium'
                })
    
    def analyze_operations(self):
        """Analyze operation patterns and success rates"""
        print("🔄 Analyzing operation patterns...")
        
        # Count different types of operations
        operation_counts = Counter()
        success_counts = Counter()
        failure_counts = Counter()
        
        operation_patterns = {
            'poll_creation': r'Creating poll|Created poll',
            'image_processing': r'Processing image|Image processed',
            'database_operation': r'Database|SQL|INSERT|UPDATE|SELECT',
            'validation': r'Validating|Validation',
            'discord_operation': r'Discord|Bot|Channel|Server',
            'emoji_operation': r'Emoji|emoji'
        }
        
        for entry in self.entries:
            for operation, pattern in operation_patterns.items():
                if re.search(pattern, entry.message, re.IGNORECASE):
                    operation_counts[operation] += 1
                    
                    if entry.level == 'ERROR':
                        failure_counts[operation] += 1
                    elif 'success' in entry.message.lower() or 'created' in entry.message.lower():
                        success_counts[operation] += 1
        
        # Calculate success rates
        success_rates = {}
        for operation in operation_counts:
            total = operation_counts[operation]
            successes = success_counts[operation]
            failures = failure_counts[operation]
            success_rates[operation] = (successes / total * 100) if total > 0 else 0
        
        self.operation_analysis = {
            'operation_counts': dict(operation_counts),
            'success_counts': dict(success_counts),
            'failure_counts': dict(failure_counts),
            'success_rates': success_rates
        }
        
        # Identify problematic operations
        for operation, rate in success_rates.items():
            if rate < 80 and operation_counts[operation] > 5:
                self.critical_issues.append(f"🚨 LOW SUCCESS RATE: {operation} has {rate:.1f}% success rate")
    
    def generate_recommendations(self):
        """Generate actionable recommendations based on analysis"""
        print("💡 Generating recommendations...")
        
        # Performance recommendations
        if self.performance_metrics.get('memory_stats', {}).get('max', 0) > 200:
            self.recommendations.append("🔧 MEMORY: Consider implementing memory pooling for large operations")
        
        if self.performance_metrics.get('cpu_stats', {}).get('avg', 0) > 50:
            self.recommendations.append("🔧 CPU: Consider implementing async processing for CPU-intensive operations")
        
        # Error-based recommendations
        if self.error_analysis.get('error_rate', 0) > 5:
            self.recommendations.append("🔧 RELIABILITY: Implement retry mechanisms for failed operations")
        
        # Timing-based recommendations
        for bottleneck in self.timing_analysis.get('bottlenecks', []):
            if bottleneck['severity'] == 'high':
                self.recommendations.append(f"🔧 PERFORMANCE: Optimize {bottleneck['operation']} - currently averaging {bottleneck['avg_time']:.2f}s")
        
        # Operation-based recommendations
        for operation, rate in self.operation_analysis.get('success_rates', {}).items():
            if rate < 90:
                self.recommendations.append(f"🔧 RELIABILITY: Improve {operation} reliability - currently {rate:.1f}% success rate")
    
    def create_visualizations(self, output_dir: str = "analysis_charts"):
        """Create visualizations if plotting libraries are available"""
        if not HAS_PLOTTING:
            print("📊 Skipping visualizations - install matplotlib, seaborn, and pandas")
            return
        
        print("📊 Creating visualizations...")
        Path(output_dir).mkdir(exist_ok=True)
        
        # Import matplotlib here to avoid issues with unbound variables
        import matplotlib.pyplot as plt
        
        # Memory usage over time
        memory_entries = [e for e in self.entries if e.memory_mb is not None]
        if memory_entries:
            plt.figure(figsize=(12, 6))
            timestamps = [e.timestamp for e in memory_entries]
            memory_values = [e.memory_mb for e in memory_entries]
            
            plt.plot(timestamps, memory_values, linewidth=2, alpha=0.8)
            plt.title('Memory Usage Over Time', fontsize=16, fontweight='bold')
            plt.xlabel('Time')
            plt.ylabel('Memory (MB)')
            plt.grid(True, alpha=0.3)
            plt.tight_layout()
            plt.savefig(f"{output_dir}/memory_usage.png", dpi=300, bbox_inches='tight')
            plt.close()
        
        # Error distribution pie chart
        if self.error_analysis.get('error_categories'):
            plt.figure(figsize=(10, 8))
            categories = []
            counts = []
            for cat, count in self.error_analysis['error_categories'].items():
                if count > 0:
                    categories.append(cat.replace('_', ' ').title())
                    counts.append(count)
            
            if counts:
                plt.pie(counts, labels=categories, autopct='%1.1f%%', startangle=90)
                plt.title('Error Distribution by Category', fontsize=16, fontweight='bold')
                plt.axis('equal')
                plt.tight_layout()
                plt.savefig(f"{output_dir}/error_distribution.png", dpi=300, bbox_inches='tight')
                plt.close()
        
        # Operation success rates bar chart
        if self.operation_analysis.get('success_rates'):
            plt.figure(figsize=(12, 6))
            operations = list(self.operation_analysis['success_rates'].keys())
            rates = list(self.operation_analysis['success_rates'].values())
            
            bars = plt.bar(operations, rates, color=['green' if r >= 90 else 'orange' if r >= 70 else 'red' for r in rates])
            plt.title('Operation Success Rates', fontsize=16, fontweight='bold')
            plt.xlabel('Operation Type')
            plt.ylabel('Success Rate (%)')
            plt.xticks(rotation=45, ha='right')
            plt.ylim(0, 100)
            
            # Add value labels on bars
            for bar, rate in zip(bars, rates):
                plt.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1, 
                        f'{rate:.1f}%', ha='center', va='bottom')
            
            plt.tight_layout()
            plt.savefig(f"{output_dir}/success_rates.png", dpi=300, bbox_inches='tight')
            plt.close()
        
        print(f"📊 Visualizations saved to {output_dir}/")
    
    def print_critical_analysis(self):
        """Print critical analysis and recommendations"""
        print("\n" + "="*80)
        print("🔍 CRITICAL ANALYSIS REPORT")
        print("="*80)
        
        # Executive Summary
        print("\n📋 EXECUTIVE SUMMARY")
        print("-" * 40)
        total_duration = self.performance_metrics.get('duration', 0)
        total_entries = self.performance_metrics.get('total_entries', 0)
        error_rate = self.error_analysis.get('error_rate', 0)
        
        print(f"• Total log entries analyzed: {total_entries:,}")
        print(f"• Analysis duration: {total_duration:.1f} seconds ({total_duration/60:.1f} minutes)")
        print(f"• Overall error rate: {error_rate:.2f}%")
        print(f"• Critical issues found: {len(self.critical_issues)}")
        print(f"• Recommendations generated: {len(self.recommendations)}")
        
        # Critical Issues
        if self.critical_issues:
            print("\n🚨 CRITICAL ISSUES")
            print("-" * 40)
            for i, issue in enumerate(self.critical_issues, 1):
                print(f"{i}. {issue}")
        else:
            print("\n✅ NO CRITICAL ISSUES DETECTED")
        
        # Performance Metrics
        print("\n⚡ PERFORMANCE METRICS")
        print("-" * 40)
        memory_stats = self.performance_metrics.get('memory_stats', {})
        cpu_stats = self.performance_metrics.get('cpu_stats', {})
        
        print(f"Memory Usage:")
        print(f"  • Peak: {memory_stats.get('max', 0):.1f} MB")
        print(f"  • Average: {memory_stats.get('avg', 0):.1f} MB")
        print(f"  • Stability: {100 - (memory_stats.get('std_dev', 0) / memory_stats.get('avg', 1) * 100):.1f}%")
        
        print(f"CPU Usage:")
        print(f"  • Peak: {cpu_stats.get('max', 0):.1f}%")
        print(f"  • Average: {cpu_stats.get('avg', 0):.1f}%")
        
        # Error Analysis
        print("\n🔍 ERROR ANALYSIS")
        print("-" * 40)
        error_categories = self.error_analysis.get('error_categories', {})
        if any(count > 0 for count in error_categories.values()):
            for category, count in error_categories.items():
                if count > 0:
                    print(f"  • {category.replace('_', ' ').title()}: {count} errors")
        else:
            print("  • No errors detected")
        
        # Timing Analysis
        print("\n⏱️ TIMING ANALYSIS")
        print("-" * 40)
        bottlenecks = self.timing_analysis.get('bottlenecks', [])
        if bottlenecks:
            for bottleneck in bottlenecks:
                severity_icon = "🔴" if bottleneck['severity'] == 'high' else "🟡"
                print(f"  {severity_icon} {bottleneck['operation']}: {bottleneck['avg_time']:.2f}s average")
        else:
            print("  • No significant bottlenecks detected")
        
        # Recommendations
        if self.recommendations:
            print("\n💡 RECOMMENDATIONS")
            print("-" * 40)
            for i, rec in enumerate(self.recommendations, 1):
                print(f"{i}. {rec}")
        
        # Overall Assessment
        print("\n🎯 OVERALL ASSESSMENT")
        print("-" * 40)
        
        score = 100
        if error_rate > 10:
            score -= 30
        elif error_rate > 5:
            score -= 15
        elif error_rate > 1:
            score -= 5
        
        if memory_stats.get('max', 0) > 500:
            score -= 20
        elif memory_stats.get('max', 0) > 200:
            score -= 10
        
        if len(self.critical_issues) > 5:
            score -= 25
        elif len(self.critical_issues) > 2:
            score -= 15
        elif len(self.critical_issues) > 0:
            score -= 10
        
        if score >= 90:
            assessment = "🟢 EXCELLENT - System performing optimally"
        elif score >= 75:
            assessment = "🟡 GOOD - Minor issues to address"
        elif score >= 60:
            assessment = "🟠 FAIR - Several issues need attention"
        else:
            assessment = "🔴 POOR - Critical issues require immediate attention"
        
        print(f"System Health Score: {score}/100")
        print(f"Assessment: {assessment}")
        
        print("\n" + "="*80)
    
    def export_analysis(self, filename: str):
        """Export analysis results to JSON"""
        print(f"💾 Exporting analysis to {filename}...")
        
        export_data = {
            'analysis_timestamp': datetime.now().isoformat(),
            'log_files': self.log_files,
            'performance_metrics': self.performance_metrics,
            'error_analysis': {k: v for k, v in self.error_analysis.items() if k != 'error_details'},
            'memory_analysis': self.memory_analysis,
            'timing_analysis': {k: v for k, v in self.timing_analysis.items() if k != 'operation_times'},
            'operation_analysis': self.operation_analysis,
            'critical_issues': self.critical_issues,
            'recommendations': self.recommendations
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, default=str)
        
        print(f"✅ Analysis exported to {filename}")
    
    def run_full_analysis(self, create_charts: bool = False, export_file: Optional[str] = None):
        """Run complete analysis pipeline"""
        if not self.load_logs():
            return False
        
        # Run all analysis modules
        self.analyze_performance()
        self.analyze_errors()
        self.analyze_memory_patterns()
        self.analyze_timing_patterns()
        self.analyze_operations()
        self.generate_recommendations()
        
        # Create visualizations if requested
        if create_charts:
            self.create_visualizations()
        
        # Print critical analysis
        self.print_critical_analysis()
        
        # Export if requested
        if export_file:
            self.export_analysis(export_file)
        
        return True

def find_latest_log_file() -> Optional[str]:
    """Find the most recent poll generation log file"""
    log_pattern = "poll_generation_*.log"
    log_files = glob.glob(log_pattern)
    
    if not log_files:
        return None
    
    # Sort by modification time, newest first
    log_files.sort(key=lambda x: Path(x).stat().st_mtime, reverse=True)
    return log_files[0]

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="Analyze poll generation logs")
    parser.add_argument("--log-file", type=str, help="Specific log file to analyze")
    parser.add_argument("--detailed", action="store_true", help="Generate detailed analysis")
    parser.add_argument("--charts", action="store_true", help="Create visualization charts")
    parser.add_argument("--export", type=str, help="Export analysis to JSON file")
    parser.add_argument("--compare", nargs="+", help="Compare multiple log files")
    
    args = parser.parse_args()
    
    # Determine which log files to analyze
    log_files = []
    
    if args.compare:
        log_files = args.compare
    elif args.log_file:
        log_files = [args.log_file]
    else:
        # Find the latest log file
        latest_log = find_latest_log_file()
        if latest_log:
            log_files = [latest_log]
            print(f"🔍 Analyzing latest log file: {latest_log}")
        else:
            print("❌ No poll generation log files found!")
            print("💡 Run the poll generation script first to create logs")
            return 1
    
    if not log_files:
        print("❌ No log files specified!")
        return 1
    
    # Create analyzer and run analysis
    analyzer = PollGenerationAnalyzer(log_files)
    
    success = analyzer.run_full_analysis(
        create_charts=args.charts,
        export_file=args.export
    )
    
    if not success:
        return 1
    
    print("\n🎉 Analysis complete!")
    
    if args.charts and HAS_PLOTTING:
        print("📊 Charts saved to analysis_charts/ directory")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
