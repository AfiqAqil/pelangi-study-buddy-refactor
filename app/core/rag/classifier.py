"""Simple content classifier for RAG routing decisions."""

from enum import Enum
from typing import Optional, Dict, Any

from app.core.logging import logger


class ContentType(Enum):
    """Content types for routing decisions."""
    EDUCATIONAL = "educational"
    GENERAL_CONVERSATION = "general_conversation"
    SUBJECT_MANAGEMENT = "subject_management"
    CURRENT_EVENTS = "current_events"


def classify_content(query: str, subject_context: Optional[Dict[str, Any]] = None) -> ContentType:
    """Simple content classification using basic rules.
    
    Args:
        query: User's query text
        subject_context: Optional subject context
        
    Returns:
        ContentType: The classified content type
    """
    if not query or len(query.strip()) < 2:
        return ContentType.GENERAL_CONVERSATION
    
    query_lower = query.lower().strip()
    
    # Check for conversation patterns first
    conversation_patterns = [
        'hello', 'hi', 'hey', 'how are you', 'good morning', 'good afternoon', 
        'good evening', 'thank you', 'thanks', 'bye', 'goodbye',
        'halo', 'hai', 'apa khabar', 'selamat pagi', 'selamat petang', 
        'selamat malam', 'terima kasih', 'selamat tinggal',
        '你好', '早上好', '下午好', '晚上好', '谢谢', '再见', '你好吗'
    ]
    
    if any(pattern in query_lower for pattern in conversation_patterns):
        logger.debug("classified_as_conversation", query=query[:50])
        return ContentType.GENERAL_CONVERSATION
    
    # Check for subject management requests
    subject_management_patterns = [
        'select subject', 'choose subject', 'change subject', 'switch subject',
        'pilih subjek', 'tukar subjek', 'pilih mata pelajaran',
        '选择科目', '更改科目', '切换科目'
    ]
    
    if any(pattern in query_lower for pattern in subject_management_patterns):
        return ContentType.SUBJECT_MANAGEMENT
    
    # Check for current events
    current_events_patterns = [
        'news', 'latest', 'recent', 'current', 'today', 'yesterday', 
        '2024', '2025', 'breaking news',
        'berita', 'terkini', 'semasa', 'hari ini', 'semalam',
        '新闻', '最新', '最近', '当前', '今天', '昨天'
    ]
    
    if any(pattern in query_lower for pattern in current_events_patterns):
        return ContentType.CURRENT_EVENTS
    
    # Check for educational content
    educational_indicators = [
        # Question patterns
        'what is', 'how does', 'why does', 'how to', 'explain', 'define', 'calculate',
        'apa itu', 'bagaimana', 'mengapa', 'cara', 'terangkan', 'takrifkan', 'kira',
        '什么是', '如何', '为什么', '怎么', '解释', '定义', '计算',
        
        # Educational terms
        'formula', 'equation', 'solution', 'answer', 'problem', 'exercise',
        'formula', 'persamaan', 'penyelesaian', 'jawapan', 'masalah', 'latihan',
        '公式', '方程', '解', '答案', '问题', '练习',
        
        # Subject references
        'biology', 'chemistry', 'physics', 'mathematics', 'science',
        'biologi', 'kimia', 'fizik', 'matematik', 'sains',
        '生物', '化学', '物理', '数学', '科学',
        
        # Academic references
        'textbook', 'chapter', 'page', 'spm', 'form 4', 'form 5',
        'buku teks', 'bab', 'muka surat', 'tingkatan 4', 'tingkatan 5',
        '教科书', '章节', '页', '中四', '中五'
    ]
    
    if any(indicator in query_lower for indicator in educational_indicators):
        logger.debug("classified_as_educational", query=query[:50])
        return ContentType.EDUCATIONAL
    
    # Check subject-specific keywords if context available
    if subject_context and subject_context.get('current_subject'):
        subject_keywords = {
            'biology': ['cell', 'dna', 'protein', 'photosynthesis', 'evolution'],
            'chemistry': ['atom', 'molecule', 'reaction', 'acid', 'base'], 
            'physics': ['force', 'energy', 'wave', 'motion', 'electricity'],
            'mathematics': ['function', 'graph', 'algebra', 'geometry', 'calculus']
        }
        
        subject = subject_context['current_subject'].lower()
        if subject in subject_keywords:
            if any(keyword in query_lower for keyword in subject_keywords[subject]):
                logger.debug("classified_as_educational_via_subject", subject=subject, query=query[:50])
                return ContentType.EDUCATIONAL
    
    # Default to conversation for ambiguous queries
    logger.debug("classified_as_conversation_default", query=query[:50])
    return ContentType.GENERAL_CONVERSATION


def should_use_rag(content_type: ContentType, rag_enabled: bool = True) -> bool:
    """Determine if RAG should be used for this content type."""
    return rag_enabled and content_type == ContentType.EDUCATIONAL


def get_recommended_tool(content_type: ContentType) -> str:
    """Get recommended tool based on content type."""
    if content_type == ContentType.EDUCATIONAL:
        return "comprehensive_rag_search"
    elif content_type == ContentType.SUBJECT_MANAGEMENT:
        return "select_subject"
    elif content_type == ContentType.CURRENT_EVENTS:
        return "duckduckgo_search"
    else:
        return "none"