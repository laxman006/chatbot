'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import Image from 'next/image';
import { apiFetch } from '@/lib/api';
import { checkSession } from '@/lib/session-utils';
import UserOnboardingModal from '@/components/UserOnboardingModal';


export default function LoginPage() {
  const router = useRouter();
  const checkedRef = useRef(false);
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [userEmail, setUserEmail] = useState<string>('');
  const [userName, setUserName] = useState<string>('');

  useEffect(() => {
    // ✅ Strict-mode safe: prevent double execution
    if (checkedRef.current) return;
    checkedRef.current = true;

    // Pass callback to handle onboarding
    initializeLoginPage((email: string, name: string) => {
      setUserEmail(email);
      setUserName(name);
      setShowOnboarding(true);
    });
  }, [router]);

  const handleOnboardingComplete = () => {
    setShowOnboarding(false);
    // Redirect to intended page after onboarding
    const redirectUrl = sessionStorage.getItem('oauth_redirect') || 
                       localStorage.getItem('oauth_redirect_backup') || 
                       '/';
    // ✅ Use router instead of window.location.href to avoid full page reload
    router.replace(redirectUrl);
  };

  return (
    <>
      {showOnboarding && (
        <UserOnboardingModal
          userEmail={userEmail}
          userName={userName}
          onComplete={handleOnboardingComplete}
        />
      )}
      <header>
        <Image src="/images/CloudFuze Horizontal Logo.svg" alt="CloudFuze Logo" width={150} height={40} priority />
      </header>

      <div className="main-content">
        <div className="login-container">
          <h1 className="login-title">Welcome to CF Chatbot</h1>
          <p className="login-subtitle">Please sign in to continue</p>
          <button id="microsoftLogin" className="login-btn">
            <svg className="provider-icon" viewBox="0 0 24 24">
              <path fill="currentColor" d="M11.4 24H0V12.6h11.4V24zM24 24H12.6V12.6H24V24zM11.4 11.4H0V0h11.4v11.4zM24 11.4H12.6V0H24v11.4z"/>
            </svg>
            Sign in with Microsoft
          </button>
        </div>
      </div>
    </>
  );
}

