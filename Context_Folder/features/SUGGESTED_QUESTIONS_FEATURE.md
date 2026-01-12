# Suggested Questions Feature

## Overview

Provides recommended follow-up questions to users based on their current query and retrieved documents. Helps users explore related topics.

---

## Related Files

### Backend Files

#### Question Generation
- **`app/llm.py`**
  - `generate_recommended_questions_from_docs()` - Generate questions from docs (line 274)
  - `_generate_simple_keyword_recommendations()` - Keyword-based questions (line 211)

#### Suggested Questions Endpoints
- **`app/routes/suggested_questions.py`**
  - Suggested questions API routes
  - Question management endpoints

#### Question Models
- **`app/models/suggested_question.py`**
  - Suggested question model
  - Question schema

#### Question Seeding
- **`scripts/seed_suggested_questions.py`**
  - Seed initial suggested questions
  - Question database management

### Frontend Files

#### Question Display
- **`frontend/src/components/ChatInterface.tsx`**
  - Display suggested questions
  - Question click handling

#### API Integration
- **`frontend/src/lib/api.ts`**
  - `getSuggestedQuestions()` - Get suggested questions API call

---

## Feature Workflow

1. **User asks question** → Query processed
2. **Documents retrieved** → Relevant docs found
3. **Questions generated** → LLM generates 4-5 follow-up questions
4. **Questions displayed** → Shown below response
5. **User clicks question** → New query with suggested question
6. **Process repeats** → New response generated

---

## Key Functions

### Backend
- `generate_recommended_questions_from_docs()` - Main generation function
- `_generate_simple_keyword_recommendations()` - Fallback keyword questions

### Frontend
- Question display in chat interface
- Question click handler

---

## Question Generation Methods

### Method 1: Document-Based (Primary)
- Uses retrieved documents
- LLM generates questions from doc content
- More relevant and contextual
- Cost: 1 small LLM call

### Method 2: Keyword-Based (Fallback)
- Uses keyword matching
- Predefined questions by topic
- Zero cost, instant
- Less contextual

---

## Question Generation Process

### Document-Based Generation
1. **Extract content** - Get top 8 documents (first 300 chars each)
2. **Extract topics** - Get tags/topics from metadata
3. **Build prompt** - Create prompt with user question, docs, topics
4. **LLM call** - Generate questions (temperature=0.7, max_tokens=200)
5. **Parse response** - Parse JSON or line-by-line
6. **Validate** - Clean and validate questions (10-200 chars)
7. **Return** - Return exactly 4 questions

### Keyword-Based Generation
1. **Check keywords** - Match question to keywords
2. **Return predefined** - Return 4 predefined questions
3. **No LLM call** - Instant, free

---

## Question Categories

### CloudFuze General
- "What are CloudFuze's main features?"
- "How does CloudFuze pricing work?"
- "What platforms does CloudFuze support?"

### Migration
- "How long does a typical migration take?"
- "What data can be migrated?"
- "How do I prepare for migration?"

### Pricing
- "What features are included in each plan?"
- "Is there a free trial available?"
- "How is pricing calculated?"

### Email/Outlook
- "How do I migrate email folders?"
- "Are email attachments migrated?"
- "Can I migrate email rules?"

### SharePoint/OneDrive
- "How do file permissions work?"
- "Can I migrate large files?"
- "Are file versions preserved?"

### Security
- "What security certifications does CloudFuze have?"
- "Is data encrypted during migration?"
- "What compliance standards are met?"

---

## Question Display

### Format
- 4 questions displayed
- Clickable buttons/cards
- Below chat response
- Styled consistently

### Interaction
- Click question → New query
- Question becomes user message
- New response generated
- Questions updated for new response

---

## Configuration

**Generation Parameters:**
- Number of questions: 4
- Max tokens: 200
- Temperature: 0.7
- Documents used: Top 8

**Validation:**
- Min length: 10 characters
- Max length: 200 characters
- Remove numbering/prefixes

---

## Cost Optimization

### Document-Based (Cost-Effective)
- Uses already-retrieved documents
- No extra embeddings
- No extra vector searches
- Only 1 small LLM call

### Keyword-Based (Free)
- Zero cost
- Instant generation
- Predefined questions

---

## Example Output

**User Question:** "How does license management work?"

**Generated Questions:**
1. "What is the renewal calendar feature?"
2. "How does CloudFuze calculate license utilization?"
3. "What cost savings can CloudFuze Manage provide?"
4. "How do you handle inactive users with licenses?"

---

**Last Updated:** 2025-01-09
