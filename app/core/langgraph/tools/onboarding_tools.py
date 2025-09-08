"""Tools for managing student onboarding process using GraphState and LLM extraction."""

import json
from typing import Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from pydantic import ValidationError

from app.core.llm.provider import create_llm_provider
from app.core.logging import logger
from app.schemas.onboarding import OnboardingFieldExtraction, StudentProfile
from app.services.user_service import user_service


def generate_unified_onboarding_form(collected_data: Dict[str, any], missing_fields: List[str], is_initial: bool = False) -> str:
    """Generate a unified onboarding form showing collected data and missing fields.
    
    Args:
        collected_data: Dictionary of already collected onboarding data
        missing_fields: List of field names that still need to be collected
        is_initial: Whether this is the initial form presentation
        
    Returns:
        str: Formatted onboarding form with filled and missing fields
    """
    # Define all fields in the required sequence
    all_fields = [
        ("full_name", "Full Name", ""),
        ("date_of_birth", "Date of Birth", "e.g., 15/03/2007 or 2007-03-15"),
        ("school_name", "School Name", ""),
        ("form_level", "Form Level", "e.g., Form 4 or Form 5"),
        ("current_subjects", "Current Subjects", "e.g., Biology, Chemistry, Physics, Mathematics"),
        ("focus_subjects", "Focus Subjects", "e.g., Biology, Chemistry (1-3 subjects for extra help)"),
        ("language_preference", "Language Preference", "e.g., English, Bahasa Malaysia, or Chinese")
    ]
    
    form_lines = []
    
    for i, (field_key, field_name, example) in enumerate(all_fields, 1):
        if field_key in collected_data and collected_data[field_key]:
            # Field is collected - show with checkmark and value
            value = collected_data[field_key]
            if isinstance(value, list):
                value = ", ".join(value)
            elif isinstance(value, str) and field_key == "date_of_birth":
                # Format date if it's a date string
                try:
                    from datetime import datetime
                    if "-" in value:
                        # Parse YYYY-MM-DD format and convert to readable format
                        parsed_date = datetime.strptime(value, "%Y-%m-%d")
                        value = parsed_date.strftime("%d %B %Y")
                except:
                    pass  # Keep original value if parsing fails
                    
            form_lines.append(f"{i}. ✅ **{field_name}**: {value}")
        elif field_key in missing_fields:
            # Field is missing - show with prompt
            if example:
                form_lines.append(f"{i}. **{field_name}** - {example}")
            else:
                form_lines.append(f"{i}. **{field_name}** - [Please provide]")
        else:
            # Field is neither collected nor in missing list (shouldn't happen)
            if example:
                form_lines.append(f"{i}. **{field_name}** - {example}")
            else:
                form_lines.append(f"{i}. **{field_name}** - [Please provide]")
    
    # Add student_id as optional
    if "student_id" in collected_data and collected_data["student_id"]:
        optional_section = f"\n📋 **Optional:**\n- ✅ **Student ID**: {collected_data['student_id']}"
    else:
        optional_section = "\n📋 **Optional:**\n- **Student ID** - [Optional]"
    
    # Create the complete form
    if is_initial:
        header = "Welcome to Pelangi Study Buddy! 🎓\n\nI'll help you set up your profile. Please provide the following information (you can fill in multiple fields at once or one by one):"
        footer = "\nYou can provide all information at once or one by one. What information can you share with me? 😊"
    else:
        completed_count = len([f for f, _, _ in all_fields if f in collected_data and collected_data[f]])
        if missing_fields:
            if len(missing_fields) == 1:
                header = f"Great progress! {completed_count}/7 fields completed. I still need one more detail:"
            else:
                header = f"Great progress! {completed_count}/7 fields completed. I still need {len(missing_fields)} more details:"
        else:
            header = "Perfect! All required fields completed:"
        footer = "\nYou can provide the missing details all at once or one by one! 😊"
    
    form = f"""{header}

📝 **Required Fields:**
{chr(10).join(form_lines)}{optional_section}{footer}"""
    
    return form


