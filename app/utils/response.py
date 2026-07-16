from flask import jsonify


def success_response(data=None, status=200):
    return jsonify({"success": True, "data": data, "error": None}), status


def error_response(code, message, status):
    return jsonify({"success": False, "data": None, "error": {"code": code, "message": message}}), status


class ApiError(Exception):
    """Base error for service-layer failures; carries the API error code (7.2절)."""

    def __init__(self, code, message, status=400):
        self.code = code
        self.message = message
        self.status = status
        super().__init__(message)
