'use client';

import { useState, useEffect, useRef } from 'react';
import { apiFetch } from '@/lib/api';

interface Team {
  team_name: string;
  lead_name: string;
  lead_email: string;
  color: string;
  description: string;
}

interface UserOnboardingModalProps {
  userEmail: string;
  userName: string;
  onComplete: () => void;
}

export default function UserOnboardingModal({
  userEmail,
  userName,
  onComplete
}: UserOnboardingModalProps) {
  const [teams, setTeams] = useState<Team[]>([]);
  const [selectedTeam, setSelectedTeam] = useState<string>('');
  const [managerName, setManagerName] = useState<string>('');
  const [managerEmail, setManagerEmail] = useState<string>('');
  const [role, setRole] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(true);
  const [saving, setSaving] = useState<boolean>(false);
  const [error, setError] = useState<string>('');
  const [isTeamDropdownOpen, setIsTeamDropdownOpen] = useState<boolean>(false);
  const teamDropdownRef = useRef<HTMLDivElement>(null);

  // Load teams list
  useEffect(() => {
    const loadTeams = async () => {
      try {
        const response = await apiFetch('/teams/list', {
          method: 'GET'
        });

        if (response.ok) {
          const data = await response.json();
          setTeams(data.teams || []);
        } else {
          setError('Failed to load teams list');
        }
      } catch (err) {
        console.error('[ONBOARDING] Error loading teams:', err);
        setError('Failed to load teams list');
      } finally {
        setLoading(false);
      }
    };

    loadTeams();
  }, []);

  // Load user's job title from backend (will be auto-filled)
  useEffect(() => {
    const loadUserRole = async () => {
      // Role will be auto-filled when team is selected and profile is saved
      // For now, we'll let user enter it or it will be filled from users.json
    };
    loadUserRole();
  }, []);

  // Update manager when team is selected
  useEffect(() => {
    if (selectedTeam) {
      const team = teams.find(t => t.team_name === selectedTeam);
      if (team) {
        setManagerName(team.lead_name || '');
        setManagerEmail(team.lead_email || '');
      } else {
        setManagerName('');
        setManagerEmail('');
      }
    }
  }, [selectedTeam, teams]);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (teamDropdownRef.current && !teamDropdownRef.current.contains(event.target as Node)) {
        setIsTeamDropdownOpen(false);
      }
    };
    if (isTeamDropdownOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isTeamDropdownOpen]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!selectedTeam) {
      setError('Please select a team');
      return;
    }

    setSaving(true);
    setError('');

    try {
      const response = await apiFetch('/user/profile', {
        method: 'POST',
        body: JSON.stringify({
          team_name: selectedTeam,
          role: role || undefined  // Let backend fill from users.json if empty
        })
      });

      if (response.ok) {
        const data = await response.json();
        console.log('[ONBOARDING] Profile saved:', data);
        onComplete();
      } else {
        const errorData = await response.json().catch(() => ({ detail: 'Failed to save profile' }));
        setError(errorData.detail || 'Failed to save profile');
      }
    } catch (err) {
      console.error('[ONBOARDING] Error saving profile:', err);
      setError('Failed to save profile. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.7)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 10000
      }}>
        <div style={{
          backgroundColor: 'white',
          padding: '40px',
          borderRadius: '12px',
          textAlign: 'center',
          minWidth: '300px'
        }}>
          <div style={{ marginBottom: '20px' }}>Loading teams...</div>
        </div>
      </div>
    );
  }

  return (
    <div style={{
      position: 'fixed',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      backgroundColor: 'rgba(0, 0, 0, 0.7)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 10000,
      padding: '20px',
      overflow: 'auto'
    }}>
      <div style={{
        backgroundColor: 'white',
        borderRadius: '12px',
        padding: '32px',
        maxWidth: '500px',
        width: '100%',
        boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)',
        position: 'relative',
        margin: 'auto',
        zIndex: 10001
      }}>
        <h2 style={{
          fontSize: '24px',
          fontWeight: '600',
          marginBottom: '8px',
          color: '#111827'
        }}>
          Welcome to CF Chatbot!
        </h2>
        <p style={{
          fontSize: '14px',
          color: '#6B7280',
          marginBottom: '24px'
        }}>
          Please complete your profile to get started.
        </p>

        <form onSubmit={handleSubmit}>
          {/* Team Selection */}
          <div style={{ marginBottom: '20px', position: 'relative' }}>
            <label style={{
              display: 'block',
              fontSize: '14px',
              fontWeight: '500',
              color: '#374151',
              marginBottom: '8px'
            }}>
              Team <span style={{ color: '#EF4444' }}>*</span>
            </label>
            <div ref={teamDropdownRef} style={{ position: 'relative', width: '100%' }}>
              <button
                type="button"
                onClick={() => setIsTeamDropdownOpen(!isTeamDropdownOpen)}
                style={{
                  width: '100%',
                  padding: '10px 12px',
                  paddingRight: '36px',
                  border: '1px solid #D1D5DB',
                  borderRadius: '8px',
                  fontSize: '14px',
                  backgroundColor: 'white',
                  color: selectedTeam ? '#111827' : '#9CA3AF',
                  cursor: 'pointer',
                  textAlign: 'left',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  outline: 'none',
                  position: 'relative'
                }}
                onFocus={(e) => {
                  e.currentTarget.style.borderColor = '#3B82F6';
                  e.currentTarget.style.boxShadow = '0 0 0 3px rgba(59, 130, 246, 0.1)';
                }}
                onBlur={(e) => {
                  e.currentTarget.style.borderColor = '#D1D5DB';
                  e.currentTarget.style.boxShadow = 'none';
                }}
              >
                <span>{selectedTeam ? teams.find(t => t.team_name === selectedTeam)?.team_name + (teams.find(t => t.team_name === selectedTeam)?.description ? ` - ${teams.find(t => t.team_name === selectedTeam)?.description}` : '') : 'Select your team...'}</span>
                <svg
                  width="12"
                  height="12"
                  viewBox="0 0 12 12"
                  fill="none"
                  style={{
                    transform: isTeamDropdownOpen ? 'translateY(-50%) rotate(180deg)' : 'translateY(-50%) rotate(0deg)',
                    transition: 'transform 0.2s',
                    position: 'absolute',
                    right: '12px',
                    top: '50%'
                  }}
                >
                  <path d="M6 9L1 4h10z" fill="#374151" />
                </svg>
              </button>
              
              {isTeamDropdownOpen && (
                <div style={{
                  position: 'absolute',
                  top: '100%',
                  left: 0,
                  right: 0,
                  marginTop: '4px',
                  backgroundColor: 'white',
                  border: '1px solid #D1D5DB',
                  borderRadius: '8px',
                  boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)',
                  zIndex: 10003,
                  maxHeight: '300px',
                  overflowY: 'auto',
                  overflowX: 'hidden'
                }}>
                  <div
                    onClick={() => {
                      setSelectedTeam('');
                      setIsTeamDropdownOpen(false);
                    }}
                    style={{
                      padding: '10px 12px',
                      cursor: 'pointer',
                      fontSize: '14px',
                      color: '#9CA3AF',
                      borderBottom: '1px solid #F3F4F6',
                      backgroundColor: selectedTeam === '' ? '#F3F4F6' : 'white'
                    }}
                    onMouseEnter={(e) => {
                      if (selectedTeam !== '') {
                        e.currentTarget.style.backgroundColor = '#F9FAFB';
                      }
                    }}
                    onMouseLeave={(e) => {
                      if (selectedTeam !== '') {
                        e.currentTarget.style.backgroundColor = 'white';
                      }
                    }}
                  >
                    Select your team...
                  </div>
                  {teams.map((team) => (
                    <div
                      key={team.team_name}
                      onClick={() => {
                        setSelectedTeam(team.team_name);
                        setIsTeamDropdownOpen(false);
                      }}
                      style={{
                        padding: '10px 12px',
                        cursor: 'pointer',
                        fontSize: '14px',
                        color: '#111827',
                        borderBottom: '1px solid #F3F4F6',
                        backgroundColor: selectedTeam === team.team_name ? '#F3F4F6' : 'white'
                      }}
                      onMouseEnter={(e) => {
                        if (selectedTeam !== team.team_name) {
                          e.currentTarget.style.backgroundColor = '#F9FAFB';
                        }
                      }}
                      onMouseLeave={(e) => {
                        if (selectedTeam !== team.team_name) {
                          e.currentTarget.style.backgroundColor = 'white';
                        }
                      }}
                    >
                      {team.team_name} {team.description ? `- ${team.description}` : ''}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Manager (Read-only, optional) */}
          {selectedTeam && (
            <div style={{ marginBottom: '20px' }}>
              <label style={{
                display: 'block',
                fontSize: '14px',
                fontWeight: '500',
                color: '#374151',
                marginBottom: '8px'
              }}>
                Manager <span style={{ fontSize: '12px', color: '#6B7280', fontWeight: 'normal' }}>(Optional)</span>
              </label>
              <input
                type="text"
                value={managerName || 'Not assigned'}
                readOnly
                disabled
                style={{
                  width: '100%',
                  padding: '10px 12px',
                  border: '1px solid #D1D5DB',
                  borderRadius: '8px',
                  fontSize: '14px',
                  backgroundColor: '#F9FAFB',
                  color: managerName ? '#111827' : '#9CA3AF',
                  cursor: 'not-allowed',
                  fontStyle: managerName ? 'normal' : 'italic'
                }}
              />
              {!managerName && (
                <p style={{
                  fontSize: '12px',
                  color: '#6B7280',
                  marginTop: '4px',
                  fontStyle: 'italic'
                }}>
                  This team doesn't have a manager assigned yet. You can still proceed.
                </p>
              )}
            </div>
          )}

          {/* Role */}
          <div style={{ marginBottom: '24px' }}>
            <label style={{
              display: 'block',
              fontSize: '14px',
              fontWeight: '500',
              color: '#374151',
              marginBottom: '8px'
            }}>
              Role
            </label>
            <input
              type="text"
              value={role}
              onChange={(e) => setRole(e.target.value)}
              placeholder="Your job title (will be auto-filled if available)"
              style={{
                width: '100%',
                padding: '10px 12px',
                border: '1px solid #D1D5DB',
                borderRadius: '8px',
                fontSize: '14px',
                color: '#111827'
              }}
            />
            <p style={{
              fontSize: '12px',
              color: '#6B7280',
              marginTop: '4px'
            }}>
              Your role will be automatically filled from your profile if available.
            </p>
          </div>

          {/* Error Message */}
          {error && (
            <div style={{
              padding: '12px',
              backgroundColor: '#FEE2E2',
              border: '1px solid #FECACA',
              borderRadius: '8px',
              color: '#DC2626',
              fontSize: '14px',
              marginBottom: '20px'
            }}>
              {error}
            </div>
          )}

          {/* Submit Button */}
          <button
            type="submit"
            disabled={saving || !selectedTeam}
            style={{
              width: '100%',
              padding: '12px',
              backgroundColor: saving || !selectedTeam ? '#9CA3AF' : '#3B82F6',
              color: 'white',
              border: 'none',
              borderRadius: '8px',
              fontSize: '16px',
              fontWeight: '500',
              cursor: saving || !selectedTeam ? 'not-allowed' : 'pointer',
              transition: 'background-color 0.2s'
            }}
          >
            {saving ? 'Saving...' : 'Complete Setup'}
          </button>
        </form>
      </div>
    </div>
  );
}