def generate_missing_field_prompts(missing_fields: List[str]) -> str:
    """Legacy function - deprecated in favor of generate_unified_onboarding_form.
    
    This function is kept for backward compatibility but should not be used for new code.
    """
    # This function is now deprecated - use generate_unified_onboarding_form instead
    return generate_unified_onboarding_form({}, missing_fields, is_initial=False)


async def extract_fields_with_llm(user_input: str) -> OnboardingFieldExtraction:
    """Extract onboarding fields from user input using LLM.
    
    Args:
        user_input: Natural language input from user
        
    Returns:
        OnboardingFieldExtraction with parsed fields
    """
    llm_provider = create_llm_provider()
    llm = llm_provider.get_llm()
    
    extraction_prompt = f"""Extract student profile information from the following text.
    
User Input: "{user_input}"

Extract the following fields if present (in this order):
- full_name: Student's complete name
- date_of_birth: Date in any format (DD/MM/YYYY, MM-DD-YYYY, 15/03/2007, etc.)
- school_name: Name of the school
- form_level: Must be exactly "Form 4" or "Form 5"
- current_subjects: List of all subjects the student is studying
- focus_subjects: 1-3 subjects they want extra help with
- language_preference: Must be exactly "English", "Bahasa Malaysia", or "Chinese"
- student_id: Student identification number (optional)

Return a JSON object with only the fields found. Use null for fields not mentioned.
Be strict about form_level and language_preference values.

Example response:
{{
    "full_name": "John Smith",
    "date_of_birth": "15/03/2007",
    "school_name": "SMK Example",
    "form_level": "Form 5",
    "current_subjects": ["Biology", "Chemistry", "Physics", "Mathematics"],
    "focus_subjects": ["Biology", "Chemistry"],
    "language_preference": "English",
    "student_id": null
}}"""

    try:
        messages = [
            SystemMessage(content="You are a data extraction assistant. Extract structured data from natural language."),
            HumanMessage(content=extraction_prompt)
        ]
        
        response = await llm.ainvoke(messages)
        
        # Parse the JSON response
        content = response.content.strip()
        # Remove markdown code blocks if present
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        if content.endswith("```"):
            content = content[:-3]
        
        extracted_data = json.loads(content.strip())
        
        # Create OnboardingFieldExtraction object
        return OnboardingFieldExtraction(**extracted_data)
        
    except Exception as e:
        logger.error("llm_field_extraction_failed", error=str(e), user_input=user_input)
        # Return empty extraction on error
        return OnboardingFieldExtraction()


@tool
async def start_onboarding(session_id: str, user_id: str, state: Optional[Dict] = None) -> str:
    """Start the onboarding process for a new student.
    
    Args:
        session_id: The session ID for tracking onboarding
        user_id: The user ID (injected by LangGraph)
        state: The current GraphState (injected by LangGraph)
        
    Returns:
        JSON string with status and welcome message
    """
    try:
        
        # Check current onboarding status from state
        onboarding_status = state.get("onboarding_status", "not_started") if state else "not_started"
        onboarding_data = state.get("onboarding_data", {}) if state else {}
        
        if onboarding_status == "completed":
            return json.dumps({
                "status": "complete",
                "message": "Your profile is already complete! Ready to start learning.",
                "profile_data": onboarding_data,
                "next_action": "begin_tutoring"
            })
        
        if onboarding_status == "in_progress" and onboarding_data:
            collected_fields = list(onboarding_data.keys())
            collected_summary = ", ".join([field.replace("_", " ").title() for field in collected_fields])
            
            missing_fields = state.get("onboarding_missing_fields", []) if state else []
            
            # Generate unified form showing progress
            form_display = generate_unified_onboarding_form(
                collected_data=onboarding_data,
                missing_fields=missing_fields,
                is_initial=False
            )
            
            message = f"Let's continue your profile setup! ✨\n\n{form_display}"
            
            return json.dumps({
                "status": "complete",
                "message": message,
                "collected_fields": collected_fields,
                "missing_fields": missing_fields,
                "next_action": "collect_multiple_fields"
            })
        
        # Generate unified initial form
        required_fields = ["full_name", "date_of_birth", "school_name", "form_level", 
                         "current_subjects", "focus_subjects", "language_preference"]
        onboarding_form = generate_unified_onboarding_form(
            collected_data={}, 
            missing_fields=required_fields, 
            is_initial=True
        )

        return json.dumps({
            "status": "complete",
            "message": onboarding_form,
            "next_action": "collect_multiple_fields",
            "update_state": {
                "onboarding_status": "in_progress"
            }
        })
        
    except Exception as e:
        logger.error("start_onboarding_failed", error=str(e), session_id=session_id)
        return json.dumps({
            "status": "error",
            "message": "Unable to start onboarding. Please try again.",
            "next_action": "retry"
        })


