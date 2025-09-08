"""Quiz tools for LangGraph agent integration.

This module provides comprehensive quiz functionality including question presentation,
answer grading with LLM-based evaluation, and performance analysis tools.
"""

import json
import re
from typing import Dict, List, Any, Optional, Union
from langchain_core.tools import tool
from langchain_core.language_models import BaseLanguageModel

from app.core.logging import logger
# Lazy import to avoid circular dependency
from app.services.question_service import question_service


@tool
async def grade_quiz_answer(
    question: str,
    correct_answer: str,
    user_answer: str,
    question_type: Optional[str] = None,
    language: str = "english",
    subject: Optional[str] = None,
    requires_calculations: bool = False,
    question_image_uri: Optional[str] = None,
    answer_image_uri: Optional[str] = None
) -> Dict[str, Any]:
    """Grade a quiz answer using LLM-based semantic evaluation.
    
    This tool provides comprehensive answer evaluation using multiple grading approaches:
    - Exact matching for simple answers
    - Semantic similarity for complex answers
    - Mathematical evaluation for calculations
    - Multi-language support
    - Image-enhanced context understanding
    
    Args:
        question: The original question text
        correct_answer: The correct/expected answer
        user_answer: The user's submitted answer
        question_type: Type of question (e.g., 'multiple_choice', 'short_answer')
        language: Language of the question and answer
        subject: Subject area for context
        requires_calculations: Whether the answer involves calculations
        question_image_uri: URI for question-associated image
        answer_image_uri: URI for answer-associated image
        
    Returns:
        Dictionary containing grading results with score, feedback, and explanation
    """
    try:
        logger.info(
            "quiz_answer_grading_started",
            question_type=question_type,
            language=language,
            subject=subject,
            requires_calculations=requires_calculations
        )
        
        # Quick exact match check first
        if _is_exact_match(correct_answer, user_answer):
            return {
                "is_correct": True,
                "score": 1.0,
                "feedback": "Correct! Perfect match.",
                "explanation": None,
                "method": "exact_match",
                "confidence": 1.0
            }
        
        # Use LLM for semantic evaluation (lazy import to avoid circular dependency)
        from app.core.llm.provider import get_llm
        llm = get_llm()
        
        # Build grading prompt based on question characteristics
        grading_prompt = _build_grading_prompt(
            question=question,
            correct_answer=correct_answer,
            user_answer=user_answer,
            question_type=question_type,
            language=language,
            subject=subject,
            requires_calculations=requires_calculations,
            question_image_uri=question_image_uri,
            answer_image_uri=answer_image_uri
        )
        
        # Get LLM evaluation
        llm_response = await llm.ainvoke(grading_prompt)
        
        # Parse LLM response
        grading_result = _parse_grading_response(llm_response.content)
        
        # Add metadata
        grading_result.update({
            "method": "llm_semantic",
            "question_type": question_type,
            "language": language,
            "subject": subject
        })
        
        logger.info(
            "quiz_answer_graded",
            is_correct=grading_result.get("is_correct"),
            score=grading_result.get("score"),
            method=grading_result.get("method"),
            confidence=grading_result.get("confidence", 0.0)
        )
        
        return grading_result
        
    except Exception as e:
        logger.error("quiz_answer_grading_failed", error=str(e), exc_info=True)
        
        # Fallback to simple matching
        is_correct = _is_exact_match(correct_answer, user_answer)
        return {
            "is_correct": is_correct,
            "score": 1.0 if is_correct else 0.0,
            "feedback": "Correct!" if is_correct else f"Incorrect. The correct answer is: {correct_answer}",
            "explanation": None,
            "method": "fallback_exact_match",
            "confidence": 1.0 if is_correct else 0.0,
            "error": str(e)
        }


