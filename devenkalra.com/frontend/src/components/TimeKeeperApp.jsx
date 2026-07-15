import React, { useState, useEffect, useRef } from 'react';

// Timezone presets
const TIMEZONE_PRESETS = [
  { name: 'San Francisco', zone: 'America/Los_Angeles' },
  { name: 'New York', zone: 'America/New_York' },
  { name: 'London', zone: 'Europe/London' },
  { name: 'Paris', zone: 'Europe/Paris' },
  { name: 'Cairo', zone: 'Africa/Cairo' },
  { name: 'Dubai', zone: 'Asia/Dubai' },
  { name: 'New Delhi', zone: 'Asia/Kolkata' },
  { name: 'Singapore', zone: 'Asia/Singapore' },
  { name: 'Tokyo', zone: 'Asia/Tokyo' },
  { name: 'Sydney', zone: 'Australia/Sydney' }
];

// Helper to format duration: mm:ss.cc
const formatStopwatch = (ms) => {
  const totalSecs = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSecs / 60);
  const seconds = totalSecs % 60;
  const centiseconds = Math.floor((ms % 1000) / 10);
  return `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}.${centiseconds.toString().padStart(2, '0')}`;
};

// Helper to format timer: hh:mm:ss
const formatTimer = (ms) => {
  const totalSecs = Math.ceil(ms / 1000);
  const hours = Math.floor(totalSecs / 3600);
  const minutes = Math.floor((totalSecs % 3600) / 60);
  const seconds = totalSecs % 60;
  return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
};

// Play a pleasant double-chime synth sound when the timer completes
const playTimerCompletionSound = () => {
  try {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) return;
    const ctx = new AudioContextClass();
    
    // Play first chime (A5, 880Hz)
    const osc1 = ctx.createOscillator();
    const gain1 = ctx.createGain();
    osc1.type = 'sine';
    osc1.frequency.setValueAtTime(880, ctx.currentTime);
    gain1.gain.setValueAtTime(0.15, ctx.currentTime);
    gain1.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.5);
    
    osc1.connect(gain1);
    gain1.connect(ctx.destination);
    osc1.start(ctx.currentTime);
    osc1.stop(ctx.currentTime + 0.5);

    // Play second chime (C6, 1046.5Hz) after 150ms delay
    const delay = 0.15;
    const osc2 = ctx.createOscillator();
    const gain2 = ctx.createGain();
    osc2.type = 'sine';
    osc2.frequency.setValueAtTime(1046.5, ctx.currentTime + delay);
    gain2.gain.setValueAtTime(0.15, ctx.currentTime + delay);
    gain2.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + delay + 0.6);
    
    osc2.connect(gain2);
    gain2.connect(ctx.destination);
    osc2.start(ctx.currentTime + delay);
    osc2.stop(ctx.currentTime + delay + 0.6);
  } catch (e) {
    console.error("Failed to play timer completion sound", e);
  }
};