@tool
async def parse_onboarding_input(session_id: str, user_input: str, user_id: str, state: Optional[Dict] = None) -> str:
    """Parse onboarding fields from natural language input using LLM.
    
    Args:
        session_id: The session ID
        user_input: User's natural language input
        user_id: The user ID (injected by LangGraph)
        state: The current GraphState (injected by LangGraph)
        
    Returns:
        JSON string with parsed fields and status
    """
    try:
        # Get current state and check if onboarding has been started
        current_data = state.get("onboarding_data", {}) if state else {}
        onboarding_status = state.get("onboarding_status", "not_started") if state else "not_started"
        
        # Auto-initialize onboarding if user provides data without starting first
        if onboarding_status == "not_started":
            onboarding_status = "in_progress"
            logger.info("auto_initializing_onboarding", session_id=session_id, user_input_preview=user_input[:50])
        
        logger.info("parse_onboarding_input_called", session_id=session_id, current_data_keys=list(current_data.keys()), onboarding_status=onboarding_status, user_input_preview=user_input[:50])
        
        # Extract fields using LLM
        extracted = await extract_fields_with_llm(user_input)
        
        # Convert to dict and filter out None values
        parsed_fields = {}
        for field, value in extracted.model_dump().items():
            if value is not None:
                parsed_fields[field] = value
        
        if not parsed_fields:
            # No fields found - provide helpful guidance
            required_fields = ["full_name", "date_of_birth", "school_name", "form_level", 
                             "current_subjects", "focus_subjects", "language_preference"]
            missing_fields = [f for f in required_fields if f not in current_data]
            form_display = generate_unified_onboarding_form(
                collected_data=current_data,
                missing_fields=missing_fields,
                is_initial=False
            )
            
            return json.dumps({
                "status": "complete",
                "message": f"I couldn't extract profile information from your message. Let me help you! 😊\n\n{form_display}",
                "missing_fields": missing_fields,
                "next_action": "provide_details"
            })
        
        # Merge with existing data
        updated_data = {**current_data, **parsed_fields}
        logger.info("onboarding_data_merged", session_id=session_id, parsed_fields=parsed_fields, updated_data_keys=list(updated_data.keys()))
        
        # Validate the complete profile
        validation_errors = {}
        try:
            # Check if we have all required fields
            required_fields = ["full_name", "date_of_birth", "school_name", "form_level", 
                             "current_subjects", "focus_subjects", "language_preference"]
            missing_fields = [f for f in required_fields if f not in updated_data]
            
            if not missing_fields:
                # Try to create StudentProfile to validate
                StudentProfile(**updated_data)
        except ValidationError as ve:
            for error in ve.errors():
                field = error["loc"][0] if error["loc"] else "unknown"
                validation_errors[field] = error["msg"]
        
        if validation_errors:
            error_msgs = []
            for field, error in validation_errors.items():
                error_msgs.append(f"• **{field.replace('_', ' ').title()}**: {error}")
            
            return json.dumps({
                "status": "validation_errors",
                "parsed_fields": parsed_fields,
                "validation_errors": validation_errors,
                "message": f"Found some information, but there were validation errors:\n{chr(10).join(error_msgs)}\n\nPlease provide the correct information.",
                "next_action": "provide_corrections"
            })
        
        # Calculate missing fields
        required_fields = ["full_name", "date_of_birth", "school_name", "form_level", 
                         "current_subjects", "focus_subjects", "language_preference"]
        missing_fields = [f for f in required_fields if f not in updated_data]
        
        # Prepare state update
        state_update = {
            "onboarding_data": updated_data,
            "onboarding_status": onboarding_status,
            "onboarding_missing_fields": missing_fields,
            "onboarding_validation_errors": {}
        }
        logger.info("onboarding_state_update_prepared", session_id=session_id, missing_fields=missing_fields, state_update_keys=list(state_update.keys()))
        
        if not missing_fields:
            # All fields collected - ready for confirmation
            profile_summary = []
            
            if updated_data.get("full_name"):
                profile_summary.append(f"📝 **Name**: {updated_data['full_name']}")
            if updated_data.get("form_level"):
                profile_summary.append(f"📚 **Form**: {updated_data['form_level']}")
            if updated_data.get("school_name"):
                profile_summary.append(f"🏫 **School**: {updated_data['school_name']}")
            if updated_data.get("current_subjects"):
                subjects = updated_data['current_subjects']
                if isinstance(subjects, list):
                    subjects = ", ".join(subjects)
                profile_summary.append(f"📖 **Current Subjects**: {subjects}")
            if updated_data.get("focus_subjects"):
                focus = updated_data['focus_subjects']
                if isinstance(focus, list):
                    focus = ", ".join(focus)
                profile_summary.append(f"🎯 **Focus Subjects**: {focus}")
            if updated_data.get("language_preference"):
                profile_summary.append(f"🌐 **Language**: {updated_data['language_preference']}")
            
            collected_info = ', '.join([field.replace('_', ' ').title() for field in parsed_fields.keys()])
            confirmation_msg = f"Perfect! ✅ I've added your **{collected_info}**.\n\n**Your Complete Profile:**\n{chr(10).join(profile_summary)}\n\n🤔 Please confirm: Is all this information correct? (Yes/No)\n\nIf anything needs to be changed, just let me know!"
            
            state_update["onboarding_status"] = "ready_for_confirmation"
            
            return json.dumps({
                "status": "complete",
                "parsed_fields": parsed_fields,
                "profile_summary": "\n".join(profile_summary),
                "message": confirmation_msg,
                "next_action": "confirm_profile",
                "update_state": state_update
            })
        
        # Still missing some fields - show unified form with progress
        collected_info = ', '.join([field.replace('_', ' ').title() for field in parsed_fields.keys()])
        form_display = generate_unified_onboarding_form(
            collected_data=updated_data,
            missing_fields=missing_fields,
            is_initial=False
        )
        
        message = f"Great! ✅ I've collected your **{collected_info}**.\n\n{form_display}"
        
        return json.dumps({
            "status": "complete",
            "parsed_fields": parsed_fields,
            "missing_fields": missing_fields,
            "message": message,
            "next_action": "collect_remaining_fields",
            "update_state": state_update
        })
        
    except Exception as e:
        logger.error("parse_onboarding_input_failed", error=str(e), session_id=session_id)
        return json.dumps({
            "status": "error",
            "message": "Unable to process your information. Please try again.",
            "next_action": "retry"
        })


