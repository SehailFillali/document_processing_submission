"""Structured error codes for the document extraction system."""

from enum import Enum


class ErrorCode(str, Enum):
    """Structured error codes for the system."""

    # Authentication/Authorization
    AUTH_MISSING_API_KEY = "AUTH_MISSING_API_KEY"
    AUTH_INVALID_API_KEY = "AUTH_INVALID_API_KEY"
    AUTH_EXPIRED_TOKEN = "AUTH_EXPIRED_TOKEN"

    # Validation Errors (VAL)
    VAL_FILE_TOO_LARGE = "VAL_FILE_TOO_LARGE"
    VAL_UNSUPPORTED_FILE_TYPE = "VAL_UNSUPPORTED_FILE_TYPE"
    VAL_FILE_CORRUPTED = "VAL_FILE_CORRUPTED"
    VAL_FILE_PASSWORD_PROTECTED = "VAL_FILE_PASSWORD_PROTECTED"
    VAL_MISSING_REQUIRED_FIELD = "VAL_MISSING_REQUIRED_FIELD"
    VAL_INVALID_FIELD_FORMAT = "VAL_INVALID_FIELD_FORMAT"
    VAL_INVALID_URI_SCHEME = "VAL_INVALID_URI_SCHEME"

    # Processing Errors (PROC)
    PROC_EXTRACTION_FAILED = "PROC_EXTRACTION_FAILED"
    PROC_VALIDATION_FAILED = "PROC_VALIDATION_FAILED"
    PROC_TIMEOUT = "PROC_TIMEOUT"
    PROC_STORAGE_ERROR = "PROC_STORAGE_ERROR"

    # Storage Errors (STORAGE)
    STORAGE_FILE_NOT_FOUND = "STORAGE_FILE_NOT_FOUND"
    STORAGE_UPLOAD_FAILED = "STORAGE_UPLOAD_FAILED"
    STORAGE_DELETE_FAILED = "STORAGE_DELETE_FAILED"
    STORAGE_BUCKET_NOT_FOUND = "STORAGE_BUCKET_NOT_FOUND"

    # LLM Errors (LLM)
    LLM_API_ERROR = "LLM_API_ERROR"
    LLM_RATE_LIMITED = "LLM_RATE_LIMITED"
    LLM_QUOTA_EXCEEDED = "LLM_QUOTA_EXCEEDED"
    LLM_INVALID_RESPONSE = "LLM_INVALID_RESPONSE"
    LLM_CIRCUIT_OPEN = "LLM_CIRCUIT_OPEN"
    LLM_TIMEOUT = "LLM_TIMEOUT"
    LLM_MODEL_UNAVAILABLE = "LLM_MODEL_UNAVAILABLE"

    # Rate Limiting (RATE)
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    RATE_DAILY_QUOTA_EXCEEDED = "RATE_DAILY_QUOTA_EXCEEDED"

    # Internal Errors (INTERNAL)
    INTERNAL_UNEXPECTED_ERROR = "INTERNAL_UNEXPECTED_ERROR"
    INTERNAL_DATABASE_ERROR = "INTERNAL_DATABASE_ERROR"
    INTERNAL_CONFIGURATION_ERROR = "INTERNAL_CONFIGURATION_ERROR"
    INTERNAL_DEPENDENCY_MISSING = "INTERNAL_DEPENDENCY_MISSING"


ERROR_CODE_TO_STATUS = {
    ErrorCode.AUTH_MISSING_API_KEY: 401,
    ErrorCode.AUTH_INVALID_API_KEY: 401,
    ErrorCode.AUTH_EXPIRED_TOKEN: 401,
    ErrorCode.VAL_FILE_TOO_LARGE: 413,
    ErrorCode.VAL_UNSUPPORTED_FILE_TYPE: 415,
    ErrorCode.VAL_FILE_CORRUPTED: 422,
    ErrorCode.VAL_FILE_PASSWORD_PROTECTED: 422,
    ErrorCode.VAL_MISSING_REQUIRED_FIELD: 400,
    ErrorCode.VAL_INVALID_FIELD_FORMAT: 400,
    ErrorCode.VAL_INVALID_URI_SCHEME: 400,
    ErrorCode.PROC_EXTRACTION_FAILED: 500,
    ErrorCode.PROC_VALIDATION_FAILED: 422,
    ErrorCode.PROC_TIMEOUT: 504,
    ErrorCode.PROC_STORAGE_ERROR: 500,
    ErrorCode.STORAGE_FILE_NOT_FOUND: 404,
    ErrorCode.STORAGE_UPLOAD_FAILED: 500,
    ErrorCode.STORAGE_DELETE_FAILED: 500,
    ErrorCode.STORAGE_BUCKET_NOT_FOUND: 500,
    ErrorCode.LLM_API_ERROR: 502,
    ErrorCode.LLM_RATE_LIMITED: 429,
    ErrorCode.LLM_QUOTA_EXCEEDED: 402,
    ErrorCode.LLM_INVALID_RESPONSE: 502,
    ErrorCode.LLM_CIRCUIT_OPEN: 503,
    ErrorCode.LLM_TIMEOUT: 504,
    ErrorCode.LLM_MODEL_UNAVAILABLE: 503,
    ErrorCode.RATE_LIMIT_EXCEEDED: 429,
    ErrorCode.RATE_DAILY_QUOTA_EXCEEDED: 429,
    ErrorCode.INTERNAL_UNEXPECTED_ERROR: 500,
    ErrorCode.INTERNAL_DATABASE_ERROR: 500,
    ErrorCode.INTERNAL_CONFIGURATION_ERROR: 500,
    ErrorCode.INTERNAL_DEPENDENCY_MISSING: 500,
}


ERROR_CODE_MESSAGES = {
    ErrorCode.VAL_FILE_TOO_LARGE: "The uploaded file exceeds the maximum allowed size",
    ErrorCode.VAL_UNSUPPORTED_FILE_TYPE: "The file type is not supported",
    ErrorCode.VAL_FILE_CORRUPTED: "The file appears to be corrupted",
    ErrorCode.VAL_FILE_PASSWORD_PROTECTED: "Password-protected files are not supported",
    ErrorCode.STORAGE_FILE_NOT_FOUND: "The requested file was not found",
    ErrorCode.LLM_RATE_LIMITED: "The LLM service is rate-limited. Please try again later",
    ErrorCode.LLM_QUOTA_EXCEEDED: "Monthly LLM quota has been exceeded",
    ErrorCode.LLM_CIRCUIT_OPEN: "The LLM service is temporarily unavailable",
    ErrorCode.RATE_LIMIT_EXCEEDED: "Too many requests. Please slow down",
    ErrorCode.RATE_DAILY_QUOTA_EXCEEDED: "Daily request quota has been exceeded",
}


def get_status_for_error_code(error_code: ErrorCode) -> int:
    """Get HTTP status code for an error code."""
    return ERROR_CODE_TO_STATUS.get(error_code, 500)


def get_message_for_error_code(
    error_code: ErrorCode, custom_message: str | None = None
) -> str:
    """Get user-friendly message for an error code."""
    if custom_message:
        return custom_message
    return ERROR_CODE_MESSAGES.get(error_code, "An unexpected error occurred")
