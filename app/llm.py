
import asyncio
from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_openai import ChatOpenAI
# RetrievalQA is now handled differently in langchain 1.x
from config import SYSTEM_PROMPT
from app.llm_factory import get_llm


class AsyncStreamHandler(BaseCallbackHandler):
    def __init__(self):
        self.queue = asyncio.Queue()

    def on_llm_new_token(self, token: str, **kwargs):
        self.queue.put_nowait(token)


def format_docs(docs):
    """Format documents with their content and metadata (especially download URLs, video URLs, and tags)."""
    formatted = []
    sources_used = []
    
    for doc in docs:
        content = doc.page_content
        metadata = doc.metadata
        
        # Track source information for logging
        source = metadata.get('source', 'Unknown')
        tag = metadata.get("tag", "unknown")
        sources_used.append(f"{source} ({tag})")
        
        # Include tag information in context (for chatbot to know data source)
        tag_info = f"[SOURCE: {tag}]"
        
        # ========== SPECIAL FORMATTING FOR JIRA TICKETS ==========
        if metadata.get("source_type") == "jira" or "jira" in tag.lower():
            ticket_key = metadata.get('ticket_key', '')
            ticket_url = metadata.get('url', '')
            section = metadata.get('section', '')
            root_cause = metadata.get('root_cause', '')
            fix_description = metadata.get('fix_description', '')
            combination = metadata.get('combination', '')
            status = metadata.get('status', '')
            
            # Build Jira ticket header with solution emphasis
            jira_header = f"{tag_info}\n"
            jira_header += f"JIRA TICKET: {ticket_key}\n"
            if ticket_url:
                jira_header += f"Ticket URL: {ticket_url}\n"
            if status:
                jira_header += f"Status: {status}\n"
            if combination:
                jira_header += f"Migration Type: {combination}\n"
            
            # Emphasize solution sections with clear labels
            if section == "root_cause" and root_cause:
                jira_header += "\n⚠️ ROOT CAUSE (Why this issue occurred):\n"
            elif section == "fix_description" and fix_description:
                jira_header += "\n✅ SOLUTION/FIX (How to resolve this issue):\n"
            elif section == "summary":
                jira_header += "\n📋 ISSUE SUMMARY:\n"
            elif section == "description":
                jira_header += "\n📝 ISSUE DESCRIPTION:\n"
            elif section and "comment" in section.lower():
                jira_header += "\n💬 DEVELOPER SOLUTION/COMMENT:\n"
            elif section and "ai" in section.lower():
                jira_header += "\n🤖 AI-GENERATED SOLUTION:\n"
            
            content = jira_header + content
            
            # Add solution reference at the end if this is a solution section
            if section in ["root_cause", "fix_description"] and ticket_key:
                content += f"\n\n[Reference: Jira Ticket {ticket_key} - {ticket_url if ticket_url else 'See ticket details above'}]"
        
        # For SharePoint documents, add additional context for better understanding
        elif metadata.get("source_type") == "sharepoint":
            file_name = metadata.get('file_name', '')
            folder_path = metadata.get('folder_path', '')
            if file_name:
                content = f"{tag_info}\nFile: {file_name}\nFolder: {folder_path}\n\n{content}"
        elif metadata.get("source_type") == "outlook" or "email" in tag.lower():
            # Add email-specific context to help LLM understand email threads
            subject = metadata.get('conversation_topic') or metadata.get('subject', '')
            participants = metadata.get('participants', '')
            date_range = metadata.get('date_range', '')
            email_count = metadata.get('email_count', '')
            first_date = metadata.get('first_email_date', '')
            last_date = metadata.get('last_email_date', '')
            
            email_header = f"{tag_info}\n"
            email_header += "EMAIL THREAD:\n"
            if subject:
                email_header += f"Thread Subject: {subject}\n"
            if participants:
                email_header += f"Participants: {participants}\n"
            if date_range:
                email_header += f"Date Range: {date_range}\n"
            elif first_date or last_date:
                if first_date and last_date:
                    email_header += f"Date Range: {first_date} to {last_date}\n"
                elif first_date:
                    email_header += f"First Email Date: {first_date}\n"
                elif last_date:
                    email_header += f"Last Email Date: {last_date}\n"
            if email_count:
                email_header += f"Number of Emails in Thread: {email_count}\n"
            email_header += "\n--- Email Thread Content ---\n\n"
            
            content = email_header + content
        else:
            content = f"{tag_info}\n{content}"
        
        # Include download URL for certificates and downloadable files (policy documents, etc.) in the context
        if metadata.get("is_downloadable") and metadata.get("download_url"):
            file_name = metadata.get('file_name', 'File')
            download_url = metadata.get('download_url')
            is_cert = metadata.get('is_certificate', False)
            # Escape any curly braces that might interfere with string formatting
            file_name_escaped = file_name.replace('{', '{{').replace('}', '}}')
            download_url_escaped = download_url.replace('{', '{{').replace('}', '}}')
            content += f"\n\n[DOWNLOAD LINK: {file_name_escaped} (is_certificate: {is_cert}, is_downloadable: True) - {download_url_escaped}]"
        
        # Include video URL for demo videos in the context
        if metadata.get("content_type") == "sharepoint_video" and metadata.get("video_url"):
            video_name = metadata.get("video_name") or metadata.get("file_name", "Video")
            video_url = metadata.get("video_url")
            video_type = metadata.get("video_type", "video")
            # Escape any curly braces that might interfere with string formatting
            video_name_escaped = video_name.replace('{', '{{').replace('}', '}}')
            video_url_escaped = video_url.replace('{', '{{').replace('}', '}}')
            content += f"\n\n[VIDEO LINK: {video_name_escaped} ({video_type}) - {video_url_escaped}]"
        
        # Include blog post URL for blog content in the context
        if metadata.get("is_blog_post") and metadata.get("post_url"):
            post_title = metadata.get('post_title', 'Blog Post')
            post_url = metadata.get('post_url')
            # Escape any curly braces that might interfere with string formatting
            post_title_escaped = post_title.replace('{', '{{').replace('}', '}}')
            post_url_escaped = post_url.replace('{', '{{').replace('}', '}}')
            content += f"\n\n[BLOG POST LINK: {post_title_escaped} - {post_url_escaped}]"
        
        formatted.append(content)
    
    return formatted


