"""GET /api/admin/usage/summary/ — API 用量聚合摘要"""
import logging
from datetime import timedelta

from django.db.models import Sum, Count
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from web.models.usage import APIUsage

logger = logging.getLogger(__name__)


class UsageSummaryView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        days = int(request.query_params.get('days', 7))
        user_id = request.query_params.get('user_id')

        since = timezone.now().date() - timedelta(days=days - 1)
        qs = APIUsage.objects.filter(created_at__date__gte=since)

        if user_id:
            qs = qs.filter(user_id=int(user_id))

        rows = (
            qs.values('user_id', 'user__user__username', 'created_at__date', 'api_type')
            .annotate(
                total_tokens=Sum('token_count'),
                call_count=Count('id'),
                total_duration_ms=Sum('duration_ms'),
            )
            .order_by('-created_at__date', 'user_id', 'api_type')
        )

        summary = [
            {
                'user_id': r['user_id'],
                'username': r['user__user__username'] or '(system)',
                'date': str(r['created_at__date']),
                'api_type': r['api_type'],
                'total_tokens': r['total_tokens'],
                'call_count': r['call_count'],
                'total_duration_ms': r['total_duration_ms'],
            }
            for r in rows
        ]

        return Response({
            'summary': summary,
            'filters': {'days': days, 'user_id': user_id},
        })
