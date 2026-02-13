'use client';

import { useState, useEffect, useRef } from 'react';
import { ADMIN_EMAILS } from '@/constants/admins';
import { apiFetch } from '@/lib/api';

interface Team {
  team_name: string;
  lead_name: string;
  lead_email: string;
  color: string;
  description: string;
}

interface CombinedExclusionFilterDropdownProps {
  onDeveloperExclusionChange: (excludedUsers: string[]) => void;
  onTeamExclusionChange: (excludedTeams: string[]) => void;
  initialExcludedUsers?: string[];
  initialExcludedTeams?: string[];
}

export default function CombinedExclusionFilterDropdown({
  onDeveloperExclusionChange,
  onTeamExclusionChange,
  initialExcludedUsers = [],
  initialExcludedTeams = []
}: CombinedExclusionFilterDropdownProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [excludedUsers, setExcludedUsers] = useState<string[]>(initialExcludedUsers);
  const [excludedTeams, setExcludedTeams] = useState<string[]>(initialExcludedTeams);
  const [teams, setTeams] = useState<Team[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const developerEmails = ADMIN_EMAILS;

  // Load teams list on mount
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
          console.error('[COMBINED EXCLUSION] Failed to load teams list');
        }
      } catch (err) {
        console.error('[COMBINED EXCLUSION] Error loading teams:', err);
      } finally {
        setLoading(false);
      }
    };

    loadTeams();
  }, []);

  useEffect(() => {
    onDeveloperExclusionChange(excludedUsers);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [excludedUsers]);

  useEffect(() => {
    onTeamExclusionChange(excludedTeams);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [excludedTeams]);

  const toggleUser = (email: string) => {
    const next = excludedUsers.includes(email)
      ? excludedUsers.filter(e => e !== email)
      : [...excludedUsers, email];
    setExcludedUsers(next);
    onDeveloperExclusionChange(next);
  };

  const toggleTeam = (teamName: string) => {
    const next = excludedTeams.includes(teamName)
      ? excludedTeams.filter(t => t !== teamName)
      : [...excludedTeams, teamName];
    setExcludedTeams(next);
    onTeamExclusionChange(next); // Notify parent immediately (avoids Apply-click race)
  };

  const selectAllDevelopers = () => {
    const next = [...developerEmails];
    setExcludedUsers(next);
    onDeveloperExclusionChange(next);
  };

  const deselectAllDevelopers = () => {
    setExcludedUsers([]);
    onDeveloperExclusionChange([]);
  };

  const selectAllTeams = () => {
    const next = teams.map(team => team.team_name);
    setExcludedTeams(next);
    onTeamExclusionChange(next);
  };

  const deselectAllTeams = () => {
    setExcludedTeams([]);
    onTeamExclusionChange([]);
  };

  const formatDisplayText = (): string => {
    const totalExcluded = excludedUsers.length + excludedTeams.length;
    if (totalExcluded === 0) return 'No exclusions';
    if (excludedUsers.length > 0 && excludedTeams.length > 0) {
      return `${excludedUsers.length} dev${excludedUsers.length !== 1 ? 's' : ''}, ${excludedTeams.length} team${excludedTeams.length !== 1 ? 's' : ''}`;
    }
    if (excludedUsers.length > 0) {
      return `${excludedUsers.length} dev${excludedUsers.length !== 1 ? 's' : ''} excluded`;
    }
    return `${excludedTeams.length} team${excludedTeams.length !== 1 ? 's' : ''} excluded`;
  };

  const hasAnyExclusions = excludedUsers.length > 0 || excludedTeams.length > 0;

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen]);

  return (
    <div ref={dropdownRef} style={{ position: 'relative', display: 'inline-block' }}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        disabled={loading}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          padding: '8px 16px',
          background: hasAnyExclusions ? '#e1f5ff' : '#ffffff',
          border: `1px solid ${hasAnyExclusions ? '#0078d4' : '#c8c6c4'}`,
          borderRadius: '4px',
          cursor: loading ? 'not-allowed' : 'pointer',
          fontSize: '14px',
          color: loading ? '#8a8886' : '#323130',
          fontWeight: hasAnyExclusions ? 500 : 400,
          transition: 'all 0.15s',
          fontFamily: 'inherit',
          minWidth: '140px',
          justifyContent: 'space-between',
          opacity: loading ? 0.6 : 1
        }}
        onMouseEnter={(e) => {
          if (!loading) {
            e.currentTarget.style.borderColor = '#8a8886';
            if (!hasAnyExclusions) {
              e.currentTarget.style.backgroundColor = '#faf9f8';
            }
          }
        }}
        onMouseLeave={(e) => {
          if (!loading) {
            e.currentTarget.style.borderColor = hasAnyExclusions ? '#0078d4' : '#c8c6c4';
            e.currentTarget.style.backgroundColor = hasAnyExclusions ? '#e1f5ff' : '#ffffff';
          }
        }}
      >
        <span>{loading ? 'Loading...' : formatDisplayText()}</span>
        <svg
          width="12"
          height="12"
          viewBox="0 0 12 12"
          fill="none"
          style={{
            transform: isOpen ? 'rotate(180deg)' : 'rotate(0deg)',
            transition: 'transform 0.15s'
          }}
        >
          <path d="M2 4L6 8L10 4" stroke="#605e5c" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      {isOpen && !loading && (
        <div style={{
          position: 'absolute',
          top: '100%',
          right: 0,
          marginTop: '4px',
          minWidth: '320px',
          maxWidth: '450px',
          background: '#ffffff',
          border: '1px solid #c8c6c4',
          borderRadius: '4px',
          boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)',
          zIndex: 1000,
          padding: '16px',
          maxHeight: '500px',
          display: 'flex',
          flexDirection: 'column',
          overflowY: 'auto'
        }}>
          {/* Developers Section */}
          <div style={{ marginBottom: '20px' }}>
            <div style={{ marginBottom: '12px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ fontWeight: 600, color: '#323130', fontSize: '14px' }}>
                Exclude Developers
              </div>
              <div style={{ display: 'flex', gap: '6px' }}>
                <button
                  onClick={selectAllDevelopers}
                  style={{
                    padding: '4px 8px',
                    fontSize: '12px',
                    borderRadius: '4px',
                    border: '1px solid #c8c6c4',
                    background: '#ffffff',
                    cursor: 'pointer',
                    color: '#323130',
                    transition: 'all 0.15s'
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.backgroundColor = '#f3f2f1';
                    e.currentTarget.style.borderColor = '#8a8886';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.backgroundColor = '#ffffff';
                    e.currentTarget.style.borderColor = '#c8c6c4';
                  }}
                >
                  All
                </button>
                <button
                  onClick={deselectAllDevelopers}
                  style={{
                    padding: '4px 8px',
                    fontSize: '12px',
                    borderRadius: '4px',
                    border: '1px solid #c8c6c4',
                    background: '#ffffff',
                    cursor: 'pointer',
                    color: '#323130',
                    transition: 'all 0.15s'
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.backgroundColor = '#f3f2f1';
                    e.currentTarget.style.borderColor = '#8a8886';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.backgroundColor = '#ffffff';
                    e.currentTarget.style.borderColor = '#c8c6c4';
                  }}
                >
                  None
                </button>
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', maxHeight: '150px', overflowY: 'auto' }}>
              {developerEmails.map((email) => {
                const isExcluded = excludedUsers.includes(email);
                const displayName = email.split('@')[0].replace(/\./g, ' ').replace(/\b\w/g, l => l.toUpperCase());
                
                return (
                  <label
                    key={email}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      padding: '8px 10px',
                      borderRadius: '4px',
                      cursor: 'pointer',
                      transition: 'background-color 0.15s'
                    }}
                    onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#faf9f8'}
                    onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
                  >
                    <input
                      type="checkbox"
                      checked={isExcluded}
                      onChange={() => toggleUser(email)}
                      style={{
                        marginRight: '10px',
                        cursor: 'pointer',
                        width: '18px',
                        height: '18px',
                        accentColor: '#0078d4'
                      }}
                    />
                    <span style={{
                      fontSize: '13px',
                      color: '#323130',
                      fontWeight: isExcluded ? 500 : 400
                    }}>
                      {displayName}
                    </span>
                  </label>
                );
              })}
            </div>
          </div>

          {/* Divider */}
          <div style={{
            height: '1px',
            background: '#e1e5e9',
            marginBottom: '20px'
          }} />

          {/* Teams Section */}
          <div>
            <div style={{ marginBottom: '12px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ fontWeight: 600, color: '#323130', fontSize: '14px' }}>
                Exclude Teams
              </div>
              <div style={{ display: 'flex', gap: '6px' }}>
                <button
                  onClick={selectAllTeams}
                  style={{
                    padding: '4px 8px',
                    fontSize: '12px',
                    borderRadius: '4px',
                    border: '1px solid #c8c6c4',
                    background: '#ffffff',
                    cursor: 'pointer',
                    color: '#323130',
                    transition: 'all 0.15s'
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.backgroundColor = '#f3f2f1';
                    e.currentTarget.style.borderColor = '#8a8886';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.backgroundColor = '#ffffff';
                    e.currentTarget.style.borderColor = '#c8c6c4';
                  }}
                >
                  All
                </button>
                <button
                  onClick={deselectAllTeams}
                  style={{
                    padding: '4px 8px',
                    fontSize: '12px',
                    borderRadius: '4px',
                    border: '1px solid #c8c6c4',
                    background: '#ffffff',
                    cursor: 'pointer',
                    color: '#323130',
                    transition: 'all 0.15s'
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.backgroundColor = '#f3f2f1';
                    e.currentTarget.style.borderColor = '#8a8886';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.backgroundColor = '#ffffff';
                    e.currentTarget.style.borderColor = '#c8c6c4';
                  }}
                >
                  None
                </button>
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', maxHeight: '200px', overflowY: 'auto' }}>
              {teams.map((team) => {
                const isExcluded = excludedTeams.includes(team.team_name);
                
                return (
                  <label
                    key={team.team_name}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      padding: '8px 10px',
                      borderRadius: '4px',
                      cursor: 'pointer',
                      transition: 'background-color 0.15s'
                    }}
                    onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#faf9f8'}
                    onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
                  >
                    <input
                      type="checkbox"
                      checked={isExcluded}
                      onChange={() => toggleTeam(team.team_name)}
                      style={{
                        marginRight: '10px',
                        cursor: 'pointer',
                        width: '18px',
                        height: '18px',
                        accentColor: '#0078d4'
                      }}
                    />
                    <span style={{
                      fontSize: '13px',
                      color: '#323130',
                      fontWeight: isExcluded ? 500 : 400
                    }}>
                      {team.team_name}
                    </span>
                  </label>
                );
              })}
            </div>
          </div>

          {/* Summary Footer */}
          {hasAnyExclusions && (
            <div style={{
              marginTop: '16px',
              padding: '8px 12px',
              background: '#e1f5ff',
              borderRadius: '4px',
              fontSize: '12px',
              color: '#004578',
              textAlign: 'center'
            }}>
              <strong>
                {excludedUsers.length > 0 && excludedTeams.length > 0 
                  ? `${excludedUsers.length} developer${excludedUsers.length !== 1 ? 's' : ''} and ${excludedTeams.length} team${excludedTeams.length !== 1 ? 's' : ''} excluded`
                  : excludedUsers.length > 0
                  ? `${excludedUsers.length} developer${excludedUsers.length !== 1 ? 's' : ''} excluded`
                  : `${excludedTeams.length} team${excludedTeams.length !== 1 ? 's' : ''} excluded`
                }
              </strong>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