@tool 
async def format_quiz_question(
    question_data: Dict[str, Any],
    include_metadata: bool = True,
    format_style: str = "conversational"
) -> str:
    """Format a quiz question for presentation to users.
    
    This tool takes raw question data and formats it for optimal presentation,
    including proper formatting for LaTeX, images, and metadata display.
    
    Args:
        question_data: Dictionary containing question data from database
        include_metadata: Whether to include metadata like difficulty, subject
        format_style: Formatting style ('conversational', 'formal', 'minimal')
        
    Returns:
        Formatted question string ready for presentation
    """
    try:
        question_text = question_data.get("question", "")
        
        if format_style == "conversational":
            formatted = _format_conversational_question(question_data, include_metadata)
        elif format_style == "formal":
            formatted = _format_formal_question(question_data, include_metadata)
        else:  # minimal
            formatted = _format_minimal_question(question_data, include_metadata)
        
        logger.debug(
            "quiz_question_formatted",
            question_id=question_data.get("id"),
            format_style=format_style,
            include_metadata=include_metadata
        )
        
        return formatted
        
    except Exception as e:
        logger.error("quiz_question_formatting_failed", error=str(e))
        return question_data.get("question", "Unable to format question")


@tool
async def calculate_quiz_summary(
    user_id: str,
    session_attempts: List[Dict[str, Any]],
    subject: Optional[str] = None,
    include_recommendations: bool = True
) -> Dict[str, Any]:
    """Calculate comprehensive quiz performance summary and recommendations.
    
    This tool analyzes quiz performance across a session or subject and provides
    detailed analytics, progress insights, and adaptive learning recommendations.
    
    Args:
        user_id: User ID for historical context
        session_attempts: List of quiz attempts in current session
        subject: Subject filter for context
        include_recommendations: Whether to include learning recommendations
        
    Returns:
        Dictionary containing performance summary and recommendations
    """
    try:
        logger.info(
            "quiz_summary_calculation_started",
            user_id=user_id,
            attempts_count=len(session_attempts),
            subject=subject
        )
        
        # Calculate session metrics
        session_metrics = _calculate_session_metrics(session_attempts)
        
        # Get historical performance for comparison
        historical_data = await question_service.get_user_quiz_history(
            user_id=user_id,
            subject=subject,
            limit=100,
            offset=0
        )
        
        # Compare with historical performance
        comparison = _compare_with_historical(session_metrics, historical_data["metrics"])
        
        # Generate adaptive recommendations
        recommendations = []
        if include_recommendations:
            recommendations = _generate_adaptive_recommendations(
                session_metrics=session_metrics,
                historical_metrics=historical_data["metrics"],
                subject=subject,
                recent_attempts=session_attempts
            )
        
        # Build comprehensive summary
        summary = {
            "session_performance": session_metrics,
            "historical_comparison": comparison,
            "recommendations": recommendations,
            "progress_indicators": _calculate_progress_indicators(
                session_metrics, historical_data["metrics"]
            ),
            "next_difficulty": _recommend_next_difficulty(
                session_metrics, historical_data["metrics"]
            ),
            "subject_focus": subject,
            "total_session_attempts": len(session_attempts),
            "analysis_timestamp": _get_current_timestamp()
        }
        
        logger.info(
            "quiz_summary_calculated",
            user_id=user_id,
            session_score=session_metrics.get("success_rate", 0.0),
            recommendations_count=len(recommendations)
        )
        
        return summary
        
    except Exception as e:
        logger.error("quiz_summary_calculation_failed", error=str(e), exc_info=True)
        return {
            "session_performance": {"error": str(e)},
            "historical_comparison": {},
            "recommendations": [],
            "progress_indicators": {},
            "next_difficulty": "easy",
            "analysis_timestamp": _get_current_timestamp()
        }


