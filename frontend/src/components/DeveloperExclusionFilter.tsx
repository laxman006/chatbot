'use client';

import { useState, useEffect } from 'react';
import { ADMIN_EMAILS } from '@/constants/admins';

interface DeveloperExclusionFilterProps {
  onExclusionChange: (excludedUsers: string[]) => void;
  initialExcluded?: string[];
}

export default function DeveloperExclusionFilter({ 
  onExclusionChange, 
  initialExcluded = [] // Default: no exclusions (opt-in filtering)
}: DeveloperExclusionFilterProps) {
  const [excludedUsers, setExcludedUsers] = useState<string[]>(initialExcluded);

  // Default developer list (can be extended)
  const developerEmails = ADMIN_EMAILS;

  useEffect(() => {
    onExclusionChange(excludedUsers);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [excludedUsers]);

  const toggleUser = (email: string) => {
    setExcludedUsers(prev => {
      if (prev.includes(email)) {
        return prev.filter(e => e !== email);
      } else {
        return [...prev, email];
      }
    });
  };

  const selectAll = () => {
    setExcludedUsers([...developerEmails]);
  };

  const deselectAll = () => {
    setExcludedUsers([]);
  };

  return (
    <div style={{
      marginBottom: '24px',
      padding: '20px',
      background: '#ffffff',
      borderRadius: '8px',
      border: '1px solid #e1e5e9',
      boxShadow: '0 1px 3px rgba(0, 0, 0, 0.05)'
    }}>
      <div style={{
        marginBottom: '16px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        paddingBottom: '12px',
        borderBottom: '1px solid #f3f2f1'
      }}>
        <div style={{
          fontWeight: 600,
          color: '#323130',
          fontSize: '14px',
          letterSpacing: '0.01em'
        }}>
          Exclude Developers
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            onClick={selectAll}
            style={{
              padding: '6px 12px',
              fontSize: '13px',
              fontWeight: 500,
              borderRadius: '4px',
              border: '1px solid #c8c6c4',
              background: '#ffffff',
              cursor: 'pointer',
              color: '#323130',
              transition: 'all 0.15s',
              fontFamily: 'inherit'
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
            Select All
          </button>
          <button
            onClick={deselectAll}
            style={{
              padding: '6px 12px',
              fontSize: '13px',
              fontWeight: 500,
              borderRadius: '4px',
              border: '1px solid #c8c6c4',
              background: '#ffffff',
              cursor: 'pointer',
              color: '#323130',
              transition: 'all 0.15s',
              fontFamily: 'inherit'
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
            Deselect All
          </button>
        </div>
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px' }}>
        {developerEmails.map((email) => {
          const isExcluded = excludedUsers.includes(email);
          const displayName = email.split('@')[0].replace(/\./g, ' ').replace(/\b\w/g, l => l.toUpperCase());
          
          return (
            <label
              key={email}
              style={{
                display: 'flex',
                alignItems: 'center',
                padding: '8px 14px',
                background: isExcluded ? '#e1f5ff' : '#ffffff',
                borderRadius: '4px',
                border: `1px solid ${isExcluded ? '#0078d4' : '#c8c6c4'}`,
                cursor: 'pointer',
                transition: 'all 0.15s',
                fontWeight: isExcluded ? 500 : 400
              }}
              onMouseEnter={(e) => {
                if (!isExcluded) {
                  e.currentTarget.style.backgroundColor = '#faf9f8';
                  e.currentTarget.style.borderColor = '#8a8886';
                }
              }}
              onMouseLeave={(e) => {
                if (!isExcluded) {
                  e.currentTarget.style.backgroundColor = '#ffffff';
                  e.currentTarget.style.borderColor = '#c8c6c4';
                }
              }}
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

      {excludedUsers.length > 0 && (
        <div style={{
          marginTop: '16px',
          padding: '10px 14px',
          background: '#e1f5ff',
          borderRadius: '4px',
          border: '1px solid #c7e0f4',
          fontSize: '12px',
          color: '#004578',
          display: 'flex',
          alignItems: 'center',
          gap: '6px'
        }}>
          <span style={{ fontWeight: 600 }}>{excludedUsers.length}</span>
          <span>developer{excludedUsers.length !== 1 ? 's' : ''} excluded from statistics</span>
        </div>
      )}
    </div>
  );
}