def setup_qa_chain(retriever):
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.runnables import RunnablePassthrough
    from langchain_core.output_parsers import StrOutputParser
    
    # Create a custom prompt template with system message
    prompt_template = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("human", "Context: {context}\n\nQuestion: {question}")
    ])
    
    # Use factory function to get the appropriate LLM based on configuration
    llm = get_llm(
        temperature=0.1,  # Low temperature for consistent, deterministic responses
        streaming=True, 
        max_tokens=1500   # Allow longer responses for comprehensive answers
    )
    
    # Create the document chain using the new langchain 1.x approach
    # Use the module-level format_docs function
    
    document_chain = prompt_template | llm | StrOutputParser()
    
    # Create a wrapper to maintain compatibility with the existing interface
    class SemanticRetrievalQA:
        def __init__(self, document_chain, retriever):
            self.document_chain = document_chain
            self.retriever = retriever
        
        def invoke(self, inputs):
            # Extract the query from the inputs dict
            query = inputs.get("query", "")
            
            # Get relevant documents using pure semantic search
            from app.vectorstore import vectorstore
            
            # PURE SEMANTIC SEARCH - Let the vectorstore handle semantic understanding
            # No predefined keywords, no hardcoded terms, no forced inclusions
            
            # Primary semantic search with the original query
            relevant_docs = vectorstore.similarity_search(query, k=25)
            
            # Secondary semantic search with query rephrasing for better coverage
            # This helps catch semantically similar but differently worded content
            try:
                # Use the LLM with ZERO temperature to create deterministic rephrasings
                # This ensures consistent retrieval for the same query
                rephrase_llm = get_llm(
                    temperature=0.0,  # Zero temperature for deterministic rephrasing
                    max_tokens=200
                )
                
                rephrase_prompt = f"""
                Rephrase this question in 2-3 different ways to help find relevant information:
                Original: {query}
                
                Provide 2-3 alternative phrasings that mean the same thing but use different words.
                Each rephrasing should be on a new line and be concise.
                """
                
                rephrase_result = rephrase_llm.invoke(rephrase_prompt)
                rephrased_queries = [line.strip() for line in rephrase_result.content.split('\n') if line.strip()]
                
                # Search with each rephrased query
                for rephrased_query in rephrased_queries[:2]:  # Limit to 2 rephrasings
                    additional_docs = vectorstore.similarity_search(rephrased_query, k=12)
                    relevant_docs.extend(additional_docs)
                    
            except Exception as e:
                # If rephrasing fails, continue with original query only
                print(f"Query rephrasing failed: {e}")
                pass
            
            # Deduplicate documents while preserving relevance order
            seen_ids = set()
            unique_docs = []
            
            for doc in relevant_docs:
                # Create a unique identifier for the document
                doc_id = f"{doc.metadata.get('source', '')}_{doc.page_content[:50]}"
                if doc_id not in seen_ids:
                    seen_ids.add(doc_id)
                    unique_docs.append(doc)
            
            # Limit to reasonable number of documents for processing
            # Too many documents can overwhelm the LLM and reduce quality
            final_docs = unique_docs[:30]
            
            # Format the documents for the context
            formatted_docs = format_docs(final_docs)
            context = "\n\n".join(formatted_docs)
            
            # Invoke the document chain with the semantically relevant documents
            result = self.document_chain.invoke({
                "context": context,
                "question": query
            })
            
            return {"result": result}
    
    qa_chain = SemanticRetrievalQA(document_chain, retriever)
    return qa_chain