@tool
async def confirm_onboarding(session_id: str, confirmed: bool, user_id: str, state: Optional[Dict] = None) -> str:
    """Confirm and complete the onboarding process.
    
    Args:
        session_id: The session ID
        confirmed: Whether the user confirmed their profile
        user_id: The user ID (injected by LangGraph)
        state: The current GraphState (injected by LangGraph)
        
    Returns:
        JSON string with completion status
    """
    try:
        onboarding_data = state.get("onboarding_data", {}) if state else {}
        
        if not confirmed:
            # User wants to make corrections
            profile_summary = []
            
            if onboarding_data.get("full_name"):
                profile_summary.append(f"📝 **Name**: {onboarding_data['full_name']}")
            if onboarding_data.get("form_level"):
                profile_summary.append(f"📚 **Form**: {onboarding_data['form_level']}")
            if onboarding_data.get("school_name"):
                profile_summary.append(f"🏫 **School**: {onboarding_data['school_name']}")
            if onboarding_data.get("current_subjects"):
                subjects = onboarding_data['current_subjects']
                if isinstance(subjects, list):
                    subjects = ", ".join(subjects)
                profile_summary.append(f"📖 **Current Subjects**: {subjects}")
            if onboarding_data.get("focus_subjects"):
                focus = onboarding_data['focus_subjects']
                if isinstance(focus, list):
                    focus = ", ".join(focus)
                profile_summary.append(f"🎯 **Focus Subjects**: {focus}")
            if onboarding_data.get("language_preference"):
                profile_summary.append(f"🌐 **Language**: {onboarding_data['language_preference']}")
            
            correction_msg = f"""No problem! I'll help you correct any information. 😊

**Current Profile:**
{chr(10).join(profile_summary)}

Please tell me what needs to be changed. You can say something like:
• "Change my name to..."
• "My school is actually..."
• "Update my subjects to..."
• "I prefer English instead"

Just tell me what to fix and I'll update it right away!"""
            
            return json.dumps({
                "status": "cancelled",
                "message": correction_msg,
                "current_profile": profile_summary,
                "next_action": "collect_corrections"
            })
        
        # Save profile to database
        profile_data = {
            "full_name": onboarding_data.get("full_name"),
            "current_subjects": onboarding_data.get("current_subjects"),
            "form_level": onboarding_data.get("form_level"),
            "school_name": onboarding_data.get("school_name"),
            "focus_subjects": onboarding_data.get("focus_subjects"),
            "language_preference": onboarding_data.get("language_preference"),
            "student_id": onboarding_data.get("student_id")
        }
        
        success = user_service.save_onboarding_profile(user_id, profile_data)
        
        if success:
            return json.dumps({
                "status": "completed",
                "message": f"🎉 Welcome aboard, {onboarding_data.get('full_name', 'Student')}! Your profile is complete and ready. Let's start your SPM journey together!",
                "profile_data": profile_data,
                "next_action": "begin_tutoring",
                "update_state": {
                    "onboarding_status": "completed",
                    "onboarding_validation_errors": {}
                }
            })
        else:
            return json.dumps({
                "status": "error",
                "message": "Unable to save your profile. Please try again.",
                "next_action": "retry"
            })
        
    except Exception as e:
        logger.error("confirm_onboarding_failed", error=str(e), session_id=session_id)
        return json.dumps({
            "status": "error",
            "message": "Unable to complete onboarding. Please try again.",
            "next_action": "retry"
        })


