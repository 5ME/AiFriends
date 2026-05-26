from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        try:
            from django.db import connections
            connections['default'].cursor()
            return Response({'status': 'ok', 'db': 'ok'})
        except Exception:
            return Response(
                {'status': 'degraded', 'db': 'error'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
