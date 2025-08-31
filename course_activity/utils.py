# authentication/utils.py

from rest_framework.response import Response
from rest_framework import status as request_status

def generate_request_response(status=True, status_code=request_status.HTTP_200_OK, message="Success", data=None):
    """
    A utility function to generate a standardized API response.
    """
    response_data = {
        "status": status,
        "status_code": status_code,
        "message": message,
    }
    # Only include the 'data' key if data is not None
    if data is not None:
        response_data["data"] = data

    return Response(response_data, status=status_code)