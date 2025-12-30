'use client';

import { useState, useEffect, useRef } from 'react';
export type DateFilterType = 'all_time' | 'today' | 'yesterday' | 'last_n_days' | 'custom';

export interface DateRange {
  startDate: string | null;
  endDate: string | null;
}

interface DateRangeFilterDropdownProps {
  onFilterChange: (range: DateRange) => void;
  initialFilterType?: DateFilterType;
}

export default function DateRangeFilterDropdown({ onFilterChange, initialFilterType = 'all_time' }: DateRangeFilterDropdownProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [filterType, setFilterType] = useState<DateFilterType>(initialFilterType);
  const [lastNDays, setLastNDays] = useState<number>(3);
  const [customStartDate, setCustomStartDate] = useState<string>('');
  const [customStartTime, setCustomStartTime] = useState<string>('00:00');
  const [customEndDate, setCustomEndDate] = useState<string>('');
  const [customEndTime, setCustomEndTime] = useState<string>('23:59');
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Calculate date ranges (using UTC to match backend)
  const getTodayRange = (): DateRange => {
    const now = new Date();
    // Get UTC date components
    const year = now.getUTCFullYear();
    const month = now.getUTCMonth();
    const day = now.getUTCDate();
    
    // Start of today in UTC
    const start = new Date(Date.UTC(year, month, day, 0, 0, 0, 0));
    // End of today in UTC
    const end = new Date(Date.UTC(year, month, day, 23, 59, 59, 999));
    
    return { startDate: start.toISOString(), endDate: end.toISOString() };
  };

  const getYesterdayRange = (): DateRange => {
    const now = new Date();
    // Get UTC date components for yesterday
    const yesterday = new Date(Date.UTC(
      now.getUTCFullYear(),
      now.getUTCMonth(),
      now.getUTCDate() - 1
    ));
    
    const year = yesterday.getUTCFullYear();
    const month = yesterday.getUTCMonth();
    const day = yesterday.getUTCDate();
    
    // Start of yesterday in UTC
    const start = new Date(Date.UTC(year, month, day, 0, 0, 0, 0));
    // End of yesterday in UTC
    const end = new Date(Date.UTC(year, month, day, 23, 59, 59, 999));
    
    return { startDate: start.toISOString(), endDate: end.toISOString() };
  };

  const getLastNDaysRange = (days: number): DateRange => {
    const now = new Date();
    // Get UTC date components
    const year = now.getUTCFullYear();
    const month = now.getUTCMonth();
    const day = now.getUTCDate();
    
    // End of today in UTC
    const end = new Date(Date.UTC(year, month, day, 23, 59, 59, 999));
    // Start of N days ago in UTC
    const startDate = new Date(end);
    startDate.setUTCDate(startDate.getUTCDate() - days);
    startDate.setUTCHours(0, 0, 0, 0);
    
    return { startDate: startDate.toISOString(), endDate: end.toISOString() };
  };

  const getCustomRange = (): DateRange | null => {
    if (!customStartDate || !customEndDate) return null;
    const [startHour, startMinute] = customStartTime.split(':').map(Number);
    const [endHour, endMinute] = customEndTime.split(':').map(Number);
    
    // Parse date strings and create UTC dates
    const [startYear, startMonth, startDay] = customStartDate.split('-').map(Number);
    const [endYear, endMonth, endDay] = customEndDate.split('-').map(Number);
    
    // Create UTC dates (month is 0-indexed in Date constructor)
    const start = new Date(Date.UTC(startYear, startMonth - 1, startDay, startHour, startMinute, 0, 0));
    const end = new Date(Date.UTC(endYear, endMonth - 1, endDay, endHour, endMinute, 59, 999));
    
    return { startDate: start.toISOString(), endDate: end.toISOString() };
  };

  const formatDisplayText = (): string => {
    switch (filterType) {
      case 'all_time': return 'All Time';
      case 'today': return 'Today';
      case 'yesterday': return 'Yesterday';
      case 'last_n_days': return `Last ${lastNDays} days`;
      case 'custom':
        if (customStartDate && customEndDate) {
          const start = new Date(customStartDate);
          const end = new Date(customEndDate);
          return `${start.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })} - ${end.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}`;
        }
        return 'Custom';
      default: return 'Select date range';
    }
  };

  // Apply filter when values change
  useEffect(() => {
    let range: DateRange | null = null;
    switch (filterType) {
      case 'all_time': 
        // All time: no dates (null)
        range = { startDate: null, endDate: null };
        break;
      case 'today': range = getTodayRange(); break;
      case 'yesterday': range = getYesterdayRange(); break;
      case 'last_n_days': range = getLastNDaysRange(lastNDays); break;
      case 'custom': range = getCustomRange(); break;
    }
    if (range) {
      onFilterChange(range);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterType, lastNDays, customStartDate, customStartTime, customEndDate, customEndTime]);

  // Initialize custom dates
  useEffect(() => {
    if (filterType === 'custom' && !customStartDate) {
      const today = new Date().toISOString().split('T')[0];
      setCustomStartDate(today);
      setCustomEndDate(today);
    }
  }, [filterType, customStartDate]);

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
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          padding: '8px 16px',
          background: '#ffffff',
          border: '1px solid #c8c6c4',
          borderRadius: '4px',
          cursor: 'pointer',
          fontSize: '14px',
          color: '#323130',
          fontWeight: 400,
          transition: 'all 0.15s',
          fontFamily: 'inherit',
          minWidth: '160px',
          justifyContent: 'space-between'
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.borderColor = '#8a8886';
          e.currentTarget.style.backgroundColor = '#faf9f8';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.borderColor = '#c8c6c4';
          e.currentTarget.style.backgroundColor = '#ffffff';
        }}
      >
        <span>{formatDisplayText()}</span>
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

      {isOpen && (
        <div style={{
          position: 'absolute',
          top: '100%',
          left: 0,
          marginTop: '4px',
          minWidth: '320px',
          background: '#ffffff',
          border: '1px solid #c8c6c4',
          borderRadius: '4px',
          boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)',
          zIndex: 1000,
          padding: '16px'
        }}>
          <div style={{ marginBottom: '16px', fontWeight: 600, color: '#323130', fontSize: '14px' }}>
            Date Range
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {/* Radio buttons */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer', padding: '6px 8px', borderRadius: '4px' }}
                onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#faf9f8'}
                onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}>
                <input type="radio" name="dateFilter" value="all_time" checked={filterType === 'all_time'}
                  onChange={(e) => setFilterType(e.target.value as DateFilterType)}
                  style={{ marginRight: '8px', accentColor: '#0078d4', cursor: 'pointer' }} />
                <span style={{ fontSize: '14px', color: '#323130' }}>All Time</span>
              </label>
              <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer', padding: '6px 8px', borderRadius: '4px' }}
                onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#faf9f8'}
                onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}>
                <input type="radio" name="dateFilter" value="today" checked={filterType === 'today'}
                  onChange={(e) => setFilterType(e.target.value as DateFilterType)}
                  style={{ marginRight: '8px', accentColor: '#0078d4', cursor: 'pointer' }} />
                <span style={{ fontSize: '14px', color: '#323130' }}>Today</span>
              </label>
              <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer', padding: '6px 8px', borderRadius: '4px' }}
                onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#faf9f8'}
                onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}>
                <input type="radio" name="dateFilter" value="yesterday" checked={filterType === 'yesterday'}
                  onChange={(e) => setFilterType(e.target.value as DateFilterType)}
                  style={{ marginRight: '8px', accentColor: '#0078d4', cursor: 'pointer' }} />
                <span style={{ fontSize: '14px', color: '#323130' }}>Yesterday</span>
              </label>
              <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer', padding: '6px 8px', borderRadius: '4px', gap: '8px' }}
                onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#faf9f8'}
                onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}>
                <input type="radio" name="dateFilter" value="last_n_days" checked={filterType === 'last_n_days'}
                  onChange={(e) => setFilterType(e.target.value as DateFilterType)}
                  style={{ accentColor: '#0078d4', cursor: 'pointer' }} />
                <span style={{ fontSize: '14px', color: '#323130' }}>Last</span>
                <input type="number" min="1" max="365" value={lastNDays}
                  onChange={(e) => setLastNDays(parseInt(e.target.value) || 1)}
                  disabled={filterType !== 'last_n_days'}
                  style={{
                    width: '70px', padding: '4px 8px', borderRadius: '4px', border: '1px solid #c8c6c4',
                    fontSize: '14px', backgroundColor: filterType === 'last_n_days' ? '#ffffff' : '#f3f2f1'
                  }} />
                <span style={{ fontSize: '14px', color: '#323130' }}>days</span>
              </label>
              <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer', padding: '6px 8px', borderRadius: '4px' }}
                onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#faf9f8'}
                onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}>
                <input type="radio" name="dateFilter" value="custom" checked={filterType === 'custom'}
                  onChange={(e) => setFilterType(e.target.value as DateFilterType)}
                  style={{ marginRight: '8px', accentColor: '#0078d4', cursor: 'pointer' }} />
                <span style={{ fontSize: '14px', color: '#323130' }}>Custom</span>
              </label>
            </div>

            {/* Custom date inputs */}
            {filterType === 'custom' && (
              <div style={{ padding: '12px', background: '#faf9f8', borderRadius: '4px', border: '1px solid #edebe9' }}>
                <div style={{ display: 'flex', gap: '12px', flexDirection: 'column' }}>
                  <div>
                    <label style={{ fontSize: '12px', fontWeight: 600, color: '#605e5c', display: 'block', marginBottom: '6px' }}>From</label>
                    <div style={{ display: 'flex', gap: '8px' }}>
                      <input type="date" value={customStartDate} onChange={(e) => setCustomStartDate(e.target.value)}
                        style={{ flex: 1, padding: '6px 10px', borderRadius: '4px', border: '1px solid #c8c6c4', fontSize: '14px' }} />
                      <input type="time" value={customStartTime} onChange={(e) => setCustomStartTime(e.target.value)}
                        style={{ flex: 1, padding: '6px 10px', borderRadius: '4px', border: '1px solid #c8c6c4', fontSize: '14px' }} />
                    </div>
                  </div>
                  <div>
                    <label style={{ fontSize: '12px', fontWeight: 600, color: '#605e5c', display: 'block', marginBottom: '6px' }}>To</label>
                    <div style={{ display: 'flex', gap: '8px' }}>
                      <input type="date" value={customEndDate} onChange={(e) => setCustomEndDate(e.target.value)}
                        style={{ flex: 1, padding: '6px 10px', borderRadius: '4px', border: '1px solid #c8c6c4', fontSize: '14px' }} />
                      <input type="time" value={customEndTime} onChange={(e) => setCustomEndTime(e.target.value)}
                        style={{ flex: 1, padding: '6px 10px', borderRadius: '4px', border: '1px solid #c8c6c4', fontSize: '14px' }} />
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

