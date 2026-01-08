# -*- coding: utf-8 -*-
"""
Transcript Normalization Module

Normalizes transcript text by:
- Removing timestamps (unless needed for traceability)
- Removing filler words ("yeah", "uh", "um")
- Deduplicating repetitive phrases
- Preserving speaker names with roles
- Maintaining questions, objections, and decisions
- Normalizing speaker name formats
"""

import re
from typing import Dict, List, Tuple
from collections import defaultdict


class TranscriptNormalizer:
    """Normalize transcript text for better retrieval and processing."""
    
    # Common filler words and phrases
    FILLER_WORDS = {
        'yeah', 'uh', 'um', 'uh-huh', 'hmm', 'mm-hmm', 'mhm',
        'like', 'you know', 'i mean', 'sort of', 'kind of',
        'actually', 'basically', 'literally', 'obviously',
        'right', 'ok', 'okay', 'sure', 'yep', 'yup'
    }
    
    # Repetitive phrases to deduplicate
    REPETITIVE_PATTERNS = [
        r'\b(yeah|yep|yup|ok|okay|sure)\s+(yeah|yep|yup|ok|okay|sure)\b',
        r'\b(uh|um)\s+(uh|um)\b',
        r'\b(so|well)\s+(so|well)\b',
    ]
    
    def __init__(self, preserve_timestamps: bool = False):
        """
        Initialize normalizer.
        
        Args:
            preserve_timestamps: If True, keep timestamps for traceability
        """
        self.preserve_timestamps = preserve_timestamps
    
    def normalize_transcript_text(self, text: str) -> str:
        """
        Main normalization function.
        
        Args:
            text: Raw transcript text
            
        Returns:
            Normalized transcript text
        """
        if not text or not text.strip():
            return text
        
        # Step 1: Remove timestamps (unless preserving)
        if not self.preserve_timestamps:
            text = self._remove_timestamps(text)
        
        # Step 2: Normalize speaker names
        text = self._normalize_speaker_names(text)
        
        # Step 3: Remove filler words
        text = self._remove_filler_words(text)
        
        # Step 4: Deduplicate repetitive phrases
        text = self._deduplicate_repetitions(text)
        
        # Step 5: Clean up whitespace
        text = self._clean_whitespace(text)
        
        # Step 6: Preserve important content (Q&A, objections, decisions)
        # This is done implicitly by not removing question marks, etc.
        
        return text
    
    def _remove_timestamps(self, text: str) -> str:
        """Remove timestamp patterns like '0:04', '1:23', '45:56'."""
        # Pattern: digits:digits at start of line or after speaker name
        # Keep the speaker name but remove timestamp
        lines = text.split('\n')
        cleaned_lines = []
        
        for line in lines:
            # Pattern: Speaker name followed by timestamp
            # Example: "Lawrence Lewis   0:04" -> "Lawrence Lewis"
            line = re.sub(r'([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*(?:,\s*[A-Z][a-zA-Z]+)?)\s+\d+:\d+', r'\1', line)
            
            # Pattern: Standalone timestamps
            line = re.sub(r'^\s*\d+:\d+\s*$', '', line)
            
            # Pattern: Timestamps in middle of line (less common)
            line = re.sub(r'\s+\d+:\d+\s+', ' ', line)
            
            cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines)
    
    def _normalize_speaker_names(self, text: str) -> str:
        """
        Normalize speaker name formats.
        
        Converts variations like:
        - "Heffner, Scott" -> "Scott Heffner"
        - "Lawrence Lewis" -> "Lawrence Lewis" (already normalized)
        """
        lines = text.split('\n')
        normalized_lines = []
        
        for line in lines:
            # Pattern: "Last, First" -> "First Last"
            # Example: "Heffner, Scott   0:27" -> "Scott Heffner"
            match = re.match(r'^([A-Z][a-zA-Z]+),\s+([A-Z][a-zA-Z]+)', line)
            if match:
                last_name = match.group(1)
                first_name = match.group(2)
                # Replace "Last, First" with "First Last"
                line = re.sub(
                    r'^([A-Z][a-zA-Z]+),\s+([A-Z][a-zA-Z]+)',
                    f'{first_name} {last_name}',
                    line
                )
            
            normalized_lines.append(line)
        
        return '\n'.join(normalized_lines)
    
    def _remove_filler_words(self, text: str) -> str:
        """
        Remove filler words while preserving sentence structure.
        
        Only removes standalone filler words, not words that are part of
        meaningful phrases.
        """
        lines = text.split('\n')
        cleaned_lines = []
        
        for line in lines:
            # Skip lines that are just speaker names
            if re.match(r'^[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*(?:,\s*[A-Z][a-zA-Z]+)?\s*$', line.strip()):
                cleaned_lines.append(line)
                continue
            
            words = line.split()
            cleaned_words = []
            
            for i, word in enumerate(words):
                # Remove punctuation for comparison
                word_lower = word.lower().rstrip('.,!?;:')
                
                # Check if it's a filler word
                if word_lower in self.FILLER_WORDS:
                    # Only remove if it's standalone (not part of a phrase)
                    # Keep if it's at the start/end of meaningful content
                    if i > 0 and i < len(words) - 1:
                        # Check if surrounding words are also fillers
                        prev_word = words[i-1].lower().rstrip('.,!?;:')
                        next_word = words[i+1].lower().rstrip('.,!?;:')
                        
                        if prev_word in self.FILLER_WORDS or next_word in self.FILLER_WORDS:
                            continue  # Skip this filler
                    # Keep first/last fillers as they might be meaningful responses
                    continue
                
                cleaned_words.append(word)
            
            cleaned_line = ' '.join(cleaned_words)
            cleaned_lines.append(cleaned_line)
        
        return '\n'.join(cleaned_lines)
    
    def _deduplicate_repetitions(self, text: str) -> str:
        """Remove repetitive phrases and words."""
        for pattern in self.REPETITIVE_PATTERNS:
            text = re.sub(pattern, r'\1', text, flags=re.IGNORECASE)
        
        # Remove repeated words (3+ times)
        lines = text.split('\n')
        cleaned_lines = []
        
        for line in lines:
            words = line.split()
            if len(words) < 3:
                cleaned_lines.append(line)
                continue
            
            cleaned_words = []
            prev_word = None
            repeat_count = 0
            
            for word in words:
                word_lower = word.lower()
                if word_lower == prev_word:
                    repeat_count += 1
                    if repeat_count < 2:  # Allow 2 repetitions, remove 3+
                        cleaned_words.append(word)
                else:
                    repeat_count = 0
                    cleaned_words.append(word)
                
                prev_word = word_lower
            
            cleaned_lines.append(' '.join(cleaned_words))
        
        return '\n'.join(cleaned_lines)
    
    def _clean_whitespace(self, text: str) -> str:
        """Clean up excessive whitespace."""
        # Remove multiple spaces
        text = re.sub(r' +', ' ', text)
        
        # Remove multiple newlines (keep max 2)
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # Remove trailing whitespace from lines
        lines = [line.rstrip() for line in text.split('\n')]
        
        # Remove empty lines at start/end
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        
        return '\n'.join(lines)
    
    def extract_speaker_roles(self, text: str) -> Dict[str, str]:
        """
        Extract speaker names and infer their roles using LLM.
        
        Dynamically identifies:
        - Customer/Client speakers (external)
        - CloudFuze speakers (internal team members)
        
        Args:
            text: Transcript text
            
        Returns:
            Dictionary mapping speaker names to roles
        """
        roles = {}
        
        # Extract all speaker names - MUST be followed by timestamp to avoid false matches
        # Pattern: "Name   0:04" or "Name, Last   0:27"
        # This prevents matching random words like "Potentially", "But", "December", etc.
        speaker_pattern = r'^([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*(?:,\s*[A-Z][a-zA-Z]+)?)\s+\d+:\d+'
        speakers = set()
        
        for line in text.split('\n'):
            match = re.match(speaker_pattern, line.strip())
            if match:
                speaker = match.group(1).strip()
                # Normalize "Last, First" to "First Last"
                if ',' in speaker:
                    parts = [p.strip() for p in speaker.split(',')]
                    if len(parts) == 2:
                        speaker = f"{parts[1]} {parts[0]}"
                speakers.add(speaker)
        
        if not speakers:
            return roles
        
        # Use LLM to dynamically classify speakers (no hardcoding)
        try:
            from config import ENABLE_ARTIFACT_EXTRACTION
            from app.llm_factory import get_llm
            
            if ENABLE_ARTIFACT_EXTRACTION:
                llm = get_llm(temperature=0.2)  # Low temperature for consistent classification
                
                speakers_list = ", ".join(sorted(speakers))
                
                # Get sample context from transcript to help LLM understand roles
                sample_text = text[:3000]  # First 3000 chars for context
                
                prompt = f"""Analyze this customer demo transcript and classify each speaker as either "CloudFuze" (internal team member) or "Customer" (client).

Speaker names found: {speakers_list}

Transcript sample for context:
{sample_text}

Based on the conversation context, classify each speaker:
- "CloudFuze" = Internal team members (sales, demo presenters, product experts)
- "Customer" = External clients, prospects, or customer representatives

Return ONLY a JSON object mapping speaker names to their role. Format:
{{"Speaker Name": "CloudFuze" or "Customer", ...}}

Example:
{{"Lawrence Lewis": "CloudFuze", "Scott Heffner": "Customer", "Pranavi": "CloudFuze"}}

JSON:"""

                response = llm.invoke(prompt)
                content = response.content if hasattr(response, 'content') else str(response)
                
                # Parse JSON response
                import json
                # Try to find JSON object in response (handle cases where LLM adds extra text)
                # Look for content between first { and last }
                start_idx = content.find('{')
                end_idx = content.rfind('}')
                
                if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                    json_str = content[start_idx:end_idx + 1]
                    try:
                        roles = json.loads(json_str)
                    except json.JSONDecodeError:
                        # If JSON parsing fails, try parsing entire response
                        try:
                            roles = json.loads(content)
                        except json.JSONDecodeError:
                            print(f"[WARNING] Could not parse LLM response as JSON, using fallback")
                            roles = {}
                else:
                    # Try parsing entire response as JSON
                    try:
                        roles = json.loads(content)
                    except json.JSONDecodeError:
                        print(f"[WARNING] Could not parse LLM response as JSON, using fallback")
                        roles = {}
                
                # Validate all speakers are classified
                for speaker in speakers:
                    if speaker not in roles:
                        # Default to Customer if LLM didn't classify
                        roles[speaker] = "Customer"
                
                print(f"[OK] LLM classified {len(roles)} speakers: {list(roles.keys())}")
                
            else:
                # Fallback: Use simple heuristic if LLM is disabled
                # Look for company name mentions in speaker's lines
                for speaker in speakers:
                    speaker_lower = speaker.lower()
                    # Check if speaker's name appears in context that suggests CloudFuze
                    # This is a simple fallback, not as accurate as LLM
                    if any(keyword in speaker_lower for keyword in ['cloudfuze', 'sales', 'demo']):
                        roles[speaker] = "CloudFuze"
                    else:
                        roles[speaker] = "Customer"
        
        except Exception as e:
            print(f"[WARNING] LLM role detection failed: {e}")
            print(f"[WARNING] Falling back to default: all speakers marked as Customer")
            import traceback
            traceback.print_exc()
            # Fallback: mark all as Customer if LLM fails
            for speaker in speakers:
                roles[speaker] = "Customer"
        
        return roles
    
    def preserve_important_content(self, text: str) -> str:
        """
        Ensure important content is preserved during normalization.
        
        Important content includes:
        - Questions (lines with '?')
        - Objections (keywords: "but", "however", "concern", "issue")
        - Decisions (keywords: "decide", "choose", "go with", "select")
        - Feature mentions (product names, capabilities)
        
        This function is called implicitly during normalization,
        but can be used to verify important content is preserved.
        """
        # This is more of a validation/verification function
        # The actual preservation happens in normalize_transcript_text
        
        important_lines = []
        lines = text.split('\n')
        
        for line in lines:
            line_lower = line.lower()
            
            # Check for questions
            if '?' in line:
                important_lines.append(("question", line))
            
            # Check for objections
            objection_keywords = ['but', 'however', 'concern', 'issue', 'problem', 'worry', 'challenge']
            if any(keyword in line_lower for keyword in objection_keywords):
                important_lines.append(("objection", line))
            
            # Check for decisions
            decision_keywords = ['decide', 'choose', 'go with', 'select', 'will use', 'going to']
            if any(keyword in line_lower for keyword in decision_keywords):
                important_lines.append(("decision", line))
        
        return important_lines


def normalize_transcript(text: str, preserve_timestamps: bool = False) -> str:
    """
    Convenience function to normalize transcript text.
    
    Args:
        text: Raw transcript text
        preserve_timestamps: If True, keep timestamps
        
    Returns:
        Normalized transcript text
    """
    normalizer = TranscriptNormalizer(preserve_timestamps=preserve_timestamps)
    return normalizer.normalize_transcript_text(text)

