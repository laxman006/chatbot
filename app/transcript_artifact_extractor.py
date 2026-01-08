# -*- coding: utf-8 -*-
"""
Transcript Artifact Extractor

Automatically extracts structured knowledge artifacts from transcript text:
- Q&A pairs (with speaker context)
- Objection-response pairs
- Feature capability records
- Decision driver records

Uses LLM for intelligent extraction and structuring.
"""

import json
import re
from typing import List, Dict, Any, Optional
from app.llm_factory import get_llm
from app.transcript_normalizer import TranscriptNormalizer


class TranscriptArtifactExtractor:
    """Extract structured artifacts from transcript text using LLM."""
    
    def __init__(self):
        """Initialize extractor with LLM."""
        self.llm = get_llm(temperature=0.3)  # Lower temperature for more consistent extraction
        self.normalizer = TranscriptNormalizer()
    
    def extract_artifacts(
        self,
        text: str,
        metadata: Dict[str, Any]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Extract all artifacts from transcript.
        
        Args:
            text: Normalized transcript text
            metadata: Transcript metadata (customer, date, etc.)
            
        Returns:
            Dictionary with keys: 'qa_pairs', 'objections', 'features', 'decision_drivers'
        """
        artifacts = {
            'qa_pairs': [],
            'objections': [],
            'features': [],
            'decision_drivers': []
        }
        
        try:
            # Extract Q&A pairs
            artifacts['qa_pairs'] = self.extract_qa_pairs(text, metadata)
            
            # Extract objections
            artifacts['objections'] = self.extract_objections(text, metadata)
            
            # Extract features
            artifacts['features'] = self.extract_features(text, metadata)
            
            # Extract decision drivers
            artifacts['decision_drivers'] = self.extract_decision_drivers(text, metadata)
            
        except Exception as e:
            print(f"[WARNING] Error extracting artifacts: {e}")
            import traceback
            traceback.print_exc()
        
        return artifacts
    
    def extract_qa_pairs(
        self,
        text: str,
        metadata: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Extract Q&A pairs with speaker context.
        
        Returns:
            List of dictionaries with: question, answer, speaker, topic, confidence
        """
        try:
            prompt = f"""Extract question-answer pairs from this customer demo transcript.

Transcript:
{text[:8000]}  # Limit to avoid token limits

Extract all meaningful Q&A pairs where:
- A customer asks a question
- A CloudFuze representative provides an answer

For each Q&A pair, provide:
1. question: The exact question asked
2. answer: The answer provided (can be multi-sentence)
3. speaker: Name of person asking (Customer) or answering (CloudFuze)
4. topic: Main topic (e.g., "Shadow IT", "Pricing", "Integrations", "Features")
5. confidence: "high" | "medium" | "low" based on clarity

Return ONLY a JSON array of objects, no other text. Format:
[
  {{
    "question": "...",
    "answer": "...",
    "speaker": "Customer" or "CloudFuze",
    "topic": "...",
    "confidence": "high"
  }}
]"""

            response = self.llm.invoke(prompt)
            content = response.content if hasattr(response, 'content') else str(response)
            
            # Extract JSON from response
            json_match = re.search(r'\[.*\]', content, re.DOTALL)
            if json_match:
                qa_pairs = json.loads(json_match.group(0))
                return qa_pairs
            else:
                # Fallback: try to parse entire response as JSON
                try:
                    return json.loads(content)
                except:
                    return []
        
        except Exception as e:
            print(f"[WARNING] Error extracting Q&A pairs: {e}")
            # Fallback to simple pattern-based extraction
            return self._fallback_qa_extraction(text)
    
    def extract_objections(
        self,
        text: str,
        metadata: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Extract customer objections and CloudFuze responses.
        
        Returns:
            List of dictionaries with: objection, response, stage, resolution_status
        """
        try:
            prompt = f"""Extract customer objections and responses from this demo transcript.

Transcript:
{text[:8000]}

Identify objections where:
- Customer expresses concerns, doubts, or challenges
- CloudFuze provides a response or clarification

For each objection-response pair, provide:
1. objection: The customer's concern or challenge
2. response: How CloudFuze addressed it
3. stage: "Discovery" | "Evaluation" | "Negotiation" | "Decision"
4. resolution_status: "Resolved" | "Partially Resolved" | "Open" | "Deferred"

Return ONLY a JSON array of objects, no other text. Format:
[
  {{
    "objection": "...",
    "response": "...",
    "stage": "Evaluation",
    "resolution_status": "Resolved"
  }}
]"""

            response = self.llm.invoke(prompt)
            content = response.content if hasattr(response, 'content') else str(response)
            
            json_match = re.search(r'\[.*\]', content, re.DOTALL)
            if json_match:
                objections = json.loads(json_match.group(0))
                return objections
            else:
                try:
                    return json.loads(content)
                except:
                    return []
        
        except Exception as e:
            print(f"[WARNING] Error extracting objections: {e}")
            return []
    
    def extract_features(
        self,
        text: str,
        metadata: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Extract feature descriptions with value propositions.
        
        Returns:
            List of dictionaries with: feature, capability, value, limitations, roadmap_status
        """
        try:
            prompt = f"""Extract product features and capabilities discussed in this demo transcript.

Transcript:
{text[:8000]}

Identify features where:
- CloudFuze explains a product capability
- Value proposition or benefit is mentioned
- Limitations or constraints are discussed

For each feature, provide:
1. feature: Feature name (e.g., "Shadow IT Detection", "License Management")
2. capability: What it does
3. value: Value proposition or benefit mentioned
4. limitations: Any constraints or limitations discussed
5. roadmap_status: "Available" | "In Development" | "Planned" | "Not Available"

Return ONLY a JSON array of objects, no other text. Format:
[
  {{
    "feature": "...",
    "capability": "...",
    "value": "...",
    "limitations": "...",
    "roadmap_status": "Available"
  }}
]"""

            response = self.llm.invoke(prompt)
            content = response.content if hasattr(response, 'content') else str(response)
            
            json_match = re.search(r'\[.*\]', content, re.DOTALL)
            if json_match:
                features = json.loads(json_match.group(0))
                return features
            else:
                try:
                    return json.loads(content)
                except:
                    return []
        
        except Exception as e:
            print(f"[WARNING] Error extracting features: {e}")
            return []
    
    def extract_decision_drivers(
        self,
        text: str,
        metadata: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Extract customer priorities and blocking factors.
        
        Returns:
            List of dictionaries with: customer_priority, blocking_factors, timeline
        """
        try:
            prompt = f"""Extract customer decision drivers from this demo transcript.

Transcript:
{text[:8000]}

Identify:
- Customer priorities (what they care about most)
- Blocking factors (what prevents them from moving forward)
- Timeline or urgency mentioned

For each decision driver, provide:
1. customer_priority: What the customer prioritizes (e.g., "Shadow IT Detection", "Cost Savings")
2. blocking_factors: List of factors blocking progress (e.g., ["Budget cycle", "On-prem AD dependency"])
3. timeline: Timeline mentioned (e.g., "Q2 2026", "Next fiscal year")

Return ONLY a JSON array of objects, no other text. Format:
[
  {{
    "customer_priority": "...",
    "blocking_factors": ["...", "..."],
    "timeline": "..."
  }}
]"""

            response = self.llm.invoke(prompt)
            content = response.content if hasattr(response, 'content') else str(response)
            
            json_match = re.search(r'\[.*\]', content, re.DOTALL)
            if json_match:
                drivers = json.loads(json_match.group(0))
                return drivers
            else:
                try:
                    return json.loads(content)
                except:
                    return []
        
        except Exception as e:
            print(f"[WARNING] Error extracting decision drivers: {e}")
            return []
    
    def _fallback_qa_extraction(self, text: str) -> List[Dict[str, Any]]:
        """
        Fallback pattern-based Q&A extraction if LLM fails.
        
        Uses regex patterns to find questions and following answers.
        """
        qa_pairs = []
        lines = text.split('\n')
        
        current_question = None
        current_answer = []
        current_speaker = None
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Check for speaker
            speaker_match = re.match(r'^([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*(?:,\s*[A-Z][a-zA-Z]+)?)', line)
            if speaker_match:
                current_speaker = speaker_match.group(1).strip()
                # Remove speaker from line
                line = line[len(speaker_match.group(0)):].strip()
            
            # Check for question
            if '?' in line or any(qw in line.lower() for qw in ['how', 'what', 'why', 'when', 'where', 'who', 'which', 'can you', 'could you']):
                # Save previous Q/A
                if current_question and current_answer:
                    qa_pairs.append({
                        "question": current_question,
                        "answer": " ".join(current_answer).strip(),
                        "speaker": current_speaker or "Unknown",
                        "topic": "General",
                        "confidence": "medium"
                    })
                
                current_question = line
                current_answer = []
            
            elif current_question:
                current_answer.append(line)
        
        # Save last Q/A
        if current_question and current_answer:
            qa_pairs.append({
                "question": current_question,
                "answer": " ".join(current_answer).strip(),
                "speaker": current_speaker or "Unknown",
                "topic": "General",
                "confidence": "medium"
            })
        
        return qa_pairs
    
    def extract_topics(self, text: str) -> List[str]:
        """
        Extract main topics from transcript using LLM.
        
        Uses NLP to dynamically identify topics discussed in the conversation.
        
        Args:
            text: Transcript text
            
        Returns:
            List of topic strings
        """
        try:
            prompt = f"""Analyze this customer demo transcript and identify the main topics discussed.

Transcript:
{text[:6000]}

Return ONLY a comma-separated list of the main topics (3-8 topics). Be specific but concise.
Focus on product features, customer concerns, technical discussions, and business topics.

Examples of good topics: Shadow IT Detection, Pricing Models, API Integrations, Workflow Automation, License Management, Security Compliance

Topics:"""

            response = self.llm.invoke(prompt)
            content = response.content if hasattr(response, 'content') else str(response)
            
            # Parse topics from response
            topics = []
            
            # Try comma-separated format first
            if ',' in content:
                topics = [t.strip() for t in content.split(',')]
            elif '|' in content:
                topics = [t.strip() for t in content.split('|')]
            else:
                # Try line-by-line extraction
                for line in content.split('\n'):
                    line = line.strip()
                    # Skip header lines
                    if line and not any(line.lower().startswith(prefix) for prefix in ['topic', 'main', 'the', 'examples']):
                        # Remove numbering (1., 2., etc.)
                        line = re.sub(r'^\d+[\.\)]\s*', '', line)
                        if line and len(line) > 3:
                            topics.append(line)
            
            # Clean and validate topics
            cleaned_topics = []
            for topic in topics:
                topic = topic.strip().rstrip('.,;:')
                # Validate topic length and content
                if topic and 3 < len(topic) < 50:
                    # Remove common prefixes
                    topic = re.sub(r'^(topic|main|the):\s*', '', topic, flags=re.IGNORECASE)
                    cleaned_topics.append(topic)
            
            # Return top 8 topics
            return cleaned_topics[:8]
        
        except Exception as e:
            print(f"[WARNING] LLM topic extraction failed: {e}")
            import traceback
            traceback.print_exc()
            return []

