"""Standard API response classes and utilities for consistent response formatting."""

from typing import Generic, TypeVar, Optional, List, Dict, Any
from pydantic import BaseModel, Field

T = TypeVar('T')


class ApiResponse(BaseModel, Generic[T]):
    """Generic API response wrapper for consistent response formatting."""
    
    success: bool = Field(True, description="Whether the request was successful")
    data: Optional[T] = Field(None, description="Response data payload")
    error: Optional[str] = Field(None, description="Error message if request failed")
    message: Optional[str] = Field(None, description="Additional message for user")
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "data": {},
                "error": None,
                "message": "Operation successful"
            }
        }


class PaginatedResponse(BaseModel, Generic[T]):
    """Response for paginated list endpoints."""
    
    items: List[T] = Field(..., description="List of items")
    total: int = Field(..., description="Total number of items")
    page: int = Field(default=1, description="Current page number")
    page_size: int = Field(..., description="Items per page")
    pages: int = Field(..., description="Total number of pages")
    
    @property
    def has_next(self) -> bool:
        """Check if there's a next page."""
        return self.page < self.pages
    
    @property
    def has_previous(self) -> bool:
        """Check if there's a previous page."""
        return self.page > 1


class ErrorResponse(BaseModel):
    """Standard error response format."""
    
    success: bool = Field(False, description="Always False for errors")
    error: str = Field(..., description="Error code/type")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": False,
                "error": "validation_error",
                "message": "Invalid request parameters",
                "details": {"field": "email", "reason": "Invalid email format"}
            }
        }


def success_response(data: Any = None, message: str = "Success") -> Dict[str, Any]:
    """Create a successful API response."""
    return {
        "success": True,
        "data": data,
        "message": message,
        "error": None
    }


def error_response(error: str, message: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Create an error API response."""
    return {
        "success": False,
        "error": error,
        "message": message,
        "details": details
    }
