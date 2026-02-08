# -*- coding: utf-8 -*-
"""
Langfuse Integration for RAG Chatbot Observability

This module handles logging all chat interactions to Langfuse for observability.
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any
from langfuse import Langfuse
from config import LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST

# Initialize Langfuse client
try:
    if not LANGFUSE_SECRET_KEY or not LANGFUSE_PUBLIC_KEY:
        print("[!] Langfuse credentials not found - observability disabled")
        langfuse_client = None
    else:
        langfuse_client = Langfuse(
            public_key=LANGFUSE_PUBLIC_KEY,
            secret_key=LANGFUSE_SECRET_KEY,
            host=LANGFUSE_HOST
        )
        print(f"[OK] Langfuse initialized: {LANGFUSE_HOST}")
except Exception as e:
    print(f"[!] Langfuse initialization failed: {e}")
    langfuse_client = None


class LangfuseTracker:
    """Handles Langfuse trace logging"""
    
    def __init__(self):
        self.client = langfuse_client
    
    def create_trace(
        self, 
        user_id: str, 
        question: str, 
        answer: str,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        user_name: Optional[str] = None,
        user_email: Optional[str] = None
    ) -> Optional[str]:
        """Create a simple chat trace (for non-RAG queries)."""
        if not self.client:
            print("[WARNING] Langfuse client not initialized - cannot create trace")
            print("[WARNING] Check LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, and LANGFUSE_HOST in config")
            return None
        
        try:
            # Build metadata (using UTC for consistency)
            trace_metadata = {**(metadata or {}), "timestamp": datetime.now(timezone.utc).isoformat()}
            
            trace = self.client.trace(
                name="chat_interaction",
                user_id=user_id,
                session_id=session_id or user_id,
                input=question,
                output=answer,
                metadata=trace_metadata,
                tags=["chat"]
            )
            
            trace.generation(
                name="chat_response",
                model="gpt-4o-mini",
                input=question,
                output=answer,
                metadata={"timestamp": datetime.now(timezone.utc).isoformat()}
            )
            
            trace_id = trace.id
            print(f"[LANGFUSE] ✓ Created trace: {trace_id}")
            return trace_id
            
        except Exception as e:
            print(f"[ERROR] Langfuse trace creation failed: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def add_feedback(self, trace_id: str, rating: str, comment: Optional[str] = None) -> bool:
        """Add user feedback (thumbs up/down) to a trace."""
        if not self.client:
            print("[WARNING] Langfuse client not initialized - feedback not logged")
            return False
        
        # ✅ STRICT VALIDATION: Reject fallback IDs (they don't exist in Langfuse)
        if trace_id.startswith('feedback_fallback_'):
            print(f"[ERROR] Rejected fallback trace_id: {trace_id}")
            print(f"[ERROR] Fallback trace_ids don't exist in Langfuse - feedback cannot be attached")
            raise ValueError(f"Invalid trace_id: {trace_id}. Fallback trace_ids are not allowed.")
        
        try:
            print(f"[LANGFUSE] Submitting feedback - trace_id: {trace_id}, rating: {rating}, comment: {comment or '(none)'}")
            
            # Get the trace first, then add score to it
            # This ensures the score is properly attached to the trace
            trace = self.client.trace(id=trace_id)
            
            # Use score() method with clear value mapping
            # thumbs_up = 1, thumbs_down = 0 (per latest UX request)
            score_value = 1 if rating == "thumbs_up" else 0
            
            trace.score(
                name="user_feedback",
                value=score_value,
                comment=comment or ""
            )
            
            print(f"[LANGFUSE] ✓ Feedback submitted successfully to trace {trace_id}")
            return True
            
        except Exception as e:
            print(f"[ERROR] Langfuse feedback failed for trace {trace_id}: {e}")
            import traceback
            traceback.print_exc()
            raise  # Re-raise to let the endpoint handle it
    
    def log_observation_to_trace(
        self, 
        trace_id: str, 
        name: str, 
        input_data: Any, 
        output_data: Any, 
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Log custom observation to existing trace (for manual corrections)."""
        if not self.client:
            return False
        
        try:
            trace = self.client.trace(id=trace_id, name="manual_correction_review")
            trace.span(
                name=name,
                input=input_data,
                output=output_data,
                metadata={**(metadata or {}), "timestamp": datetime.now(timezone.utc).isoformat()}
            )
            return True
            
        except Exception as e:
            print(f"[ERROR] Langfuse observation failed: {e}")
            return False
    
    def create_rag_pipeline_trace(
        self, 
        user_id: str, 
        question: str, 
        session_id: Optional[str] = None, 
        metadata: Optional[Dict[str, Any]] = None,
        user_name: Optional[str] = None,
        user_email: Optional[str] = None
    ):
        """Create structured RAG pipeline trace with nested spans."""
        if not self.client:
            print("[WARNING] Langfuse client not initialized - cannot create RAG trace")
            print("[WARNING] Check LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, and LANGFUSE_HOST in config")
            return None
        
        try:
            # Build metadata (using UTC for consistency)
            trace_metadata = {**(metadata or {}), "timestamp": datetime.now(timezone.utc).isoformat()}
            
            trace = self.client.trace(
                name="chat_interaction",
                user_id=user_id,
                session_id=session_id or user_id,
                input=question,
                metadata=trace_metadata,
                tags=["rag", "chat"]
            )
            rag_trace = RAGPipelineTrace(trace)
            print(f"[LANGFUSE] ✓ Created RAG trace: {rag_trace.trace_id}")
            return rag_trace
            
        except Exception as e:
            print(f"[ERROR] RAG trace creation failed: {e}")
            import traceback
            traceback.print_exc()
            return None


