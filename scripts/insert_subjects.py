#!/usr/bin/env python3
"""Script to insert Focus SPM subjects into the database.

This script populates the subjects table with the 11 Focus SPM subjects
and their corresponding book codes for RAG filtering.
"""

import sys
import os
import uuid
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlmodel import Session, select
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.logging import logger
from app.services.database import database_service
from app.models.subject import Subject


def get_focus_spm_subjects():
    """Get the list of Focus SPM subjects to insert.
    
    Returns:
        List of subject dictionaries with id, name, description, and book_code
    """
    return [
        {
            "id": str(uuid.uuid4()),
            "name": "Focus SPM Biology",
            "description": "SPM Biology preparation with comprehensive coverage of Form 4 and 5 biology topics including cell biology, genetics, ecology, and more.",
            "book_code": "ePDF FOCUS SPM (2025) BIOLOGY AAEVSB2572004A.pdf"
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Focus SPM Chemistry", 
            "description": "SPM Chemistry preparation covering inorganic, organic, and physical chemistry topics for Form 4 and 5 students.",
            "book_code": "ePDF FOCUS SPM (2025) CHEMISTRY AAEVSC2572004A.pdf"
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Focus SPM Physics",
            "description": "SPM Physics preparation with detailed coverage of mechanics, electricity, waves, and modern physics concepts.",
            "book_code": "ePDF FOCUS SPM (2025) PHYSICS AAEVSP2572004A.pdf"
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Focus SPM Mathematics",
            "description": "SPM Mathematics preparation covering algebra, calculus, statistics, and geometry for Form 4 and 5 students.",
            "book_code": "ePDF FOCUS SPM (2025) MATHEMATICS AAEVMM2572004A.pdf"
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Focus SPM Science",
            "description": "SPM Science preparation with integrated approach to scientific concepts for lower secondary students.",
            "book_code": "ePDF FOCUS SPM (2025) SCIENCE AAEVSN2572004A.pdf"
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Focus SPM Matematik",
            "description": "SPM Matematik dalam Bahasa Malaysia dengan liputan lengkap algebra, kalkulus, statistik, dan geometri.",
            "book_code": "ePDF FOCUS SPM (2025) MATEMATIK AAMVMM2572004A.pdf"
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Focus SPM Matematik Tambahan",
            "description": "SPM Matematik Tambahan untuk pelajar lanjutan dengan topik kalkulus, statistik, dan matematik diskrit.",
            "book_code": "ePDF FOCUS SPM (2025) MATEMATIK TAMBAHAN AAMVMB2572004A.pdf"
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Focus SPM Sains", 
            "description": "SPM Sains dalam Bahasa Malaysia dengan pendekatan bersepadu kepada konsep saintifik.",
            "book_code": "ePDF FOCUS SPM (2025) SAINS AAMVSN2572004A.pdf"
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Focus SPM Kimia",
            "description": "SPM Kimia dalam Bahasa Malaysia meliputi kimia tak organik, organik, dan fizik untuk pelajar Tingkatan 4 dan 5.",
            "book_code": "ePDF FOCUS SPM (2025) KIMIA AAMVSC2572004A.pdf"
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Focus SPM Fizik",
            "description": "SPM Fizik dalam Bahasa Malaysia dengan liputan terperinci mekanik, elektrik, gelombang, dan fizik moden.",
            "book_code": "ePDF FOCUS SPM (2025) FIZIK AAMVSP2572004A.pdf"
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Focus SPM Sejarah",
            "description": "SPM Sejarah dalam Bahasa Malaysia meliputi sejarah Malaysia dan dunia untuk pelajar Tingkatan 4 dan 5.",
            "book_code": "ePDF FOCUS SPM (2025) SEJARAH AAMVSJ2572004A.pdf"
        }
    ]


def subject_exists(session: Session, subject_name: str) -> bool:
    """Check if a subject already exists in the database.
    
    Args:
        session: Database session
        subject_name: Name of the subject to check
        
    Returns:
        True if subject exists, False otherwise
    """
    try:
        statement = select(Subject).where(Subject.name == subject_name)
        existing = session.exec(statement).first()
        return existing is not None
    except SQLAlchemyError:
        return False


