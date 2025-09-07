"""Subject management API endpoints."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from app.core.limiter import limiter
from app.core.logging import logger
from app.api.v1.auth import get_current_session
from app.models.session import Session
from app.services.subject_service import subject_service
from app.schemas.subject import (
    SubjectResponse,
    SubjectListResponse,
    SubjectSelectionRequest,
    SubjectSelectionResponse,
    UserSubjectResponse,
    SubjectSearchResponse,
)

router = APIRouter()


@router.get("/", response_model=SubjectListResponse)
@limiter.limit("30/minute")
async def get_subjects(
    request: Request,
    form_level: Optional[int] = Query(None, ge=1, le=5, description="Filter by form level (1-5)"),
    language: Optional[str] = Query(None, description="Filter by language preference"),
    include_message: bool = Query(True, description="Include formatted selection message"),
):
    """Get list of available subjects with optional filtering.

    Args:
        request: FastAPI request object for rate limiting
        form_level: Optional form level filter (1-5)
        language: Optional language preference filter
        include_message: Whether to include formatted selection message

    Returns:
        SubjectListResponse: List of subjects with metadata
    """
    try:
        subjects = await subject_service.get_available_subjects(form_level=form_level, language=language)

        subject_responses = [
            SubjectResponse(
                id=subject["id"],
                name=subject["name"],
                description=subject.get("description"),
                book_code=subject.get("book_code"),
                alt_names=subject.get("alt_names", []),
            )
            for subject in subjects
        ]

        formatted_message = None
        if include_message:
            context = ""
            if form_level:
                context += f"Showing subjects for Form {form_level}. "
            if language:
                context += f"Language preference: {language}. "

            formatted_message = subject_service.format_subject_selection_message(subjects, context.strip())

        logger.info("subjects_retrieved", count=len(subjects), form_level=form_level, language=language)

        return SubjectListResponse(
            subjects=subject_responses, total=len(subject_responses), formatted_message=formatted_message
        )

    except Exception as e:
        logger.error("error_getting_subjects", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to retrieve subjects")


@router.get("/search", response_model=SubjectSearchResponse)
@limiter.limit("20/minute")
async def search_subjects(
    request: Request,
    query: str = Query(..., min_length=1, description="Search query"),
    include_alternatives: bool = Query(True, description="Include alternative names in search"),
    exact_match: bool = Query(False, description="Require exact match"),
):
    """Search subjects by name or alternative names.

    Args:
        request: FastAPI request object for rate limiting
        query: Search query string
        include_alternatives: Whether to include alternative names
        exact_match: Whether to require exact matching

    Returns:
        SubjectSearchResponse: Search results
    """
    try:
        if exact_match:
            # For exact match, find single subject
            subject = await subject_service.find_subject_by_name_or_number(query)
            results = [subject] if subject else []
        else:
            # For non-exact match, get all subjects and filter
            all_subjects = await subject_service.get_available_subjects()
            query_lower = query.lower()
            results = []

            for subject in all_subjects:
                # Check name
                if query_lower in subject["name"].lower():
                    results.append(subject)
                    continue

                # Check description
                if subject.get("description") and query_lower in subject["description"].lower():
                    results.append(subject)
                    continue

                # Check alternative names if enabled
                if include_alternatives and "alt_names" in subject:
                    for alt_name in subject["alt_names"]:
                        if query_lower in alt_name.lower():
                            results.append(subject)
                            break

        subject_responses = [
            SubjectResponse(
                id=subject["id"],
                name=subject["name"],
                description=subject.get("description"),
                book_code=subject.get("book_code"),
                alt_names=subject.get("alt_names", []),
            )
            for subject in results
        ]

        # Generate search suggestions (simple implementation)
        suggestions = []
        if len(results) == 0 and len(query) > 2:
            all_subjects = await subject_service.get_available_subjects()
            for subject in all_subjects:
                subject_name = subject["name"].lower()
                # Simple fuzzy matching - check if any word in subject name starts with query
                for word in subject_name.split():
                    if word.startswith(query_lower):
                        suggestions.append(subject["name"])
                        break

            suggestions = suggestions[:3]  # Limit to 3 suggestions

        logger.info("subjects_searched", query=query, results_count=len(results))

        return SubjectSearchResponse(
            results=subject_responses, query=query, total_results=len(results), suggestions=suggestions
        )

    except Exception as e:
        logger.error("error_searching_subjects", error=str(e), query=query)
        raise HTTPException(status_code=500, detail="Failed to search subjects")


@router.get("/{subject_id}", response_model=SubjectResponse)
@limiter.limit("30/minute")
async def get_subject(request: Request, subject_id: str):
    """Get detailed information about a specific subject.

    Args:
        request: FastAPI request object for rate limiting
        subject_id: Subject ID

    Returns:
        SubjectResponse: Subject details
    """
    try:
        # Get all subjects and find the specific one
        all_subjects = await subject_service.get_available_subjects()
        subject = next((s for s in all_subjects if s["id"] == subject_id), None)

        if not subject:
            raise HTTPException(status_code=404, detail="Subject not found")

        logger.info("subject_retrieved", subject_id=subject_id, subject_name=subject["name"])

        return SubjectResponse(
            id=subject["id"],
            name=subject["name"],
            description=subject.get("description"),
            book_code=subject.get("book_code"),
            alt_names=subject.get("alt_names", []),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("error_getting_subject", error=str(e), subject_id=subject_id)
        raise HTTPException(status_code=500, detail="Failed to retrieve subject")


@router.post("/select", response_model=SubjectSelectionResponse)
@limiter.limit("10/minute")
async def select_subject(
    request: Request, selection_request: SubjectSelectionRequest, session: Session = Depends(get_current_session)
):
    """Set user's focus subject.

    Args:
        request: FastAPI request object for rate limiting
        selection_request: Subject selection request
        session: Current user session

    Returns:
        SubjectSelectionResponse: Selection result
    """
    try:
        user_id = session.user_id
        subject_input = selection_request.subject_input.strip()

        # Find subject by name or number
        found_subject = await subject_service.find_subject_by_name_or_number(subject_input)

        if not found_subject:
            logger.warning("subject_not_found_for_selection", input=subject_input, user_id=user_id)
            return SubjectSelectionResponse(
                success=False,
                message=f"Subject '{subject_input}' not found. Please try a different name or use the subject number.",
                selected_subject=None,
            )

        # Set as user's focus subject
        success = await subject_service.set_user_focus_subject(user_id, found_subject["id"])

        if not success:
            logger.error("failed_to_set_focus_subject", user_id=user_id, subject_id=found_subject["id"])
            raise HTTPException(status_code=500, detail="Failed to set focus subject")

        selected_subject = SubjectResponse(
            id=found_subject["id"],
            name=found_subject["name"],
            description=found_subject.get("description"),
            book_code=found_subject.get("book_code"),
            alt_names=found_subject.get("alt_names", []),
        )

        logger.info("subject_selected", user_id=user_id, subject_name=found_subject["name"], input=subject_input)

        return SubjectSelectionResponse(
            success=True,
            message=f"✅ Great! I've set **{found_subject['name']}** as your focus subject. I'll now provide content and questions specifically for this subject.",
            selected_subject=selected_subject,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("error_selecting_subject", error=str(e), user_id=session.user_id)
        raise HTTPException(status_code=500, detail="Failed to select subject")


@router.get("/user/current", response_model=UserSubjectResponse)
@limiter.limit("30/minute")
async def get_user_current_subject(request: Request, session: Session = Depends(get_current_session)):
    """Get user's current focus subject and subject preferences.

    Args:
        request: FastAPI request object for rate limiting
        session: Current user session

    Returns:
        UserSubjectResponse: User's subject information
    """
    try:
        user_id = session.user_id

        # Get current subject
        current_subject_data = await subject_service.get_user_current_subject(user_id)
        current_subject = None
        if current_subject_data:
            current_subject = SubjectResponse(
                id=current_subject_data["id"],
                name=current_subject_data["name"],
                description=current_subject_data.get("description"),
                book_code=current_subject_data.get("book_code"),
                alt_names=current_subject_data.get("alt_names", []),
            )

        # Get user details from session
        from app.services.database import database_service

        user = await database_service.get_user(user_id)

        current_subjects = user.current_subjects if user and user.current_subjects else []
        focus_subjects = user.focus_subjects if user and user.focus_subjects else []
        form_level = user.form_level if user else None
        language = user.language if user else "English"

        logger.info("user_current_subject_retrieved", user_id=user_id, has_current=current_subject is not None)

        return UserSubjectResponse(
            current_subject=current_subject,
            current_subjects=current_subjects,
            focus_subjects=focus_subjects,
            form_level=form_level,
            language=language,
        )

    except Exception as e:
        logger.error("error_getting_user_current_subject", error=str(e), user_id=session.user_id)
        raise HTTPException(status_code=500, detail="Failed to retrieve user's current subject")
