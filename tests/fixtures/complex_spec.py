"""
Complex spec fixture for integration testing.

This represents a realistic, multi-faceted feature spec that exercises
all aspects of the Docker isolation strategy and workflow.
"""

from pathlib import Path
import json
from typing import Dict, Any


COMPLEX_SPEC_NAME = "001-user-dashboard-api"

COMPLEX_SPEC_CONTENT = """# User Dashboard API

## Overview
Implement a RESTful API for user dashboard with real-time notifications, data visualization endpoints, and comprehensive error handling.

## Requirements

### Core Functionality
1. **User Profile Management**
   - GET /api/users/:id - Retrieve user profile
   - PUT /api/users/:id - Update user profile
   - DELETE /api/users/:id - Soft delete user
   - Input validation with comprehensive error messages
   - Rate limiting (100 requests per minute)

2. **Dashboard Analytics**
   - GET /api/dashboard/stats - User statistics
   - GET /api/dashboard/activity - Recent activity timeline
   - GET /api/dashboard/metrics - Performance metrics
   - Support date range filtering
   - Implement caching (5-minute TTL)

3. **Real-time Notifications**
   - WebSocket endpoint /ws/notifications
   - Push notifications for user actions
   - Connection health monitoring
   - Automatic reconnection logic

4. **Data Export**
   - POST /api/export/csv - Export data as CSV
   - POST /api/export/json - Export data as JSON
   - Background job processing
   - Email notification on completion

### Technical Requirements
- Framework: FastAPI with async/await
- Database: PostgreSQL with SQLAlchemy ORM
- Caching: Redis for session and data caching
- Testing: 90%+ code coverage with pytest
- Documentation: OpenAPI/Swagger auto-generated
- Security: JWT authentication, CORS configuration
- Logging: Structured JSON logging with correlation IDs

### Quality Standards
- All endpoints must handle errors gracefully
- Database queries must be optimized (no N+1 queries)
- API response time < 200ms for non-export endpoints
- WebSocket connections must auto-recover on disconnect
- All endpoints must have comprehensive tests

### Acceptance Criteria
- [ ] All API endpoints implemented and documented
- [ ] Unit tests pass with 90%+ coverage
- [ ] Integration tests verify endpoint behavior
- [ ] WebSocket connection handling is robust
- [ ] Error responses are consistent and helpful
- [ ] Performance benchmarks are met
- [ ] Security best practices are followed
- [ ] Code passes linting and type checking
"""

COMPLEX_IMPLEMENTATION_PLAN = {
    "spec_name": COMPLEX_SPEC_NAME,
    "feature": "User Dashboard API with real-time notifications",
    "estimated_complexity": "complex",
    "phases": [
        {
            "name": "Foundation",
            "order": 1,
            "subtasks": [
                {
                    "id": "setup-001",
                    "description": "Set up FastAPI project structure with async support",
                    "dependencies": [],
                    "files": ["api/main.py", "api/__init__.py", "api/config.py"],
                    "estimated_lines": 150,
                    "status": "completed"
                },
                {
                    "id": "setup-002",
                    "description": "Configure database models with SQLAlchemy",
                    "dependencies": ["setup-001"],
                    "files": ["api/models/user.py", "api/models/activity.py", "api/database.py"],
                    "estimated_lines": 200,
                    "status": "completed"
                },
                {
                    "id": "setup-003",
                    "description": "Set up Redis caching layer with connection pooling",
                    "dependencies": ["setup-001"],
                    "files": ["api/cache.py", "api/utils/redis_client.py"],
                    "estimated_lines": 100,
                    "status": "completed"
                }
            ]
        },
        {
            "name": "Core Endpoints",
            "order": 2,
            "subtasks": [
                {
                    "id": "api-001",
                    "description": "Implement user profile GET endpoint with caching",
                    "dependencies": ["setup-002", "setup-003"],
                    "files": ["api/routers/users.py", "api/services/user_service.py"],
                    "estimated_lines": 120,
                    "status": "in_progress"
                },
                {
                    "id": "api-002",
                    "description": "Implement user profile PUT endpoint with validation",
                    "dependencies": ["api-001"],
                    "files": ["api/routers/users.py", "api/schemas/user.py"],
                    "estimated_lines": 150,
                    "status": "pending"
                },
                {
                    "id": "api-003",
                    "description": "Implement soft delete endpoint with cascade handling",
                    "dependencies": ["api-001"],
                    "files": ["api/routers/users.py", "api/services/user_service.py"],
                    "estimated_lines": 80,
                    "status": "pending"
                }
            ]
        },
        {
            "name": "Dashboard Analytics",
            "order": 3,
            "subtasks": [
                {
                    "id": "dash-001",
                    "description": "Implement dashboard stats endpoint with aggregations",
                    "dependencies": ["setup-002", "setup-003"],
                    "files": ["api/routers/dashboard.py", "api/services/analytics_service.py"],
                    "estimated_lines": 200,
                    "status": "pending"
                },
                {
                    "id": "dash-002",
                    "description": "Implement activity timeline with pagination",
                    "dependencies": ["dash-001"],
                    "files": ["api/routers/dashboard.py", "api/services/activity_service.py"],
                    "estimated_lines": 180,
                    "status": "pending"
                },
                {
                    "id": "dash-003",
                    "description": "Implement metrics endpoint with time-series data",
                    "dependencies": ["dash-001"],
                    "files": ["api/routers/dashboard.py", "api/services/metrics_service.py"],
                    "estimated_lines": 150,
                    "status": "pending"
                }
            ]
        },
        {
            "name": "Real-time Features",
            "order": 4,
            "subtasks": [
                {
                    "id": "ws-001",
                    "description": "Implement WebSocket notification endpoint",
                    "dependencies": ["setup-001"],
                    "files": ["api/websocket.py", "api/services/notification_service.py"],
                    "estimated_lines": 250,
                    "status": "pending"
                },
                {
                    "id": "ws-002",
                    "description": "Add connection health monitoring and auto-recovery",
                    "dependencies": ["ws-001"],
                    "files": ["api/websocket.py", "api/utils/ws_manager.py"],
                    "estimated_lines": 120,
                    "status": "pending"
                }
            ]
        },
        {
            "name": "Data Export",
            "order": 5,
            "subtasks": [
                {
                    "id": "export-001",
                    "description": "Implement CSV export with background processing",
                    "dependencies": ["setup-002"],
                    "files": ["api/routers/export.py", "api/services/export_service.py", "api/tasks/export_tasks.py"],
                    "estimated_lines": 180,
                    "status": "pending"
                },
                {
                    "id": "export-002",
                    "description": "Implement JSON export with streaming",
                    "dependencies": ["export-001"],
                    "files": ["api/routers/export.py", "api/services/export_service.py"],
                    "estimated_lines": 100,
                    "status": "pending"
                }
            ]
        },
        {
            "name": "Testing & Quality",
            "order": 6,
            "subtasks": [
                {
                    "id": "test-001",
                    "description": "Write unit tests for all service functions",
                    "dependencies": ["api-001", "api-002", "api-003"],
                    "files": ["tests/test_user_service.py", "tests/test_analytics_service.py"],
                    "estimated_lines": 400,
                    "status": "pending"
                },
                {
                    "id": "test-002",
                    "description": "Write integration tests for API endpoints",
                    "dependencies": ["test-001"],
                    "files": ["tests/test_api_endpoints.py", "tests/conftest.py"],
                    "estimated_lines": 500,
                    "status": "pending"
                },
                {
                    "id": "test-003",
                    "description": "Write WebSocket connection tests",
                    "dependencies": ["ws-002"],
                    "files": ["tests/test_websocket.py"],
                    "estimated_lines": 200,
                    "status": "pending"
                }
            ]
        }
    ]
}