def _generate_simple_keyword_recommendations(user_question: str) -> list:
    """
    Simple keyword-based recommendations when no docs are available.
    Zero cost, instant generation.
    """
    question_lower = user_question.lower()
    questions = []
    
    # CloudFuze specific questions based on keywords
    if any(word in question_lower for word in ['cloudfuze', 'what is', 'about', 'hello', 'hi']):
        questions = [
            "What are CloudFuze's main features?",
            "How does CloudFuze pricing work?",
            "What platforms does CloudFuze support?",
            "How do I get started with CloudFuze?"
        ]
    elif any(word in question_lower for word in ['migrate', 'migration', 'transfer', 'move']):
        questions = [
            "How long does a typical migration take?",
            "What data can be migrated?",
            "How do I prepare for migration?",
            "Can I schedule migrations automatically?"
        ]
    elif any(word in question_lower for word in ['price', 'cost', 'pricing', 'plan']):
        questions = [
            "What features are included in each plan?",
            "Is there a free trial available?",
            "Are there enterprise discounts?",
            "How is pricing calculated?"
        ]
    elif any(word in question_lower for word in ['email', 'outlook', 'gmail']):
        questions = [
            "How do I migrate email folders?",
            "Are email attachments migrated?",
            "Can I migrate email rules?",
            "How are contacts handled?"
        ]
    elif any(word in question_lower for word in ['sharepoint', 'onedrive', 'drive']):
        questions = [
            "How do file permissions work?",
            "Can I migrate large files?",
            "Are file versions preserved?",
            "How do I migrate SharePoint sites?"
        ]
    elif any(word in question_lower for word in ['security', 'safe', 'encrypt']):
        questions = [
            "What security certifications does CloudFuze have?",
            "Is data encrypted during migration?",
            "What compliance standards are met?",
            "How is my data protected?"
        ]
    else:
        # Generic CloudFuze questions
        questions = [
            "What migration services does CloudFuze offer?",
            "How do I get technical support?",
            "What are the key features?",
            "Can I see a demo or trial?"
        ]
    
    return questions[:4]


