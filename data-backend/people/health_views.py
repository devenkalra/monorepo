"""
Health check endpoints for monitoring
"""
from django.http import JsonResponse
from django.db import connection
from django.core.cache import cache
import logging

logger = logging.getLogger(__name__)


def health_check(request):
    """
    Basic health check endpoint
    Returns 200 OK if service is running
    """
    return JsonResponse({
        'status': 'healthy',
        'service': 'bldrdojo-backend',
    })


def health_detailed(request):
    """
    Detailed health check with dependency checks
    Checks database, cache, and other services
    """
    health_status = {
        'status': 'healthy',
        'service': 'bldrdojo-backend',
        'checks': {}
    }
    
    all_healthy = True
    
    # Check database
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        health_status['checks']['database'] = 'healthy'
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        health_status['checks']['database'] = 'unhealthy'
        all_healthy = False
    
    # Check cache (Redis)
    try:
        cache.set('health_check', 'ok', 10)
        if cache.get('health_check') == 'ok':
            health_status['checks']['cache'] = 'healthy'
        else:
            health_status['checks']['cache'] = 'unhealthy'
            all_healthy = False
    except Exception as e:
        logger.error(f"Cache health check failed: {e}")
        health_status['checks']['cache'] = 'unhealthy'
        all_healthy = False
    
    # Overall status
    if not all_healthy:
        health_status['status'] = 'unhealthy'
    
    status_code = 200 if all_healthy else 503
    return JsonResponse(health_status, status=status_code)