def insert_subject(session: Session, subject_data: dict) -> bool:
    """Insert a single subject into the database.
    
    Args:
        session: Database session
        subject_data: Dictionary containing subject information
        
    Returns:
        True if insertion was successful, False otherwise
    """
    try:
        subject = Subject(
            id=subject_data["id"],
            name=subject_data["name"],
            description=subject_data["description"],
            book_code=subject_data["book_code"]
        )
        
        session.add(subject)
        session.commit()
        session.refresh(subject)
        
        logger.info(
            "subject_inserted",
            subject_id=subject.id,
            subject_name=subject.name,
            book_code=subject.book_code
        )
        
        return True
        
    except SQLAlchemyError as e:
        logger.error(
            "subject_insertion_failed",
            subject_name=subject_data["name"],
            error=str(e)
        )
        session.rollback()
        return False


def update_subject(session: Session, existing_subject: Subject, subject_data: dict) -> bool:
    """Update an existing subject with new data.
    
    Args:
        session: Database session
        existing_subject: Existing subject record
        subject_data: New subject data
        
    Returns:
        True if update was successful, False otherwise
    """
    try:
        existing_subject.description = subject_data["description"]
        existing_subject.book_code = subject_data["book_code"]
        
        session.add(existing_subject)
        session.commit()
        
        logger.info(
            "subject_updated",
            subject_id=existing_subject.id,
            subject_name=existing_subject.name,
            book_code=existing_subject.book_code
        )
        
        return True
        
    except SQLAlchemyError as e:
        logger.error(
            "subject_update_failed",
            subject_name=subject_data["name"],
            error=str(e)
        )
        session.rollback()
        return False


def main():
    """Main function to insert Focus SPM subjects."""
    print("🚀 Starting Focus SPM subjects insertion...")
    print(f"Environment: {settings.ENVIRONMENT.value}")
    print(f"Database URL: {settings.POSTGRES_URL[:50]}...")
    
    try:
        subjects_data = get_focus_spm_subjects()
        print(f"📚 Found {len(subjects_data)} subjects to process")
        
        success_count = 0
        update_count = 0
        error_count = 0
        
        with database_service.get_session_maker() as session:
            for subject_data in subjects_data:
                subject_name = subject_data["name"]
                print(f"\n📖 Processing: {subject_name}")
                
                # Check if subject already exists
                statement = select(Subject).where(Subject.name == subject_name)
                existing_subject = session.exec(statement).first()
                
                if existing_subject:
                    print("   ⚠️  Subject already exists, updating...")
                    if update_subject(session, existing_subject, subject_data):
                        update_count += 1
                        print("   ✅ Updated successfully")
                    else:
                        error_count += 1
                        print("   ❌ Update failed")
                else:
                    print("   🆕 Creating new subject...")
                    if insert_subject(session, subject_data):
                        success_count += 1
                        print("   ✅ Created successfully")
                    else:
                        error_count += 1
                        print("   ❌ Creation failed")
        
        print("\n🎉 Subjects insertion completed!")
        print(f"   ✅ Created: {success_count}")
        print(f"   🔄 Updated: {update_count}")
        print(f"   ❌ Errors: {error_count}")
        print(f"   📊 Total processed: {len(subjects_data)}")
        
        # Verify insertion by counting subjects
        try:
            with database_service.get_session_maker() as session:
                total_subjects = len(session.exec(select(Subject)).all())
                print(f"   📚 Total subjects in database: {total_subjects}")
        except Exception as e:
            print(f"   ⚠️  Could not verify total count: {e}")
        
        if error_count == 0:
            print("\n🌟 All subjects processed successfully!")
            return 0
        else:
            print(f"\n⚠️  {error_count} subjects had errors. Check logs for details.")
            return 1
            
    except Exception as e:
        logger.error("subjects_insertion_script_failed", error=str(e), exc_info=True)
        print(f"\n💥 Script failed with error: {e}")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)