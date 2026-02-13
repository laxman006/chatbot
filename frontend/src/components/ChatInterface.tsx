'use client';

import { useRef, useEffect, useState } from 'react';
import { MAX_PROMPT_LENGTH } from '@/types/chat';
import ChatHeader from './ChatHeader';

interface ChatInterfaceProps {
  sessionId?: string;
  onSendMessage?: (message: string) => void;
}

export default function ChatInterface({ sessionId, onSendMessage }: ChatInterfaceProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [emailMode, setEmailMode] = useState(false);
  
  // ✅ CRITICAL FIX: Clear messages when sessionId changes to undefined (new chat)
  useEffect(() => {
    if (sessionId === undefined) {
      // This is a new chat - clear any stale messages
      const messagesDiv = document.getElementById('messages');
      if (messagesDiv) {
        messagesDiv.innerHTML = '';
      }
      const emptyState = document.getElementById('empty-state');
      const inputSection = document.querySelector('.chatgpt-input-section') as HTMLElement;
      if (emptyState && inputSection && messagesDiv) {
        emptyState.style.display = 'flex';
        messagesDiv.style.display = 'none';
        inputSection.classList.remove('show');
      }
    }
  }, [sessionId]);

  return (
    <main className="chatgpt-main" data-email-mode={emailMode ? 'true' : 'false'}>
      {/* Chat Header - will be shown/hidden by chat initialization */}
      <div id="chat-header-container"></div>
      
      {/* Messages Container */}
      <div className="messages-container">
        {/* Empty State - Shows when no messages */}
        <div id="empty-state" className="empty-state">
          <div className="empty-state-content">
            {/* Welcome Message */}
            <div className="welcome-section">
              <h1 className="welcome-title">How can I help you today?</h1>
            </div>

            {/* Input Section for Empty State */}
            <div className="empty-state-input">
              <div className="input-wrapper-chatgpt" style={{ position: 'relative' }}>
                <textarea
                  id="user-input-empty"
                  className="chatgpt-textarea"
                  placeholder="Ask me anything about CloudFuze..."
                  rows={1}
                  maxLength={MAX_PROMPT_LENGTH}
                  style={{ paddingBottom: '28px' }}
                />
                <span id="char-counter-empty" style={{
                  fontSize: '12px',
                  color: '#6b7280',
                  position: 'absolute',
                  right: '90px',
                  bottom: '8px',
                  display: 'none',
                  fontWeight: '400',
                  pointerEvents: 'none'
                }}></span>
                <button
                  type="button"
                  className={`email-draft-toggle-btn ${emailMode ? 'active' : ''}`}
                  onClick={() => setEmailMode((v) => !v)}
                  title={emailMode ? 'Email drafting on – click to turn off' : 'Email drafting – polish and rephrase emails'}
                  aria-label={emailMode ? 'Email drafting on' : 'Email drafting off'}
                  aria-pressed={emailMode}
                >
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
                    <polyline points="22,6 12,13 2,6" />
                  </svg>
                </button>
                <button id="send-btn-empty" className="chatgpt-send-btn">
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                    <path d="M8 1a1 1 0 011 1v10.586l2.293-2.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 111.414-1.414L7 12.586V2a1 1 0 011-1z" transform="rotate(180 8 8)"/>
                  </svg>
                </button>
                <div id="tooltip-empty" style={{
                  display: 'none',
                  position: 'absolute',
                  bottom: 'calc(100% + 8px)',
                  right: '0',
                  padding: '8px 12px',
                  backgroundColor: '#1f2937',
                  color: 'white',
                  fontSize: '13px',
                  borderRadius: '8px',
                  whiteSpace: 'nowrap',
                  zIndex: 1000,
                  boxShadow: '0 4px 6px rgba(0, 0, 0, 0.1)',
                  pointerEvents: 'none'
                }}>Message is too long</div>
              </div>
              {/* Suggested Questions - Loaded Dynamically */}
              <div className="suggested-questions-container" id="suggested-questions-empty">
                {/* Questions loaded from API */}
              </div>
            </div>
          </div>
        </div>

        {/* Messages List */}
        <div id="messages" className="messages-list"></div>
      </div>

      {/* Scroll to Bottom Button */}
      <button id="scroll-to-bottom-btn" className="scroll-to-bottom" title="Scroll to bottom">
        <svg width="16" height="16" viewBox="0 0 20 20" fill="currentColor">
          <path d="M10 3a1 1 0 011 1v10.586l3.293-3.293a1 1 0 111.414 1.414l-5 5a1 1 0 01-1.414 0l-5-5a1 1 0 111.414-1.414L9 14.586V4a1 1 0 011-1z"/>
        </svg>
      </button>

      {/* Feedback Modal */}
      <div id="feedback-modal" className="feedback-modal-overlay">
        <div className="feedback-modal">
          <div className="feedback-modal-header">
            <h3>Provide additional feedback</h3>
            <button className="feedback-modal-close" id="feedback-modal-close">
              <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor">
                <path d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"/>
              </svg>
            </button>
          </div>
          <div className="feedback-modal-body">
            <div className="feedback-categories">
              <button className="feedback-category-btn" data-category="Incorrect">
                Incorrect
              </button>
              <button className="feedback-category-btn" data-category="Irrelevant/Out of context">
                Irrelevant/Out of context
              </button>
              <button className="feedback-category-btn" data-category="Partially correct">
                Partially correct
              </button>
              <button className="feedback-category-btn" data-category="Too generic/not Specific">
                Too generic/not Specific
              </button>
              <button className="feedback-category-btn" data-category="Restricted response">
                Restricted response
              </button>
              <button className="feedback-category-btn" data-category="Too verbose">
                Too verbose
              </button>
              <button className="feedback-category-btn" data-category="Other">
                Other
              </button>
            </div>
            <textarea 
              id="feedback-comment" 
              className="feedback-comment-textarea" 
              placeholder="(Optional) Feel free to add specific details"
              rows={3}
            ></textarea>
            <div className="feedback-modal-note">
              Submitting feedback will include this full conversation to help improve CloudFuze AI.
            </div>
          </div>
          <div className="feedback-modal-footer">
            <button className="feedback-submit-btn" id="feedback-submit-btn">
              Submit
            </button>
          </div>
        </div>
      </div>

      {/* ChatGPT-Style Input Section - Shows when there are messages */}
      <div className="chatgpt-input-section">
        <div className="input-container-inner">
          {/* Hidden checkbox so chat-initialization can read email mode; toggled by Email icon in input bar */}
          <input
            type="checkbox"
            id="email-drafting-toggle"
            checked={emailMode}
            onChange={() => setEmailMode((v) => !v)}
            aria-hidden="true"
            tabIndex={-1}
            style={{ position: 'absolute', opacity: 0, pointerEvents: 'none', width: 0, height: 0 }}
          />
          <div className="input-wrapper-chatgpt" style={{ position: 'relative' }}>
            <textarea
              ref={textareaRef}
              id="user-input"
              className="chatgpt-textarea"
              placeholder="Ask me anything about CloudFuze..."
              rows={1}
              maxLength={MAX_PROMPT_LENGTH}
              style={{ paddingBottom: '28px' }}
            />
            <span id="char-counter" style={{
              fontSize: '12px',
              color: '#6b7280',
              position: 'absolute',
              right: '90px',
              bottom: '8px',
              display: 'none',
              fontWeight: '400',
              pointerEvents: 'none'
            }}></span>
            <button
              type="button"
              className={`email-draft-toggle-btn ${emailMode ? 'active' : ''}`}
              onClick={() => setEmailMode((v) => !v)}
              title={emailMode ? 'Email drafting on – click to turn off' : 'Email drafting – polish and rephrase emails'}
              aria-label={emailMode ? 'Email drafting on' : 'Email drafting off'}
              aria-pressed={emailMode}
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
                <polyline points="22,6 12,13 2,6" />
              </svg>
            </button>
            <button id="send-btn" className="chatgpt-send-btn">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                <path d="M8 1a1 1 0 011 1v10.586l2.293-2.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 111.414-1.414L7 12.586V2a1 1 0 011-1z" transform="rotate(180 8 8)"/>
              </svg>
            </button>
            <div id="tooltip-main" style={{
              display: 'none',
              position: 'absolute',
              bottom: 'calc(100% + 8px)',
              right: '0',
              padding: '8px 12px',
              backgroundColor: '#1f2937',
              color: 'white',
              fontSize: '13px',
              borderRadius: '8px',
              whiteSpace: 'nowrap',
              zIndex: 1000,
              boxShadow: '0 4px 6px rgba(0, 0, 0, 0.1)',
              pointerEvents: 'none'
            }}>Message is too long</div>
          </div>
          {/* Suggested Questions - Loaded Dynamically */}
          <div className="suggested-questions-container" id="suggested-questions-main">
            {/* Questions loaded from API */}
          </div>
          <p className="input-disclaimer">CloudFuze AI can make mistakes. Check important info.</p>
        </div>
      </div>
    </main>
  );
}

