from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    """Simple JSON endpoint to verify the API and CORS."""

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response(
            {
                'status': 'ok',
                'message': 'Django API is running.',
            }
        )
