#!/usr/bin/env python3
"""
CSV Import Script for Questions Bank

This script imports questions from a CSV file into the questions_bank table,
automatically handling missing fields like created_at with appropriate defaults.

Usage:
    python scripts/import_questions_csv.py path/to/questions.csv

Required CSV columns:
    - question: The question text (required)
    - answer: The correct answer (required) 
    - type: Question type, e.g. 'quiz' or 'exam' (required)
    - subject: Subject area (required)
    - language: Language code (required)
    - difficulty_level: 'easy', 'moderate', or 'hard' (required)

Optional CSV columns:
    - forms: Comma-separated form levels, e.g. "1,2,3"
    - blooms_level: Bloom's taxonomy level
    - blooms_descriptor: Bloom's taxonomy descriptor
    - question_type: Type of question format
    - learning_standards: Comma-separated learning standards
    - answer_page: Page number for answer reference
    - chapter_number: Chapter number
    - chapter_name: Chapter name
    - source: Source identifier
    - assessment_type: Assessment type
    - requires_latex: 'true' or 'false'
    - contains_calculations: 'true' or 'false'
    - knowledge_snippet: Context snippet
    - knowledge_snippet_type: Type of knowledge snippet
    - question_image_uri: URI for question image
    - answer_image_uri: URI for answer image

Missing fields will be handled with appropriate defaults:
    - created_at: Current timestamp
    - id: Generated UUID
    - forms: Parsed from string or set to null
    - boolean fields: Converted from string or set to null
"""

import csv
import sys
import uuid
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Union
from pathlib import Path

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.logging import logger
from app.models.questions_bank import QuestionsBank
from app.services.database import database_service