@tool
async def get_adaptive_quiz_question(
    user_id: str,
    subject: Optional[str] = None,
    form_level: Optional[int] = None,
    session_performance: Optional[Union[Dict[str, Any], str]] = None,
    exclude_attempted: bool = True,
    language: str = "english"
) -> Optional[Dict[str, Any]]:
    """Get next quiz question with adaptive difficulty selection.
    
    This tool intelligently selects the next question based on user performance,
    learning patterns, and adaptive difficulty algorithms.
    
    Args:
        user_id: User ID for performance tracking
        subject: Subject filter for question selection
        form_level: Form level filter (1-5 for Malaysian education system)
        session_performance: Current session performance metrics (dictionary with 'success_rate', 'recent_trend')
                            Note: If string is passed, it will be treated as None
        exclude_attempted: Whether to exclude previously attempted questions
        language: Question language preference
        
    Returns:
        Dictionary containing selected question data, or None if none available
    """
    try:
        # Determine adaptive difficulty based on performance
        if session_performance:
            # Handle case where LLM mistakenly passes a string instead of dict
            if isinstance(session_performance, str):
                try:
                    # Try to parse JSON string
                    import json
                    parsed_performance = json.loads(session_performance)
                    if isinstance(parsed_performance, dict):
                        logger.info(
                            "session_performance_json_parsed",
                            user_id=user_id,
                            original_string=session_performance,
                            message="Successfully parsed JSON string to dictionary"
                        )
                        # Use parsed dictionary
                        success_rate = parsed_performance.get("success_rate", 0.0)
                        recent_trend = parsed_performance.get("recent_trend", "stable")
                        
                        # Extract difficulty if provided directly
                        if "difficulty" in parsed_performance:
                            target_difficulty = parsed_performance["difficulty"]
                        else:
                            # Apply adaptive logic
                            if success_rate >= 0.85 and recent_trend in ["improving", "stable"]:
                                target_difficulty = "hard"
                            elif success_rate >= 0.6:
                                target_difficulty = "moderate"  
                            else:
                                target_difficulty = "easy"
                    else:
                        raise ValueError("Parsed JSON is not a dictionary")
                except (json.JSONDecodeError, ValueError, KeyError) as e:
                    logger.warning(
                        "session_performance_json_parse_failed",
                        user_id=user_id,
                        value=session_performance,
                        error=str(e),
                        message="Failed to parse JSON string, treating as None"
                    )
                    target_difficulty = None  # Let service decide
            else:
                # Normal dictionary processing
                success_rate = session_performance.get("success_rate", 0.0)
                recent_trend = session_performance.get("recent_trend", "stable")
                
                # Adaptive difficulty logic
                if success_rate >= 0.85 and recent_trend in ["improving", "stable"]:
                    target_difficulty = "hard"
                elif success_rate >= 0.6:
                    target_difficulty = "moderate"  
                else:
                    target_difficulty = "easy"
        else:
            target_difficulty = None  # Let service decide
        
        # Get question using adaptive selection
        question_data = await question_service.get_random_question(
            user_id=user_id,
            subject=subject,
            difficulty_level=target_difficulty,
            form_level=form_level,
            language=language,
            exclude_attempted=exclude_attempted,
            adaptive_difficulty=True
        )
        
        if question_data:
            # Add adaptive context - safely handle session_performance
            if session_performance and isinstance(session_performance, dict):
                success_rate = session_performance.get('success_rate', 0.0)
                reason = f"Based on {success_rate:.1%} success rate"
            else:
                reason = "Initial assessment"
            
            question_data["adaptive_info"] = {
                "selected_difficulty": target_difficulty,
                "reason": reason,
                "session_context": session_performance is not None and isinstance(session_performance, dict)
            }
        
        logger.info(
            "adaptive_question_selected",
            user_id=user_id,
            subject=subject,
            form_level=form_level,
            target_difficulty=target_difficulty,
            question_found=question_data is not None
        )
        
        return question_data
        
    except Exception as e:
        logger.error("adaptive_question_selection_failed", error=str(e), exc_info=True)
        return None


# Helper Functions
def _is_exact_match(correct: str, user_input: str) -> bool:
    """Check if answers match exactly (case-insensitive, whitespace-normalized)."""
    if not correct or not user_input:
        return False
    
    # Normalize whitespace and case
    correct_clean = re.sub(r'\s+', ' ', correct.strip().lower())
    user_clean = re.sub(r'\s+', ' ', user_input.strip().lower())
    
    return correct_clean == user_clean