@tool
async def get_onboarding_status(session_id: str, user_id: str, state: Optional[Dict] = None) -> str:
    """Get the current onboarding status and progress.
    
    Args:
        session_id: The session ID
        user_id: The user ID (injected by LangGraph)
        state: The current GraphState (injected by LangGraph)
        
    Returns:
        JSON string with current onboarding state
    """
    try:
        onboarding_status = state.get("onboarding_status", "not_started") if state else "not_started"
        onboarding_data = state.get("onboarding_data", {}) if state else {}
        missing_fields = state.get("onboarding_missing_fields", []) if state else []
        
        if onboarding_status == "completed":
            return json.dumps({
                "status": "completed",
                "onboarding_completed": True,
                "message": "Your profile is already complete! Ready to start learning.",
                "profile_data": onboarding_data,
                "next_action": "begin_tutoring"
            })
        
        if onboarding_status in ["in_progress", "ready_for_confirmation"]:
            completed_fields = list(onboarding_data.keys())
            return json.dumps({
                "status": onboarding_status,
                "onboarding_completed": False,
                "completed_fields": completed_fields,
                "missing_fields": missing_fields,
                "is_ready_for_confirmation": onboarding_status == "ready_for_confirmation",
                "message": "You have onboarding in progress. Let's continue where you left off.",
                "next_action": "continue_onboarding"
            })
        
        return json.dumps({
            "status": "not_started",
            "onboarding_completed": False,
            "message": "Welcome! Let's set up your profile to get started.",
            "next_action": "start_onboarding"
        })
            
    except Exception as e:
        logger.error("get_onboarding_status_failed", error=str(e), session_id=session_id)
        return json.dumps({
            "status": "error",
            "onboarding_completed": False,
            "message": "Unable to check onboarding status. Please try again.",
            "next_action": "retry"
        })


# Tool aliases for consistency
onboarding_start_tool = start_onboarding
onboarding_parse_tool = parse_onboarding_input
onboarding_confirm_tool = confirm_onboarding
onboarding_status_tool = get_onboarding_status