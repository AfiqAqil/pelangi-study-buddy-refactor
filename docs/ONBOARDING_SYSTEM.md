# User Onboarding System

## Overview

The onboarding system collects essential student profile information to provide personalized tutoring experiences. It presents all required fields upfront for easier completion and uses intelligent natural language parsing to extract multiple fields from user responses.

## Features

### ✅ Comprehensive Data Collection
- **Full Name**: Student's complete name
- **Date of Birth**: Optional birth date with age validation (13-20 years)
- **Current Subjects**: All subjects the student is studying
- **Form Level**: Must be Form 4 or Form 5 (Malaysian education system)
- **School Name**: Name of the student's school
- **Focus Subjects**: 1-3 subjects for extra help (selected from current subjects)
- **Language Preference**: English, Bahasa Malaysia, or Chinese
- **Student ID**: Optional school ID number

### ✅ Smart Flow Management
- **Bulk data collection**: Present all fields upfront for easier completion
- **Natural language parsing**: Extract multiple fields from conversational responses
- **Flexible input**: Accept structured or casual responses
- **Partial data handling**: Show what was found, ask for missing information
- **Skip optional fields**: Users can skip date of birth and student ID
- **Intelligent validation**: Real-time validation with helpful error messages
- **Confirmation step**: Final review before profile creation
- **Correction handling**: Users can modify any field during confirmation

### ✅ Validation & Error Handling
- **Form level validation**: Only accepts Form 4 or Form 5
- **Age validation**: Birth date must result in reasonable age (13-20 years)
- **Subject validation**: Focus subjects must be from current subjects list
- **Language validation**: Only accepts supported languages
- **Data format validation**: Handles multiple date formats and language variants

## Architecture

### Components

1. **Schema** (`app/schemas/onboarding.py`)
   - `StudentProfile`: Complete profile model
   - `OnboardingState`: Session state tracking

2. **Tools** (`app/core/langgraph/tools/onboarding_tools.py`)
   - `start_onboarding`: Initialize onboarding session with all fields displayed
   - `parse_multiple_onboarding_fields`: Extract multiple fields from natural language
   - `collect_onboarding_data`: Collect individual fields (fallback)
   - `confirm_onboarding`: Final confirmation and profile creation
   - `get_onboarding_status`: Check current progress

3. **Graph Integration** (`app/core/langgraph/graph.py`)
   - Session ID injection for onboarding tools
   - New user detection in prompt enhancement
   - Automatic onboarding trigger hints

4. **System Prompts** (`app/core/prompts/system.md`)
   - Onboarding flow instructions
   - When to trigger onboarding
   - Step-by-step guidance rules

## Usage

### Agent Behavior

The agent automatically detects new users and triggers onboarding when:
1. First interaction with greeting words (hi, hello, hey, start, begin, help)
2. User explicitly asks to set up profile
3. No profile data exists for the session

### Example Flows

#### Bulk Response (Recommended)
```
User: "Hi there!"

Agent: [Uses get_onboarding_status → start_onboarding]
"Welcome to Pelangi Study Buddy! 🎓 

I'll help you set up your profile. Please provide the following information:

📝 **Required Fields:**
1. **Full Name** - Your complete name
2. **Current Subjects** - All subjects you're studying
3. **Form Level** - Form 4 or Form 5
4. **School Name** - Name of your school
5. **Focus Subjects** - 1-3 subjects you want extra help with
6. **Language Preference** - English, Bahasa Malaysia, or Chinese

📋 **Optional Fields:**
7. **Date of Birth** - Your birth date (can skip)
8. **Student ID** - Your school ID number (can skip)

You can provide all at once like:
'My name is Ahmad Ibrahim, I'm in Form 5 at SMK Taman Melawati...'
Or answer one field at a time."

User: "My name is Ahmad Ibrahim, I'm in Form 5 at SMK Taman Melawati. I study Biology, Chemistry, Physics, Mathematics, English, BM, and Sejarah. I want help with Biology, Chemistry, and Physics. I prefer English."

Agent: [Uses parse_onboarding_input with LLM extraction]
"Great! I found most of your information:

📝 **Name**: Ahmad Ibrahim
📚 **Form Level**: Form 5
🏫 **School**: SMK Taman Melawati
📖 **Current Subjects**: Biology, Chemistry, Physics, Mathematics, English, BM, Sejarah
🎯 **Focus Subjects**: Biology, Chemistry, Physics
🌐 **Language**: English

Is everything correct? (Yes/No)"

User: "Yes"

Agent: [Uses confirm_onboarding with confirmed=True]
"Perfect! Your profile is all set up, Ahmad Ibrahim! 🎉
I'm ready to help you with Biology, Chemistry, Physics. Let's start learning!"
```

#### Partial Response Handling
```
User: "Hi! I'm Sarah, Form 4 student. I study science subjects."

Agent: [Uses parse_onboarding_input with LLM extraction]
"✅ **Found**: full_name, form_level, current_subjects

📋 **Still need**:
🏫 **School Name**
🎯 **Focus Subjects** (1-3 subjects for extra help)
🌐 **Language Preference** (English, Bahasa Malaysia, or Chinese)

Please provide the missing information:"

User: "My school is SMK Damansara. I want help with Biology and Chemistry. I prefer English."

Agent: [Uses parse_multiple_onboarding_fields again]
"Perfect! Now I have everything. Let me confirm your details..."
```

## Testing

Run the comprehensive test suite:

```bash
python scripts/test_onboarding.py
```

The test covers:
- Complete onboarding flow
- Field validation
- Error handling
- Skip functionality
- Confirmation process

## Storage

Currently uses in-memory storage for onboarding sessions. In production, consider:
- Database persistence for reliability
- Session cleanup mechanisms
- User profile integration

## Future Enhancements

- **Multi-language forms**: Collect data in user's preferred language
- **Profile editing**: Allow users to update their profile later
- **Advanced validation**: More sophisticated subject and school validation
- **Progress indicators**: Show completion percentage
- **Batch data collection**: Allow multiple fields in single response