def _build_grading_prompt(
    question: str,
    correct_answer: str,
    user_answer: str,
    question_type: Optional[str],
    language: str,
    subject: Optional[str],
    requires_calculations: bool,
    question_image_uri: Optional[str] = None,
    answer_image_uri: Optional[str] = None
) -> str:
    """Build contextual grading prompt for LLM evaluation."""
    
    prompt_parts = [
        "You are an expert educational assessor. Grade this student's answer carefully.",
        "",
        f"QUESTION: {question}",
        f"CORRECT ANSWER: {correct_answer}",
        f"STUDENT'S ANSWER: {user_answer}",
        ""
    ]
    
    # Add context
    if subject:
        prompt_parts.append(f"SUBJECT: {subject}")
    if question_type:
        prompt_parts.append(f"QUESTION TYPE: {question_type}")
    if language != "english":
        prompt_parts.append(f"LANGUAGE: {language}")
    if requires_calculations:
        prompt_parts.append("NOTE: This question involves calculations - check mathematical accuracy.")
    
    # Add image context if available
    if question_image_uri:
        prompt_parts.append(f"QUESTION IMAGE: {question_image_uri}")
        prompt_parts.append("NOTE: The question includes an image that provides visual context.")
    
    if answer_image_uri:
        prompt_parts.append(f"ANSWER IMAGE: {answer_image_uri}")
        prompt_parts.append("NOTE: The correct answer may reference visual elements in the answer image.")
    
    prompt_parts.extend([
        "",
        "GRADING INSTRUCTIONS:",
        "1. Evaluate semantic meaning, not just exact word matching",
        "2. Consider alternative correct phrasings",
        "3. For calculations, verify mathematical accuracy",
        "4. Be understanding of minor spelling/grammar errors if meaning is clear",
        "5. Consider visual context from images when evaluating answers",
        "6. Provide constructive feedback",
        "",
        "RESPONSE FORMAT (JSON):",
        "{",
        '  "is_correct": true/false,',
        '  "score": 0.0 to 1.0,',
        '  "feedback": "Brief explanation of why correct/incorrect",',
        '  "explanation": "Optional detailed explanation of correct answer",',
        '  "confidence": 0.0 to 1.0',
        "}"
    ])
    
    return "\n".join(prompt_parts)


def _parse_grading_response(response: str) -> Dict[str, Any]:
    """Parse LLM grading response into structured data."""
    try:
        # Try to extract JSON from response
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            json_str = json_match.group()
            return json.loads(json_str)
    except (json.JSONDecodeError, AttributeError):
        pass
    
    # Fallback parsing based on keywords
    response_lower = response.lower()
    
    is_correct = any(word in response_lower for word in ["correct", "right", "yes", "true"])
    score = 1.0 if is_correct else 0.0
    confidence = 0.7  # Medium confidence for fallback parsing
    
    return {
        "is_correct": is_correct,
        "score": score,
        "feedback": response[:200],  # First 200 chars as feedback
        "explanation": None,
        "confidence": confidence
    }


def _format_conversational_question(question_data: Dict[str, Any], include_metadata: bool) -> str:
    """Format question in conversational style."""
    parts = []
    
    if include_metadata:
        subject = question_data.get("subject", "")
        difficulty = question_data.get("difficulty_level", "")
        if subject or difficulty:
            parts.append(f"📚 {subject.title() if subject else 'General'} | {difficulty.title() if difficulty else 'Standard'} Level")
            parts.append("")
    
    # Main question
    question_text = question_data.get("question", "")
    parts.append(f"❓ {question_text}")
    
    # Question image if available
    if question_data.get("question_image_uri"):
        parts.append("")
        parts.append(f"🖼️ Question Image: {question_data['question_image_uri']}")
    
    # Knowledge snippet if available
    if question_data.get("knowledge_snippet"):
        parts.append("")
        parts.append(f"💡 Context: {question_data['knowledge_snippet']}")
    
    # Chapter info if available
    if question_data.get("chapter_name"):
        parts.append(f"📖 From: {question_data['chapter_name']}")
    
    # Answer image reference if available (for instructor reference)
    if question_data.get("answer_image_uri") and include_metadata:
        parts.append(f"📷 Answer includes image reference")
    
    return "\n".join(parts)


