// Shared TypeScript types and interfaces for the chat application

export interface User {
  id: string;
  name: string;
  email: string;
  /** Server-computed; never trust client for authorization. Used only for UI (e.g. showing Admin link). */
  is_admin?: boolean;
  /** Only set for admins; list of emails that can be excluded from dashboard stats. From backend only. */
  excludable_developer_emails?: string[];
  // Session is managed by backend via session_id cookie
}

export interface Message {
  role: string;
  content: string;
  traceId?: string; // Persist Langfuse trace mapping for feedback after refresh
  feedbackSubmitted?: boolean;
  feedbackRating?: 'thumbs_up' | 'thumbs_down';
  recommendedQuestions?: string[];
  /** When "email_draft", UI shows email heading/body/refinement buttons; preserved on refresh */
  intent?: string;
  /** Raw email text for refinement buttons; only set when intent === "email_draft" */
  emailContent?: string;
}

export interface ChatSession {
  id: string;
  title: string;
  timestamp: number;
  createdAt: number;
  messages: Message[];
  deletedAt?: number; // Timestamp when session was deleted (for soft delete)
}

export interface OtherUserChat {
  session_id: string;
  title: string;
  user_email?: string;
  created_at?: string;
  conversation_id?: string; // MongoDB _id as conversation identifier
}

export interface SuggestedQuestion {
  id: string;
  question_text: string;
}

// Extend Window interface for marked.js and global functions
declare global {
  interface Window {
    marked?: {
      parse: (text: string) => string;
    };
    copyMessage?: (button: HTMLElement) => void;
    submitFeedback?: (button: HTMLElement, rating: string) => void;
    editMessage?: (button: HTMLElement) => void;
    cancelEdit?: (button: HTMLElement) => void;
    saveEdit?: (button: HTMLElement) => void;
    askRecommendedQuestion?: (button: HTMLElement) => void;
    showFeedbackModal?: (messageDiv: HTMLElement, traceId: string) => void;
    submitDetailedFeedback?: () => void;
    copyUserMessage?: (button: HTMLElement) => void;
  }
}

// Character limit constants
export const MAX_PROMPT_LENGTH = 20000; // ~5K tokens (safe for RAG)
export const WARN_PROMPT_LENGTH = 10000; // ~2.5K tokens - warning threshold

