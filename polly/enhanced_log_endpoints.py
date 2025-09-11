"""
Enhanced Log Endpoints for Super Admin Panel
Advanced logging with category and severity filtering.
"""

import logging
from fastapi import Request, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from typing import Optional
from datetime import datetime

from .super_admin import require_super_admin, DiscordUser

logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="templates")


async def get_enhanced_system_logs_htmx(
    request: Request,
    level: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    time_range: str = Query("24h"),
    category: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    current_user: DiscordUser = Depends(require_super_admin)
) -> HTMLResponse:
    """Enhanced HTMX endpoint for system logs with advanced filtering"""
    try:
        from .pandas_log_analyzer import pandas_log_analyzer
        
        # Use async pandas analyzer to prevent blocking Discord bot heartbeat
        log_entries, analytics = await pandas_log_analyzer.get_filtered_logs_async(
            level_filter=level,
            search_filter=search,
            time_range=time_range,
            category_filter=category,
            severity_filter=severity,
            limit=500
        )
        
        return templates.TemplateResponse(
            "htmx/super_admin_logs_enhanced.html",
            {
                "request": request,
                "log_entries": log_entries,
                "analytics": analytics,
                "filters": {
                    "level": level,
                    "search": search,
                    "time_range": time_range,
                    "category": category,
                    "severity": severity
                }
            }
        )
        
    except Exception as e:
        logger.error(f"Error getting enhanced system logs: {e}")
        return HTMLResponse(
            content="<div class='alert alert-danger'>Error loading enhanced system logs</div>",
            status_code=500
        )


async def download_enhanced_logs_api(
    request: Request,
    level: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    time_range: str = Query("24h"),
    category: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    current_user: DiscordUser = Depends(require_super_admin)
) -> StreamingResponse:
    """Enhanced download filtered logs with advanced filtering"""
    try:
        from .pandas_log_analyzer import pandas_log_analyzer
        
        # Use async pandas analyzer to prevent blocking Discord bot heartbeat
        log_entries, analytics = await pandas_log_analyzer.get_filtered_logs_async(
            level_filter=level,
            search_filter=search,
            time_range=time_range,
            category_filter=category,
            severity_filter=severity,
            limit=10000  # Higher limit for downloads
        )
        
        # Generate enhanced log content with analytics header
        def generate_log_content():
            yield f"# Polly Enhanced System Logs Export\n"
            yield f"# Generated: {datetime.now().isoformat()}\n"
            yield f"# Filters Applied:\n"
            yield f"#   - Level: {level or 'All'}\n"
            yield f"#   - Search: {search or 'None'}\n"
            yield f"#   - Time Range: {time_range}\n"
            yield f"#   - Category: {category or 'All'}\n"
            yield f"#   - Severity: {severity or 'All'}\n"
            yield f"# Total Entries: {len(log_entries)}\n"
            yield f"# Enhanced Analytics Summary:\n"
            yield f"#   - Error Rate: {analytics.get('error_rate', 0):.2f}%\n"
            yield f"#   - System Health Score: {analytics.get('structured_insights', {}).get('system_health', {}).get('health_score', 0)}/100\n"
            yield f"#   - Data Quality: {analytics.get('structured_insights', {}).get('data_quality', {}).get('structured_entries', 0)} structured entries\n"
            yield f"#   - Poll Events: {analytics.get('poll_activity', {}).get('total_poll_events', 0)}\n"
            yield f"#   - Performance Metrics: {analytics.get('performance_metrics', {}).get('avg_response_time', 0):.2f}ms avg response\n"
            yield f"\n"
            
            for entry in log_entries:
                metadata = entry.get('metadata', {})
                
                # Enhanced metadata string with category and severity
                metadata_str = ""
                if metadata.get('category'):
                    metadata_str += f" [Category:{metadata['category']}]"
                if metadata.get('severity_score'):
                    metadata_str += f" [Severity:{metadata['severity_score']}]"
                if metadata.get('poll_id'):
                    metadata_str += f" [Poll:{metadata['poll_id']}]"
                if metadata.get('user_id'):
                    metadata_str += f" [User:{metadata['user_id']}]"
                if metadata.get('endpoint'):
                    metadata_str += f" [API:{metadata['endpoint']}]"
                if metadata.get('response_time'):
                    metadata_str += f" [RT:{metadata['response_time']}ms]"
                if metadata.get('status_code'):
                    metadata_str += f" [Status:{metadata['status_code']}]"
                
                yield f"{entry['timestamp']} - {entry['level']} - {entry['message']}{metadata_str}\n"
        
        filename = f"polly_enhanced_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        
        return StreamingResponse(
            generate_log_content(),
            media_type="text/plain",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except Exception as e:
        logger.error(f"Error downloading enhanced logs: {e}")
        raise HTTPException(status_code=500, detail="Error generating enhanced log download")


def add_enhanced_log_routes(app):
    """Add enhanced logging routes to the FastAPI app"""

    @app.get("/super-admin/htmx/logs/enhanced", response_class=HTMLResponse)
    async def super_admin_enhanced_logs_htmx(
        request: Request,
        level: Optional[str] = Query(None),
        search: Optional[str] = Query(None),
        time_range: str = Query("24h"),
        category: Optional[str] = Query(None),
        severity: Optional[str] = Query(None),
        current_user: DiscordUser = Depends(require_super_admin)
    ):
        return await get_enhanced_system_logs_htmx(
            request, level, search, time_range, category, severity, current_user
        )

    @app.get("/super-admin/api/logs/download/enhanced")
    async def super_admin_download_enhanced_logs(
        request: Request,
        level: Optional[str] = Query(None),
        search: Optional[str] = Query(None),
        time_range: str = Query("24h"),
        category: Optional[str] = Query(None),
        severity: Optional[str] = Query(None),
        current_user: DiscordUser = Depends(require_super_admin)
    ):
        return await download_enhanced_logs_api(
            request, level, search, time_range, category, severity, current_user
        )