class QuestionCSVImporter:
    """Handles importing questions from CSV files into the database."""
    
    def __init__(self):
        """Initialize the CSV importer."""
        self.required_fields = {
            'question', 'answer', 'type', 'subject', 'language', 'difficulty_level'
        }
        self.optional_fields = {
            'forms', 'blooms_level', 'blooms_descriptor', 'question_type',
            'learning_standards', 'answer_page', 'chapter_number', 'chapter_name',
            'source', 'assessment_type', 'requires_latex', 'contains_calculations',
            'knowledge_snippet', 'knowledge_snippet_type', 'question_image_uri',
            'answer_image_uri'
        }
        self.imported_count = 0
        self.error_count = 0
        self.errors = []
    
    def validate_csv_headers(self, headers: List[str]) -> bool:
        """Validate that CSV has required headers.
        
        Args:
            headers: List of CSV column headers
            
        Returns:
            True if valid, False otherwise
        """
        headers_set = set(headers)
        missing_required = self.required_fields - headers_set
        
        if missing_required:
            logger.error(
                "csv_missing_required_headers",
                missing_headers=list(missing_required),
                found_headers=headers
            )
            print(f"❌ Missing required CSV headers: {', '.join(missing_required)}")
            return False
        
        # Check for unexpected headers
        all_expected = self.required_fields | self.optional_fields
        unexpected = headers_set - all_expected
        
        if unexpected:
            logger.warning(
                "csv_unexpected_headers",
                unexpected_headers=list(unexpected)
            )
            print(f"⚠️  Unexpected CSV headers (will be ignored): {', '.join(unexpected)}")
        
        return True
    
    def parse_csv_row(self, row: Dict[str, str], row_num: int) -> Optional[Dict[str, Any]]:
        """Parse a single CSV row into question data.
        
        Args:
            row: CSV row as dictionary
            row_num: Row number for error reporting
            
        Returns:
            Parsed question data or None if parsing fails
        """
        try:
            # Generate ID and timestamp
            question_data = {
                'id': str(uuid.uuid4()),
                'created_at': datetime.now(timezone.utc)
            }
            
            # Required fields
            for field in self.required_fields:
                value = row.get(field, '').strip()
                if not value:
                    raise ValueError(f"Required field '{field}' is empty")
                question_data[field] = value
            
            # Optional fields with type conversion
            question_data.update(self._parse_optional_fields(row))
            
            return question_data
            
        except Exception as e:
            error_msg = f"Row {row_num}: {str(e)}"
            self.errors.append(error_msg)
            logger.error("csv_row_parse_error", row_num=row_num, error=str(e))
            return None
    
    def _parse_optional_fields(self, row: Dict[str, str]) -> Dict[str, Any]:
        """Parse optional fields with appropriate type conversions.
        
        Args:
            row: CSV row dictionary
            
        Returns:
            Dictionary of parsed optional fields
        """
        parsed = {}
        
        # Parse forms as list of integers
        forms_str = row.get('forms', '').strip()
        if forms_str:
            try:
                parsed['forms'] = [int(f.strip()) for f in forms_str.split(',') if f.strip()]
            except ValueError:
                logger.warning("invalid_forms_format", forms=forms_str)
                parsed['forms'] = None
        else:
            parsed['forms'] = None
        
        # Parse learning standards as list of strings
        standards_str = row.get('learning_standards', '').strip()
        if standards_str:
            parsed['learning_standards'] = [s.strip() for s in standards_str.split(',') if s.strip()]
        else:
            parsed['learning_standards'] = None
        
        # Parse boolean fields
        for bool_field in ['requires_latex', 'contains_calculations']:
            value = row.get(bool_field, '').strip().lower()
            if value in ['true', '1', 'yes', 'y']:
                parsed[bool_field] = True
            elif value in ['false', '0', 'no', 'n']:
                parsed[bool_field] = False
            else:
                parsed[bool_field] = None
        
        # Parse integer fields
        answer_page = row.get('answer_page', '').strip()
        if answer_page:
            try:
                parsed['answer_page'] = int(answer_page)
            except ValueError:
                parsed['answer_page'] = None
        else:
            parsed['answer_page'] = None
        
        # Parse string fields (allowing empty strings to become None)
        string_fields = [
            'blooms_level', 'blooms_descriptor', 'question_type', 'chapter_number',
            'chapter_name', 'source', 'assessment_type', 'knowledge_snippet',
            'knowledge_snippet_type', 'question_image_uri', 'answer_image_uri'
        ]
        
        for field in string_fields:
            value = row.get(field, '').strip()
            parsed[field] = value if value else None
        
        return parsed
    
    async def import_questions(self, csv_file_path: str) -> bool:
        """Import questions from CSV file.
        
        Args:
            csv_file_path: Path to the CSV file
            
        Returns:
            True if import successful, False otherwise
        """
        try:
            logger.info("csv_import_started", file_path=csv_file_path)
            print(f"🚀 Starting CSV import from: {csv_file_path}")
            
            # Validate file exists
            if not Path(csv_file_path).exists():
                print(f"❌ File not found: {csv_file_path}")
                return False
            
            # Read and validate CSV
            with open(csv_file_path, 'r', encoding='utf-8') as file:
                # Detect CSV dialect with fallback options
                sample = file.read(1024)
                file.seek(0)
                
                delimiter = ','  # Default delimiter
                try:
                    sniffer = csv.Sniffer()
                    dialect = sniffer.sniff(sample, delimiters=',;\t|')
                    delimiter = dialect.delimiter
                    print(f"📋 Detected delimiter: '{delimiter}'")
                except csv.Error:
                    # Try common delimiters in order
                    for test_delimiter in [',', ';', '\t', '|']:
                        file.seek(0)
                        test_reader = csv.reader(file, delimiter=test_delimiter)
                        try:
                            first_row = next(test_reader)
                            if len(first_row) > 1:  # Multiple columns detected
                                delimiter = test_delimiter
                                print(f"📋 Using delimiter: '{delimiter}' (auto-detected)")
                                break
                        except:
                            continue
                    else:
                        print(f"⚠️  Could not detect delimiter, using comma as default")
                
                file.seek(0)
                reader = csv.DictReader(file, delimiter=delimiter)
                
                # Validate headers
                if not self.validate_csv_headers(reader.fieldnames):
                    return False
                
                print(f"✅ CSV validation passed. Found {len(reader.fieldnames)} columns.")
                
                # Process rows
                questions_to_import = []
                row_num = 1
                
                for row in reader:
                    row_num += 1
                    question_data = self.parse_csv_row(row, row_num)
                    
                    if question_data:
                        questions_to_import.append(question_data)
                    else:
                        self.error_count += 1
                
                print(f"📊 Parsed {len(questions_to_import)} questions, {self.error_count} errors")
                
                if self.error_count > 0:
                    print("⚠️  Errors encountered:")
                    for error in self.errors:
                        print(f"   {error}")
                    
                    if len(questions_to_import) == 0:
                        print("❌ No valid questions to import")
                        return False
                    
                    response = input("Continue with import? (y/N): ").strip().lower()
                    if response != 'y':
                        print("❌ Import cancelled")
                        return False
                
                # Import to database
                if questions_to_import:
                    success = await self._bulk_insert_questions(questions_to_import)
                    if success:
                        print(f"🎉 Successfully imported {self.imported_count} questions!")
                        logger.info(
                            "csv_import_completed",
                            imported_count=self.imported_count,
                            error_count=self.error_count
                        )
                        return True
                    else:
                        return False
                
                return True
                
        except Exception as e:
            logger.error("csv_import_failed", error=str(e), exc_info=True)
            print(f"❌ Import failed: {str(e)}")
            return False
    
    async def _bulk_insert_questions(self, questions: List[Dict[str, Any]]) -> bool:
        """Bulk insert questions into database.
        
        Args:
            questions: List of question data dictionaries
            
        Returns:
            True if successful, False otherwise
        """
        try:
            print(f"💾 Inserting {len(questions)} questions into database...")
            
            with database_service.get_session_maker() as session:
                for i, question_data in enumerate(questions, 1):
                    try:
                        # Create QuestionsBank instance
                        question = QuestionsBank(**question_data)
                        session.add(question)
                        
                        # Commit in batches of 100
                        if i % 100 == 0:
                            session.commit()
                            print(f"   ✅ Inserted {i}/{len(questions)} questions...")
                        
                        self.imported_count += 1
                        
                    except Exception as e:
                        logger.error(
                            "question_insert_failed",
                            question_id=question_data.get('id'),
                            error=str(e)
                        )
                        self.error_count += 1
                        continue
                
                # Final commit
                session.commit()
                
            return True
            
        except Exception as e:
            logger.error("bulk_insert_failed", error=str(e), exc_info=True)
            print(f"❌ Database insert failed: {str(e)}")
            return False
    
    def print_import_summary(self):
        """Print import summary statistics."""
        print("\n📈 Import Summary")
        print("=" * 30)
        print(f"✅ Successfully imported: {self.imported_count}")
        print(f"❌ Errors encountered: {self.error_count}")
        
        total = self.imported_count + self.error_count
        if total > 0:
            success_rate = (self.imported_count / total) * 100
            print(f"📊 Success rate: {success_rate:.1f}%")
        else:
            print("📊 Success rate: N/A (no records processed)")


async def main():
    """Main function for CSV import script."""
    if len(sys.argv) != 2:
        print("Usage: python scripts/import_questions_csv.py <csv_file_path>")
        print("\nExample:")
        print("  python scripts/import_questions_csv.py data/questions.csv")
        sys.exit(1)
    
    csv_file_path = sys.argv[1]
    
    print("🎯 Questions Bank CSV Importer")
    print("=" * 50)
    
    importer = QuestionCSVImporter()
    
    try:
        success = await importer.import_questions(csv_file_path)
        importer.print_import_summary()
        
        if success:
            print("\n🎉 CSV import completed successfully!")
            sys.exit(0)
        else:
            print("\n💥 CSV import failed!")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n🛑 Import cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Unexpected error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())