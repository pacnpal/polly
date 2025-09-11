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
        
        # Create DataFrame
        df = pd.DataFrame(all_log_data)
        
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
        """Extract metadata from log message content"""
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
        
        # Check for error indicators
        error_keywords = ['error', 'exception', 'failed', 'traceback', 'critical']
        metadata['is_error'] = any(keyword in message.lower() for keyword in error_keywords)
        
        # Extract poll ID
        poll_match = re.search(r'poll[_\s]?(?:id)?[:\s]+(\d+)', message, re.IGNORECASE)
        if poll_match:
            metadata['has_poll_id'] = True
            metadata['poll_id'] = int(poll_match.group(1))
        
        # Extract user ID
        user_match = re.search(r'user[_\s]?(?:id)?[:\s]+(\d+)', message, re.IGNORECASE)
        if user_match:
            metadata['has_user_id'] = True
            metadata['user_id'] = user_match.group(1)
        
        # Extract server ID
        server_match = re.search(r'server[_\s]?(?:id)?[:\s]+(\d+)', message, re.IGNORECASE)
        if server_match:
            metadata['has_server_id'] = True
            metadata['server_id'] = server_match.group(1)
        
        # Extract HTTP endpoint
        endpoint_match = re.search(r'(GET|POST|PUT|DELETE|PATCH)\s+([/\w\-]+)', message)
        if endpoint_match:
            metadata['endpoint'] = f"{endpoint_match.group(1)} {endpoint_match.group(2)}"
        
        # Extract status code
        status_match = re.search(r'status[:\s]+(\d{3})', message, re.IGNORECASE)
        if status_match:
            metadata['status_code'] = int(status_match.group(1))
        
        # Extract response time
        time_match = re.search(r'(\d+(?:\.\d+)?)\s*ms', message)
        if time_match:
            metadata['response_time'] = float(time_match.group(1))
        
        return metadata
    
    def get_log_analytics(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Generate comprehensive log analytics from DataFrame"""
        
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
                'performance_metrics': {}
            }
        
        analytics = {
            'total_entries': len(df),
            'time_range': {
                'start': df['timestamp'].min().isoformat() if not df.empty and not pd.isna(df['timestamp'].min()) else None,
                'end': df['timestamp'].max().isoformat() if not df.empty and not pd.isna(df['timestamp'].max()) else None,
                'duration_hours': (df['timestamp'].max() - df['timestamp'].min()).total_seconds() / 3600 if len(df) > 1 and not pd.isna(df['timestamp'].min()) and not pd.isna(df['timestamp'].max()) else 0
            }
        }
        
        # Level distribution
        level_counts = df['level'].value_counts()
        analytics['level_distribution'] = level_counts.to_dict()
        
        # Error rate
        error_count = df['is_error'].sum()
        analytics['error_rate'] = (error_count / len(df)) * 100 if len(df) > 0 else 0
        
        # Top error messages
        error_df = df[df['is_error'] == True]
        if not error_df.empty:
            top_errors = error_df['message'].value_counts().head(10)
            analytics['top_errors'] = [
                {'message': msg, 'count': count} 
                for msg, count in top_errors.items()
            ]
        else:
            analytics['top_errors'] = []
        
        # Activity by hour
        hourly_activity = df.groupby('hour').size()
        analytics['activity_by_hour'] = hourly_activity.to_dict()
        
        # Activity by day of week
        daily_activity = df.groupby('day_of_week').size()
        analytics['activity_by_day'] = daily_activity.to_dict()
        
        # Poll-related activity
        poll_df = df[df['has_poll_id'] == True]
        if not poll_df.empty:
            analytics['poll_activity'] = {
                'total_poll_events': len(poll_df),
                'unique_polls': poll_df['poll_id'].nunique(),
                'most_active_polls': poll_df['poll_id'].value_counts().head(10).to_dict()
            }
        else:
            analytics['poll_activity'] = {
                'total_poll_events': 0,
                'unique_polls': 0,
                'most_active_polls': {}
            }
        
        # Performance metrics
        response_time_df = df[df['response_time'].notna() & (df['response_time'] != '')]
        if not response_time_df.empty:
            try:
                # Convert to numeric, handling any string values
                response_times = pd.to_numeric(response_time_df['response_time'], errors='coerce')
                response_times = response_times.dropna()
                
                if not response_times.empty:
                    analytics['performance_metrics'] = {
                        'avg_response_time': float(response_times.mean()),
                        'median_response_time': float(response_times.median()),
                        'max_response_time': float(response_times.max()),
                        'slow_requests': int(len(response_times[response_times > 1000]))
                    }
                else:
                    analytics['performance_metrics'] = {
                        'avg_response_time': 0,
                        'median_response_time': 0,
                        'max_response_time': 0,
                        'slow_requests': 0
                    }
            except Exception as e:
                logger.warning(f"Error calculating performance metrics: {e}")
                analytics['performance_metrics'] = {
                    'avg_response_time': 0,
                    'median_response_time': 0,
                    'max_response_time': 0,
                    'slow_requests': 0
                }
        else:
            analytics['performance_metrics'] = {
                'avg_response_time': 0,
                'median_response_time': 0,
                'max_response_time': 0,
                'slow_requests': 0
            }
        
        return analytics
    
    def get_filtered_logs(
        self,
        level_filter: Optional[str] = None,
        search_filter: Optional[str] = None,
        time_range: str = "24h",
        limit: int = 500
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Get filtered logs with analytics - main interface for super admin panel"""
        
        # Parse time range
        time_cutoff = self._parse_time_range(time_range)
        
        # Get DataFrame
        df = self.parse_logs_to_dataframe(time_cutoff, level_filter, search_filter)
        
        # Generate analytics
        analytics = self.get_log_analytics(df)
        
        # Convert to list format for template (limit results)
        limited_df = df.head(limit)
        log_entries = []
        
        for _, row in limited_df.iterrows():
            # Safe access to row data with proper type checking
            log_entries.append({
                'timestamp': row['timestamp'].isoformat() if hasattr(row['timestamp'], 'isoformat') else str(row['timestamp']),
                'level': str(row['level']) if row['level'] is not None else 'INFO',
                'message': str(row['message']) if row['message'] is not None else '',
                'file': str(row['file']) if row['file'] is not None else '',
                'line_number': int(row['line_number']) if row['line_number'] is not None else 0,
                'metadata': {
                    'is_error': bool(row.get('is_error', False)),
                    'has_poll_id': bool(row.get('has_poll_id', False)),
                    'poll_id': int(row['poll_id']) if row.get('poll_id') is not None and not pd.isna(row['poll_id']) else None,
                    'has_user_id': bool(row.get('has_user_id', False)),
                    'user_id': str(row['user_id']) if row.get('user_id') is not None and not pd.isna(row['user_id']) else None,
                    'endpoint': str(row['endpoint']) if row.get('endpoint') is not None and not pd.isna(row['endpoint']) else None,
                    'status_code': int(row['status_code']) if row.get('status_code') is not None and not pd.isna(row['status_code']) else None,
                    'response_time': float(row['response_time']) if row.get('response_time') is not None and not pd.isna(row['response_time']) else None
                }
            })
        
        return log_entries, analytics
    
    async def get_filtered_logs_async(
        self,
        level_filter: Optional[str] = None,
        search_filter: Optional[str] = None,
        time_range: str = "24h",
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
            'daily_errors': daily_errors.to_dict(),
            'error_types': error_df['level'].value_counts().to_dict(),
            'trend': trend,
            'total_errors': len(error_df),
            'error_rate': (len(error_df) / len(df)) * 100 if len(df) > 0 else 0
        }


# Global analyzer instance
pandas_log_analyzer = PandasLogAnalyzer()
