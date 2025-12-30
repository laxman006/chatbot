'use client';

import { useState, useEffect } from 'react';

export type DateFilterType = 'today' | 'yesterday' | 'last_n_days' | 'custom';

export interface DateRange {
  startDate: string | null;
  endDate: string | null;
}

interface DateRangeFilterProps {
  onFilterChange: (range: DateRange) => void;
  initialFilterType?: DateFilterType;
}

export default function DateRangeFilter({ onFilterChange, initialFilterType = 'today' }: DateRangeFilterProps) {
  const [filterType, setFilterType] = useState<DateFilterType>(initialFilterType);
  const [lastNDays, setLastNDays] = useState<number>(3);
  const [customStartDate, setCustomStartDate] = useState<string>('');
  const [customStartTime, setCustomStartTime] = useState<string>('00:00');
  const [customEndDate, setCustomEndDate] = useState<string>('');
  const [customEndTime, setCustomEndTime] = useState<string>('23:59');

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
    
    return {
      startDate: start.toISOString(),
      endDate: end.toISOString()
    };
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
    
    return {
      startDate: start.toISOString(),
      endDate: end.toISOString()
    };
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
    const start = new Date(end);
    start.setUTCDate(start.getUTCDate() - days);
    start.setUTCHours(0, 0, 0, 0);
    
    return {
      startDate: start.toISOString(),
      endDate: end.toISOString()
    };
  };

  const getCustomRange = (): DateRange | null => {
    if (!customStartDate || !customEndDate) {
      return null;
    }
    const [startHour, startMinute] = customStartTime.split(':').map(Number);
    const [endHour, endMinute] = customEndTime.split(':').map(Number);
    
    // Parse date strings and create UTC dates
    const [startYear, startMonth, startDay] = customStartDate.split('-').map(Number);
    const [endYear, endMonth, endDay] = customEndDate.split('-').map(Number);
    
    // Create UTC dates (month is 0-indexed in Date constructor)
    const start = new Date(Date.UTC(startYear, startMonth - 1, startDay, startHour, startMinute, 0, 0));
    const end = new Date(Date.UTC(endYear, endMonth - 1, endDay, endHour, endMinute, 59, 999));
    
    return {
      startDate: start.toISOString(),
      endDate: end.toISOString()
    };
  };

  // Apply filter when filter type or values change
  useEffect(() => {
    let range: DateRange | null = null;
    
    switch (filterType) {
      case 'today':
        range = getTodayRange();
        break;
      case 'yesterday':
        range = getYesterdayRange();
        break;
      case 'last_n_days':
        range = getLastNDaysRange(lastNDays);
        break;
      case 'custom':
        range = getCustomRange();
        break;
    }
    
    if (range && range.startDate && range.endDate) {
      onFilterChange(range);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterType, lastNDays, customStartDate, customStartTime, customEndDate, customEndTime]);

  // Initialize custom dates to today if not set
  useEffect(() => {
    if (filterType === 'custom' && !customStartDate) {
      const today = new Date().toISOString().split('T')[0];
      setCustomStartDate(today);
      setCustomEndDate(today);
    }
  }, [filterType, customStartDate]);

  const formatDateRange = (): string => {
    switch (filterType) {
      case 'today':
        const todayRange = getTodayRange();
        return formatRangeDisplay(todayRange.startDate!, todayRange.endDate!);
      case 'yesterday':
        const yesterdayRange = getYesterdayRange();
        return formatRangeDisplay(yesterdayRange.startDate!, yesterdayRange.endDate!);
      case 'last_n_days':
        const lastNDaysRange = getLastNDaysRange(lastNDays);
        return formatRangeDisplay(lastNDaysRange.startDate!, lastNDaysRange.endDate!);
      case 'custom':
        if (customStartDate && customEndDate) {
          const custom = getCustomRange();
          if (custom) {
            return formatRangeDisplay(custom.startDate!, custom.endDate!);
          }
        }
        return 'Select date range';
      default:
        return '';
    }
  };

  const formatRangeDisplay = (start: string, end: string): string => {
    const startDate = new Date(start);
    const endDate = new Date(end);
    const startStr = startDate.toLocaleDateString('en-US', {
      month: '2-digit',
      day: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: true
    });
    const endStr = endDate.toLocaleDateString('en-US', {
      month: '2-digit',
      day: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: true
    });
    return `${startStr} - ${endStr}`;
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
        fontWeight: 600,
        color: '#323130',
        fontSize: '14px',
        letterSpacing: '0.01em'
      }}>
        Date Range Filter
      </div>
      
      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {/* Radio buttons for filter type - Clarity style */}
        <div style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: '20px',
          alignItems: 'center',
          paddingBottom: '12px',
          borderBottom: '1px solid #f3f2f1'
        }}>
          <label style={{
            display: 'flex',
            alignItems: 'center',
            cursor: 'pointer',
            padding: '6px 12px',
            borderRadius: '4px',
            transition: 'background-color 0.15s',
            backgroundColor: filterType === 'today' ? '#f3f2f1' : 'transparent'
          }}
          onMouseEnter={(e) => {
            if (filterType !== 'today') e.currentTarget.style.backgroundColor = '#faf9f8';
          }}
          onMouseLeave={(e) => {
            if (filterType !== 'today') e.currentTarget.style.backgroundColor = 'transparent';
          }}
          >
            <input
              type="radio"
              name="dateFilter"
              value="today"
              checked={filterType === 'today'}
              onChange={(e) => setFilterType(e.target.value as DateFilterType)}
              style={{
                marginRight: '8px',
                cursor: 'pointer',
                width: '16px',
                height: '16px',
                accentColor: '#0078d4'
              }}
            />
            <span style={{ fontSize: '14px', color: '#323130', fontWeight: filterType === 'today' ? 500 : 400 }}>
              Today
            </span>
          </label>
          
          <label style={{
            display: 'flex',
            alignItems: 'center',
            cursor: 'pointer',
            padding: '6px 12px',
            borderRadius: '4px',
            transition: 'background-color 0.15s',
            backgroundColor: filterType === 'yesterday' ? '#f3f2f1' : 'transparent'
          }}
          onMouseEnter={(e) => {
            if (filterType !== 'yesterday') e.currentTarget.style.backgroundColor = '#faf9f8';
          }}
          onMouseLeave={(e) => {
            if (filterType !== 'yesterday') e.currentTarget.style.backgroundColor = 'transparent';
          }}
          >
            <input
              type="radio"
              name="dateFilter"
              value="yesterday"
              checked={filterType === 'yesterday'}
              onChange={(e) => setFilterType(e.target.value as DateFilterType)}
              style={{
                marginRight: '8px',
                cursor: 'pointer',
                width: '16px',
                height: '16px',
                accentColor: '#0078d4'
              }}
            />
            <span style={{ fontSize: '14px', color: '#323130', fontWeight: filterType === 'yesterday' ? 500 : 400 }}>
              Yesterday
            </span>
          </label>
          
          <label style={{
            display: 'flex',
            alignItems: 'center',
            cursor: 'pointer',
            gap: '8px',
            padding: '6px 12px',
            borderRadius: '4px',
            transition: 'background-color 0.15s',
            backgroundColor: filterType === 'last_n_days' ? '#f3f2f1' : 'transparent'
          }}
          onMouseEnter={(e) => {
            if (filterType !== 'last_n_days') e.currentTarget.style.backgroundColor = '#faf9f8';
          }}
          onMouseLeave={(e) => {
            if (filterType !== 'last_n_days') e.currentTarget.style.backgroundColor = 'transparent';
          }}
          >
            <input
              type="radio"
              name="dateFilter"
              value="last_n_days"
              checked={filterType === 'last_n_days'}
              onChange={(e) => setFilterType(e.target.value as DateFilterType)}
              style={{
                marginRight: '0',
                cursor: 'pointer',
                width: '16px',
                height: '16px',
                accentColor: '#0078d4'
              }}
            />
            <span style={{ fontSize: '14px', color: '#323130', fontWeight: filterType === 'last_n_days' ? 500 : 400 }}>
              Last
            </span>
            <input
              type="number"
              min="1"
              max="365"
              value={lastNDays}
              onChange={(e) => setLastNDays(parseInt(e.target.value) || 1)}
              disabled={filterType !== 'last_n_days'}
              style={{
                width: '70px',
                padding: '6px 10px',
                borderRadius: '4px',
                border: '1px solid #c8c6c4',
                fontSize: '14px',
                color: '#323130',
                backgroundColor: filterType === 'last_n_days' ? '#ffffff' : '#f3f2f1',
                cursor: filterType === 'last_n_days' ? 'text' : 'not-allowed',
                transition: 'border-color 0.15s'
              }}
              onFocus={(e) => e.currentTarget.style.borderColor = '#0078d4'}
              onBlur={(e) => e.currentTarget.style.borderColor = '#c8c6c4'}
            />
            <span style={{ fontSize: '14px', color: '#323130' }}>days</span>
          </label>
          
          <label style={{
            display: 'flex',
            alignItems: 'center',
            cursor: 'pointer',
            padding: '6px 12px',
            borderRadius: '4px',
            transition: 'background-color 0.15s',
            backgroundColor: filterType === 'custom' ? '#f3f2f1' : 'transparent'
          }}
          onMouseEnter={(e) => {
            if (filterType !== 'custom') e.currentTarget.style.backgroundColor = '#faf9f8';
          }}
          onMouseLeave={(e) => {
            if (filterType !== 'custom') e.currentTarget.style.backgroundColor = 'transparent';
          }}
          >
            <input
              type="radio"
              name="dateFilter"
              value="custom"
              checked={filterType === 'custom'}
              onChange={(e) => setFilterType(e.target.value as DateFilterType)}
              style={{
                marginRight: '8px',
                cursor: 'pointer',
                width: '16px',
                height: '16px',
                accentColor: '#0078d4'
              }}
            />
            <span style={{ fontSize: '14px', color: '#323130', fontWeight: filterType === 'custom' ? 500 : 400 }}>
              Custom
            </span>
          </label>
        </div>

        {/* Custom date range picker - Clarity style */}
        {filterType === 'custom' && (
          <div style={{
            display: 'flex',
            gap: '20px',
            flexWrap: 'wrap',
            alignItems: 'flex-start',
            padding: '16px',
            background: '#faf9f8',
            borderRadius: '6px',
            border: '1px solid #edebe9'
          }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', flex: '1', minWidth: '200px' }}>
              <label style={{
                fontSize: '12px',
                fontWeight: 600,
                color: '#605e5c',
                textTransform: 'uppercase',
                letterSpacing: '0.5px'
              }}>
                From
              </label>
              <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                <div style={{ position: 'relative', flex: '1' }}>
                  <input
                    type="date"
                    value={customStartDate}
                    onChange={(e) => setCustomStartDate(e.target.value)}
                    style={{
                      width: '100%',
                      padding: '8px 12px',
                      borderRadius: '4px',
                      border: '1px solid #c8c6c4',
                      fontSize: '14px',
                      color: '#323130',
                      backgroundColor: '#ffffff',
                      transition: 'border-color 0.15s',
                      fontFamily: 'inherit'
                    }}
                    onFocus={(e) => e.currentTarget.style.borderColor = '#0078d4'}
                    onBlur={(e) => e.currentTarget.style.borderColor = '#c8c6c4'}
                  />
                </div>
                <div style={{ position: 'relative', flex: '1' }}>
                  <input
                    type="time"
                    value={customStartTime}
                    onChange={(e) => setCustomStartTime(e.target.value)}
                    style={{
                      width: '100%',
                      padding: '8px 12px',
                      borderRadius: '4px',
                      border: '1px solid #c8c6c4',
                      fontSize: '14px',
                      color: '#323130',
                      backgroundColor: '#ffffff',
                      transition: 'border-color 0.15s',
                      fontFamily: 'inherit'
                    }}
                    onFocus={(e) => e.currentTarget.style.borderColor = '#0078d4'}
                    onBlur={(e) => e.currentTarget.style.borderColor = '#c8c6c4'}
                  />
                </div>
              </div>
            </div>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', flex: '1', minWidth: '200px' }}>
              <label style={{
                fontSize: '12px',
                fontWeight: 600,
                color: '#605e5c',
                textTransform: 'uppercase',
                letterSpacing: '0.5px'
              }}>
                To
              </label>
              <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                <div style={{ position: 'relative', flex: '1' }}>
                  <input
                    type="date"
                    value={customEndDate}
                    onChange={(e) => setCustomEndDate(e.target.value)}
                    style={{
                      width: '100%',
                      padding: '8px 12px',
                      borderRadius: '4px',
                      border: '1px solid #c8c6c4',
                      fontSize: '14px',
                      color: '#323130',
                      backgroundColor: '#ffffff',
                      transition: 'border-color 0.15s',
                      fontFamily: 'inherit'
                    }}
                    onFocus={(e) => e.currentTarget.style.borderColor = '#0078d4'}
                    onBlur={(e) => e.currentTarget.style.borderColor = '#c8c6c4'}
                  />
                </div>
                <div style={{ position: 'relative', flex: '1' }}>
                  <input
                    type="time"
                    value={customEndTime}
                    onChange={(e) => setCustomEndTime(e.target.value)}
                    style={{
                      width: '100%',
                      padding: '8px 12px',
                      borderRadius: '4px',
                      border: '1px solid #c8c6c4',
                      fontSize: '14px',
                      color: '#323130',
                      backgroundColor: '#ffffff',
                      transition: 'border-color 0.15s',
                      fontFamily: 'inherit'
                    }}
                    onFocus={(e) => e.currentTarget.style.borderColor = '#0078d4'}
                    onBlur={(e) => e.currentTarget.style.borderColor = '#c8c6c4'}
                  />
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Display selected range - Clarity style */}
        <div style={{
          padding: '12px 16px',
          background: '#f3f2f1',
          borderRadius: '4px',
          border: '1px solid #edebe9',
          fontSize: '13px',
          color: '#605e5c',
          display: 'flex',
          alignItems: 'center',
          gap: '8px'
        }}>
          <span style={{ fontWeight: 600, color: '#323130' }}>Selected Range:</span>
          <span style={{ color: '#323130' }}>{formatDateRange()}</span>
        </div>
      </div>
    </div>
  );
}
