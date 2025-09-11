"""
Advanced Log Analytics Endpoints
Additional endpoints for pandas-powered log analytics and insights.
"""

import logging
from datetime import datetime, timedelta
from fastapi import Request, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, HTMLResponse
from typing import Optional

from .super_admin import require_super_admin, DiscordUser

logger = logging.getLogger(__name__)


async def get_log_analytics_api(
    request: Request,
    days: int = Query(7, ge=1, le=30, description="Number of days to analyze"),
    current_user: DiscordUser = Depends(require_super_admin)
) -> JSONResponse:
    """Get comprehensive log analytics using pandas"""
    try:
        from .pandas_log_analyzer import pandas_log_analyzer
        
        # Get error trends
        error_trends = pandas_log_analyzer.get_error_trends(days=days)
        
        # Get overall analytics for the time period
        time_range = f"{days}d"
        log_entries, analytics = pandas_log_analyzer.get_filtered_logs(
            time_range=time_range,
            limit=10000
        )
        
        # Combine analytics
        comprehensive_analytics = {
            "overview": analytics,
            "error_trends": error_trends,
            "generated_at": datetime.now().isoformat(),
            "analysis_period_days": days
        }
        
        return JSONResponse(content={
            "success": True,
            "analytics": comprehensive_analytics
        })
        
    except Exception as e:
        logger.error(f"Error getting log analytics: {e}")
        raise HTTPException(status_code=500, detail="Error generating analytics")


async def export_log_analytics_api(
    request: Request,
    days: int = Query(7, ge=1, le=30),
    current_user: DiscordUser = Depends(require_super_admin)
) -> JSONResponse:
    """Export log analytics as JSON"""
    try:
        from .pandas_log_analyzer import pandas_log_analyzer
        
        # Get comprehensive analytics
        error_trends = pandas_log_analyzer.get_error_trends(days=days)
        time_range = f"{days}d"
        log_entries, analytics = pandas_log_analyzer.get_filtered_logs(
            time_range=time_range,
            limit=10000
        )
        
        export_data = {
            "export_info": {
                "generated_at": datetime.now().isoformat(),
                "generated_by": current_user.username,
                "analysis_period_days": days,
                "version": "1.0-pandas"
            },
            "analytics": analytics,
            "error_trends": error_trends,
            "sample_entries": log_entries[:100]  # Include sample entries
        }
        
        return JSONResponse(content=export_data)
        
    except Exception as e:
        logger.error(f"Error exporting log analytics: {e}")
        raise HTTPException(status_code=500, detail="Error exporting analytics")


def add_log_analytics_routes(app):
    """Add log analytics routes to the FastAPI app"""
    
    @app.get("/super-admin/api/logs/analytics")
    async def super_admin_log_analytics(
        request: Request,
        days: int = Query(7, ge=1, le=30),
        current_user: DiscordUser = Depends(require_super_admin)
    ):
        return await get_log_analytics_api(request, days, current_user)
    
    @app.get("/super-admin/api/logs/analytics/export")
    async def super_admin_export_log_analytics(
        request: Request,
        days: int = Query(7, ge=1, le=30),
        current_user: DiscordUser = Depends(require_super_admin)
    ):
        return await export_log_analytics_api(request, days, current_user)
