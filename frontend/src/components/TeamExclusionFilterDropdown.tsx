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

interface TeamExclusionFilterDropdownProps {
  onExclusionChange: (excludedTeams: string[]) => void;
  initialExcluded?: string[];
}

export default function TeamExclusionFilterDropdown({
  onExclusionChange,
  initialExcluded = [] // Default: no exclusions (opt-in filtering)
}: TeamExclusionFilterDropdownProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [excludedTeams, setExcludedTeams] = useState<string[]>(initialExcluded);
  const [teams, setTeams] = useState<Team[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const dropdownRef = useRef<HTMLDivElement>(null);

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
          console.error('[TEAM EXCLUSION] Failed to load teams list');
        }
      } catch (err) {
        console.error('[TEAM EXCLUSION] Error loading teams:', err);
      } finally {
        setLoading(false);
      }
    };

    loadTeams();
  }, []);

  useEffect(() => {
    onExclusionChange(excludedTeams);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [excludedTeams]);

  const toggleTeam = (teamName: string) => {
    setExcludedTeams(prev => {
      if (prev.includes(teamName)) {
        return prev.filter(t => t !== teamName);
      } else {
        return [...prev, teamName];
      }
    });
  };

  const selectAll = () => {
    setExcludedTeams(teams.map(team => team.team_name));
  };

  const deselectAll = () => {
    setExcludedTeams([]);
  };

  const formatDisplayText = (): string => {
    if (excludedTeams.length === 0) return 'No exclusions';
    if (excludedTeams.length === teams.length) return 'All excluded';
    return `${excludedTeams.length} excluded`;
  };

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
          background: excludedTeams.length > 0 ? '#e1f5ff' : '#ffffff',
          border: `1px solid ${excludedTeams.length > 0 ? '#0078d4' : '#c8c6c4'}`,
          borderRadius: '4px',
          cursor: loading ? 'not-allowed' : 'pointer',
          fontSize: '14px',
          color: loading ? '#8a8886' : '#323130',
          fontWeight: excludedTeams.length > 0 ? 500 : 400,
          transition: 'all 0.15s',
          fontFamily: 'inherit',
          minWidth: '140px',
          justifyContent: 'space-between',
          opacity: loading ? 0.6 : 1
        }}
        onMouseEnter={(e) => {
          if (!loading) {
            e.currentTarget.style.borderColor = '#8a8886';
            if (excludedTeams.length === 0) {
              e.currentTarget.style.backgroundColor = '#faf9f8';
            }
          }
        }}
        onMouseLeave={(e) => {
          if (!loading) {
            e.currentTarget.style.borderColor = excludedTeams.length > 0 ? '#0078d4' : '#c8c6c4';
            e.currentTarget.style.backgroundColor = excludedTeams.length > 0 ? '#e1f5ff' : '#ffffff';
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
          minWidth: '280px',
          maxWidth: '400px',
          background: '#ffffff',
          border: '1px solid #c8c6c4',
          borderRadius: '4px',
          boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)',
          zIndex: 1000,
          padding: '16px',
          maxHeight: '400px',
          display: 'flex',
          flexDirection: 'column'
        }}>
          <div style={{ marginBottom: '12px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ fontWeight: 600, color: '#323130', fontSize: '14px' }}>
              Exclude Teams
            </div>
            <div style={{ display: 'flex', gap: '6px' }}>
              <button
                onClick={selectAll}
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
                onClick={deselectAll}
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

          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', maxHeight: '300px', overflowY: 'auto' }}>
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

          {excludedTeams.length > 0 && (
            <div style={{
              marginTop: '12px',
              padding: '8px 12px',
              background: '#e1f5ff',
              borderRadius: '4px',
              fontSize: '12px',
              color: '#004578',
              textAlign: 'center'
            }}>
              <strong>{excludedTeams.length}</strong> team{excludedTeams.length !== 1 ? 's' : ''} excluded
            </div>
          )}
        </div>
      )}
    </div>
  );
}