def _format_formal_question(question_data: Dict[str, Any], include_metadata: bool) -> str:
    """Format question in formal academic style."""
    parts = []
    
    if include_metadata:
        parts.append("QUESTION DETAILS")
        parts.append("-" * 50)
        if question_data.get("subject"):
            parts.append(f"Subject: {question_data['subject'].title()}")
        if question_data.get("difficulty_level"):
            parts.append(f"Difficulty: {question_data['difficulty_level'].title()}")
        if question_data.get("blooms_level"):
            parts.append(f"Bloom's Level: {question_data['blooms_level']}")
        if question_data.get("question_image_uri"):
            parts.append(f"Question Image: {question_data['question_image_uri']}")
        if question_data.get("answer_image_uri"):
            parts.append(f"Answer Image Reference: {question_data['answer_image_uri']}")
        parts.append("")
    
    parts.append("QUESTION:")
    parts.append(question_data.get("question", ""))
    
    # Add image reference in formal style
    if question_data.get("question_image_uri") and not include_metadata:
        parts.append("")
        parts.append(f"[Image: {question_data['question_image_uri']}]")
    
    return "\n".join(parts)


def _format_minimal_question(question_data: Dict[str, Any], include_metadata: bool) -> str:
    """Format question in minimal style."""
    parts = [question_data.get("question", "")]
    
    # Add image reference in minimal style
    if question_data.get("question_image_uri"):
        parts.append(f"[IMG: {question_data['question_image_uri']}]")
    
    if include_metadata and question_data.get("subject"):
        parts.append(f"({question_data['subject']})")
    
    return " ".join(parts)


