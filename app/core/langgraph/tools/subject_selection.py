"""Subject selection tool for the LangGraph agent."""

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from app.core.logging import logger
from app.services.subject_service import subject_service
from app.services.database import database_service


class SubjectSelectionInput(BaseModel):
    """Input for subject selection tool."""

    subject_input: str = Field(description="Subject name, number, or alternative name to select")
    user_id: str = Field(description="User ID for setting the focus subject")


class SubjectSelectionTool(BaseTool):
    """Tool for selecting user's focus subject during conversation."""

    name: str = "select_subject"
    description: str = """Select a subject as the user's current focus for study. 
    Use this when a user wants to:
    - Choose a specific subject to study
    - Switch to a different subject
    - Set their learning focus
    
    Input should be the subject name, number (e.g., "1", "2"), or alternative name (e.g., "bio", "math", "fizik").
    Always include the user_id to properly set their focus subject.
    
    Examples:
    - "I want to study Biology" -> select_subject(subject_input="Biology", user_id="user123")
    - "Switch to subject 3" -> select_subject(subject_input="3", user_id="user123") 
    - "Let's focus on Fizik" -> select_subject(subject_input="Fizik", user_id="user123")
    """

    args_schema: type = SubjectSelectionInput

    def _run(self, subject_input: str, user_id: str) -> str:
        """Select a subject for the user (sync version - not implemented)."""
        raise NotImplementedError("SubjectSelectionTool only supports async operation")

    async def _arun(self, subject_input: str, user_id: str) -> str:
        """Select a subject for the user.

        Args:
            subject_input: Subject identifier (name, number, or alternative)
            user_id: User ID

        Returns:
            Confirmation message about subject selection
        """
        try:
            logger.info("subject_selection_tool_called", subject_input=subject_input, user_id=user_id)

            # Find subject by input
            found_subject = await subject_service.find_subject_by_name_or_number(subject_input)

            if not found_subject:
                logger.warning("subject_not_found_in_tool", input=subject_input, user_id=user_id)

                # Get available subjects for user reference
                available_subjects = await subject_service.get_available_subjects()
                subject_list_message = subject_service.format_subject_selection_message(
                    available_subjects, f"Sorry, I couldn't find '{subject_input}'. Here are the available subjects:"
                )

                return f"❌ Subject '{subject_input}' not found.\n\n{subject_list_message}"

            # Set as user's focus subject
            success = await subject_service.set_user_focus_subject(user_id, found_subject["id"])

            if not success:
                logger.error("failed_to_set_focus_subject_in_tool", user_id=user_id, subject_id=found_subject["id"])
                return f"❌ Sorry, I couldn't set '{found_subject['name']}' as your focus subject. Please try again."

            logger.info(
                "subject_selected_via_tool", user_id=user_id, subject_name=found_subject["name"], input=subject_input
            )

            # Create response with subject context
            alt_names = found_subject.get("alt_names", [])
            alt_names_text = f" (also known as: {', '.join(alt_names)})" if alt_names else ""

            response = f"✅ Perfect! I've set **{found_subject['name']}**{alt_names_text} as your focus subject.\n\n"
            response += "🎯 **What this means:**\n"
            response += "• All my explanations will be tailored to this subject\n"
            response += "• Quiz questions will focus on this subject content\n"
            response += "• I'll use subject-specific terminology and examples\n"
            response += "• My responses will reference the relevant textbook content\n\n"
            response += f"📚 **Ready to help with {found_subject['name']}!** What would you like to learn about?"

            return response

        except Exception as e:
            logger.error("subject_selection_tool_error", error=str(e), user_id=user_id, subject_input=subject_input)
            return "❌ An error occurred while selecting the subject. Please try again or contact support."


class SubjectContextInput(BaseModel):
    """Input for subject context tool."""

    user_id: str = Field(description="User ID to get subject context for")


class SubjectContextTool(BaseTool):
    """Tool for getting current subject context and available subjects."""

    name: str = "get_subject_context"
    description: str = """Get the user's current subject context and available subjects.
    Use this when you need to:
    - Check what subject the user is currently focused on
    - Show available subjects for selection
    - Provide subject-specific help
    
    Always include the user_id to get their personal subject context.
    """

    args_schema: type = SubjectContextInput

    def _run(self, user_id: str) -> str:
        """Get subject context for the user (sync version - not implemented)."""
        raise NotImplementedError("SubjectContextTool only supports async operation")

    async def _arun(self, user_id: str) -> str:
        """Get subject context for the user.

        Args:
            user_id: User ID

        Returns:
            Subject context information
        """
        try:
            logger.info("subject_context_tool_called", user_id=user_id)

            # Get user's current subject
            current_subject = await subject_service.get_user_current_subject(user_id)

            # Get user details for additional context
            user = await database_service.get_user(user_id)

            response = "📚 **Your Subject Context:**\n\n"

            if current_subject:
                response += f"🎯 **Current Focus Subject:** {current_subject['name']}\n"
                if current_subject.get("description"):
                    response += f"📖 **Description:** {current_subject['description']}\n"

                # Show alternative names
                alt_names = current_subject.get("alt_names", [])
                if alt_names:
                    response += f"🔤 **Also known as:** {', '.join(alt_names)}\n"

                response += "\n"
            else:
                response += "❓ **No subject currently selected**\n\n"

            # Show user's subject preferences if available
            if user:
                if user.current_subjects:
                    response += f"📝 **Your Subjects:** {', '.join(user.current_subjects[:3])}\n"
                if user.focus_subjects:
                    response += f"⭐ **Focus Areas:** {', '.join(user.focus_subjects[:3])}\n"
                if user.form_level:
                    response += f"🎓 **Form Level:** Form {user.form_level}\n"
                if user.language:
                    response += f"🌐 **Language:** {user.language}\n"

                response += "\n"

            # Show available subjects
            available_subjects = await subject_service.get_available_subjects()
            if available_subjects:
                response += "📋 **Available Subjects:**\n"
                for i, subject in enumerate(available_subjects[:5], 1):  # Show first 5
                    response += f"{i}. {subject['name']}\n"

                if len(available_subjects) > 5:
                    response += f"... and {len(available_subjects) - 5} more\n"

                response += "\n💡 Say 'select [subject name]' or 'I want to study [subject]' to choose a subject!"

            logger.info("subject_context_retrieved", user_id=user_id, has_current=current_subject is not None)
            return response

        except Exception as e:
            logger.error("subject_context_tool_error", error=str(e), user_id=user_id)
            return "❌ Sorry, I couldn't retrieve your subject context. Please try again."


# Create tool instances
subject_selection_tool = SubjectSelectionTool()
subject_context_tool = SubjectContextTool()
