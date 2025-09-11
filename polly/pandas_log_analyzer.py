"""
Pandas-based Log Analyzer for Super Admin Panel
Advanced log parsing and analysis using pandas for better performance and analytics.
"""

import logging
import os
import re
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor
import functools

logger = logging.getLogger(__name__)


class PandasLogAnalyzer:
    """Advanced log analyzer using pandas for high-performance log analysis"""
    
    def __init__(self):
        self.log_files = [
            "polly.log",
            "logs/polly.log", 
            "logs/dev.log"
        ]
        self.log_pattern = re.compile(
            r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ - (\w+) - (.+)$'
        )
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="log_parser")
    
    def parse_logs_to_dataframe(
        self, 
        time_cutoff: Optional[datetime] = None,
        level_filter: Optional[str] = None,
        search_filter: Optional[str] = None
    ) -> pd.DataFrame:
        """Parse all log files into a pandas DataFrame for advanced analysis"""
        
        all_log_data = []
        
        for log_file in self.log_files:
            if not os.path.exists(log_file):
                continue
                
            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    for line_num, line in enumerate(f, 1):
                        line = line.strip()
                        if not line:
                            continue
                        
                        # Parse structured log entry
                        match = self.log_pattern.match(line)
                        if match:
                            timestamp_str, level, message = match.groups()
                            
                            try:
                                timestamp = pd.to_datetime(timestamp_str, format='%Y-%m-%d %H:%M:%S')
                            except ValueError:
                                timestamp = pd.Timestamp.now()
                            
                            log_entry = {
                                'timestamp': timestamp,
                                'level': level,
                                'message': message,
                                'file': log_file,
                                'line_number': line_num,
                                'message_length': len(message),
                                'hour': timestamp.hour,
                                'day_of_week': timestamp.day_name(),
                                'date': timestamp.date()
                            }
                            
                            # Extract additional metadata from message
                            log_entry.update(self._extract_message_metadata(message))
                            
                            all_log_data.append(log_entry)
                        else:
                            # Handle unstructured log lines
                            timestamp = pd.Timestamp.now()
                            unstructured_entry = {
                                'timestamp': timestamp,
                                'level': 'UNSTRUCTURED',
                                'message': line,
                                'file': log_file,
                                'line_number': line_num,
                                'message_length': len(line),
                                'hour': timestamp.hour,
                                'day_of_week': timestamp.day_name(),
                                'date': timestamp.date(),
                                'is_error': False,
                                'has_poll_id': False,
                                'has_user_id': False,
                                'has_server_id': False,
                                'poll_id': None,
                                'user_id': None,
                                'server_id': None,
                                'endpoint': None,
                                'status_code': None,
                                'response_time': None
                            }
                            all_log_data.append(unstructured_entry)
                            
            except Exception as e:
                logger.error(f"Error parsing log file {log_file}: {e}")
                continue
        
        if not all_log_data:
            return pd.DataFrame()
        
        # Create DataFrame with optimized dtypes for performance
        df = pd.DataFrame(all_log_data)
        
        # Optimize data types for better performance (pandas best practice)
        if not df.empty:
            # Convert categorical columns for memory efficiency
            df['level'] = df['level'].astype('category')
            df['file'] = df['file'].astype('category')
            df['day_of_week'] = df['day_of_week'].astype('category')
            
            # Optimize numeric columns
            df['line_number'] = pd.to_numeric(df['line_number'], downcast='integer')
            df['message_length'] = pd.to_numeric(df['message_length'], downcast='integer')
            df['hour'] = pd.to_numeric(df['hour'], downcast='integer')
        
        # Apply filters
        if time_cutoff:
            df = df[df['timestamp'] >= time_cutoff]
        
        if level_filter:
            df = df[df['level'] == level_filter]
        
        if search_filter:
            df = df[df['message'].str.contains(search_filter, case=False, na=False)]
        
        # Sort by timestamp (most recent first)
        df = df.sort_values('timestamp', ascending=False)
        
        return df
    
    def _extract_message_metadata(self, message: str) -> Dict[str, Any]:
        """Extract metadata from log message content with enhanced patterns"""
        metadata = {
            'is_error': False,
            'has_poll_id': False,
            'has_user_id': False,
            'has_server_id': False,
            'poll_id': None,
            'user_id': None,
            'server_id': None,
            'endpoint': None,
            'status_code': None,
            'response_time': None
        }
        
        # Enhanced error detection with more patterns
        error_keywords = ['error', 'exception', 'failed', 'traceback', 'critical', 'warning', 'timeout', 'refused']
        metadata['is_error'] = any(keyword in message.lower() for keyword in error_keywords)
        
        # Enhanced poll ID extraction with multiple patterns
        poll_patterns = [
            r'poll[_\s]?(?:id)?[:\s]+(\d+)',
            r'poll\s*=\s*(\d+)',
            r'#(\d+)',  # Poll ID in format #123
        ]
        for pattern in poll_patterns:
            poll_match = re.search(pattern, message, re.IGNORECASE)
            if poll_match:
                metadata['has_poll_id'] = True
                metadata['poll_id'] = int(poll_match.group(1))
                break
        
        # Enhanced user ID extraction
        user_patterns = [
            r'user[_\s]?(?:id)?[:\s]+(\d+)',
            r'@(\d+)',  # Discord mention format
            r'creator[_\s]?(?:id)?[:\s]+(\d+)'
        ]
        for pattern in user_patterns:
            user_match = re.search(pattern, message, re.IGNORECASE)
            if user_match:
                metadata['has_user_id'] = True
                metadata['user_id'] = user_match.group(1)
                break
        
        # Enhanced server/guild ID extraction
        server_patterns = [
            r'server[_\s]?(?:id)?[:\s]+(\d+)',
            r'guild[_\s]?(?:id)?[:\s]+(\d+)'
        ]
        for pattern in server_patterns:
            server_match = re.search(pattern, message, re.IGNORECASE)
            if server_match:
                metadata['has_server_id'] = True
                metadata['server_id'] = server_match.group(1)
                break
        
        # Enhanced HTTP endpoint extraction
        endpoint_patterns = [
            r'(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+([/\w\-\{\}]+)',
            r'endpoint[:\s]+([/\w\-\{\}]+)',
            r'route[:\s]+([/\w\-\{\}]+)'
        ]
        for pattern in endpoint_patterns:
            endpoint_match = re.search(pattern, message, re.IGNORECASE)
            if endpoint_match:
                if len(endpoint_match.groups()) == 2:
                    metadata['endpoint'] = f"{endpoint_match.group(1)} {endpoint_match.group(2)}"
                else:
                    metadata['endpoint'] = endpoint_match.group(1)
                break
        
        # Enhanced status code extraction
        status_patterns = [
            r'status[:\s]+(\d{3})',
            r'HTTP[:\s]+(\d{3})',
            r'response[:\s]+(\d{3})'
        ]
        for pattern in status_patterns:
            status_match = re.search(pattern, message, re.IGNORECASE)
            if status_match:
                metadata['status_code'] = int(status_match.group(1))
                break
        
        # Enhanced response time extraction
        time_patterns = [
            r'(\d+(?:\.\d+)?)\s*ms',
            r'(\d+(?:\.\d+)?)\s*milliseconds',
            r'took\s+(\d+(?:\.\d+)?)\s*ms',
            r'duration[:\s]+(\d+(?:\.\d+)?)\s*ms'
        ]
        for pattern in time_patterns:
            time_match = re.search(pattern, message, re.IGNORECASE)
            if time_match:
                metadata['response_time'] = float(time_match.group(1))
                break
        
        return metadata
    
    def get_log_analytics(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Generate comprehensive log analytics from DataFrame with enhanced metrics"""
        
        if df.empty:
            return {
                'total_entries': 0,
                'time_range': None,
                'level_distribution': {},
                'error_rate': 0.0,
                'top_errors': [],
                'activity_by_hour': {},
                'activity_by_day': {},
                'poll_activity': {},
                'performance_metrics': {},
                'structured_insights': {}
            }
        
        analytics = {
            'total_entries': len(df),
            'time_range': {
                'start': df['timestamp'].min().isoformat() if not df.empty and not pd.isna(df['timestamp'].min()) else None,
                'end': df['timestamp'].max().isoformat() if not df.empty and not pd.isna(df['timestamp'].max()) else None,
                'duration_hours': (df['timestamp'].max() - df['timestamp'].min()).total_seconds() / 3600 if len(df) > 1 and not pd.isna(df['timestamp'].min()) and not pd.isna(df['timestamp'].max()) else 0
            }
        }
        
        # Level distribution with percentages
        level_counts = df['level'].value_counts()
        total_entries = len(df)
        analytics['level_distribution'] = {
            level: {
                'count': int(count),
                'percentage': round((count / total_entries) * 100, 2)
            }
            for level, count in level_counts.items()
        }
        
        # Enhanced error analysis
        error_count = df['is_error'].sum()
        analytics['error_rate'] = round((error_count / len(df)) * 100, 2) if len(df) > 0 else 0
        
        # Top error messages with context
        error_df = df[df['is_error'] == True]
        if not error_df.empty:
            top_errors = error_df['message'].value_counts().head(10)
            analytics['top_errors'] = [
                {
                    'message': msg[:200] + '...' if len(msg) > 200 else msg,
                    'count': int(count),
                    'percentage': round((count / len(error_df)) * 100, 2)
                } 
                for msg, count in top_errors.items()
            ]
        else:
            analytics['top_errors'] = []
        
        # Activity patterns
        hourly_activity = df.groupby('hour').size()
        analytics['activity_by_hour'] = {int(hour): int(count) for hour, count in hourly_activity.items()}
        
        daily_activity = df.groupby('day_of_week').size()
        analytics['activity_by_day'] = {day: int(count) for day, count in daily_activity.items()}
        
        # Enhanced poll activity analysis
        poll_df = df[df['has_poll_id'] == True]
        if not poll_df.empty:
            analytics['poll_activity'] = {
                'total_poll_events': int(len(poll_df)),
                'unique_polls': int(poll_df['poll_id'].nunique()),
                'most_active_polls': {int(poll_id): int(count) for poll_id, count in poll_df['poll_id'].value_counts().head(10).items()},
                'poll_event_rate': round((len(poll_df) / len(df)) * 100, 2)
            }
        else:
            analytics['poll_activity'] = {
                'total_poll_events': 0,
                'unique_polls': 0,
                'most_active_polls': {},
                'poll_event_rate': 0.0
            }
        
        # Enhanced performance metrics
        response_time_df = df[df['response_time'].notna() & (df['response_time'] != '')]
        if not response_time_df.empty:
            try:
                response_times = pd.to_numeric(response_time_df['response_time'], errors='coerce')
                response_times = response_times.dropna()
                
                if not response_times.empty:
                    analytics['performance_metrics'] = {
                        'avg_response_time': round(float(response_times.mean()), 2),
                        'median_response_time': round(float(response_times.median()), 2),
                        'max_response_time': round(float(response_times.max()), 2),
                        'min_response_time': round(float(response_times.min()), 2),
                        'p95_response_time': round(float(response_times.quantile(0.95)), 2),
                        'slow_requests': int(len(response_times[response_times > 1000])),
                        'fast_requests': int(len(response_times[response_times < 100])),
                        'total_timed_requests': int(len(response_times))
                    }
                else:
                    analytics['performance_metrics'] = self._empty_performance_metrics()
            except Exception as e:
                logger.warning(f"Error calculating performance metrics: {e}")
                analytics['performance_metrics'] = self._empty_performance_metrics()
        else:
            analytics['performance_metrics'] = self._empty_performance_metrics()
        
        # Structured insights
        analytics['structured_insights'] = self._generate_structured_insights(df)
        
        return analytics
    
    def _empty_performance_metrics(self) -> Dict[str, Any]:
        """Return empty performance metrics structure"""
        return {
            'avg_response_time': 0,
            'median_response_time': 0,
            'max_response_time': 0,
            'min_response_time': 0,
            'p95_response_time': 0,
            'slow_requests': 0,
            'fast_requests': 0,
            'total_timed_requests': 0
        }
    
    def _generate_structured_insights(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Generate structured insights from log data"""
        insights = {
            'data_quality': {
                'structured_entries': int(len(df[df['level'] != 'UNSTRUCTURED'])),
                'unstructured_entries': int(len(df[df['level'] == 'UNSTRUCTURED'])),
                'entries_with_metadata': int(len(df[
                    (df['has_poll_id'] == True) | 
                    (df['has_user_id'] == True) | 
                    (df['endpoint'].notna())
                ]))
            },
            'system_health': {
                'critical_errors': int(len(df[df['level'] == 'CRITICAL'])),
                'errors': int(len(df[df['level'] == 'ERROR'])),
                'warnings': int(len(df[df['level'] == 'WARNING'])),
                'health_score': self._calculate_health_score(df)
            },
            'activity_patterns': {
                'peak_hour': int(df.groupby('hour').size().idxmax()) if not df.empty else 0,
                'busiest_day': df.groupby('day_of_week').size().idxmax() if not df.empty else 'Unknown',
                'avg_entries_per_hour': round(len(df) / max(df['hour'].nunique(), 1), 2)
            }
        }
        
        return insights
    
    def _calculate_health_score(self, df: pd.DataFrame) -> float:
        """Calculate system health score (0-100) based on log patterns"""
        if df.empty:
            return 100.0
        
        total_entries = len(df)
        critical_count = len(df[df['level'] == 'CRITICAL'])
        error_count = len(df[df['level'] == 'ERROR'])
        warning_count = len(df[df['level'] == 'WARNING'])
        
        # Calculate penalty points
        penalty = 0
        penalty += (critical_count / total_entries) * 50  # Critical errors heavily penalized
        penalty += (error_count / total_entries) * 30    # Errors moderately penalized
        penalty += (warning_count / total_entries) * 10  # Warnings lightly penalized
        
        # Health score (higher is better)
        health_score = max(0, 100 - penalty)
        return round(health_score, 2)
    
    def get_filtered_logs(
        self,
        level_filter: Optional[str] = None,
        search_filter: Optional[str] = None,
        time_range: str = "24h",
        category_filter: Optional[str] = None,
        severity_filter: Optional[str] = None,
        limit: int = 500
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Get filtered logs with analytics - main interface for super admin panel"""
        
        # Parse time range
        time_cutoff = self._parse_time_range(time_range)
        
        # Get DataFrame
        df = self.parse_logs_to_dataframe(time_cutoff, level_filter, search_filter)
        
        # Apply category and severity filters after initial parsing
        if not df.empty:
            # Add category and severity columns for filtering
            df['category'] = df.apply(lambda row: self._categorize_log_entry(row), axis=1)
            df['severity_score'] = df.apply(lambda row: self._calculate_severity_score(row), axis=1)
            
            # Apply category filter
            if category_filter:
                df = df[df['category'] == category_filter]
            
            # Apply severity filter
            if severity_filter:
                if severity_filter == 'high':
                    df = df[df['severity_score'] >= 80]
                elif severity_filter == 'medium':
                    df = df[(df['severity_score'] >= 40) & (df['severity_score'] < 80)]
                elif severity_filter == 'low':
                    df = df[df['severity_score'] < 40]
        
        # Generate analytics
        analytics = self.get_log_analytics(df)
        
        # Convert to list format for template (limit results)
        limited_df = df.head(limit)
        log_entries = []
        
        for _, row in limited_df.iterrows():
            # Create structured log entry with enhanced metadata
            log_entry = {
                'timestamp': row['timestamp'].isoformat() if hasattr(row['timestamp'], 'isoformat') else str(row['timestamp']),
                'level': str(row['level']) if row['level'] is not None else 'INFO',
                'message': str(row['message']) if row['message'] is not None else '',
                'file': str(row['file']) if row['file'] is not None else '',
                'line_number': int(row['line_number']) if row['line_number'] is not None else 0,
                'structured_data': self._create_structured_log_data(row),
                'metadata': {
                    'is_error': bool(row.get('is_error', False)),
                    'has_poll_id': bool(row.get('has_poll_id', False)),
                    'poll_id': int(row['poll_id']) if row.get('poll_id') is not None and not pd.isna(row['poll_id']) else None,
                    'has_user_id': bool(row.get('has_user_id', False)),
                    'user_id': str(row['user_id']) if row.get('user_id') is not None and not pd.isna(row['user_id']) else None,
                    'endpoint': str(row['endpoint']) if row.get('endpoint') is not None and not pd.isna(row['endpoint']) else None,
                    'status_code': int(row['status_code']) if row.get('status_code') is not None and not pd.isna(row['status_code']) else None,
                    'response_time': float(row['response_time']) if row.get('response_time') is not None and not pd.isna(row['response_time']) else None,
                    'severity_score': self._calculate_severity_score(row),
                    'category': self._categorize_log_entry(row)
                }
            }
            log_entries.append(log_entry)
        
        return log_entries, analytics
    
    def _create_structured_log_data(self, row) -> Dict[str, Any]:
        """Create structured data representation of log entry"""
        structured = {
            'timestamp_unix': int(row['timestamp'].timestamp()) if hasattr(row['timestamp'], 'timestamp') else 0,
            'level_numeric': self._get_level_numeric(row.get('level', 'INFO')),
            'message_hash': hash(str(row.get('message', ''))) % (10**8),  # 8-digit hash for deduplication
            'source_file': str(row.get('file', '')).split('/')[-1],  # Just filename
            'has_metadata': any([
                row.get('has_poll_id', False),
                row.get('has_user_id', False),
                row.get('endpoint') is not None,
                row.get('status_code') is not None
            ]),
            'performance_flag': 'slow' if row.get('response_time', 0) and float(row.get('response_time', 0)) > 1000 else 'normal'
        }
        return structured
    
    def _get_level_numeric(self, level: str) -> int:
        """Convert log level to numeric value for sorting/analysis"""
        level_map = {
            'DEBUG': 10,
            'INFO': 20,
            'WARNING': 30,
            'ERROR': 40,
            'CRITICAL': 50,
            'UNSTRUCTURED': 15
        }
        return level_map.get(level.upper(), 20)
    
    def _calculate_severity_score(self, row) -> int:
        """Calculate severity score (0-100) based on log entry characteristics"""
        score = 0
        
        # Base score from log level
        level_scores = {
            'DEBUG': 5,
            'INFO': 10,
            'WARNING': 30,
            'ERROR': 60,
            'CRITICAL': 90,
            'UNSTRUCTURED': 15
        }
        score += level_scores.get(str(row.get('level', 'INFO')).upper(), 10)
        
        # Add points for error indicators
        if row.get('is_error', False):
            score += 20
        
        # Add points for slow performance
        if row.get('response_time') and float(row.get('response_time', 0)) > 1000:
            score += 15
        
        # Add points for HTTP error status codes
        status_code = row.get('status_code')
        if status_code:
            if status_code >= 500:
                score += 25
            elif status_code >= 400:
                score += 15
        
        # Cap at 100
        return min(score, 100)
    
    def _categorize_log_entry(self, row) -> str:
        """Categorize log entry into functional areas"""
        message = str(row.get('message', '')).lower()
        
        # Poll-related operations
        if row.get('has_poll_id') or any(keyword in message for keyword in ['poll', 'vote', 'option']):
            return 'poll_operations'
        
        # Discord bot operations
        if any(keyword in message for keyword in ['discord', 'bot', 'guild', 'channel', 'user']):
            return 'discord_operations'
        
        # HTTP/API operations
        if row.get('endpoint') or any(keyword in message for keyword in ['http', 'api', 'request', 'response']):
            return 'api_operations'
        
        # Database operations
        if any(keyword in message for keyword in ['database', 'db', 'sql', 'query']):
            return 'database_operations'
        
        # Authentication/Security
        if any(keyword in message for keyword in ['auth', 'login', 'token', 'permission', 'security']):
            return 'auth_security'
        
        # System/Infrastructure
        if any(keyword in message for keyword in ['redis', 'cache', 'memory', 'startup', 'shutdown']):
            return 'system_infrastructure'
        
        # Error handling
        if row.get('is_error') or any(keyword in message for keyword in ['error', 'exception', 'failed']):
            return 'error_handling'
        
        return 'general'
    
    async def get_filtered_logs_async(
        self,
        level_filter: Optional[str] = None,
        search_filter: Optional[str] = None,
        time_range: str = "24h",
        category_filter: Optional[str] = None,
        severity_filter: Optional[str] = None,
        limit: int = 500
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Async version of get_filtered_logs - runs in thread pool to prevent blocking"""
        
        loop = asyncio.get_event_loop()
        
        # Run the blocking operation in a thread pool
        return await loop.run_in_executor(
            self._executor,
            functools.partial(
                self.get_filtered_logs,
                level_filter=level_filter,
                search_filter=search_filter,
                time_range=time_range,
                category_filter=category_filter,
                severity_filter=severity_filter,
                limit=limit
            )
        )
    
    async def parse_logs_to_dataframe_async(
        self, 
        time_cutoff: Optional[datetime] = None,
        level_filter: Optional[str] = None,
        search_filter: Optional[str] = None
    ) -> pd.DataFrame:
        """Async version of parse_logs_to_dataframe - runs in thread pool to prevent blocking"""
        
        loop = asyncio.get_event_loop()
        
        # Run the blocking operation in a thread pool
        return await loop.run_in_executor(
            self._executor,
            functools.partial(
                self.parse_logs_to_dataframe,
                time_cutoff=time_cutoff,
                level_filter=level_filter,
                search_filter=search_filter
            )
        )
    
    async def get_error_trends_async(self, days: int = 7) -> Dict[str, Any]:
        """Async version of get_error_trends - runs in thread pool to prevent blocking"""
        
        loop = asyncio.get_event_loop()
        
        # Run the blocking operation in a thread pool
        return await loop.run_in_executor(
            self._executor,
            functools.partial(self.get_error_trends, days=days)
        )
    
    def _parse_time_range(self, time_range: str) -> datetime:
        """Parse time range string and return cutoff datetime"""
        now = datetime.now()
        
        time_ranges = {
            "1h": timedelta(hours=1),
            "6h": timedelta(hours=6),
            "24h": timedelta(hours=24),
            "7d": timedelta(days=7),
            "30d": timedelta(days=30)
        }
        
        delta = time_ranges.get(time_range, timedelta(hours=24))
        return now - delta
    
    def export_analytics_to_json(self, analytics: Dict[str, Any]) -> str:
        """Export analytics data to JSON format"""
        return json.dumps(analytics, indent=2, default=str)
    
    def get_error_trends(self, days: int = 7) -> Dict[str, Any]:
        """Analyze error trends over time"""
        cutoff = datetime.now() - timedelta(days=days)
        df = self.parse_logs_to_dataframe(time_cutoff=cutoff)
        
        if df.empty:
            return {'daily_errors': {}, 'error_types': {}, 'trend': 'stable'}
        
        # Group errors by date
        error_df = df[df['is_error'] == True]
        daily_errors = error_df.groupby('date').size()
        
        # Analyze trend
        if len(daily_errors) > 1:
            recent_avg = daily_errors.tail(3).mean()
            older_avg = daily_errors.head(3).mean()
            
            if recent_avg > older_avg * 1.2:
                trend = 'increasing'
            elif recent_avg < older_avg * 0.8:
                trend = 'decreasing'
            else:
                trend = 'stable'
        else:
            trend = 'insufficient_data'
        
        return {
            'daily_errors': {str(date): int(count) for date, count in daily_errors.items()},
            'error_types': {level: int(count) for level, count in error_df['level'].value_counts().items()},
            'trend': trend,
            'total_errors': int(len(error_df)),
            'error_rate': round((len(error_df) / len(df)) * 100, 2) if len(df) > 0 else 0
        }


# Global analyzer instance
pandas_log_analyzer = PandasLogAnalyzer()