def _calculate_session_metrics(attempts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculate performance metrics for a quiz session."""
    if not attempts:
        return {
            "total_attempts": 0,
            "correct_attempts": 0,
            "success_rate": 0.0,
            "average_time": None,
            "recent_trend": "no_data"
        }
    
    total = len(attempts)
    correct = sum(1 for attempt in attempts if attempt.get("is_correct", False))
    success_rate = correct / total
    
    # Calculate average time (excluding None values)
    times = [a.get("time_taken_seconds") for a in attempts if a.get("time_taken_seconds")]
    average_time = sum(times) / len(times) if times else None
    
    # Analyze recent trend (last 5 vs previous attempts)
    recent_trend = "stable"
    if total >= 5:
        recent_5 = attempts[-5:]
        recent_correct = sum(1 for a in recent_5 if a.get("is_correct", False))
        recent_rate = recent_correct / 5
        
        if total > 5:
            earlier_attempts = attempts[:-5]
            earlier_correct = sum(1 for a in earlier_attempts if a.get("is_correct", False))
            earlier_rate = earlier_correct / len(earlier_attempts)
            
            if recent_rate > earlier_rate + 0.2:
                recent_trend = "improving"
            elif recent_rate < earlier_rate - 0.2:
                recent_trend = "declining"
    
    return {
        "total_attempts": total,
        "correct_attempts": correct,
        "success_rate": success_rate,
        "average_time": round(average_time, 1) if average_time else None,
        "recent_trend": recent_trend,
        "difficulty_breakdown": _analyze_difficulty_performance(attempts)
    }


def _compare_with_historical(session_metrics: Dict[str, Any], historical_metrics: Dict[str, Any]) -> Dict[str, Any]:
    """Compare session performance with historical averages."""
    if not historical_metrics:
        return {"comparison": "no_historical_data"}
    
    session_rate = session_metrics.get("success_rate", 0.0)
    historical_rate = historical_metrics.get("success_rate", 0.0)
    
    difference = session_rate - historical_rate
    
    if abs(difference) < 0.1:
        comparison = "similar"
    elif difference > 0.1:
        comparison = "improved"
    else:
        comparison = "declined"
    
    return {
        "comparison": comparison,
        "session_rate": session_rate,
        "historical_rate": historical_rate,
        "difference": difference,
        "improvement_percentage": (difference / historical_rate * 100) if historical_rate > 0 else 0
    }


def _generate_adaptive_recommendations(
    session_metrics: Dict[str, Any],
    historical_metrics: Dict[str, Any],
    subject: Optional[str],
    recent_attempts: List[Dict[str, Any]]
) -> List[str]:
    """Generate personalized learning recommendations."""
    recommendations = []
    success_rate = session_metrics.get("success_rate", 0.0)
    
    # Performance-based recommendations
    if success_rate >= 0.85:
        recommendations.append("🎉 Excellent performance! Consider moving to harder questions to challenge yourself.")
        recommendations.append("💪 You're ready for advanced topics in this subject.")
    elif success_rate >= 0.6:
        recommendations.append("📈 Good progress! Keep practicing to build confidence.")
        recommendations.append("🎯 Focus on understanding concepts rather than just memorizing.")
    else:
        recommendations.append("📚 Consider reviewing fundamental concepts before attempting more questions.")
        recommendations.append("🤝 Don't hesitate to ask for help with topics you find challenging.")
    
    # Time-based recommendations
    avg_time = session_metrics.get("average_time")
    if avg_time and avg_time > 120:  # More than 2 minutes per question
        recommendations.append("⏰ Take your time to understand questions thoroughly - accuracy is more important than speed.")
    elif avg_time and avg_time < 30:  # Less than 30 seconds
        recommendations.append("🤔 Consider taking more time to carefully read and analyze questions.")
    
    # Trend-based recommendations
    trend = session_metrics.get("recent_trend")
    if trend == "improving":
        recommendations.append("📊 Your performance is trending upward - great job staying consistent!")
    elif trend == "declining":
        recommendations.append("🔄 Consider taking a short break or reviewing recent topics to refresh your understanding.")
    
    return recommendations


def _calculate_progress_indicators(session_metrics: Dict[str, Any], historical_metrics: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate various progress indicators."""
    return {
        "session_score": session_metrics.get("success_rate", 0.0),
        "improvement_trend": session_metrics.get("recent_trend", "stable"),
        "consistency_score": min(session_metrics.get("success_rate", 0.0) * 1.2, 1.0),  # Bonus for current performance
        "time_efficiency": _calculate_time_efficiency(session_metrics.get("average_time"))
    }


def _recommend_next_difficulty(session_metrics: Dict[str, Any], historical_metrics: Dict[str, Any]) -> str:
    """Recommend difficulty level for next questions."""
    success_rate = session_metrics.get("success_rate", 0.0)
    recent_trend = session_metrics.get("recent_trend", "stable")
    
    if success_rate >= 0.85 and recent_trend in ["improving", "stable"]:
        return "hard"
    elif success_rate >= 0.6 and recent_trend != "declining":
        return "moderate"
    else:
        return "easy"


def _analyze_difficulty_performance(attempts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze performance breakdown by difficulty level."""
    difficulty_stats = {"easy": {"total": 0, "correct": 0}, "moderate": {"total": 0, "correct": 0}, "hard": {"total": 0, "correct": 0}}
    
    for attempt in attempts:
        question = attempt.get("question", {})
        difficulty = question.get("difficulty_level", "moderate")
        
        if difficulty in difficulty_stats:
            difficulty_stats[difficulty]["total"] += 1
            if attempt.get("is_correct", False):
                difficulty_stats[difficulty]["correct"] += 1
    
    # Calculate success rates
    for difficulty in difficulty_stats:
        stats = difficulty_stats[difficulty]
        if stats["total"] > 0:
            stats["success_rate"] = stats["correct"] / stats["total"]
        else:
            stats["success_rate"] = 0.0
    
    return difficulty_stats


def _calculate_time_efficiency(average_time: Optional[float]) -> float:
    """Calculate time efficiency score (0.0 to 1.0)."""
    if not average_time:
        return 0.5  # Neutral score when no timing data
    
    # Optimal time is around 60-90 seconds per question
    if 60 <= average_time <= 90:
        return 1.0
    elif 30 <= average_time < 60 or 90 < average_time <= 120:
        return 0.8
    elif 15 <= average_time < 30 or 120 < average_time <= 180:
        return 0.6
    else:
        return 0.4


def _get_current_timestamp() -> str:
    """Get current timestamp in ISO format."""
    from datetime import datetime
    return datetime.utcnow().isoformat()


# Export tools for LangGraph integration
grade_quiz_answer_tool = grade_quiz_answer
format_quiz_question_tool = format_quiz_question
calculate_quiz_summary_tool = calculate_quiz_summary
get_adaptive_quiz_question_tool = get_adaptive_quiz_question