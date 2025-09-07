"""Question Service for quiz system functionality.

This service provides comprehensive question filtering, selection, and management
capabilities for the quiz system. It includes adaptive difficulty progression,
random question selection with criteria, and various question type handling.
"""

import random
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from sqlmodel import Session, select, func, and_, or_
from sqlalchemy.orm import selectinload

from app.core.logging import logger
from app.models.questions_bank import QuestionsBank
from app.models.quiz_attempt import QuizAttempt
from app.models.user import User
from app.services.database import database_service


class QuestionService:
    """Service class for managing quiz questions and user progress."""
    
    def __init__(self):
        """Initialize the question service."""
        pass
    
    async def get_random_question(
        self,
        user_id: str,
        subject: Optional[str] = None,
        difficulty_level: Optional[str] = None,
        form_level: Optional[int] = None,
        question_type: Optional[str] = None,
        language: str = "english",
        exclude_attempted: bool = True,
        adaptive_difficulty: bool = True
    ) -> Optional[Dict[str, Any]]:
        """Get a random question based on criteria and user progress.
        
        Args:
            user_id: User ID for tracking attempts and adaptive difficulty
            subject: Subject filter (e.g., 'math', 'science')
            difficulty_level: Difficulty filter ('easy', 'moderate', 'hard')
            form_level: Form level filter (1-5)
            question_type: Question type filter
            language: Language filter ('english', 'malay', 'chinese')
            exclude_attempted: Whether to exclude previously attempted questions
            adaptive_difficulty: Whether to use adaptive difficulty based on performance
            
        Returns:
            Dictionary containing question data and metadata, or None if no questions found
        """
        try:
            with database_service.get_session_maker() as session:
                # Build base query with case-insensitive matching
                query = select(QuestionsBank).where(
                    and_(
                        or_(
                            QuestionsBank.type.ilike("quiz"),   # Quiz questions
                            QuestionsBank.type.ilike("exam")    # Exam questions  
                        ),
                        QuestionsBank.language.ilike(language)  # Case-insensitive language matching
                    )
                )
                
                # Apply filters
                if subject:
                    query = query.where(QuestionsBank.subject.ilike(f"%{subject}%"))
                
                # TODO: Temporarily commented out - most questions have forms: null
                # if form_level:
                #     query = query.where(QuestionsBank.forms.any(form_level))
                
                if question_type:
                    query = query.where(QuestionsBank.question_type == question_type)
                
                # Apply adaptive difficulty or static difficulty
                target_difficulty = difficulty_level
                if adaptive_difficulty and not difficulty_level:
                    target_difficulty = await self._get_adaptive_difficulty(session, user_id, subject)
                
                if target_difficulty:
                    query = query.where(QuestionsBank.difficulty_level == target_difficulty)
                
                # Exclude previously attempted questions if requested
                if exclude_attempted:
                    attempted_questions = select(QuizAttempt.question_id).where(
                        QuizAttempt.user_id == user_id
                    )
                    query = query.where(~QuestionsBank.id.in_(attempted_questions))
                
                # Execute query and get results
                result = session.exec(query)
                questions = result.all()
                
                if not questions:
                    logger.warning(
                        "no_questions_found",
                        user_id=user_id,
                        subject=subject,
                        difficulty=target_difficulty,
                        form_level=form_level
                    )
                    return None
                
                # Select random question
                selected_question = random.choice(questions)
                
                # Format response
                question_data = {
                    "id": selected_question.id,
                    "question": selected_question.question,
                    "subject": selected_question.subject,
                    "difficulty_level": selected_question.difficulty_level,
                    "forms": selected_question.forms,
                    "language": selected_question.language,
                    "question_type": selected_question.question_type,
                    "blooms_level": selected_question.blooms_level,
                    "blooms_descriptor": selected_question.blooms_descriptor,
                    "learning_standards": selected_question.learning_standards,
                    "chapter_number": selected_question.chapter_number,
                    "chapter_name": selected_question.chapter_name,
                    "source": selected_question.source,
                    "requires_latex": selected_question.requires_latex,
                    "contains_calculations": selected_question.contains_calculations,
                    "knowledge_snippet": selected_question.knowledge_snippet,
                    "knowledge_snippet_type": selected_question.knowledge_snippet_type,
                    "question_image_uri": selected_question.question_image_uri,
                    "answer_image_uri": selected_question.answer_image_uri,
                    "created_at": selected_question.created_at
                }
                
                logger.info(
                    "random_question_selected",
                    user_id=user_id,
                    question_id=selected_question.id,
                    subject=selected_question.subject,
                    difficulty=selected_question.difficulty_level
                )
                
                return question_data
                
        except Exception as e:
            logger.error(
                "random_question_selection_failed",
                user_id=user_id,
                error=str(e),
                exc_info=True
            )
            return None
    
    async def get_question_by_id(self, question_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific question by ID.
        
        Args:
            question_id: Question ID to retrieve
            
        Returns:
            Dictionary containing question data, or None if not found
        """
        try:
            with database_service.get_session_maker() as session:
                query = select(QuestionsBank).where(QuestionsBank.id == question_id)
                result = session.exec(query)
                question = result.first()
                
                if not question:
                    return None
                
                return {
                    "id": question.id,
                    "question": question.question,
                    "answer": question.answer,
                    "subject": question.subject,
                    "difficulty_level": question.difficulty_level,
                    "forms": question.forms,
                    "language": question.language,
                    "question_type": question.question_type,
                    "blooms_level": question.blooms_level,
                    "blooms_descriptor": question.blooms_descriptor,
                    "learning_standards": question.learning_standards,
                    "chapter_number": question.chapter_number,
                    "chapter_name": question.chapter_name,
                    "source": question.source,
                    "requires_latex": question.requires_latex,
                    "contains_calculations": question.contains_calculations,
                    "knowledge_snippet": question.knowledge_snippet,
                    "knowledge_snippet_type": question.knowledge_snippet_type,
                    "question_image_uri": question.question_image_uri,
                    "answer_image_uri": question.answer_image_uri,
                    "created_at": question.created_at
                }
                
        except Exception as e:
            logger.error("question_retrieval_failed", question_id=question_id, error=str(e))
            return None
    
    async def get_user_quiz_history(
        self,
        user_id: str,
        subject: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Dict[str, Any]:
        """Get user's quiz attempt history with performance metrics.
        
        Args:
            user_id: User ID to get history for
            subject: Optional subject filter
            limit: Maximum number of attempts to return
            offset: Number of attempts to skip
            
        Returns:
            Dictionary containing attempts and performance metrics
        """
        try:
            with database_service.get_session_maker() as session:
                # Build base query for attempts
                query = (
                    select(QuizAttempt)
                    .options(selectinload(QuizAttempt.question))
                    .where(QuizAttempt.user_id == user_id)
                    .order_by(QuizAttempt.created_at.desc())
                    .offset(offset)
                    .limit(limit)
                )
                
                # Apply subject filter if provided
                if subject:
                    query = query.join(QuestionsBank).where(
                        QuestionsBank.subject.ilike(f"%{subject}%")
                    )
                
                result = session.exec(query)
                attempts = result.all()
                
                # Format attempts
                formatted_attempts = []
                for attempt in attempts:
                    formatted_attempts.append({
                        "id": attempt.id,
                        "question_id": attempt.question_id,
                        "user_answer": attempt.user_answer,
                        "is_correct": attempt.is_correct,
                        "time_taken_seconds": attempt.time_taken_seconds,
                        "created_at": attempt.created_at,
                        "question": {
                            "subject": attempt.question.subject,
                            "difficulty_level": attempt.question.difficulty_level,
                            "question_type": attempt.question.question_type,
                            "chapter_name": attempt.question.chapter_name
                        } if attempt.question else None
                    })
                
                # Calculate performance metrics
                metrics = await self._calculate_performance_metrics(session, user_id, subject)
                
                return {
                    "attempts": formatted_attempts,
                    "metrics": metrics,
                    "total_attempts": len(formatted_attempts),
                    "subject_filter": subject
                }
                
        except Exception as e:
            logger.error(
                "quiz_history_retrieval_failed",
                user_id=user_id,
                error=str(e),
                exc_info=True
            )
            return {"attempts": [], "metrics": {}, "total_attempts": 0, "subject_filter": subject}
    
    async def record_quiz_attempt(
        self,
        user_id: str,
        question_id: str,
        session_id: str,
        user_answer: str,
        is_correct: bool,
        time_taken_seconds: Optional[int] = None
    ) -> bool:
        """Record a quiz attempt in the database.
        
        Args:
            user_id: User ID making the attempt
            question_id: Question ID being attempted
            session_id: Chat session ID
            user_answer: User's answer
            is_correct: Whether the answer was correct
            time_taken_seconds: Time taken to answer (optional)
            
        Returns:
            True if recorded successfully, False otherwise
        """
        try:
            with database_service.get_session_maker() as session:
                attempt = QuizAttempt(
                    user_id=user_id,
                    question_id=question_id,
                    session_id=session_id,
                    user_answer=user_answer,
                    is_correct=is_correct,
                    time_taken_seconds=time_taken_seconds
                )
                
                session.add(attempt)
                session.commit()
                
                logger.info(
                    "quiz_attempt_recorded",
                    user_id=user_id,
                    question_id=question_id,
                    is_correct=is_correct,
                    attempt_id=attempt.id
                )
                
                return True
                
        except Exception as e:
            logger.error(
                "quiz_attempt_recording_failed",
                user_id=user_id,
                question_id=question_id,
                error=str(e),
                exc_info=True
            )
            return False
    
    async def _get_adaptive_difficulty(
        self, session: Session, user_id: str, subject: Optional[str] = None
    ) -> str:
        """Calculate adaptive difficulty based on user performance.
        
        Args:
            session: Database session
            user_id: User ID to analyze
            subject: Optional subject filter for performance analysis
            
        Returns:
            Recommended difficulty level ('easy', 'moderate', 'hard')
        """
        try:
            # Get recent attempts (last 10 or within 7 days)
            recent_cutoff = datetime.utcnow() - timedelta(days=7)
            
            query = (
                select(QuizAttempt)
                .join(QuestionsBank)
                .where(
                    and_(
                        QuizAttempt.user_id == user_id,
                        QuizAttempt.created_at >= recent_cutoff
                    )
                )
                .order_by(QuizAttempt.created_at.desc())
                .limit(10)
            )
            
            if subject:
                query = query.where(QuestionsBank.subject.ilike(f"%{subject}%"))
            
            result = session.exec(query)
            recent_attempts = result.all()
            
            if not recent_attempts:
                # No recent history, start with easy
                return "easy"
            
            # Calculate success rate
            correct_count = sum(1 for attempt in recent_attempts if attempt.is_correct)
            success_rate = correct_count / len(recent_attempts)
            
            # Determine difficulty based on performance
            if success_rate >= 0.8:
                return "hard"
            elif success_rate >= 0.6:
                return "moderate"
            else:
                return "easy"
                
        except Exception as e:
            logger.warning("adaptive_difficulty_calculation_failed", error=str(e))
            return "easy"  # Default fallback
    
    async def _calculate_performance_metrics(
        self, session: Session, user_id: str, subject: Optional[str] = None
    ) -> Dict[str, Any]:
        """Calculate comprehensive performance metrics for a user.
        
        Args:
            session: Database session
            user_id: User ID to analyze
            subject: Optional subject filter
            
        Returns:
            Dictionary containing various performance metrics
        """
        try:
            # Base query for all attempts
            base_query = select(QuizAttempt).where(QuizAttempt.user_id == user_id)
            
            if subject:
                base_query = base_query.join(QuestionsBank).where(
                    QuestionsBank.subject.ilike(f"%{subject}%")
                )
            
            # Total attempts
            total_result = session.exec(base_query)
            all_attempts = total_result.all()
            total_attempts = len(all_attempts)
            
            if total_attempts == 0:
                return {
                    "total_attempts": 0,
                    "correct_attempts": 0,
                    "success_rate": 0.0,
                    "average_time": None,
                    "difficulty_breakdown": {},
                    "recent_performance": {},
                    "streak": {"current": 0, "longest": 0}
                }
            
            # Basic metrics
            correct_attempts = sum(1 for attempt in all_attempts if attempt.is_correct)
            success_rate = correct_attempts / total_attempts
            
            # Average time (excluding None values)
            times = [a.time_taken_seconds for a in all_attempts if a.time_taken_seconds]
            average_time = sum(times) / len(times) if times else None
            
            # Recent performance (last 10 attempts)
            recent_attempts = sorted(all_attempts, key=lambda x: x.created_at, reverse=True)[:10]
            recent_correct = sum(1 for attempt in recent_attempts if attempt.is_correct)
            recent_success_rate = recent_correct / len(recent_attempts) if recent_attempts else 0.0
            
            # Calculate streaks
            streak_info = self._calculate_streaks(all_attempts)
            
            # Difficulty breakdown (if subject not filtered)
            difficulty_breakdown = {}
            if not subject:
                # This would require joining with QuestionsBank, simplified for now
                difficulty_breakdown = {"easy": 0, "moderate": 0, "hard": 0}
            
            return {
                "total_attempts": total_attempts,
                "correct_attempts": correct_attempts,
                "success_rate": round(success_rate, 3),
                "average_time": round(average_time, 1) if average_time else None,
                "difficulty_breakdown": difficulty_breakdown,
                "recent_performance": {
                    "attempts": len(recent_attempts),
                    "correct": recent_correct,
                    "success_rate": round(recent_success_rate, 3)
                },
                "streak": streak_info
            }
            
        except Exception as e:
            logger.error("performance_metrics_calculation_failed", error=str(e))
            return {}
    
    def _calculate_streaks(self, attempts: List[QuizAttempt]) -> Dict[str, int]:
        """Calculate current and longest correct answer streaks.
        
        Args:
            attempts: List of quiz attempts sorted by creation time
            
        Returns:
            Dictionary with current and longest streak counts
        """
        if not attempts:
            return {"current": 0, "longest": 0}
        
        # Sort by creation time (most recent first for current streak)
        sorted_attempts = sorted(attempts, key=lambda x: x.created_at, reverse=True)
        
        # Calculate current streak (from most recent)
        current_streak = 0
        for attempt in sorted_attempts:
            if attempt.is_correct:
                current_streak += 1
            else:
                break
        
        # Calculate longest streak
        longest_streak = 0
        temp_streak = 0
        
        # Sort chronologically for longest streak calculation
        chronological_attempts = sorted(attempts, key=lambda x: x.created_at)
        
        for attempt in chronological_attempts:
            if attempt.is_correct:
                temp_streak += 1
                longest_streak = max(longest_streak, temp_streak)
            else:
                temp_streak = 0
        
        return {"current": current_streak, "longest": longest_streak}


# Create a global instance
question_service = QuestionService()