def get_complex_spec() -> Dict[str, Any]:
    """Get the complex spec fixture as a dictionary."""
    return {
        "spec_name": COMPLEX_SPEC_NAME,
        "spec_content": COMPLEX_SPEC_CONTENT,
        "implementation_plan": COMPLEX_IMPLEMENTATION_PLAN,
    }


def create_complex_spec_files(base_dir: Path) -> Path:
    """
    Create the complex spec files in a test directory.

    Args:
        base_dir: Base directory where to create .auto-claude/specs/

    Returns:
        Path to the created spec directory
    """
    spec_dir = base_dir / ".auto-claude" / "specs" / COMPLEX_SPEC_NAME
    spec_dir.mkdir(parents=True, exist_ok=True)

    # Write spec.md
    spec_file = spec_dir / "spec.md"
    spec_file.write_text(COMPLEX_SPEC_CONTENT, encoding="utf-8")

    # Write implementation_plan.json
    plan_file = spec_dir / "implementation_plan.json"
    plan_file.write_text(json.dumps(COMPLEX_IMPLEMENTATION_PLAN, indent=2), encoding="utf-8")

    # Write requirements.json (extracted from spec)
    requirements = {
        "user_request": "I need a comprehensive user dashboard API with real-time features",
        "clarifications": [
            "Framework preference: FastAPI for async support",
            "Database: PostgreSQL with SQLAlchemy",
            "Real-time: WebSocket for notifications",
            "Testing: 90%+ coverage requirement"
        ],
        "key_requirements": [
            "User profile CRUD operations",
            "Dashboard analytics endpoints",
            "Real-time WebSocket notifications",
            "Data export functionality (CSV/JSON)",
            "Comprehensive error handling",
            "High test coverage"
        ]
    }
    req_file = spec_dir / "requirements.json"
    req_file.write_text(json.dumps(requirements, indent=2), encoding="utf-8")

    # Write context.json (codebase context)
    context = {
        "similar_patterns": [
            "Found existing FastAPI patterns in api/legacy_users.py",
            "SQLAlchemy models follow established patterns in api/models/",
            "WebSocket handling exists in api/legacy_notifications.py"
        ],
        "dependencies": [
            "fastapi",
            "sqlalchemy",
            "redis",
            "pytest",
            "pytest-asyncio"
        ],
        "project_structure": {
            "api/": "Main API directory",
            "api/routers/": "API route handlers",
            "api/services/": "Business logic layer",
            "api/models/": "Database models",
            "tests/": "Test suite"
        }
    }
    ctx_file = spec_dir / "context.json"
    ctx_file.write_text(json.dumps(context, indent=2), encoding="utf-8")

    return spec_dir


def get_expected_workflow_states() -> list[str]:
    """Get the expected workflow states for the complex spec."""
    return [
        "planning",
        "coding",
        "ai_review",
        "ai_testing",
        "ready_for_review"
    ]


def get_expected_phases() -> list[str]:
    """Get the expected phase names."""
    return ["planning", "coding", "validation", "testing"]