class RAGPipelineTrace:
    """
    RAG pipeline trace with nested spans:
    chat_interaction → query → retrieve/synthesize/generating_response
    """
    
    def __init__(self, trace):
        self.trace = trace
        self.trace_id = trace.id
        self.query_span = None
        self.retrieve_span = None
        self.synthesize_span = None
    
    def start_query(self, enhanced_query: str, metadata: Optional[Dict[str, Any]] = None):
        """Start query processing span."""
        try:
            self.query_span = self.trace.span(
                name="query",
                input=enhanced_query,
                metadata={**(metadata or {}), "timestamp": datetime.now(timezone.utc).isoformat()}
            )
            return self.query_span
        except Exception as e:
            print(f"[ERROR] Query span failed: {e}")
            return None
    
    def log_retrieval(self, query: str, retrieved_docs: list, doc_count: int, sources_breakdown: Dict[str, int], metadata: Optional[Dict[str, Any]] = None):
        """Log document retrieval with nested embedding span."""
        try:
            self.retrieve_span = self.query_span.span(
                name="retrieve",
                input=query,
                output=f"Retrieved {doc_count} documents",
                metadata={
                    **(metadata or {}),
                    "document_count": doc_count,
                    "sources_breakdown": sources_breakdown,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            )
            
            self.retrieve_span.span(
                name="vectorstore_embedding",
                input=query,
                output=f"Embedded query and searched {doc_count} documents",
                metadata={"embedding_model": "text-embedding-3-small", "timestamp": datetime.now(timezone.utc).isoformat()}
            )
            
            return self.retrieve_span
            
        except Exception as e:
            print(f"[ERROR] Retrieval span failed: {e}")
            return None
    
    def start_synthesis(self, context: str, metadata: Optional[Dict[str, Any]] = None):
        """Start synthesis span."""
        try:
            if not getattr(self, "query_span", None):
                print("[LANGFUSE][WARN] start_synthesis skipped: query_span not initialized")
                return None

            self.synthesize_span = self.query_span.span(
                name="synthesize",
                input={"context_length": len(context)},
                metadata={**(metadata or {}), "timestamp": datetime.now(timezone.utc).isoformat()}
            )
            return self.synthesize_span
            
        except Exception as e:
            print(f"[LANGFUSE][ERROR] start_synthesis failed: {e}")
            self.synthesize_span = None
            return None
    
    def log_llm_generation(self, prompt: str, response: str, model: str = "gpt-4o-mini", metadata: Optional[Dict[str, Any]] = None):
        """Log LLM generation span."""
        try:
            if not getattr(self, "synthesize_span", None):
                print("[LANGFUSE][WARN] log_llm_generation skipped: synthesize_span not initialized")
                return None

            return self.synthesize_span.generation(
                name="openai_llm",
                model=model,
                input=prompt,
                output=response,
                metadata={**(metadata or {}), "timestamp": datetime.now(timezone.utc).isoformat()}
            )
        except Exception as e:
            print(f"[LANGFUSE][ERROR] log_llm_generation failed: {e}")
            return None
    
    def log_response_generation(self, final_response: str, metadata: Optional[Dict[str, Any]] = None):
        """Log final response generation span."""
        try:
            return self.query_span.span(
                name="generating_response",
                input="Formatted LLM output",
                output=final_response,
                metadata={
                    **(metadata or {}),
                    "response_length": len(final_response),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            )
        except Exception as e:
            print(f"[ERROR] Response generation failed: {e}")
            return None
    
    def complete(self, final_output: str, metadata: Optional[Dict[str, Any]] = None):
        """Complete trace with final output and metadata."""
        try:
            if self.query_span:
                self.query_span.end(output=final_output)
            
            # Update trace with output
            self.trace.update(output=final_output)
            
            # If metadata is provided, update it separately
            # Langfuse merges metadata on update, not replaces
            if metadata:
                self.trace.update(metadata=metadata)
            
            print(f"[LANGFUSE] ✓ Completed RAG trace: {self.trace_id}")
            return self.trace_id
        except Exception as e:
            print(f"[ERROR] Trace completion failed: {e}")
            import traceback
            traceback.print_exc()
            # Still return trace_id even if completion failed
            return self.trace_id

    # ---------- Antigravity evaluation spans (no RAGAS) ----------
    def _parent_span(self):
        """Parent for node spans: query_span if set, else trace."""
        return self.query_span if getattr(self, "query_span", None) else self.trace

    def log_intent_span(self, intent: str, confidence: float, metadata: Optional[Dict[str, Any]] = None):
        """Span for classify_intent node."""
        try:
            p = self._parent_span()
            return p.span(name="intent", input={}, output={"intent": intent, "confidence": confidence}, metadata=metadata or {})
        except Exception as e:
            print(f"[LANGFUSE] log_intent_span failed: {e}")
            return None

    def log_rerank_span(self, doc_count: int, top_k: int, rerank_top_k: int, metadata: Optional[Dict[str, Any]] = None):
        """Span for rerank_results node."""
        try:
            p = self._parent_span()
            return p.span(
                name="rerank",
                input={"input_count": doc_count},
                output={"output_count": min(doc_count, rerank_top_k)},
                metadata={**(metadata or {}), "top_k": top_k, "rerank_top_k": rerank_top_k}
            )
        except Exception as e:
            print(f"[LANGFUSE] log_rerank_span failed: {e}")
            return None

    def log_validate_context_span(self, validation_result: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None):
        """Span for validate_context (CRAG) node. Also logs trace.score(crag_quality)."""
        try:
            p = self._parent_span()
            meta = {
                "relevance_scores": validation_result.get("relevance_scores", []),
                "coverage_sufficient": validation_result.get("coverage_sufficient", False),
                "diversity_score": validation_result.get("diversity_score", 0.0),
                "issues": validation_result.get("issues", []),
                "corrective_action": validation_result.get("corrective_action", "none"),
                **(metadata or {}),
            }
            span = p.span(
                name="validate_context",
                input={},
                output={"quality_score": validation_result.get("quality_score", 0.0)},
                metadata=meta,
            )
            q = validation_result.get("quality_score")
            if q is not None:
                self.trace.score(name="crag_quality", value=float(q))
            return span
        except Exception as e:
            print(f"[LANGFUSE] log_validate_context_span failed: {e}")
            return None

    def log_apply_corrective_action_span(self, action: str, retry_count: int, metadata: Optional[Dict[str, Any]] = None):
        """Span for apply_corrective_action node."""
        try:
            p = self._parent_span()
            return p.span(name="apply_corrective_action", input={"retry": retry_count}, output=action, metadata=metadata or {})
        except Exception as e:
            print(f"[LANGFUSE] log_apply_corrective_action_span failed: {e}")
            return None

    def log_compress_context_span(self, token_count: int, metadata: Optional[Dict[str, Any]] = None):
        """Span for compress_context node."""
        try:
            p = self._parent_span()
            return p.span(name="compress_context", input={}, output={"token_count": token_count}, metadata=metadata or {})
        except Exception as e:
            print(f"[LANGFUSE] log_compress_context_span failed: {e}")
            return None

    def log_extract_citations_span(self, citation_count: int, chunk_keys_cited: list, metadata: Optional[Dict[str, Any]] = None):
        """Span for extract_citations node."""
        try:
            p = self._parent_span()
            return p.span(
                name="extract_citations",
                input={},
                output={"citation_count": citation_count},
                metadata={**(metadata or {}), "chunk_keys_cited": chunk_keys_cited or []}
            )
        except Exception as e:
            print(f"[LANGFUSE] log_extract_citations_span failed: {e}")
            return None


# Global tracker instance
langfuse_tracker = LangfuseTracker()