def generate_recommended_questions_from_docs(user_question: str, retrieved_docs: list, bot_response: str = None) -> list:
    """
    Generate 4-5 recommended follow-up questions using ALREADY-RETRIEVED documents.
    
    This is the MOST COST-EFFECTIVE approach:
    - NO extra embeddings
    - NO extra vector searches
    - Only ONE small LLM call to extract suggestions from docs we already have
    
    Similar to Perplexity's Comet feature, but optimized for cost.
    
    Args:
        user_question: The original question the user asked
        retrieved_docs: The documents already retrieved for answering (langchain Document objects)
        bot_response: Optional - the bot's answer (can help contextualize)
    
    Returns:
        List of 4-5 recommended follow-up questions as strings
    """
    import json
    
    # If no docs, use simple keyword-based recommendations
    if not retrieved_docs:
        return _generate_simple_keyword_recommendations(user_question)
    
    try:
        # Extract relevant content and metadata from retrieved docs
        docs_content = []
        topics_set = set()
        
        for doc in retrieved_docs[:8]:  # Use top 8 docs to keep context manageable
            # Get the actual content
            content = doc.page_content[:300]  # First 300 chars per doc
            docs_content.append(content)
            
            # Extract topics/tags for better context
            tag = doc.metadata.get("tag", "")
            if tag and tag.lower() not in ['unknown', 'general']:
                topics_set.add(tag)
        
        # Build a concise context from retrieved docs
        docs_text = "\n\n---\n\n".join(docs_content)
        topics_hint = f"Available topics: {', '.join(list(topics_set)[:5])}" if topics_set else ""
        
        # Create a focused prompt for generating recommendations
        prompt = f"""You are helping generate follow-up questions for a CloudFuze knowledge base chatbot.

User asked: "{user_question}"

Here are the retrieved documents that were used to answer:
{docs_text}

{topics_hint}

Based on these documents, generate 4-5 natural follow-up questions that:
1. Go deeper into topics mentioned in the documents
2. Are practical and actionable
3. Are relevant to CloudFuze (cloud migration, data sync, security, pricing, features)
4. Are concise (max 12 words each)
5. Avoid generic questions like "tell me more" or "what else"

Return ONLY a valid JSON array of questions, nothing else.
Example format: ["Question 1?", "Question 2?", "Question 3?", "Question 4?"]
"""

        # Use a small, fast LLM call with factory function
        llm = get_llm(
            temperature=0.7,  # Some creativity for diverse questions
            max_tokens=200    # Keep it minimal
        )
        
        response = llm.invoke(prompt)
        raw_content = response.content.strip()
        
        # Try to parse as JSON
        try:
            # Remove markdown code blocks if present
            if raw_content.startswith("```"):
                raw_content = raw_content.split("```")[1]
                if raw_content.startswith("json"):
                    raw_content = raw_content[4:]
                raw_content = raw_content.strip()
            
            questions = json.loads(raw_content)
            
            if isinstance(questions, list):
                # Clean and validate questions
                cleaned = []
                for q in questions[:5]:  # Max 5 questions
                    if isinstance(q, str) and len(q) > 10 and len(q) < 200:
                        # Remove numbering if present
                        q = q.lstrip('0123456789.-•*) ').strip()
                        if q and not q.startswith('['):
                            cleaned.append(q)
                
                return cleaned[:4]  # Return exactly 4 questions
        except json.JSONDecodeError:
            # Fallback: parse line by line
            lines = raw_content.split('\n')
            questions = []
            for line in lines:
                line = line.strip()
                # Remove common prefixes
                line = line.lstrip('0123456789.-•*"[] ').strip().rstrip('",')
                if line and len(line) > 10 and len(line) < 200:
                    questions.append(line)
            
            return questions[:4]
        
        return []
        
    except Exception as e:
        print(f"[WARNING] Failed to generate recommended questions: {e}")
        import traceback
        traceback.print_exc()
        return []  # Non-critical feature, fail gracefully