export const TimeKeeperApp = () => {
  // --- PERSISTED STATE ---
  const [activeTab, setActiveTab] = useState(() => {
    return localStorage.getItem('tk_active_tab') || 'clock';
  });
  const [theme, setTheme] = useState(() => {
    return localStorage.getItem('tk_theme') || 'dark';
  });
  const [layout, setLayout] = useState(() => {
    return localStorage.getItem('tk_layout') || 'concentric';
  });
  const [worldCities, setWorldCities] = useState(() => {
    const saved = localStorage.getItem('tk_world_cities');
    return saved ? JSON.parse(saved) : ['New York', 'London', 'Tokyo', 'New Delhi'];
  });

  // --- COMPONENT STATE ---
  const [resolutions, setResolutions] = useState(() => {
    const saved = localStorage.getItem('tk_resolutions');
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed) && parsed.length === 4) {
          return parsed;
        }
      } catch (e) {}
    }
    return [5, 30, 60, 300];
  });
  const [time, setTime] = useState(new Date());
  const [isEditingResolutions, setIsEditingResolutions] = useState(false);
  const [editResolutionsInput, setEditResolutionsInput] = useState('');
  const [resolutionsError, setResolutionsError] = useState('');

  useEffect(() => {
    localStorage.setItem('tk_resolutions', JSON.stringify(resolutions));
  }, [resolutions]);

  // --- STOPWATCH STATE ---
  const [stopwatchRunning, setStopwatchRunning] = useState(false);
  const [stopwatchTime, setStopwatchTime] = useState(0);
  const [laps, setLaps] = useState([]);
  const stopwatchStartRef = useRef(0);
  const stopwatchAccumulatedRef = useRef(0);

  // --- TIMER STATE ---
  const [timerRunning, setTimerRunning] = useState(false);
  const [timerTime, setTimerTime] = useState(0); // in ms
  const [timerInitialTime, setTimerInitialTime] = useState(0); // in ms
  const [timerInputHours, setTimerInputHours] = useState(0);
  const [timerInputMinutes, setTimerInputMinutes] = useState(5);
  const [timerInputSeconds, setTimerInputSeconds] = useState(0);
  const timerStartRef = useRef(0);
  const timerAccumulatedRef = useRef(0);

  // --- WORLD CLOCK STATE ---
  const [newCityName, setNewCityName] = useState('');

  // --- FULLSCREEN STATE & REF ---
  const containerRef = useRef(null);
  const [isFullscreen, setIsFullscreen] = useState(false);

  const toggleFullscreen = () => {
    if (!containerRef.current) return;
    const nextFullscreen = !isFullscreen;
    setIsFullscreen(nextFullscreen);

    if (nextFullscreen) {
      if (containerRef.current.requestFullscreen) {
        containerRef.current.requestFullscreen().catch(() => {});
      }
    } else {
      if (document.fullscreenElement && document.exitFullscreen) {
        document.exitFullscreen().catch(() => {});
      }
    }
  };

  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(!!document.fullscreenElement);
    };
    document.addEventListener('fullscreenchange', handleFullscreenChange);
    return () => {
      document.removeEventListener('fullscreenchange', handleFullscreenChange);
    };
  }, []);

  // Save preferences to localStorage
  useEffect(() => {
    localStorage.setItem('tk_active_tab', activeTab);
  }, [activeTab]);

  useEffect(() => {
    localStorage.setItem('tk_theme', theme);
  }, [theme]);

  useEffect(() => {
    localStorage.setItem('tk_layout', layout);
  }, [layout]);

  useEffect(() => {
    localStorage.setItem('tk_world_cities', JSON.stringify(worldCities));
  }, [worldCities]);

  // Parse URL parameters for resolutions
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const resParam = params.get('res') || params.get('resolutions');
    if (resParam) {
      const parsed = resParam.split(',')
        .map(str => {
          const match = str.trim().toLowerCase().match(/^(\d+)([smh]?)$/);
          if (!match) return null;
          const val = parseInt(match[1], 10);
          const unit = match[2];
          if (unit === 'm') return val * 60;
          if (unit === 'h') return val * 3600;
          return val; // default is seconds
        })
        .filter(val => val !== null && val > 0);
      if (parsed.length === 4) {
        setResolutions(parsed);
      }
    }
  }, []);

  // Master update loop for high-precision ticking
  useEffect(() => {
    let active = true;
    const tick = () => {
      if (!active) return;
      
      // Update Clock Time
      setTime(new Date());

      // Update Stopwatch
      if (stopwatchRunning) {
        const elapsed = performance.now() - stopwatchStartRef.current + stopwatchAccumulatedRef.current;
        setStopwatchTime(elapsed);
      }

      // Update Timer
      if (timerRunning) {
        const elapsed = performance.now() - timerStartRef.current;
        const remaining = Math.max(0, timerInitialTime - elapsed);
        setTimerTime(remaining);
        if (remaining <= 0) {
          setTimerRunning(false);
          timerAccumulatedRef.current = 0;
          setTimerTime(0);
          playTimerCompletionSound();
        }
      }

      requestAnimationFrame(tick);
    };

    requestAnimationFrame(tick);
    return () => {
      active = false;
    };
  }, [stopwatchRunning, timerRunning, timerInitialTime]);

  // --- STOPWATCH FUNCTIONS ---
  const startStopwatch = () => {
    if (!stopwatchRunning) {
      stopwatchStartRef.current = performance.now();
      setStopwatchRunning(true);
    }
  };

  const pauseStopwatch = () => {
    if (stopwatchRunning) {
      stopwatchAccumulatedRef.current += performance.now() - stopwatchStartRef.current;
      setStopwatchRunning(false);
    }
  };

  const resetStopwatch = () => {
    setStopwatchRunning(false);
    stopwatchAccumulatedRef.current = 0;
    setStopwatchTime(0);
    setLaps([]);
  };

  const recordLap = () => {
    if (stopwatchRunning || stopwatchTime > 0) {
      const currentLapTime = laps.length === 0 ? stopwatchTime : stopwatchTime - laps[0].cumulativeTime;
      setLaps([{
        lapNumber: laps.length + 1,
        lapTime: currentLapTime,
        cumulativeTime: stopwatchTime
      }, ...laps]);
    }
  };

  // --- TIMER FUNCTIONS ---
  const startTimer = () => {
    if (!timerRunning) {
      const totalMs = (timerInputHours * 3600 + timerInputMinutes * 60 + timerInputSeconds) * 1000;
      if (totalMs <= 0) return;

      if (timerTime === 0) {
        setTimerInitialTime(totalMs);
        setTimerTime(totalMs);
        timerStartRef.current = performance.now();
      } else {
        // Resume
        timerStartRef.current = performance.now() - (timerInitialTime - timerTime);
      }
      setTimerRunning(true);
    }
  };

  const pauseTimer = () => {
    if (timerRunning) {
      setTimerRunning(false);
    }
  };

  const resetTimer = () => {
    setTimerRunning(false);
    setTimerTime(0);
    setTimerInitialTime(0);
  };

  // --- WORLD CLOCK FUNCTIONS ---
  const addWorldCity = (e) => {
    e.preventDefault();
    if (!newCityName) return;
    const match = TIMEZONE_PRESETS.find(p => p.name === newCityName);
    if (match && !worldCities.includes(match.name)) {
      setWorldCities([...worldCities, match.name]);
    }
    setNewCityName('');
  };

  const removeWorldCity = (cityName) => {
    setWorldCities(worldCities.filter(c => c !== cityName));
  };
 
  // --- RESOLUTIONS EDIT FUNCTIONS ---
  const startEditingResolutions = () => {
    setEditResolutionsInput(resolutions.map(formatResLabel).join(', '));
    setResolutionsError('');
    setIsEditingResolutions(true);
  };

  const saveResolutions = (e) => {
    e.preventDefault();
    const parsed = editResolutionsInput.split(',')
      .map(str => {
        const match = str.trim().toLowerCase().match(/^(\d+)([smh]?)$/);
        if (!match) return null;
        const val = parseInt(match[1], 10);
        const unit = match[2];
        if (unit === 'm') return val * 60;
        if (unit === 'h') return val * 3600;
        return val;
      })
      .filter(val => val !== null && val > 0);

    if (parsed.length !== 4) {
      setResolutionsError('Please enter exactly 4 resolutions (e.g. 5s, 30s, 1m, 5m)');
      return;
    }

    setResolutions(parsed);
    setIsEditingResolutions(false);
  };

  // --- SVG PROGRESS RING MATH ---
  const renderProgressRing = (cx, cy, r, progress, strokeColor, strokeWidth = 6, glow = false, isMini = false, antiClockwise = false) => {
    const isBrown = strokeColor === '#a27b5c';
    const actualStrokeWidth = isMini ? strokeWidth : (isBrown ? 8 : 4);

    const angle = -Math.PI / 2 + (antiClockwise ? -1 : 1) * 2 * Math.PI * progress;
    const mx = cx + r * Math.cos(angle);
    const my = cy + r * Math.sin(angle);

    let ballRadius = 8;
    if (isMini) {
      ballRadius = Math.max(actualStrokeWidth * 1.2, 3.5);
    } else {
      ballRadius = isBrown ? 13 : 8;
    }

    return (
      <g key={r}>
        {/* Track */}
        <circle
          cx={cx}
          cy={cy}
          r={r}
          className="dial-track"
          strokeWidth={actualStrokeWidth}
          fill="none"
        />
        {/* Fixed Complete Colored Circle Path */}
        <circle
          cx={cx}
          cy={cy}
          r={r}
          stroke={strokeColor}
          strokeWidth={actualStrokeWidth}
          strokeOpacity={theme === 'dark' ? 0.75 : 0.65}
          fill="none"
          style={{
            filter: glow ? `drop-shadow(0 0 4px ${strokeColor})` : 'none',
          }}
        />
        {/* Traveling Marker Dot */}
        <circle
          cx={mx}
          cy={my}
          r={ballRadius}
          fill="#ffffff"
          stroke={strokeColor}
          strokeWidth={3}
          style={{
            filter: `drop-shadow(0 0 8px ${strokeColor})`,
            transition: (activeTab === 'clock' || stopwatchRunning || timerRunning) ? 'none' : 'cx 0.15s ease, cy 0.15s ease'
          }}
        />
      </g>
    );
  };

  // Colors for concentric dials
  const ringColors = [
    '#f43f5e', // Rose
    '#10b981', // Emerald
    '#0ea5e9', // Sky
    '#f59e0b', // Amber
    '#8b5cf6', // Violet
    '#ec4899'  // Pink
  ];

  // Helper to format resolution labels
  const formatResLabel = (secs) => {
    if (secs >= 3600) return `${secs / 3600}h`;
    if (secs >= 60) return `${secs / 60}m`;
    return `${secs}s`;
  };

  // Render Sub dials Side-By-Side helper
  const renderSideBySideDials = (elapsedSecs) => {
    if (activeTab === 'clock') {
      const minProgress = (time.getMinutes() + time.getSeconds() / 60) / 60;
      const hrProgress = ((time.getHours() % 12) + time.getMinutes() / 60 + time.getSeconds() / 3600) / 12;
      const dials = [
        { label: 'Minute', progress: minProgress, color: '#10b981' },
        { label: 'Hour', progress: hrProgress, color: '#0ea5e9' }
      ];

      return (
        <div className="sub-dials-grid">
          {dials.map((dial) => (
            <div key={dial.label} className="sub-dial-card">
              <svg width="100" height="100" viewBox="0 0 100 100">
                {renderProgressRing(50, 50, 40, dial.progress, dial.color, 4, theme === 'dark')}
              </svg>
              <div className="sub-dial-label">
                <span className="dot" style={{ backgroundColor: dial.color }}></span>
                {dial.label} Dial
              </div>
            </div>
          ))}
        </div>
      );
    }

    return (
      <div className="sub-dials-grid">
        {resolutions.slice(0, 6).map((res, idx) => {
          const progress = (elapsedSecs % res) / res;
          const color = ringColors[idx % ringColors.length];
          return (
            <div key={res} className="sub-dial-card">
              <svg width="100" height="100" viewBox="0 0 100 100">
                {renderProgressRing(50, 50, 40, progress, color, 4, theme === 'dark', false, activeTab === 'timer')}
              </svg>
              <div className="sub-dial-label">
                <span className="dot" style={{ backgroundColor: color }}></span>
                {formatResLabel(res)} Resolution
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  // Fetch local timezone time for World Clock
  const getCityTime = (zone) => {
    try {
      const options = {
        timeZone: zone,
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
      };
      const formatter = new Intl.DateTimeFormat([], options);
      const parts = formatter.formatToParts(new Date());
      const hour = parts.find(p => p.type === 'hour').value;
      const minute = parts.find(p => p.type === 'minute').value;
      const second = parts.find(p => p.type === 'second').value;
      return { hour, minute, second };
    } catch (e) {
      return { hour: '00', minute: '00', second: '00' };
    }
  };

  // Calculate elapsed time in seconds for visual dials
  const getElapsedSecondsForTab = () => {
    if (activeTab === 'clock') {
      const ms = time.getMilliseconds();
      return time.getHours() * 3600 + time.getMinutes() * 60 + time.getSeconds() + ms / 1000;
    }
    if (activeTab === 'stopwatch') {
      return stopwatchTime / 1000;
    }
    if (activeTab === 'timer') {
      return (timerInitialTime - timerTime) / 1000;
    }
    return 0;
  };

  const elapsedSecs = getElapsedSecondsForTab();

  const getConcentricRings = () => {
    const list = [];

    if (activeTab === 'clock') {
      const secProgress = (time.getSeconds() + time.getMilliseconds() / 1000) / 60;
      const minProgress = (time.getMinutes() + time.getSeconds() / 60) / 60;
      const hrProgress = ((time.getHours() % 12) + time.getMinutes() / 60 + time.getSeconds() / 3600) / 12;

      list.push({
        period: 60,
        progress: secProgress,
        color: '#a27b5c', // Brown main (second)
        isMain: true
      });

      list.push({
        period: 3600,
        progress: minProgress,
        color: '#10b981', // Emerald (minute)
        isMain: false
      });

      list.push({
        period: 43200,
        progress: hrProgress,
        color: '#0ea5e9', // Sky (hour)
        isMain: false
      });

      list.sort((a, b) => a.period - b.period);
    } else if (activeTab === 'stopwatch') {
      const activeRes = resolutions.slice(0, 4);
      while (activeRes.length < 4) {
        activeRes.push(60);
      }
      activeRes.forEach((res, idx) => {
        const isMainStopwatchRing = (res === 60);
        list.push({
          period: res,
          progress: (elapsedSecs % res) / res,
          color: isMainStopwatchRing ? '#a27b5c' : ringColors[idx % ringColors.length],
          isMain: isMainStopwatchRing
        });
      });

      list.sort((a, b) => a.period - b.period);
    } else if (activeTab === 'timer') {
      const activeRes = resolutions.slice(0, 4);
      while (activeRes.length < 4) {
        activeRes.push(60);
      }
      const resList = [];
      activeRes.forEach((res, idx) => {
        resList.push({
          period: res,
          progress: (elapsedSecs % res) / res,
          color: ringColors[idx % ringColors.length],
          isMain: false
        });
      });

      // Sort resolutions only (fastest outer, slowest inner)
      resList.sort((a, b) => a.period - b.period);
      list.push(...resList);

      // Add full timer interval as the absolute innermost ring
      const inputDurationSecs = timerInputHours * 3600 + timerInputMinutes * 60 + timerInputSeconds;
      const timerDurationSecs = timerInitialTime > 0 ? (timerInitialTime / 1000) : (inputDurationSecs > 0 ? inputDurationSecs : 300);
      list.push({
        period: timerDurationSecs,
        progress: timerInitialTime > 0 ? (timerInitialTime - timerTime) / timerInitialTime : 0,
        color: '#a27b5c', // Brown main
        isMain: true
      });
    }

    return list;
  };

  return (
    <div ref={containerRef} className={`timekeeper-container theme-${theme} ${isFullscreen ? 'fullscreen-mode' : ''}`}>
      <style>{`
        /* Local styling to keep styles modular and fully responsive */
        .timekeeper-container {
          --bg-panel: #ffffff;
          --bg-panel-glow: rgba(0, 0, 0, 0.02);
          --text-main: #2b2b2a;
          --text-sub: #6e6d6a;
          --border-main: #e6e3dd;
          --dial-bg: rgba(0, 0, 0, 0.03);
          --accent: #a27b5c;
          --accent-light: #f4efe6;
          --control-btn-bg: #2b2b2a;
          --control-btn-text: #ffffff;
          --glow-effect: none;
          
          font-family: 'Inter', -apple-system, sans-serif;
          border: 1px solid var(--border-main);
          border-radius: 12px;
          padding: 2rem;
          transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
          box-shadow: 0 4px 20px rgba(0, 0, 0, 0.03);
          background-color: var(--bg-panel);
          color: var(--text-main);
          margin-top: 1rem;
        }

        .timekeeper-container.theme-dark {
          --bg-panel: #111112;
          --bg-panel-glow: rgba(255, 255, 255, 0.02);
          --text-main: #f3f4f6;
          --text-sub: #9ca3af;
          --border-main: #27272a;
          --dial-bg: rgba(255, 255, 255, 0.02);
          --accent: #a27b5c;
          --accent-light: #2c2520;
          --control-btn-bg: #f3f4f6;
          --control-btn-text: #111112;
          --glow-effect: drop-shadow(0 0 10px rgba(255, 255, 255, 0.15));
          
          box-shadow: 0 4px 30px rgba(0, 0, 0, 0.4);
        }

        .main-dial-svg, .world-dial-svg {
          filter: var(--glow-effect);
        }

        /* Nav controls */
        .tk-navbar {
          display: flex;
          justify-content: space-between;
          align-items: center;
          border-bottom: 1px solid var(--border-main);
          padding-bottom: 1rem;
          margin-bottom: 2rem;
          flex-wrap: wrap;
          gap: 1rem;
        }

        .tk-tabs {
          display: flex;
          gap: 0.5rem;
        }

        .tk-tab-btn {
          background: none;
          border: 1px solid transparent;
          color: var(--text-sub);
          padding: 0.5rem 1rem;
          font-weight: 500;
          font-size: 0.9rem;
          border-radius: 6px;
          cursor: pointer;
          transition: all 0.2s ease;
        }

        .tk-tab-btn:hover {
          color: var(--text-main);
          background-color: var(--dial-bg);
        }

        .tk-tab-btn.active {
          color: var(--text-main);
          border-color: var(--border-main);
          background-color: var(--dial-bg);
          font-weight: 600;
        }

        .tk-settings {
          display: flex;
          gap: 0.5rem;
        }

        .tk-settings-btn {
          background: none;
          border: 1px solid var(--border-main);
          color: var(--text-main);
          padding: 0.4rem 0.8rem;
          font-size: 0.8rem;
          border-radius: 6px;
          cursor: pointer;
          display: flex;
          align-items: center;
          gap: 0.4rem;
          transition: all 0.2s ease;
        }

        .tk-settings-btn:hover {
          background-color: var(--dial-bg);
        }

        /* Dial Area styling */
        .dial-viewport {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          position: relative;
          margin: 1.5rem 0;
          width: min(80vw, 550px);
          height: min(80vw, 550px);
          container-type: size;
          transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
        }

        .main-dial-svg {
          width: 100%;
          height: 100%;
          max-width: 100%;
          max-height: 100%;
          filter: var(--glow-effect);
        }

        .dial-track {
          stroke: var(--dial-bg);
        }

        .dial-center-content {
          position: absolute;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          text-align: center;
          pointer-events: none;
          width: 65%;
        }

        .dial-digital-display {
          font-family: monospace;
          font-weight: 700;
          font-size: 13.5cqw;
          letter-spacing: -0.02em;
          color: var(--text-main);
          line-height: 1;
        }

        .dial-sub-text {
          font-size: 3.2cqw;
          color: var(--text-sub);
          margin-top: 2.2cqw;
          font-weight: 500;
          text-transform: uppercase;
          letter-spacing: 0.05em;
        }

        .layout-concentric .dial-digital-display {
          font-size: 9.5cqw;
        }

        .layout-concentric .dial-sub-text {
          font-size: 2.2cqw;
          margin-top: 1.2cqw;
        }

        /* Buttons and Inputs */
        .controls-row {
          display: flex;
          justify-content: center;
          gap: 0.75rem;
          margin-top: 1.5rem;
        }

        .control-btn {
          background-color: var(--control-btn-bg);
          color: var(--control-btn-text);
          border: none;
          padding: 0.6rem 1.2rem;
          font-weight: 600;
          font-size: 0.85rem;
          border-radius: 6px;
          cursor: pointer;
          transition: all 0.2s ease;
          display: flex;
          align-items: center;
          gap: 0.4rem;
        }

        .control-btn:hover {
          opacity: 0.9;
          transform: translateY(-1px);
        }

        .control-btn.secondary {
          background-color: transparent;
          border: 1px solid var(--border-main);
          color: var(--text-main);
        }

        .control-btn.secondary:hover {
          background-color: var(--dial-bg);
        }

        .timer-inputs-container {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          margin-bottom: 1.5rem;
        }

        .timer-input-box {
          display: flex;
          flex-direction: column;
          align-items: center;
        }

        .timer-input-box input {
          width: 50px;
          padding: 0.4rem;
          font-size: 1.1rem;
          text-align: center;
          background-color: var(--dial-bg);
          border: 1px solid var(--border-main);
          color: var(--text-main);
          border-radius: 6px;
          outline: none;
          font-family: monospace;
        }

        .timer-input-box label {
          font-size: 0.7rem;
          color: var(--text-sub);
          margin-top: 0.2rem;
          text-transform: uppercase;
          font-weight: 500;
        }

        .timer-colon {
          font-weight: bold;
          font-size: 1.2rem;
          color: var(--text-sub);
          margin-top: -12px;
        }

        /* Laps Table */
        .laps-container {
          max-height: 180px;
          overflow-y: auto;
          margin-top: 1.5rem;
          border: 1px solid var(--border-main);
          border-radius: 6px;
        }

        .laps-table {
          width: 100%;
          border-collapse: collapse;
          font-size: 0.8rem;
          text-align: left;
        }

        .laps-table th {
          background-color: var(--dial-bg);
          color: var(--text-sub);
          padding: 0.5rem;
          font-weight: 600;
        }

        .laps-table td {
          padding: 0.5rem;
          border-bottom: 1px solid var(--border-main);
          color: var(--text-main);
          font-family: monospace;
        }

        /* Side-By-Side Dials Grid */
        .sub-dials-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
          gap: 1rem;
          width: 100%;
          margin-top: 1.5rem;
          border-top: 1px solid var(--border-main);
          padding-top: 1.5rem;
        }

        .sub-dial-card {
          display: flex;
          flex-direction: column;
          align-items: center;
          background-color: var(--bg-panel-glow);
          border: 1px solid var(--border-main);
          border-radius: 8px;
          padding: 0.8rem 0.5rem;
        }

        .sub-dial-label {
          font-size: 0.7rem;
          color: var(--text-sub);
          margin-top: 0.4rem;
          font-weight: 600;
          display: flex;
          align-items: center;
          gap: 0.3rem;
          text-transform: uppercase;
        }

        .sub-dial-label .dot {
          width: 6px;
          height: 6px;
          border-radius: 50%;
          display: inline-block;
        }

        .tk-world-clock-wrapper {
          width: 100%;
        }

        /* World Clock Grid */
        .world-clock-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
          gap: 1.5rem;
          margin-top: 1.5rem;
        }

        .world-clock-card {
          border: 1px solid var(--border-main);
          border-radius: 10px;
          background-color: var(--bg-panel-glow);
          padding: 1.2rem;
          position: relative;
          display: flex;
          align-items: center;
          justify-content: space-between;
          transition: all 0.25s ease;
        }

        .world-clock-card:hover {
          border-color: var(--accent);
          transform: translateY(-1px);
        }

        .world-card-info {
          display: flex;
          flex-direction: column;
        }

        .world-card-city {
          font-weight: 600;
          font-size: 1.1rem;
          color: var(--text-main);
        }

        .world-card-timezone {
          font-size: 0.75rem;
          color: var(--text-sub);
        }

        .world-card-time {
          font-family: monospace;
          font-size: 1.5rem;
          font-weight: 700;
          color: var(--text-main);
          margin-top: 0.4rem;
        }

        .world-dial-svg {
          width: 70px;
          height: 70px;
          transition: all 0.3s ease;
        }

        .world-card-remove-btn {
          position: absolute;
          top: 0.4rem;
          right: 0.4rem;
          background: none;
          border: none;
          color: var(--text-sub);
          cursor: pointer;
          font-size: 0.75rem;
          opacity: 0;
          transition: opacity 0.2s ease;
        }

        .world-clock-card:hover .world-card-remove-btn {
          opacity: 1;
        }

        .world-clock-card .world-card-remove-btn:hover {
          color: #f43f5e;
        }

        .world-clock-adder-form {
          display: flex;
          gap: 0.5rem;
          margin-top: 2rem;
          border-top: 1px solid var(--border-main);
          padding-top: 1.5rem;
          justify-content: flex-start;
          align-items: center;
          flex-wrap: wrap;
        }

        .world-clock-adder-form select {
          padding: 0.5rem 1rem;
          background-color: var(--dial-bg);
          border: 1px solid var(--border-main);
          color: var(--text-main);
          border-radius: 6px;
          outline: none;
          font-size: 0.85rem;
        }

        /* Configured resolutions display */
        .resolutions-list {
          display: flex;
          gap: 0.5rem;
          font-size: 0.75rem;
          color: var(--text-sub);
          align-items: center;
          justify-content: center;
          margin-top: 1.5rem;
          font-weight: 500;
          flex-wrap: wrap;
          min-height: 24px;
        }

        .resolutions-list-badge {
          background-color: var(--dial-bg);
          border: 1px solid var(--border-main);
          padding: 0.1rem 0.4rem;
          border-radius: 4px;
          font-family: monospace;
          color: var(--text-main);
        }

        .resolutions-edit-trigger {
          background: none;
          border: none;
          color: var(--accent);
          cursor: pointer;
          font-size: 0.75rem;
          font-weight: 600;
          padding: 0 0.2rem;
          margin-left: 0.2rem;
        }

        .resolutions-edit-trigger:hover {
          text-decoration: underline;
        }

        .resolutions-edit-form {
          display: flex;
          align-items: center;
          gap: 0.4rem;
        }

        .resolutions-input {
          padding: 0.2rem 0.5rem;
          font-size: 0.8rem;
          background-color: var(--dial-bg);
          border: 1px solid var(--border-main);
          color: var(--text-main);
          border-radius: 4px;
          outline: none;
          width: 150px;
          font-family: monospace;
        }

        .control-btn.mini {
          padding: 0.2rem 0.5rem;
          font-size: 0.75rem;
          margin: 0;
          border-radius: 4px;
        }

        .resolutions-error-msg {
          color: #f43f5e;
          font-size: 0.7rem;
          margin-top: 0.2rem;
          width: 100%;
          text-align: center;
        }

        /* Fullscreen Mode Styles */
        .timekeeper-container.fullscreen-mode {
          position: fixed;
          top: 0;
          left: 0;
          width: 100vw;
          height: 100vh;
          z-index: 9999;
          border-radius: 0;
          margin: 0;
          padding: 3rem 2rem;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: space-between;
          background-color: var(--bg-panel);
          box-sizing: border-box;
          overflow-y: auto;
        }

        .timekeeper-container.fullscreen-mode .tk-navbar {
          width: 100%;
          max-width: 1200px;
        }

        .timekeeper-container.fullscreen-mode .dial-viewport {
          flex: 1;
          display: flex;
          flex-direction: column;
          justify-content: center;
          align-items: center;
          width: 78vmin;
          height: 78vmin;
          max-width: 85vw;
          max-height: 80vh;
          margin: auto 0;
          transform: none;
        }

        .timekeeper-container.fullscreen-mode .sub-dials-grid {
          width: 100%;
          max-width: 1200px;
          margin-top: 1rem;
        }
        
        .timekeeper-container.fullscreen-mode .world-clock-grid {
          width: 100%;
          max-width: 1400px;
          flex: 1;
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
          grid-auto-rows: 1fr;
          gap: 2rem;
          margin: auto 0;
          padding: 1rem 0;
          align-content: center;
        }

        .timekeeper-container.fullscreen-mode .world-clock-grid.items-1 {
          grid-template-columns: 1fr;
        }

        .timekeeper-container.fullscreen-mode .world-clock-grid.items-2 {
          grid-template-columns: repeat(2, 1fr);
        }

        .timekeeper-container.fullscreen-mode .world-clock-grid.items-3 {
          grid-template-columns: repeat(3, 1fr);
        }

        .timekeeper-container.fullscreen-mode .world-clock-grid.items-4 {
          grid-template-columns: repeat(2, 1fr);
          grid-template-rows: repeat(2, 1fr);
        }

        .timekeeper-container.fullscreen-mode .world-clock-grid.items-5,
        .timekeeper-container.fullscreen-mode .world-clock-grid.items-6 {
          grid-template-columns: repeat(3, 1fr);
        }

        .timekeeper-container.fullscreen-mode .world-clock-card {
          padding: 2.5rem 2rem;
          border-radius: 16px;
          height: 100%;
          box-sizing: border-box;
        }

        .timekeeper-container.fullscreen-mode .world-card-city {
          font-size: 1.8rem;
        }

        .timekeeper-container.fullscreen-mode .world-card-timezone {
          font-size: 1rem;
          margin-top: 0.2rem;
        }

        .timekeeper-container.fullscreen-mode .world-card-time {
          font-size: 2.8rem;
          margin-top: 0.8rem;
        }

        .timekeeper-container.fullscreen-mode .world-dial-svg {
          width: 120px;
          height: 120px;
        }

        .timekeeper-container.fullscreen-mode .tk-world-clock-wrapper {
          flex: 1;
          display: flex;
          flex-direction: column;
          justify-content: center;
          width: 100%;
          height: 100%;
          max-width: 1400px;
          margin: auto 0;
        }

        /* Workspace Layout Wrapper */
        .tk-workspace-layout {
          display: flex;
          flex-direction: column;
          align-items: center;
          width: 100%;
          gap: 1.5rem;
        }

        .tk-main-column {
          display: flex;
          flex-direction: column;
          align-items: center;
          width: 100%;
        }

        .tk-side-column {
          width: 100%;
        }

        .tk-controls-container {
          width: 100%;
          display: flex;
          flex-direction: column;
          align-items: center;
        }

        @media (min-width: 900px) {
          .tk-workspace-layout.layout-side_by_side {
            flex-direction: row;
            align-items: center;
            justify-content: center;
            gap: 3rem;
          }

          .tk-workspace-layout.layout-side_by_side .tk-main-column {
            flex: 1.1;
            max-width: 550px;
          }

          .tk-workspace-layout.layout-side_by_side .tk-side-column {
            flex: 0.9;
            max-width: 500px;
            border-left: 1px solid var(--border-main);
            padding-left: 3rem;
            margin-top: 0;
          }

          .tk-workspace-layout.layout-side_by_side .sub-dials-grid {
            border-top: none;
            padding-top: 0;
            margin-top: 0;
          }
        }

        /* Fullscreen responsive overrides */
        .timekeeper-container.fullscreen-mode .tk-workspace-layout {
          flex: 1;
          width: 100%;
          max-width: 1200px;
          justify-content: center;
          margin: auto 0;
          height: 100%;
        }

        .timekeeper-container.fullscreen-mode .tk-main-column {
          flex: 1;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          width: 100%;
          height: 100%;
        }

        /* Fullscreen responsive overrides for side-by-side layout */
        @media (min-width: 900px) {
          .timekeeper-container.fullscreen-mode .layout-side_by_side .dial-viewport {
            width: 45vmin;
            height: 45vmin;
            max-width: 450px;
            max-height: 450px;
          }
        }

      `}</style>

      {/* --- NAVBAR --- */}
      <div className="tk-navbar">
        <div className="tk-tabs">
          <button
            onClick={() => setActiveTab('clock')}
            className={`tk-tab-btn ${activeTab === 'clock' ? 'active' : ''}`}
          >
            ⏱ Clock
          </button>
          <button
            onClick={() => setActiveTab('world_clock')}
            className={`tk-tab-btn ${activeTab === 'world_clock' ? 'active' : ''}`}
          >
            🌐 World Clock
          </button>
          <button
            onClick={() => setActiveTab('stopwatch')}
            className={`tk-tab-btn ${activeTab === 'stopwatch' ? 'active' : ''}`}
          >
            ⏱ Stopwatch
          </button>
          <button
            onClick={() => setActiveTab('timer')}
            className={`tk-tab-btn ${activeTab === 'timer' ? 'active' : ''}`}
          >
            ⏳ Timer
          </button>
        </div>

        <div className="tk-settings">
          <button
            onClick={() => setLayout(layout === 'concentric' ? 'side_by_side' : 'concentric')}
            className="tk-settings-btn"
          >
            📐 Layout: {layout === 'concentric' ? 'Concentric' : 'Side-by-Side'}
          </button>
          <button
            onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            className="tk-settings-btn"
          >
            {theme === 'dark' ? '☀️ Light Mode' : '🌙 Dark Mode'}
          </button>
          <button
            onClick={toggleFullscreen}
            className="tk-settings-btn"
          >
            {isFullscreen ? '📺 Exit Full' : '📺 Fullscreen'}
          </button>
        </div>
      </div>

      {/* --- DIAL VISUALIZATION FOR CLOCK / STOPWATCH / TIMER --- */}
      {activeTab !== 'world_clock' ? (
        <div className={`tk-workspace-layout layout-${layout}`}>
          <div className="tk-main-column">
            <div className="dial-viewport">
              <svg viewBox="0 0 300 300" className="main-dial-svg">
                {layout === 'concentric' ? (
                  (() => {
                    const rings = getConcentricRings();
                    const numRings = rings.length;
                    const spacing = numRings <= 3 ? 20 : (numRings === 4 ? 15 : 12);
                    return rings.map((ring, idx) => {
                      const r = 130 - spacing * idx;
                      const strokeWidth = ring.isMain ? 8 : 4;
                      return renderProgressRing(150, 150, r, ring.progress, ring.color, strokeWidth, theme === 'dark', false, activeTab === 'timer');
                    });
                  })()
                ) : (
                  activeTab === 'clock' ? (
                    renderProgressRing(150, 150, 130, (time.getSeconds() + time.getMilliseconds() / 1000) / 60, '#a27b5c', 8, theme === 'dark')
                  ) : activeTab === 'stopwatch' ? (
                    renderProgressRing(150, 150, 130, ((stopwatchTime / 1000) % 60) / 60, '#a27b5c', 8, theme === 'dark')
                  ) : activeTab === 'timer' ? (
                    renderProgressRing(
                      150, 150, 130,
                      timerInitialTime > 0 ? (timerInitialTime - timerTime) / timerInitialTime : 0,
                      '#a27b5c', 8, theme === 'dark', false, true
                    )
                  ) : null
                )}
              </svg>

              {/* Central digital value overlay */}
              <div className="dial-center-content">
                <div className="dial-digital-display">
                  {activeTab === 'clock' && time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })}
                  {activeTab === 'stopwatch' && formatStopwatch(stopwatchTime)}
                  {activeTab === 'timer' && formatTimer(timerTime)}
                </div>
                <div className="dial-sub-text">
                  {activeTab === 'clock' && 'Local Time'}
                  {activeTab === 'stopwatch' && 'Stopwatch'}
                  {activeTab === 'timer' && 'Countdown Timer'}
                </div>
              </div>
            </div>

            {/* --- WIDGET CONTROL WORKSPACES --- */}
            <div className="tk-controls-container">
              {/* 1. CLOCK VIEW OPTIONS */}
              {activeTab === 'clock' && (
                <div style={{ textAlign: 'center', marginTop: '1rem' }}>
                  <div style={{ fontSize: '0.9rem', color: 'var(--text-sub)' }}>
                    Today is <b>{time.toLocaleDateString([], { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}</b>
                  </div>
                </div>
              )}

              {/* 2. STOPWATCH VIEW */}
              {activeTab === 'stopwatch' && (
                <div style={{ width: '100%' }}>
                  <div className="controls-row">
                    {!stopwatchRunning ? (
                      <button onClick={startStopwatch} className="control-btn">
                        ▶ Start
                      </button>
                    ) : (
                      <button onClick={pauseStopwatch} className="control-btn" style={{ backgroundColor: '#f43f5e', color: '#fff' }}>
                        ⏸ Pause
                      </button>
                    )}
                    <button onClick={recordLap} className="control-btn secondary" disabled={!stopwatchRunning && stopwatchTime === 0}>
                      🚩 Lap
                    </button>
                    <button onClick={resetStopwatch} className="control-btn secondary">
                      🔄 Reset
                    </button>
                  </div>

                  {laps.length > 0 && (
                    <div className="laps-container">
                      <table className="laps-table">
                        <thead>
                          <tr>
                            <th>Lap</th>
                            <th>Lap Time</th>
                            <th>Cumulative Time</th>
                          </tr>
                        </thead>
                        <tbody>
                          {laps.map((lap) => (
                            <tr key={lap.lapNumber}>
                              <td>🚩 Lap {lap.lapNumber}</td>
                              <td>{formatStopwatch(lap.lapTime)}</td>
                              <td>{formatStopwatch(lap.cumulativeTime)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}

              {/* 3. TIMER VIEW */}
              {activeTab === 'timer' && (
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: '100%' }}>
                  {/* Duration setter inputs when stopped */}
                  {!timerRunning && timerTime === 0 && (
                    <div className="timer-inputs-container">
                      <div className="timer-input-box">
                        <input
                          type="number"
                          min="0"
                          max="23"
                          value={timerInputHours}
                          onChange={(e) => setTimerInputHours(Math.max(0, parseInt(e.target.value, 10) || 0))}
                        />
                        <label>Hours</label>
                      </div>
                      <div className="timer-colon">:</div>
                      <div className="timer-input-box">
                        <input
                          type="number"
                          min="0"
                          max="59"
                          value={timerInputMinutes}
                          onChange={(e) => setTimerInputMinutes(Math.max(0, Math.min(59, parseInt(e.target.value, 10) || 0)))}
                        />
                        <label>Mins</label>
                      </div>
                      <div className="timer-colon">:</div>
                      <div className="timer-input-box">
                        <input
                          type="number"
                          min="0"
                          max="59"
                          value={timerInputSeconds}
                          onChange={(e) => setTimerInputSeconds(Math.max(0, Math.min(59, parseInt(e.target.value, 10) || 0)))}
                        />
                        <label>Secs</label>
                      </div>
                    </div>
                  )}

                  <div className="controls-row">
                    {!timerRunning ? (
                      <button onClick={startTimer} className="control-btn" disabled={(timerInputHours || timerInputMinutes || timerInputSeconds) === 0 && timerTime === 0}>
                        ▶ Start
                      </button>
                    ) : (
                      <button onClick={pauseTimer} className="control-btn" style={{ backgroundColor: '#f43f5e', color: '#fff' }}>
                        ⏸ Pause
                      </button>
                    )}
                    <button onClick={resetTimer} className="control-btn secondary" disabled={timerTime === 0 && !timerRunning}>
                      🔄 Reset
                    </button>
                  </div>
                </div>
              )}

              {/* Shared Resolutions Editor */}
              {activeTab !== 'clock' && (
                <div className="resolutions-list">
                  <span>Sub-dial resolutions:</span>
                  {isEditingResolutions ? (
                    <form onSubmit={saveResolutions} className="resolutions-edit-form">
                      <input
                        type="text"
                        className="resolutions-input"
                        value={editResolutionsInput}
                        onChange={(e) => {
                          setEditResolutionsInput(e.target.value);
                          setResolutionsError('');
                        }}
                        placeholder="e.g. 5s, 30s, 1m, 5m"
                        autoFocus
                      />
                      <button type="submit" className="control-btn mini">Save</button>
                      <button type="button" onClick={() => setIsEditingResolutions(false)} className="control-btn secondary mini">Cancel</button>
                    </form>
                  ) : (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', flexWrap: 'wrap' }}>
                      {resolutions.map(res => (
                        <span key={res} className="resolutions-list-badge">{formatResLabel(res)}</span>
                      ))}
                      <button onClick={startEditingResolutions} className="resolutions-edit-trigger" title="Edit resolutions">
                        ✏️ Edit
                      </button>
                    </div>
                  )}
                  {resolutionsError && (
                    <div className="resolutions-error-msg">{resolutionsError}</div>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Side Column for Sub-dials in side_by_side layout */}
          {layout === 'side_by_side' && (
            <div className="tk-side-column">
              {renderSideBySideDials(elapsedSecs)}
            </div>
          )}
        </div>
      ) : null}

      {/* 4. WORLD CLOCK VIEW */}
      {activeTab === 'world_clock' && (
        <div className="tk-world-clock-wrapper">
          <div className={`world-clock-grid items-${worldCities.length}`}>
            {worldCities.map((cityName) => {
              const preset = TIMEZONE_PRESETS.find(p => p.name === cityName);
              if (!preset) return null;
              
              const { hour, minute, second } = getCityTime(preset.zone);
              const elapsedCitySeconds = parseInt(hour, 10) * 3600 + parseInt(minute, 10) * 60 + parseInt(second, 10);
              
              return (
                <div key={cityName} className="world-clock-card">
                  <div className="world-card-info">
                    <span className="world-card-city">{preset.name}</span>
                    <span className="world-card-timezone">{preset.zone.split('/')[0]} Time</span>
                    <span className="world-card-time">{hour}:{minute}:{second}</span>
                  </div>
                  
                  {/* Miniature concentric dials for world clocks */}
                  <svg viewBox="0 0 100 100" className="world-dial-svg">
                    <circle cx="50" cy="50" r="44" className="dial-track" strokeWidth="4" fill="none" />
                    {/* Second ring */}
                    {renderProgressRing(50, 50, 44, parseInt(second, 10) / 60, '#a27b5c', 4, theme === 'dark', true)}
                    {/* Minute ring */}
                    {renderProgressRing(50, 50, 34, (parseInt(minute, 10) + parseInt(second, 10) / 60) / 60, '#10b981', 2.5, theme === 'dark', true)}
                    {/* Hour ring */}
                    {renderProgressRing(50, 50, 24, ((parseInt(hour, 10) % 12) + parseInt(minute, 10) / 60) / 12, '#0ea5e9', 2.5, theme === 'dark', true)}
                  </svg>
                  
                  <button
                    onClick={() => removeWorldCity(cityName)}
                    className="world-card-remove-btn"
                    title="Remove City"
                  >
                    ❌ Remove
                  </button>
                </div>
              );
            })}
          </div>

          {/* Form to add a new city */}
          {worldCities.length < TIMEZONE_PRESETS.length && (
            <form onSubmit={addWorldCity} className="world-clock-adder-form">
              <label style={{ fontSize: '0.85rem', fontWeight: '600', marginRight: '0.5rem' }}>
                Add City:
              </label>
              <select
                value={newCityName}
                onChange={(e) => setNewCityName(e.target.value)}
                required
              >
                <option value="">-- Choose City --</option>
                {TIMEZONE_PRESETS
                  .filter(p => !worldCities.includes(p.name))
                  .map(p => (
                    <option key={p.name} value={p.name}>{p.name} ({p.zone})</option>
                  ))
                }
              </select>
              <button type="submit" className="control-btn" style={{ padding: '0.5rem 1rem', marginTop: 0 }}>
                ➕ Add
              </button>
            </form>
          )}
        </div>
      )}
    </div>
  );
};