function initializeLoginPage(onShowOnboarding?: (email: string, name: string) => void) {
  // Microsoft OAuth configuration
  let MICROSOFT_CLIENT_ID: string | null = null;
  let MICROSOFT_TENANT = "cloudfuze.com";
  const MICROSOFT_REDIRECT_URI = window.location.origin + '/login';
  const MICROSOFT_SCOPE = "openid email profile User.Read";

  // ✅ Save redirect URL immediately on page load (not just on button click)
  // This ensures the redirect URL is preserved even if sessionStorage is cleared during OAuth
  const urlParamsOnLoad = new URLSearchParams(window.location.search);
  const redirectUrlOnLoad = urlParamsOnLoad.get('redirect');
  if (redirectUrlOnLoad) {
    // Only save if not already saved or if it's different (don't overwrite unnecessarily)
    const existingRedirect = sessionStorage.getItem('oauth_redirect');
    if (!existingRedirect || existingRedirect !== redirectUrlOnLoad) {
      sessionStorage.setItem('oauth_redirect', redirectUrlOnLoad);
      localStorage.setItem('oauth_redirect_backup', redirectUrlOnLoad);
      console.log('[AUTH] Saved redirect URL on page load:', redirectUrlOnLoad);
    } else {
      console.log('[AUTH] Redirect URL already saved:', redirectUrlOnLoad);
    }
  }

  // Load Microsoft OAuth configuration from backend
  async function loadOAuthConfig() {
    try {
      const response = await apiFetch('/auth/config');
      if (response.ok) {
        const config = await response.json();
        MICROSOFT_CLIENT_ID = config.client_id;
        MICROSOFT_TENANT = config.tenant || "cloudfuze.com";
        console.log('[AUTH] Loaded OAuth config:', { client_id: MICROSOFT_CLIENT_ID, tenant: MICROSOFT_TENANT });
      } else {
        throw new Error('Failed to load OAuth configuration');
      }
    } catch (error) {
      console.error('[AUTH] Error loading OAuth config:', error);
      MICROSOFT_CLIENT_ID = process.env.NEXT_PUBLIC_MICROSOFT_CLIENT_ID || "861e696d-f41c-41ee-a7c2-c838fd185d6d";
      console.log('[AUTH] Using fallback client ID');
    }
  }

  // PKCE helper functions
  function generateCodeVerifier() {
    const array = new Uint8Array(32);
    crypto.getRandomValues(array);
    return base64URLEncode(array);
  }

  async function generateCodeChallenge(verifier: string) {
    const encoder = new TextEncoder();
    const data = encoder.encode(verifier);
    const hash = await crypto.subtle.digest('SHA-256', data);
    return base64URLEncode(new Uint8Array(hash));
  }

  function base64URLEncode(array: Uint8Array) {
    return btoa(String.fromCharCode.apply(null, Array.from(array)))
      .replace(/\+/g, '-')
      .replace(/\//g, '_')
      .replace(/=/g, '');
  }

  // ✅ Simple session check (session-based auth only)
  async function checkSessionStatus() {
    console.log('[AUTH] Checking session status...');
    
    // 🔒 CRITICAL: Check if this is a manual logout (don't show error)
    const isManualLogout = sessionStorage.getItem('manual_logout') === 'true';
    if (isManualLogout) {
      // User manually logged out - clear flags and don't show error
      sessionStorage.removeItem('manual_logout');
      sessionStorage.removeItem('session_expired');
      console.log('[AUTH] Manual logout detected - no error message');
      return; // Don't check session, just stay on login page
    }
    
    const isLoggedIn = await checkSession();
    
    if (isLoggedIn) {
      // Session is valid - user is logged in
      console.log('[AUTH] ✅ Session valid, redirecting to main page');
      // Clear any stored session expiration error
      sessionStorage.removeItem('session_expired');
      sessionStorage.removeItem('manual_logout');
      // Redirect to home page
      window.location.href = '/';
    } else {
      // Session expired or invalid - stay on login page
      console.log('[AUTH] No valid session');
      localStorage.removeItem('user');
      
      // Only show error if it's actually a session expiration (not manual logout)
      const hasStoredExpiration = sessionStorage.getItem('session_expired') === 'true';
      if (hasStoredExpiration) {
        // Set session expiration flag so error persists across refreshes
        sessionStorage.setItem('session_expired', 'true');
        // Show persistent error message
        showError('⚠️ Your session has expired. Please log in again.', true);
      }
      // If no stored expiration flag, it might be a fresh page load - don't show error
    }
  }

  // Microsoft login handler
  async function handleMicrosoftLogin(event: Event) {
    event.preventDefault();
    
    sessionStorage.removeItem('code_verifier');
    localStorage.removeItem('user'); // Clear any old user data
    
    // Save redirect URL before starting OAuth (use both sessionStorage and localStorage for reliability)
    // ✅ ENHANCED: Check URL params first, then use existing saved value if URL params are empty
    const urlParams = new URLSearchParams(window.location.search);
    let redirectUrl = urlParams.get('redirect');
    
    // If no redirect in URL params, check if we already saved one (from page load)
    if (!redirectUrl) {
      redirectUrl = sessionStorage.getItem('oauth_redirect') || localStorage.getItem('oauth_redirect_backup') || null;
      if (redirectUrl) {
        console.log('[AUTH] No redirect in URL params, using saved redirect URL:', redirectUrl);
      }
    }
    
    if (redirectUrl) {
      sessionStorage.setItem('oauth_redirect', redirectUrl);
      localStorage.setItem('oauth_redirect_backup', redirectUrl);  // Backup in localStorage
      console.log('[AUTH] Saved redirect URL to sessionStorage:', redirectUrl);
      console.log('[AUTH] Saved redirect URL backup to localStorage:', redirectUrl);
      console.log('[AUTH] sessionStorage value after save:', sessionStorage.getItem('oauth_redirect'));
      console.log('[AUTH] localStorage backup value after save:', localStorage.getItem('oauth_redirect_backup'));
    } else {
      console.log('[AUTH] No redirect URL found in URL parameters or storage');
    }
    
    const button = event.target as HTMLButtonElement;
    const originalText = button.innerHTML;
    button.innerHTML = '<span>Signing in...</span>';
    button.disabled = true;
    
    const codeVerifier = generateCodeVerifier();
    const codeChallenge = await generateCodeChallenge(codeVerifier);
    
    sessionStorage.setItem('code_verifier', codeVerifier);
    sessionStorage.setItem('login_in_progress', 'true');
    
    const authUrl = `https://login.microsoftonline.com/${MICROSOFT_TENANT}/oauth2/v2.0/authorize?` +
      `client_id=${MICROSOFT_CLIENT_ID}&` +
      `response_type=code&` +
      `redirect_uri=${encodeURIComponent(MICROSOFT_REDIRECT_URI)}&` +
      `response_mode=query&` +
      `scope=${encodeURIComponent(MICROSOFT_SCOPE)}&` +
      `prompt=select_account&` +
      `code_challenge=${codeChallenge}&` +
      `code_challenge_method=S256&` +
      `state=${Date.now()}`;
    
    try {
      window.location.href = authUrl;
    } catch (error) {
      button.innerHTML = originalText;
      button.disabled = false;
      sessionStorage.removeItem('login_in_progress');
      showError('Failed to initiate login: ' + (error instanceof Error ? error.message : 'Unknown error'));
    }
  }

  // Error display function
  function showError(message: string, persist: boolean = false) {
    const existingError = document.querySelector('.error-message');
    if (existingError) {
      existingError.remove();
    }
    
    const errorDiv = document.createElement('div');
    errorDiv.className = 'error-message';
    errorDiv.style.cssText = `
      background: #fee;
      color: #c33;
      padding: 15px;
      border-radius: 10px;
      margin-top: 20px;
      border: 1px solid #fcc;
      font-size: 14px;
    `;
    errorDiv.innerHTML = message;
    document.querySelector('.login-container')!.appendChild(errorDiv);
    
    // Only auto-dismiss if persist is false
    if (!persist) {
      setTimeout(() => {
        if (errorDiv.parentNode) {
          errorDiv.remove();
        }
      }, 5000);
    }
  }

  // Success display function
  function showSuccess(message: string) {
    const successDiv = document.createElement('div');
    successDiv.className = 'success-message';
    successDiv.style.cssText = `
      background: #efe;
      color: #363;
      padding: 15px;
      border-radius: 10px;
      margin-top: 20px;
      border: 1px solid #cfc;
      font-size: 14px;
    `;
    successDiv.innerHTML = message;
    document.querySelector('.login-container')!.appendChild(successDiv);
  }

  // Loading indicator functions
  function showLoadingIndicator(message: string) {
    const loadingDiv = document.createElement('div');
    loadingDiv.id = 'loading-indicator';
    loadingDiv.style.cssText = `
      position: fixed;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      background: rgba(0, 0, 0, 0.8);
      color: white;
      padding: 20px 30px;
      border-radius: 8px;
      z-index: 10000;
      font-size: 16px;
      display: flex;
      align-items: center;
      gap: 10px;
    `;
    loadingDiv.innerHTML = `
      <div style="width: 20px; height: 20px; border: 2px solid #fff; border-top: 2px solid transparent; border-radius: 50%; animation: spin 1s linear infinite;"></div>
      ${message}
    `;
    document.body.appendChild(loadingDiv);
  }
  
  function hideLoadingIndicator() {
    const loadingDiv = document.getElementById('loading-indicator');
    if (loadingDiv) {
      loadingDiv.remove();
    }
  }

  // Handle OAuth callback
  function handleOAuthCallback() {
    const urlParams = new URLSearchParams(window.location.search);
    const code = urlParams.get('code');
    const error = urlParams.get('error');

    if (error) {
      console.log('OAuth error:', error);
      showError('Microsoft login failed: ' + error);
      return;
    }

    if (code) {
      console.log('OAuth code received, processing...');
      // Show loading indicator immediately and hide login form
      showLoadingIndicator('Completing sign-in...');
      const loginContainer = document.querySelector('.login-container') as HTMLElement;
      if (loginContainer) {
        loginContainer.style.display = 'none';
      }
      exchangeCodeForToken(code);
    }
  }

  // Exchange authorization code for access token
  async function exchangeCodeForToken(code: string) {
    const codeVerifier = sessionStorage.getItem('code_verifier');
    
    if (!codeVerifier) {
      console.log('Code verifier not found, starting fresh login flow...');
      hideLoadingIndicator();
      const loginContainer = document.querySelector('.login-container') as HTMLElement;
      if (loginContainer) {
        loginContainer.style.display = 'block';
      }
      localStorage.removeItem('user');
      window.history.replaceState({}, document.title, window.location.pathname);
      showSuccess('Starting fresh login...');
      setTimeout(() => {
        const loginButton = document.getElementById('microsoftLogin');
        if (loginButton) {
          loginButton.click();
        }
      }, 1000);
      return;
    }
    
    try {
      const requestBody = {
        code: code,
        redirect_uri: MICROSOFT_REDIRECT_URI,
        code_verifier: codeVerifier
      };

      // ✅ Session cookie sent automatically via proxy
      const response = await apiFetch('/auth/microsoft/callback', {
        method: 'POST',
        body: JSON.stringify(requestBody)
      });

      if (response.ok) {
        const data = await response.json();
        
        sessionStorage.removeItem('code_verifier');
        sessionStorage.removeItem('login_in_progress');
        
        // ✅ Session-based auth - backend sets session_id cookie automatically
        // Store ONLY UI info (id, name, email) - NO tokens
        const user = {
          id: data.user_id,
          name: data.name,
          email: data.email
        };
        
        localStorage.setItem('user', JSON.stringify(user));
        // Clear all session-related flags on successful login
        sessionStorage.removeItem('session_expired');
        sessionStorage.removeItem('manual_logout');
        console.log('[AUTH] ✅ Session created - session_id cookie set by backend');
        console.log('[AUTH] User info stored:', { id: user.id, email: user.email });
        
        // ✅ Check if user needs onboarding
        try {
          const profileResponse = await apiFetch('/user/profile', {
            method: 'GET'
          });
          
          if (profileResponse.ok) {
            const profileData = await profileResponse.json();
            console.log('[AUTH] User profile:', profileData);
            
            if (profileData.needs_onboarding && onShowOnboarding) {
              // Hide loading indicator before showing onboarding modal
              hideLoadingIndicator();
              const loginContainer = document.querySelector('.login-container') as HTMLElement;
              if (loginContainer) {
                loginContainer.style.display = 'none';
              }
              
              // Show onboarding modal
              console.log('[AUTH] User needs onboarding, showing modal');
              onShowOnboarding(user.email, user.name);
              // Don't redirect yet - wait for onboarding completion
              return;
            }
          }
        } catch (profileError) {
          console.error('[AUTH] Error checking user profile:', profileError);
          // Continue with normal redirect if profile check fails
        }
        
        // Get redirect URL from sessionStorage (saved before OAuth)
        // Use backup from localStorage if sessionStorage is empty
        let redirectUrl = sessionStorage.getItem('oauth_redirect') || '';
        
        if (!redirectUrl) {
          redirectUrl = localStorage.getItem('oauth_redirect_backup') || '/';
          console.log('[AUTH] sessionStorage was empty, using localStorage backup');
        } else {
          console.log('[AUTH] Retrieved redirect URL from sessionStorage');
        }
        
        // ✅ ADD THIS: Log warning if redirect URL is default (might indicate a problem)
        if (redirectUrl === '/') {
          console.warn('[AUTH] ⚠️ Redirect URL is default (/). This might indicate the redirect URL was lost.');
          console.warn('[AUTH] Current URL:', window.location.href);
          console.warn('[AUTH] sessionStorage oauth_redirect:', sessionStorage.getItem('oauth_redirect'));
          console.warn('[AUTH] localStorage oauth_redirect_backup:', localStorage.getItem('oauth_redirect_backup'));
        }
        
        // Clean up both storage locations
        sessionStorage.removeItem('oauth_redirect');
        localStorage.removeItem('oauth_redirect_backup');
        
        console.log('[AUTH] Final redirect URL:', redirectUrl);
        console.log('[AUTH] Redirect URL is default (/):', redirectUrl === '/');
        console.log('[AUTH] Login successful, redirecting to:', redirectUrl);
        
        // Clear URL parameters before redirecting
        window.history.replaceState({}, document.title, window.location.pathname);
        
        // Redirect to the intended page
        window.location.href = redirectUrl;
      } else {
        const errorText = await response.text();
        console.log('Server error response:', errorText);
        hideLoadingIndicator();
        const loginContainer = document.querySelector('.login-container') as HTMLElement;
        if (loginContainer) {
          loginContainer.style.display = 'block';
        }
        
        if (errorText.includes('code_verifier') || errorText.includes('Code verifier')) {
          console.log('Code verifier error detected, starting fresh login...');
          localStorage.removeItem('user');
          window.history.replaceState({}, document.title, window.location.pathname);
          showSuccess('Starting fresh login...');
          setTimeout(() => {
            const loginButton = document.getElementById('microsoftLogin');
            if (loginButton) {
              loginButton.click();
            }
          }, 1000);
          return;
        }
        
        window.history.replaceState({}, document.title, window.location.pathname);
        showError('Login failed: ' + (errorText || 'Unknown error'));
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      console.log('Network or other error:', errorMessage);
      hideLoadingIndicator();
      const loginContainer = document.querySelector('.login-container') as HTMLElement;
      if (loginContainer) {
        loginContainer.style.display = 'block';
      }
      
      if (errorMessage.includes('code_verifier') || errorMessage.includes('Code verifier')) {
        console.log('Code verifier error detected in catch, starting fresh login...');
        localStorage.removeItem('user');
        window.history.replaceState({}, document.title, window.location.pathname);
        showSuccess('Starting fresh login...');
        setTimeout(() => {
          const loginButton = document.getElementById('microsoftLogin');
          if (loginButton) {
            loginButton.click();
          }
        }, 1000);
        return;
      }
      
      window.history.replaceState({}, document.title, window.location.pathname);
      showError('Login failed: ' + (error instanceof Error ? error.message : 'Unknown error'));
    }
  }

  // Reset login button to original state
  function resetLoginButton() {
    const button = document.getElementById('microsoftLogin') as HTMLButtonElement;
    if (button) {
      sessionStorage.removeItem('login_in_progress');
      
      button.innerHTML = `
        <svg class="provider-icon" viewBox="0 0 24 24">
          <path fill="currentColor" d="M11.4 24H0V12.6h11.4V24zM24 24H12.6V12.6H24V24zM11.4 11.4H0V0h11.4v11.4zM24 11.4H12.6V0H24v11.4z"/>
        </svg>
        Sign in with Microsoft
      `;
      button.disabled = false;
    }
  }

  // Initialize when DOM is loaded
  resetLoginButton();
  
  loadOAuthConfig().then(() => {
    console.log('Login page initialized');
    console.log('Current hostname:', window.location.hostname);
    
    // ✅ FIX 3: Check OAuth callback FIRST, then auth status (prevents race condition)
    const urlParams = new URLSearchParams(window.location.search);
    const code = urlParams.get('code');
    const error = urlParams.get('error');
    const email = urlParams.get('email');
    
    // Handle error messages from URL params
    if (error === 'unauthorized_domain') {
      const errorMessage = `⚠️ Access Denied\n\nOnly CloudFuze company accounts (@cloudfuze.com) are allowed to access this application.\n\n${email ? `Your email: ${decodeURIComponent(email)}` : ''}\n\nPlease log in with your CloudFuze account.`;
      showError(errorMessage.replace(/\n/g, '<br>'), true); // Persist until user logs in
      window.history.replaceState({}, document.title, window.location.pathname);
    } else if (error === 'invalid_token' || error === 'session_expired') {
      // Store session expiration state so it persists across page refreshes
      sessionStorage.setItem('session_expired', 'true');
      showError('⚠️ Your session has expired. Please log in again.', true); // Persist until user logs in
      window.history.replaceState({}, document.title, window.location.pathname);
    } else if (error === 'verification_failed') {
      showError('⚠️ Unable to verify your access. Please log in again.', true); // Persist until user logs in
      window.history.replaceState({}, document.title, window.location.pathname);
    } else {
      // Check for stored session expiration state (for page refreshes)
      const hasStoredExpiration = sessionStorage.getItem('session_expired') === 'true';
      if (hasStoredExpiration) {
        showError('⚠️ Your session has expired. Please log in again.', true);
      }
    }
    
    const microsoftButton = document.getElementById("microsoftLogin");
    
    if (microsoftButton) {
      microsoftButton.addEventListener("click", handleMicrosoftLogin);
    } else {
      console.error('Microsoft login button not found');
    }
    
    // ✅ Check OAuth callback FIRST, then session (prevents race condition)
    if (code) {
      // OAuth callback in progress - handle it first
      console.log('[AUTH] OAuth callback detected, handling first...');
      handleOAuthCallback();
    } else {
      // No OAuth callback - check existing session
      console.log('[AUTH] No OAuth callback, checking existing session...');
      checkSessionStatus();
    }
  });

  // ❌ REMOVED: Multiple auth checks on focus/visibility cause race conditions
  // Auth check is already handled in loadOAuthConfig().then() above
  // No need for duplicate checks on focus/load events
}
