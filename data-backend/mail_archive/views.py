from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q
from celery.result import AsyncResult
from django.core.cache import cache
import logging

from .models import EmailAccount, ImportConfig, Email
from .serializers import (
    EmailAccountSerializer, ImportConfigSerializer, 
    EmailSerializer, EmailListSerializer
)
from .tasks import import_emails_async

logger = logging.getLogger(__name__)


class IsOwner(IsAuthenticated):
    """Permission class to ensure users can only access their own data"""
    def has_object_permission(self, request, view, obj):
        return obj.user == request.user


class EmailAccountViewSet(viewsets.ModelViewSet):
    """API endpoints for email accounts"""
    serializer_class = EmailAccountSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return EmailAccount.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
    
    @action(detail=True, methods=['post'])
    def test_connection(self, request, pk=None):
        """Test IMAP connection for an account"""
        account = self.get_object()
        
        try:
            from .imap_service import IMAPService
            with IMAPService(
                host=account.imap_host,
                port=account.imap_port,
                username=account.username,
                password=account.password,
                use_ssl=account.imap_use_ssl
            ) as imap:
                mailboxes = imap.list_mailboxes()
                return Response({
                    'success': True,
                    'message': 'Connection successful',
                    'mailboxes': mailboxes[:20]  # Return first 20 mailboxes
                })
        except Exception as e:
            logger.error(f"Connection test failed for account {pk}: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)


class ImportConfigViewSet(viewsets.ModelViewSet):
    """API endpoints for import configurations"""
    serializer_class = ImportConfigSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return ImportConfig.objects.filter(user=self.request.user).select_related('account')
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
    
    @action(detail=True, methods=['post'])
    def import_now(self, request, pk=None):
        """Trigger async import for this configuration"""
        config = self.get_object()
        
        if not config.is_active:
            return Response({
                'success': False,
                'error': 'Configuration is not active'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if not config.account.is_active:
            return Response({
                'success': False,
                'error': 'Email account is not active'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Start async task
        task = import_emails_async.delay(config.id, request.user.id)
        
        logger.info(f"Started email import task {task.id} for config {config.id}")
        
        return Response({
            'success': True,
            'task_id': task.id,
            'message': 'Email import started'
        })


class EmailViewSet(viewsets.ReadOnlyModelViewSet):
    """API endpoints for viewing emails"""
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Email.objects.filter(user=self.request.user).select_related('account')
    
    def get_serializer_class(self):
        if self.action == 'list':
            return EmailListSerializer
        return EmailSerializer
    
    def list(self, request):
        """List emails with filtering, sorting, and pagination"""
        queryset = self.get_queryset()
        
        # Filters
        account_id = request.query_params.get('account')
        if account_id:
            queryset = queryset.filter(account_id=account_id)
        
        from_filter = request.query_params.get('from')
        if from_filter:
            queryset = queryset.filter(from_address__icontains=from_filter)
        
        to_filter = request.query_params.get('to')
        if to_filter:
            queryset = queryset.filter(
                Q(to_addresses__icontains=to_filter) |
                Q(cc_addresses__icontains=to_filter) |
                Q(bcc_addresses__icontains=to_filter)
            )
        
        subject_filter = request.query_params.get('subject')
        if subject_filter:
            queryset = queryset.filter(subject__icontains=subject_filter)
        
        search_query = request.query_params.get('q')
        if search_query:
            queryset = queryset.filter(
                Q(subject__icontains=search_query) |
                Q(from_address__icontains=search_query) |
                Q(body_text__icontains=search_query)
            )
        
        has_attachments = request.query_params.get('has_attachments')
        if has_attachments:
            queryset = queryset.filter(has_attachments=has_attachments.lower() == 'true')
        
        date_from = request.query_params.get('date_from')
        if date_from:
            queryset = queryset.filter(date__gte=date_from)
        
        date_to = request.query_params.get('date_to')
        if date_to:
            queryset = queryset.filter(date__lte=date_to)
        
        # Sorting
        sort_by = request.query_params.get('sort_by', 'date')
        if sort_by == 'date':
            queryset = queryset.order_by('-date')
        elif sort_by == 'date_asc':
            queryset = queryset.order_by('date')
        elif sort_by == 'subject':
            queryset = queryset.order_by('subject')
        elif sort_by == 'from':
            queryset = queryset.order_by('from_address')
        else:
            queryset = queryset.order_by('-date')
        
        # Pagination
        try:
            page = int(request.query_params.get('page', 1))
            page_size = int(request.query_params.get('page_size', 20))
            page = max(1, page)
            page_size = min(max(1, page_size), 100)
        except ValueError:
            page = 1
            page_size = 20
        
        total_count = queryset.count()
        start = (page - 1) * page_size
        end = start + page_size
        paginated_queryset = queryset[start:end]
        
        serializer = self.get_serializer(paginated_queryset, many=True)
        
        return Response({
            'results': serializer.data,
            'count': total_count,
            'page': page,
            'page_size': page_size,
            'total_pages': (total_count + page_size - 1) // page_size
        })
    
    @action(detail=False, methods=['get'])
    def task_progress(self, request):
        """Get progress of an email import task"""
        task_id = request.query_params.get('task_id')
        if not task_id:
            return Response({'error': 'task_id required'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Check cache first
        progress_data = cache.get(f'task_progress_{task_id}')
        
        if progress_data:
            logger.info(f"Task {task_id} progress from cache: {progress_data}")
            return Response(progress_data)
        
        # Fall back to Celery task state
        task = AsyncResult(task_id)
        logger.info(f"Task {task_id} state from Celery: {task.state}")
        
        if task.state == 'PENDING':
            return Response({
                'task_id': task_id,
                'status': 'pending',
                'current': 0,
                'total': 0,
                'percentage': 0,
                'message': 'Task is pending...'
            })
        elif task.state == 'SUCCESS':
            return Response({
                'task_id': task_id,
                'status': 'completed',
                'current': 100,
                'total': 100,
                'percentage': 100,
                'message': 'Task completed successfully'
            })
        elif task.state == 'FAILURE':
            return Response({
                'task_id': task_id,
                'status': 'failed',
                'current': 0,
                'total': 0,
                'percentage': 0,
                'message': f'Task failed: {str(task.info)}'
            })
        else:
            return Response({
                'task_id': task_id,
                'status': task.state.lower(),
                'current': 0,
                'total': 0,
                'percentage': 0,
                'message': f'Task is {task.state}'
            })
    
    @action(detail=False, methods=['post'])
    def cancel_task(self, request):
        """Cancel an email import task"""
        task_id = request.data.get('task_id')
        if not task_id:
            return Response({'error': 'task_id required'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Mark task for cancellation in cache
        cache.set(f'task_cancel_{task_id}', True, timeout=3600)
        
        # Revoke the Celery task
        from celery import current_app
        current_app.control.revoke(task_id, terminate=True)
        
        logger.info(f"Email import task {task_id} marked for cancellation")
        
        return Response({
            'success': True,
            'message': 'Task cancellation requested'
        })
