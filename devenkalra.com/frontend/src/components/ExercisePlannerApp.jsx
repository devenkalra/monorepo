import { useState, useEffect, useRef, useCallback } from 'react';

// Preset default workouts
const DEFAULT_WORKOUTS = [
  {
    id: 'pt-knees',
    name: 'Knee Strengthening Routine',
    category: 'Physical Therapy',
    sets: 2,
    reps: 10,
    interSetRest: 30, // seconds
    steps: [
      {
        id: 'step-1',
        title: 'Quad Sets Setup',
        type: 'prepare',
        duration: 5,
        instruction: 'Sit straight with a rolled towel under your knee. Contract your core and prepare.',
        mediaUrl: 'https://images.unsplash.com/photo-1544367567-0f2fcb009e0b?auto=format&fit=crop&q=80&w=400'
      },
      {
        id: 'step-2',
        title: 'Quad Sets Hold',
        type: 'work',
        duration: 5,
        instruction: 'Press the back of your knee down firmly into the towel. Tighten your thigh muscle.',
        mediaUrl: 'https://images.unsplash.com/photo-1517838277536-f5f99be501cd?auto=format&fit=crop&q=80&w=400'
      },
      {
        id: 'step-3',
        title: 'Relax Rest',
        type: 'rest',
        duration: 3,
        instruction: 'Relax your leg completely. Let the joint recover before the next rep.',
        mediaUrl: ''
      }
    ]
  },
  {
    id: 'hiit-7min',
    name: '7-Minute HIIT Workout',
    category: 'Cardio & Strength',
    sets: 1,
    reps: 1,
    interSetRest: 0,
    steps: [
      {
        id: 'hiit-1',
        title: 'Jumping Jacks',
        type: 'work',
        duration: 30,
        instruction: 'Perform rapid jumping jacks. Keep arms straight and land softly on the balls of your feet.',
        mediaUrl: 'https://images.unsplash.com/photo-1601422407692-ec4eeec1d9b3?auto=format&fit=crop&q=80&w=400'
      },
      {
        id: 'hiit-2',
        title: 'Rest',
        type: 'rest',
        duration: 10,
        instruction: 'Inhale deeply. Prepare for Wall Sit.',
        mediaUrl: ''
      },
      {
        id: 'hiit-3',
        title: 'Wall Sit',
        type: 'work',
        duration: 30,
        instruction: 'Lean against a wall and slide down until your knees form a 90-degree angle. Hold.',
        mediaUrl: 'https://images.unsplash.com/photo-1574680096145-d05b474e2155?auto=format&fit=crop&q=80&w=400'
      },
      {
        id: 'hiit-4',
        title: 'Rest',
        type: 'rest',
        duration: 10,
        instruction: 'Catch your breath. Prepare for Push Ups.',
        mediaUrl: ''
      },
      {
        id: 'hiit-5',
        title: 'Push Ups',
        type: 'work',
        duration: 30,
        instruction: 'Keep body in a straight line from head to heels. Lower chest to the floor.',
        mediaUrl: ''
      }
    ]
  },
  {
    id: 'weight-chest',
    name: 'Weight Machine: Chest Press',
    category: 'Strength Training',
    sets: 3,
    reps: 1,
    interSetRest: 60,
    steps: [
      {
        id: 'weight-1',
        title: 'Chest Press Sets',
        type: 'reps',
        repsCount: 10,
        instruction: 'Perform 10 controlled repetitions. Press outward on exhale, return slowly on inhale.',
        mediaUrl: 'https://images.unsplash.com/photo-1534438327276-14e5300c3a48?auto=format&fit=crop&q=80&w=400'
      }
    ]
  }
];

// Helper to format duration: mm:ss
const formatDuration = (secs) => {
  const mins = Math.floor(secs / 60);
  const remaining = Math.round(secs) % 60;
  return `${mins.toString().padStart(2, '0')}:${remaining.toString().padStart(2, '0')}`;
};

// Text to speech announcer
const speakAnnouncement = (text, enabled) => {
  if (!enabled || !window.speechSynthesis) return;
  try {
    // Cancel any ongoing speech first
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1.0;
    utterance.pitch = 1.05;
    window.speechSynthesis.speak(utterance);
  } catch (e) {
    console.error("Speech announcement failed:", e);
  }
};

// Play synthesized warning beep or chime
const playSynthBeep = (freq, duration, type = 'sine', enabled) => {
  if (!enabled) return;
  try {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) return;
    const ctx = new AudioContextClass();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    
    osc.type = type;
    osc.frequency.setValueAtTime(freq, ctx.currentTime);
    
    gain.gain.setValueAtTime(0.12, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + duration - 0.02);
    
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start(ctx.currentTime);
    osc.stop(ctx.currentTime + duration);
  } catch (e) {
    console.error("Synthesizer sound failed:", e);
  }
};

// Pure helper function to generate unique IDs
const generateUniqueId = (prefix = 'id') => {
  return `${prefix}-${Date.now()}-${Math.floor(Math.random() * 1000000)}`;
};

export const ExercisePlannerApp = () => {
  // --- PERSISTED STATE ---
  const [workouts, setWorkouts] = useState(() => {
    const saved = localStorage.getItem('ex_workouts');
    return saved ? JSON.parse(saved) : DEFAULT_WORKOUTS;
  });
  const [activeWorkoutId, setActiveWorkoutId] = useState(() => {
    return localStorage.getItem('ex_active_workout_id') || DEFAULT_WORKOUTS[0].id;
  });
  const [activeTab, setActiveTab] = useState(() => {
    return localStorage.getItem('ex_active_tab') || 'planner';
  });
  const [speechEnabled, setSpeechEnabled] = useState(() => {
    return localStorage.getItem('ex_speech_enabled') !== 'false';
  });
  const [soundEnabled, setSoundEnabled] = useState(() => {
    return localStorage.getItem('ex_sound_enabled') !== 'false';
  });
  const [theme, setTheme] = useState(() => {
    return localStorage.getItem('ex_theme') || 'dark';
  });

  // --- COMPONENT / WORKOUT STATE ---
  const [dbStatus, setDbStatus] = useState('offline');
  const [isSyncing, setIsSyncing] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);

  // Active workout run states
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentSet, setCurrentSet] = useState(1);
  const [currentRep, setCurrentRep] = useState(1);
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [stepTimeRemaining, setStepTimeRemaining] = useState(0);
  const [stepTotalTime, setStepTotalTime] = useState(0);
  const [workoutPhase, setWorkoutPhase] = useState('prepare'); // 'prepare' | 'work' | 'rest' | 'inter_set_rest' | 'completed'

  // Edit fields inside Planner
  const [editingWorkoutId, setEditingWorkoutId] = useState(null);
  const [editWorkoutName, setEditWorkoutName] = useState('');
  const [editWorkoutCategory, setEditWorkoutCategory] = useState('');
  const [editWorkoutSets, setEditWorkoutSets] = useState(1);
  const [editWorkoutReps, setEditWorkoutReps] = useState(1);
  const [editWorkoutRest, setEditWorkoutRest] = useState(30);

  // References
  const timerRef = useRef(null);
  const lastTimeRef = useRef(0);
  const speechCooldownRef = useRef(false);
  const containerRef = useRef(null);

  // Current active workout plan details
  const activeWorkout = workouts.find(w => w.id === activeWorkoutId) || workouts[0];

  // Helper to extract auth token
  const getAuthToken = () => {
    if (typeof window !== 'undefined' && window.__authToken) {
      return window.__authToken;
    }
    try {
      if (window.parent && window.parent.__authToken) {
        return window.parent.__authToken;
      }
    } catch {
      // Ignore cross-origin access blocks
    }
    try {
      return localStorage.getItem('authToken');
    } catch {
      return null;
    }
  };

  // Sync to database PageData
  const syncWorkoutsToDb = useCallback(async (workoutsToSync = workouts) => {
    const token = getAuthToken();
    setIsSyncing(true);
    try {
      const headers = { 'Content-Type': 'application/json' };
      if (token) {
        headers['Authorization'] = `Token ${token}`;
      }
      const response = await fetch('/api/page-data/exercise-planner/', {
        method: 'POST',
        headers,
        body: JSON.stringify({ workouts: workoutsToSync })
      });
      if (response.ok) {
        setDbStatus('synced');
      } else {
        setDbStatus('error');
      }
    } catch (e) {
      console.error(e);
      setDbStatus('offline');
    } finally {
      setIsSyncing(false);
    }
  }, [workouts]);

  // Fetch from DB
  const fetchWorkoutsFromDb = useCallback(async () => {
    const token = getAuthToken();
    setDbStatus('loading');
    try {
      const headers = { 'Content-Type': 'application/json' };
      if (token) {
        headers['Authorization'] = `Token ${token}`;
      }
      const response = await fetch('/api/page-data/exercise-planner/', { headers });
      if (response.ok) {
        const data = await response.json();
        if (data && Array.isArray(data.workouts) && data.workouts.length > 0) {
          setWorkouts(data.workouts);
          const activeExists = data.workouts.some(w => w.id === activeWorkoutId);
          if (!activeExists) {
            setActiveWorkoutId(data.workouts[0].id);
          }
          setDbStatus('synced');
        } else {
          // Push initial presets to DB
          await syncWorkoutsToDb(DEFAULT_WORKOUTS);
          setDbStatus('synced');
        }
      } else {
        setDbStatus('error');
      }
    } catch (e) {
      console.error(e);
      setDbStatus('offline');
    }
  }, [activeWorkoutId, syncWorkoutsToDb]);

  // Player state controls
  const resetPlayerState = useCallback(() => {
    setIsPlaying(false);
    setCurrentSet(1);
    setCurrentRep(1);
    setCurrentStepIndex(0);
    setWorkoutPhase('prepare');

    if (activeWorkout && activeWorkout.steps && activeWorkout.steps.length > 0) {
      const firstStep = activeWorkout.steps[0];
      setStepTimeRemaining(firstStep.duration || 0);
      setStepTotalTime(firstStep.duration || 0);
    } else {
      setStepTimeRemaining(0);
      setStepTotalTime(0);
    }
  }, [activeWorkout]);

  // Loop runner logic
  const advanceWorkoutPhase = useCallback(() => {
    if (!activeWorkout || !activeWorkout.steps || activeWorkout.steps.length === 0) return;

    // 1. Advance steps within the active repetition/cycle
    const nextStepIdx = currentStepIndex + 1;
    if (nextStepIdx < activeWorkout.steps.length) {
      setCurrentStepIndex(nextStepIdx);
      const nextStep = activeWorkout.steps[nextStepIdx];
      setWorkoutPhase(nextStep.type);
      setStepTimeRemaining(nextStep.duration || 0);
      setStepTotalTime(nextStep.duration || 0);
    } else {
      // Completed all steps in this cycle
      // 2. Advance reps/cycles
      const nextRep = currentRep + 1;
      if (nextRep <= activeWorkout.reps) {
        setCurrentRep(nextRep);
        setCurrentStepIndex(0);
        const firstStep = activeWorkout.steps[0];
        setWorkoutPhase(firstStep.type);
        setStepTimeRemaining(firstStep.duration || 0);
        setStepTotalTime(firstStep.duration || 0);
      } else {
        // Completed all reps in this set
        // 3. Advance sets
        const nextSet = currentSet + 1;
        if (nextSet <= activeWorkout.sets) {
          // Inter-set rest triggered
          if (activeWorkout.interSetRest > 0 && workoutPhase !== 'inter_set_rest') {
            setWorkoutPhase('inter_set_rest');
            setStepTimeRemaining(activeWorkout.interSetRest);
            setStepTotalTime(activeWorkout.interSetRest);
          } else {
            // No rest or rest completed, start next set
            setCurrentSet(nextSet);
            setCurrentRep(1);
            setCurrentStepIndex(0);
            const firstStep = activeWorkout.steps[0];
            setWorkoutPhase(firstStep.type);
            setStepTimeRemaining(firstStep.duration || 0);
            setStepTotalTime(firstStep.duration || 0);
          }
        } else {
          // Workout finished!
          setIsPlaying(false);
          setWorkoutPhase('completed');
          setStepTimeRemaining(0);
          setStepTotalTime(0);
        }
      }
    }
  }, [activeWorkout, currentStepIndex, currentRep, currentSet, workoutPhase]);

  // Manual Skip Forward
  const skipStepForward = useCallback(() => {
    if (workoutPhase === 'completed') return;
    
    if (workoutPhase === 'inter_set_rest') {
      // Skip the rest, start the next set
      setCurrentSet(prev => prev + 1);
      setCurrentRep(1);
      setCurrentStepIndex(0);
      const firstStep = activeWorkout.steps[0];
      setWorkoutPhase(firstStep.type);
      setStepTimeRemaining(firstStep.duration || 0);
      setStepTotalTime(firstStep.duration || 0);
    } else {
      advanceWorkoutPhase();
    }
  }, [activeWorkout, workoutPhase, advanceWorkoutPhase]);

  // Manual Skip Backward
  const skipStepBackward = useCallback(() => {
    if (!activeWorkout || !activeWorkout.steps || activeWorkout.steps.length === 0) return;

    if (workoutPhase === 'completed') {
      setWorkoutPhase(activeWorkout.steps[activeWorkout.steps.length - 1].type);
      setCurrentSet(activeWorkout.sets);
      setCurrentRep(activeWorkout.reps);
      setCurrentStepIndex(activeWorkout.steps.length - 1);
      const lastStep = activeWorkout.steps[activeWorkout.steps.length - 1];
      setStepTimeRemaining(lastStep.duration || 0);
      setStepTotalTime(lastStep.duration || 0);
      return;
    }

    if (workoutPhase === 'inter_set_rest') {
      // Go back to the end of the previous set (last step, last rep)
      setWorkoutPhase(activeWorkout.steps[activeWorkout.steps.length - 1].type);
      setCurrentStepIndex(activeWorkout.steps.length - 1);
      const lastStep = activeWorkout.steps[activeWorkout.steps.length - 1];
      setStepTimeRemaining(lastStep.duration || 0);
      setStepTotalTime(lastStep.duration || 0);
      return;
    }

    // Go back step by step
    const prevStepIdx = currentStepIndex - 1;
    if (prevStepIdx >= 0) {
      setCurrentStepIndex(prevStepIdx);
      const prevStep = activeWorkout.steps[prevStepIdx];
      setWorkoutPhase(prevStep.type);
      setStepTimeRemaining(prevStep.duration || 0);
      setStepTotalTime(prevStep.duration || 0);
    } else {
      // Go back reps
      const prevRep = currentRep - 1;
      if (prevRep >= 1) {
        setCurrentRep(prevRep);
        setCurrentStepIndex(activeWorkout.steps.length - 1);
        const lastStep = activeWorkout.steps[activeWorkout.steps.length - 1];
        setWorkoutPhase(lastStep.type);
        setStepTimeRemaining(lastStep.duration || 0);
        setStepTotalTime(lastStep.duration || 0);
      } else {
        // Go back sets
        const prevSet = currentSet - 1;
        if (prevSet >= 1) {
          // Trigger inter-set rest from previous set
          if (activeWorkout.interSetRest > 0) {
            setCurrentSet(prevSet);
            setWorkoutPhase('inter_set_rest');
            setStepTimeRemaining(activeWorkout.interSetRest);
            setStepTotalTime(activeWorkout.interSetRest);
          } else {
            setCurrentSet(prevSet);
            setCurrentRep(activeWorkout.reps);
            setCurrentStepIndex(activeWorkout.steps.length - 1);
            const lastStep = activeWorkout.steps[activeWorkout.steps.length - 1];
            setWorkoutPhase(lastStep.type);
            setStepTimeRemaining(lastStep.duration || 0);
            setStepTotalTime(lastStep.duration || 0);
          }
        } else {
          // At the absolute beginning
          resetPlayerState();
        }
      }
    }
  }, [activeWorkout, currentStepIndex, currentRep, currentSet, workoutPhase, resetPlayerState]);

  // Audio/Narrator step speech triggers
  const announceCurrentStepState = useCallback(() => {
    if (speechCooldownRef.current) return;
    
    speechCooldownRef.current = true;
    setTimeout(() => { speechCooldownRef.current = false; }, 200);

    if (workoutPhase === 'inter_set_rest') {
      playSynthBeep(660, 0.4, 'triangle', soundEnabled);
      speakAnnouncement(`Rest set completed. Take a ${activeWorkout.interSetRest} second break.`, speechEnabled);
    } else if (workoutPhase === 'completed') {
      playSynthBeep(880, 0.8, 'sine', soundEnabled);
      setTimeout(() => { playSynthBeep(1100, 0.6, 'sine', soundEnabled); }, 150);
      speakAnnouncement(`Congratulations! You have completed the ${activeWorkout.name} workout!`, speechEnabled);
    } else {
      const step = activeWorkout?.steps?.[currentStepIndex];
      if (step) {
        playSynthBeep(587.33, 0.3, 'sine', soundEnabled); // D5
        
        const countText = activeWorkout.reps > 1 ? `Repetition ${currentRep} of ${activeWorkout.reps}.` : '';
        const setText = activeWorkout.sets > 1 ? `Set ${currentSet} of ${activeWorkout.sets}.` : '';
        const nameText = step.title;
        const instText = step.instruction ? `. ${step.instruction}` : '';
        const speechMsg = `Starting ${nameText}. ${setText} ${countText} ${instText}`;
        
        speakAnnouncement(speechMsg, speechEnabled);
      }
    }
  }, [activeWorkout, currentStepIndex, currentRep, currentSet, workoutPhase, soundEnabled, speechEnabled]);

  const toggleFullscreen = useCallback(() => {
    if (!containerRef.current) return;
    const nextFs = !isFullscreen;
    setIsFullscreen(nextFs);
    if (nextFs) {
      if (containerRef.current.requestFullscreen) {
        containerRef.current.requestFullscreen().catch(() => {});
      }
    } else {
      if (document.fullscreenElement && document.exitFullscreen) {
        document.exitFullscreen().catch(() => {});
      }
    }
  }, [isFullscreen]);

  // Setup initial load and localStorage syncs
  useEffect(() => {
    const timer = setTimeout(() => {
      fetchWorkoutsFromDb();
    }, 0);
    return () => clearTimeout(timer);
  }, [fetchWorkoutsFromDb]);

  useEffect(() => {
    localStorage.setItem('ex_workouts', JSON.stringify(workouts));
  }, [workouts]);

  useEffect(() => {
    localStorage.setItem('ex_active_workout_id', activeWorkoutId);
    const timer = setTimeout(() => {
      resetPlayerState();
    }, 0);
    return () => clearTimeout(timer);
  }, [activeWorkoutId, resetPlayerState]);

  useEffect(() => {
    localStorage.setItem('ex_active_tab', activeTab);
  }, [activeTab]);

  useEffect(() => {
    localStorage.setItem('ex_speech_enabled', speechEnabled);
  }, [speechEnabled]);

  useEffect(() => {
    localStorage.setItem('ex_sound_enabled', soundEnabled);
  }, [soundEnabled]);

  useEffect(() => {
    localStorage.setItem('ex_theme', theme);
  }, [theme]);

  // Full Screen Listeners
  useEffect(() => {
    const handleFsChange = () => {
      setIsFullscreen(!!document.fullscreenElement);
    };
    document.addEventListener('fullscreenchange', handleFsChange);
    return () => {
      document.removeEventListener('fullscreenchange', handleFsChange);
    };
  }, []);

  // Keyboard shortcut accelerations
  useEffect(() => {
    const handleKeyDown = (e) => {
      // Avoid firing hotkeys when user is editing plan text fields
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName)) return;

      if (e.key === ' ' || e.code === 'Space') {
        e.preventDefault();
        if (activeTab === 'player') setIsPlaying(prev => !prev);
      } else if (e.key?.toLowerCase() === 'f') {
        e.preventDefault();
        toggleFullscreen();
      } else if (e.key?.toLowerCase() === 'n' && activeTab === 'player') {
        e.preventDefault();
        skipStepForward();
      } else if (e.key?.toLowerCase() === 'p' && activeTab === 'player') {
        e.preventDefault();
        skipStepBackward();
      } else if (e.key?.toLowerCase() === 's' && activeTab === 'player') {
        e.preventDefault();
        if (workoutPhase === 'inter_set_rest') {
          advanceWorkoutPhase();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [activeTab, isFullscreen, workoutPhase, skipStepForward, skipStepBackward, advanceWorkoutPhase, toggleFullscreen]);

  // Player precision ticker
  useEffect(() => {
    if (!isPlaying) {
      if (timerRef.current) {
        cancelAnimationFrame(timerRef.current);
        timerRef.current = null;
      }
      return;
    }

    lastTimeRef.current = performance.now();

    const loop = (timestamp) => {
      const delta = timestamp - lastTimeRef.current;
      lastTimeRef.current = timestamp;

      // Only tick timers if active step is time-based OR we are in a rest phase
      if (workoutPhase === 'inter_set_rest') {
        setStepTimeRemaining(prev => {
          const next = prev - delta / 1000;
          if (next <= 0) {
            advanceWorkoutPhase();
            return 0;
          }
          // Warn beep on final 3 seconds
          if (Math.ceil(next) !== Math.ceil(prev) && next <= 3 && next > 0) {
            playSynthBeep(440, 0.1, 'sine', soundEnabled);
          }
          return next;
        });
      } else {
        const currentStep = activeWorkout?.steps?.[currentStepIndex];
        if (currentStep && currentStep.type !== 'reps') {
          // Time-based step countdown
          setStepTimeRemaining(prev => {
            const next = prev - delta / 1000;
            if (next <= 0) {
              advanceWorkoutPhase();
              return 0;
            }
            // Warn beep on final 3 seconds
            if (Math.ceil(next) !== Math.ceil(prev) && next <= 3 && next > 0) {
              playSynthBeep(440, 0.1, 'sine', soundEnabled);
            }
            return next;
          });
        }
      }

      timerRef.current = requestAnimationFrame(loop);
    };

    timerRef.current = requestAnimationFrame(loop);

    return () => {
      if (timerRef.current) {
        cancelAnimationFrame(timerRef.current);
      }
    };
  }, [isPlaying, workoutPhase, activeWorkout, currentStepIndex, advanceWorkoutPhase, soundEnabled]);

  // Audio/Narrator trigger on step activation
  useEffect(() => {
    if (!isPlaying || activeTab !== 'player') return;
    announceCurrentStepState();
  }, [currentStepIndex, currentRep, currentSet, workoutPhase, isPlaying, activeTab, announceCurrentStepState]);

  // --- PLANNER ACTIONS ---
  const handleAddWorkout = () => {
    const newId = generateUniqueId('w');
    const newWorkout = {
      id: newId,
      name: 'New Custom Exercise Event',
      category: 'Strength',
      sets: 3,
      reps: 1,
      interSetRest: 60,
      steps: [
        {
          id: generateUniqueId('step'),
          title: 'Action Step 1',
          type: 'work',
          duration: 30,
          instruction: 'Perform workout movement.',
          mediaUrl: ''
        }
      ]
    };
    const updated = [...workouts, newWorkout];
    setWorkouts(updated);
    setActiveWorkoutId(newId);
    setEditingWorkoutId(newId);
    setEditWorkoutName(newWorkout.name);
    setEditWorkoutCategory(newWorkout.category);
    setEditWorkoutSets(newWorkout.sets);
    setEditWorkoutReps(newWorkout.reps);
    setEditWorkoutRest(newWorkout.interSetRest);
    syncWorkoutsToDb(updated);
  };

  const handleStartEdit = (workout) => {
    setEditingWorkoutId(workout.id);
    setEditWorkoutName(workout.name);
    setEditWorkoutCategory(workout.category);
    setEditWorkoutSets(workout.sets);
    setEditWorkoutReps(workout.reps);
    setEditWorkoutRest(workout.interSetRest);
  };

  const handleSaveWorkoutDetails = (wId) => {
    const updated = workouts.map(w => {
      if (w.id === wId) {
        return {
          ...w,
          name: editWorkoutName,
          category: editWorkoutCategory,
          sets: Number(editWorkoutSets) || 1,
          reps: Number(editWorkoutReps) || 1,
          interSetRest: Number(editWorkoutRest) || 0
        };
      }
      return w;
    });
    setWorkouts(updated);
    setEditingWorkoutId(null);
    syncWorkoutsToDb(updated);
  };

  const handleDeleteWorkout = (wId, e) => {
    e.stopPropagation();
    if (workouts.length <= 1) {
      alert("Cannot delete the last remaining workout!");
      return;
    }
    if (!window.confirm("Are you sure you want to delete this workout?")) return;

    const updated = workouts.filter(w => w.id !== wId);
    setWorkouts(updated);
    if (activeWorkoutId === wId) {
      setActiveWorkoutId(updated[0].id);
    }
    syncWorkoutsToDb(updated);
  };

  const handleDuplicateWorkout = (workout, e) => {
    e.stopPropagation();
    const newId = generateUniqueId('w');
    const duplicated = {
      ...workout,
      id: newId,
      name: `${workout.name} (Copy)`
    };
    const updated = [...workouts, duplicated];
    setWorkouts(updated);
    setActiveWorkoutId(newId);
    syncWorkoutsToDb(updated);
  };

  // Planner step modifications
  const handleUpdateStepField = (workoutId, stepId, field, val) => {
    const updated = workouts.map(w => {
      if (w.id === workoutId) {
        const updatedSteps = w.steps.map(s => {
          if (s.id === stepId) {
            return { ...s, [field]: val };
          }
          return s;
        });
        return { ...w, steps: updatedSteps };
      }
      return w;
    });
    setWorkouts(updated);
    syncWorkoutsToDb(updated);
  };

  const handleAddStep = (workoutId) => {
    const updated = workouts.map(w => {
      if (w.id === workoutId) {
        const newStep = {
          id: generateUniqueId('step'),
          title: 'New Workout Step',
          type: 'work',
          duration: 30,
          instruction: 'Describe how to do this step.',
          mediaUrl: ''
        };
        return { ...w, steps: [...w.steps, newStep] };
      }
      return w;
    });
    setWorkouts(updated);
    syncWorkoutsToDb(updated);
  };

  const handleDeleteStep = (workoutId, stepId) => {
    const workout = workouts.find(w => w.id === workoutId);
    if (workout.steps.length <= 1) {
      alert("Exercises must have at least 1 step!");
      return;
    }
    const updated = workouts.map(w => {
      if (w.id === workoutId) {
        return { ...w, steps: w.steps.filter(s => s.id !== stepId) };
      }
      return w;
    });
    setWorkouts(updated);
    syncWorkoutsToDb(updated);
  };

  const handleMoveStep = (workoutId, stepIndex, direction) => {
    const updated = workouts.map(w => {
      if (w.id === workoutId) {
        const steps = [...w.steps];
        const targetIdx = stepIndex + direction;
        if (targetIdx < 0 || targetIdx >= steps.length) return w;
        
        // Swap steps
        const temp = steps[stepIndex];
        steps[stepIndex] = steps[targetIdx];
        steps[targetIdx] = temp;
        
        return { ...w, steps };
      }
      return w;
    });
    setWorkouts(updated);
    syncWorkoutsToDb(updated);
  };

  // Reorder Workouts
  const handleMoveWorkout = (workoutIndex, direction) => {
    const targetIdx = workoutIndex + direction;
    if (targetIdx < 0 || targetIdx >= workouts.length) return;
    const updated = [...workouts];
    const temp = updated[workoutIndex];
    updated[workoutIndex] = updated[targetIdx];
    updated[targetIdx] = temp;
    setWorkouts(updated);
    syncWorkoutsToDb(updated);
  };

  // JSON Import/Export
  const handleExportWorkouts = () => {
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(workouts, null, 2));
    const downloadAnchor = document.createElement('a');
    downloadAnchor.setAttribute("href", dataStr);
    downloadAnchor.setAttribute("download", `exercise_workouts_backup.json`);
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
  };

  const handleImportWorkouts = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (event) => {
      try {
        const parsed = JSON.parse(event.target.result);
        if (Array.isArray(parsed) && parsed.length > 0 && parsed[0].steps) {
          setWorkouts(parsed);
          setActiveWorkoutId(parsed[0].id);
          syncWorkoutsToDb(parsed);
          alert("Workouts imported successfully!");
        } else {
          alert("Invalid backup file structure!");
        }
      } catch (err) {
        alert("Failed to parse JSON backup: " + err.message);
      }
    };
    reader.readAsText(file);
  };

  // --- RENDERING HELPERS ---

  // Media rendering switcher (supports Direct Images, YouTube, direct MP4 videos)
  const renderMediaIllustration = (mediaUrl, title = '') => {
    if (!mediaUrl) return null;

    // Check if it's a YouTube Link
    /* eslint-disable-next-line no-useless-escape */
    const ytMatch = mediaUrl.match(/(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^"&?\/\s]{11})/i);
    if (ytMatch && ytMatch[1]) {
      const ytId = ytMatch[1];
      return (
        <div className="media-container yt-embed">
          <iframe
            src={`https://www.youtube.com/embed/${ytId}?autoplay=1&mute=1&loop=1&playlist=${ytId}`}
            title={title}
            frameBorder="0"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowFullScreen
          />
        </div>
      );
    }


    // Check if it is a direct video link (MP4/WebM)
    const isVideo = mediaUrl.match(/\.(mp4|webm|ogg|mov)(\?.*)?$/i) || mediaUrl.includes('video');
    if (isVideo) {
      return (
        <div className="media-container video-player">
          <video
            src={mediaUrl}
            loop
            muted
            autoPlay
            playsInline
            key={mediaUrl} // Force reload when src changes
          />
        </div>
      );
    }

    // Default to Image rendering
    return (
      <div className="media-container image-player">
        <img src={mediaUrl} alt={title} loading="lazy" />
      </div>
    );
  };

  // Circular timer details calculation
  const getTimerProgress = () => {
    if (workoutPhase === 'completed') return 1;
    if (workoutPhase === 'inter_set_rest') {
      return stepTotalTime > 0 ? (stepTimeRemaining / stepTotalTime) : 0;
    }
    const currentStep = activeWorkout?.steps?.[currentStepIndex];
    if (currentStep) {
      if (currentStep.type === 'reps') return 1; // full static ring for rep-based work
      return stepTotalTime > 0 ? (stepTimeRemaining / stepTotalTime) : 0;
    }
    return 0;
  };

  // Progress concentric circles rings list
  const getConcentricRings = () => {
    const list = [];
    if (!activeWorkout || !activeWorkout.steps || activeWorkout.steps.length === 0) return list;

    // Ring 1: Active Step Progress (Innermost or Outermost)
    const stepColorMap = {
      work: '#10b981', // Emerald Work
      rest: '#3b82f6', // Blue Rest
      prepare: '#eab308', // Amber Prepare
      reps: '#a855f7', // Purple Reps
      inter_set_rest: '#f97316' // Orange InterSetRest
    };
    const activeColor = stepColorMap[workoutPhase] || '#a27b5c';
    list.push({
      radius: 95,
      progress: getTimerProgress(),
      color: activeColor,
      strokeWidth: 8,
      glow: true,
      label: 'Step Time'
    });

    // Ring 2: Current Rep/Cycle Progress
    if (activeWorkout.reps > 1) {
      const repProgress = (currentRep - 1 + (1 - getTimerProgress())) / activeWorkout.reps;
      list.push({
        radius: 82,
        progress: 1 - repProgress,
        color: '#a855f7', // Purple reps circle
        strokeWidth: 5,
        glow: false,
        label: 'Reps Progress'
      });
    }

    // Ring 3: Current Set Progress
    if (activeWorkout.sets > 1) {
      const setProgress = (currentSet - 1 + (currentStepIndex + (currentRep - 1) * activeWorkout.steps.length) / (activeWorkout.reps * activeWorkout.steps.length)) / activeWorkout.sets;
      list.push({
        radius: 70,
        progress: 1 - setProgress,
        color: '#a27b5c', // Brown main theme sets circle
        strokeWidth: 5,
        glow: false,
        label: 'Sets Progress'
      });
    }

    return list;
  };

  const activeStep = activeWorkout?.steps?.[currentStepIndex];

  return (
    <div ref={containerRef} className={`exercise-app-container theme-${theme} ${isFullscreen ? 'fullscreen-active' : ''}`}>
      <style>{`
        /* Scoped styles */
        .exercise-app-container {
          --bg-panel: #111112;
          --bg-card: rgba(255, 255, 255, 0.02);
          --bg-card-hover: rgba(255, 255, 255, 0.04);
          --border-color: rgba(255, 255, 255, 0.08);
          --border-focus: rgba(255, 255, 255, 0.2);
          --text-main: #f3f4f6;
          --text-sub: #9ca3af;
          --accent: #a27b5c;
          --accent-glow: rgba(162, 123, 92, 0.35);
          --success: #10b981;
          --danger: #ef4444;
          --warning: #f59e0b;
          --info: #0ea5e9;
          
          font-family: 'Inter', system-ui, sans-serif;
          background-color: var(--bg-panel);
          color: var(--text-main);
          border: 1px solid var(--border-color);
          border-radius: 12px;
          padding: 1.75rem;
          transition: background-color 0.3s ease, color 0.3s ease;
          display: flex;
          flex-direction: column;
          gap: 1.5rem;
          margin-top: 1rem;
          box-sizing: border-box;
          width: 100%;
        }

        .exercise-app-container.theme-light {
          --bg-panel: #fbfaf7;
          --bg-card: rgba(0, 0, 0, 0.02);
          --bg-card-hover: rgba(0, 0, 0, 0.04);
          --border-color: rgba(0, 0, 0, 0.08);
          --border-focus: rgba(0, 0, 0, 0.25);
          --text-main: #2b2b2a;
          --text-sub: #6e6d6a;
          --accent-glow: rgba(162, 123, 92, 0.12);
        }

        .ex-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          border-bottom: 1px solid var(--border-color);
          padding-bottom: 1rem;
          flex-wrap: wrap;
          gap: 1rem;
        }

        .ex-title-group h1 {
          font-family: 'Lora', Georgia, serif;
          font-size: 1.8rem;
          margin: 0;
          font-weight: 400;
        }

        .ex-title-group p {
          margin: 0.25rem 0 0 0;
          font-size: 0.85rem;
          color: var(--text-sub);
        }

        .ex-header-controls {
          display: flex;
          gap: 0.75rem;
          align-items: center;
        }

        .ex-btn {
          background: var(--text-main);
          color: var(--bg-panel);
          border: none;
          padding: 0.5rem 1rem;
          font-weight: 600;
          font-size: 0.8rem;
          border-radius: 6px;
          cursor: pointer;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          transition: all 0.2s ease;
          display: inline-flex;
          align-items: center;
          gap: 0.4rem;
        }

        .ex-btn:hover {
          opacity: 0.9;
          transform: translateY(-1px);
        }

        .ex-btn.secondary {
          background: transparent;
          border: 1px solid var(--border-color);
          color: var(--text-main);
        }

        .ex-btn.secondary:hover {
          background: var(--bg-card-hover);
          border-color: var(--border-focus);
        }

        .ex-btn.danger {
          background: var(--danger);
          color: #ffffff;
        }

        .sync-badge {
          font-size: 0.75rem;
          padding: 0.35rem 0.65rem;
          border-radius: 6px;
          border: 1px solid var(--border-color);
          color: var(--text-sub);
          background: var(--bg-card);
          display: inline-flex;
          align-items: center;
          gap: 0.3rem;
        }

        /* Tabs Navigation */
        .ex-tabs {
          display: flex;
          gap: 0.5rem;
          border-bottom: 1px solid var(--border-color);
          padding-bottom: 0.5rem;
        }

        .ex-tab-btn {
          background: none;
          border: none;
          padding: 0.5rem 1.25rem;
          color: var(--text-sub);
          font-weight: 500;
          font-size: 0.9rem;
          cursor: pointer;
          border-radius: 6px;
          transition: all 0.2s ease;
        }

        .ex-tab-btn:hover {
          color: var(--text-main);
          background: var(--bg-card-hover);
        }

        .ex-tab-btn.active {
          color: var(--text-main);
          background: var(--accent-glow);
          font-weight: 600;
        }

        /* --- PLANNER LAYOUT --- */
        .planner-layout {
          display: grid;
          grid-template-columns: 300px 1fr;
          gap: 1.5rem;
        }

        @media (max-width: 800px) {
          .planner-layout {
            grid-template-columns: 1fr;
          }
        }

        .workout-sidebar {
          display: flex;
          flex-direction: column;
          gap: 0.75rem;
          border-right: 1px solid var(--border-color);
          padding-right: 1rem;
        }

        @media (max-width: 800px) {
          .workout-sidebar {
            border-right: none;
            padding-right: 0;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 1rem;
          }
        }

        .workout-list-title {
          font-size: 0.85rem;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          color: var(--text-sub);
          margin-bottom: 0.25rem;
        }

        .workout-card {
          padding: 0.75rem 1rem;
          border: 1px solid var(--border-color);
          border-radius: 8px;
          cursor: pointer;
          transition: all 0.2s ease;
          background: transparent;
          display: flex;
          justify-content: space-between;
          align-items: center;
          text-align: left;
        }

        .workout-card:hover {
          border-color: var(--border-focus);
          background: var(--bg-card-hover);
        }

        .workout-card.active {
          border-color: var(--accent);
          background: var(--accent-glow);
        }

        .workout-info {
          display: flex;
          flex-direction: column;
          gap: 0.15rem;
        }

        .workout-name {
          font-size: 0.95rem;
          font-weight: 600;
        }

        .workout-meta {
          font-size: 0.75rem;
          color: var(--text-sub);
        }

        .card-actions {
          display: flex;
          gap: 0.35rem;
        }

        .card-action-btn {
          background: none;
          border: none;
          color: var(--text-sub);
          cursor: pointer;
          opacity: 0.6;
          transition: opacity 0.2s ease;
          padding: 0.25rem;
          border-radius: 4px;
        }

        .card-action-btn:hover {
          opacity: 1;
          color: var(--text-main);
          background: var(--bg-card-hover);
        }

        .card-action-btn.delete:hover {
          color: var(--danger);
          background: rgba(239, 68, 68, 0.1);
        }

        /* Planner editing area */
        .planner-details {
          display: flex;
          flex-direction: column;
          gap: 1.5rem;
        }

        .workout-detail-header {
          background: var(--bg-card);
          border: 1px solid var(--border-color);
          border-radius: 10px;
          padding: 1.25rem;
          display: flex;
          flex-direction: column;
          gap: 1rem;
        }

        .form-row {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
          gap: 1rem;
        }

        .form-group {
          display: flex;
          flex-direction: column;
          gap: 0.35rem;
        }

        .form-label {
          font-size: 0.75rem;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          color: var(--text-sub);
          font-weight: 600;
        }

        .form-input {
          background: var(--bg-panel);
          border: 1px solid var(--border-color);
          color: var(--text-main);
          padding: 0.55rem;
          border-radius: 6px;
          font-size: 0.9rem;
          outline: none;
          transition: border-color 0.2s ease;
        }

        .form-input:focus {
          border-color: var(--accent);
        }

        .steps-editor-list {
          display: flex;
          flex-direction: column;
          gap: 1rem;
        }

        .step-editor-card {
          background: var(--bg-card);
          border: 1px solid var(--border-color);
          border-radius: 8px;
          padding: 1rem;
          display: flex;
          flex-direction: column;
          gap: 0.75rem;
        }

        .step-editor-row1 {
          display: grid;
          grid-template-columns: 1fr 140px 100px auto;
          gap: 0.75rem;
          align-items: center;
        }

        @media (max-width: 600px) {
          .step-editor-row1 {
            grid-template-columns: 1fr;
          }
        }

        .step-drag-btn-group {
          display: flex;
          gap: 2px;
        }

        .step-drag-btn {
          background: none;
          border: 1px solid var(--border-color);
          color: var(--text-sub);
          cursor: pointer;
          padding: 0.25rem 0.5rem;
          font-size: 0.8rem;
          border-radius: 4px;
        }

        .step-drag-btn:hover {
          color: var(--text-main);
          border-color: var(--border-focus);
        }

        /* --- PLAYER LAYOUT --- */
        .player-layout {
          display: grid;
          grid-template-columns: 45% 55%;
          gap: 2rem;
          align-items: center;
          min-height: 480px;
        }

        @media (max-width: 800px) {
          .player-layout {
            grid-template-columns: 1fr;
            gap: 1.5rem;
            min-height: auto;
          }
        }

        .player-left {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          position: relative;
        }

        /* SVG concentric rings dial */
        .svg-dial-container {
          position: relative;
          width: min(85vw, 320px);
          height: min(85vw, 320px);
          display: flex;
          justify-content: center;
          align-items: center;
        }

        .dial-svg {
          width: 100%;
          height: 100%;
          transform: rotate(-90deg);
        }

        .dial-center-label {
          position: absolute;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          text-align: center;
          pointer-events: none;
          width: 60%;
        }

        .time-display {
          font-family: monospace;
          font-size: 3.2rem;
          font-weight: 700;
          line-height: 1;
        }

        .phase-badge {
          font-size: 0.75rem;
          text-transform: uppercase;
          letter-spacing: 0.08em;
          font-weight: 600;
          padding: 0.2rem 0.5rem;
          border-radius: 4px;
          margin-top: 0.5rem;
          background: rgba(255, 255, 255, 0.1);
        }

        .phase-badge.work { background: var(--success); color: #ffffff; }
        .phase-badge.rest { background: var(--info); color: #ffffff; }
        .phase-badge.prepare { background: var(--warning); color: #ffffff; }
        .phase-badge.reps { background: #a855f7; color: #ffffff; }
        .phase-badge.inter_set_rest { background: #f97316; color: #ffffff; }

        .player-right {
          display: flex;
          flex-direction: column;
          gap: 1.5rem;
          justify-content: center;
        }

        .active-step-info-card {
          background: var(--bg-card);
          border: 1px solid var(--border-color);
          border-radius: 12px;
          padding: 1.5rem;
        }

        .active-workout-name {
          font-size: 0.95rem;
          text-transform: uppercase;
          letter-spacing: 0.08em;
          color: var(--accent);
          font-weight: 700;
        }

        .active-step-title {
          font-family: 'Lora', Georgia, serif;
          font-size: 1.8rem;
          margin: 0.35rem 0;
          font-weight: 400;
        }

        .active-step-instruction {
          color: var(--text-sub);
          font-size: 1rem;
          line-height: 1.5;
          margin-top: 0.5rem;
        }

        .active-totals-grid {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 1rem;
          margin-top: 1rem;
          border-top: 1px solid var(--border-color);
          padding-top: 1rem;
        }

        .total-item {
          display: flex;
          flex-direction: column;
          align-items: center;
        }

        .total-val {
          font-size: 1.3rem;
          font-weight: 700;
        }

        .total-lbl {
          font-size: 0.7rem;
          text-transform: uppercase;
          color: var(--text-sub);
          margin-top: 0.15rem;
        }

        /* Playback controls row */
        .player-controls-row {
          display: flex;
          gap: 0.75rem;
          justify-content: center;
          flex-wrap: wrap;
        }

        /* Illustration panel media containers */
        .media-container {
          width: 100%;
          border-radius: 8px;
          border: 1px solid var(--border-color);
          overflow: hidden;
          background: #000;
          display: flex;
          align-items: center;
          justify-content: center;
          max-height: 240px;
          aspect-ratio: 16 / 9;
        }

        .media-container img {
          width: 100%;
          height: 100%;
          object-fit: cover;
        }

        .media-container video {
          width: 100%;
          height: 100%;
          object-fit: cover;
        }

        .media-container iframe {
          width: 100%;
          height: 100%;
          border: none;
        }

        .next-preview {
          background: rgba(255, 255, 255, 0.01);
          border: 1px dashed var(--border-color);
          border-radius: 8px;
          padding: 0.75rem 1rem;
          display: flex;
          justify-content: space-between;
          align-items: center;
          font-size: 0.85rem;
        }

        /* Full Screen styling */
        .exercise-app-container.fullscreen-active {
          position: fixed;
          top: 0; left: 0; right: 0; bottom: 0;
          z-index: 9999;
          border-radius: 0;
          margin: 0;
          padding: 2rem;
          height: 100vh;
          width: 100vw;
          justify-content: center;
          align-items: center;
          overflow: hidden;
        }

        .exercise-app-container.fullscreen-active .ex-header,
        .exercise-app-container.fullscreen-active .ex-tabs,
        .exercise-app-container.fullscreen-active .next-preview,
        .exercise-app-container.fullscreen-active .import-export-row {
          display: none !important;
        }

        .exercise-app-container.fullscreen-active .player-layout {
          width: 100% !important;
          height: calc(100vh - 120px) !important;
          max-width: 1200px !important;
          grid-template-columns: 48% 52% !important;
        }

        @media (max-width: 800px) and (orientation: portrait) {
          .exercise-app-container.fullscreen-active .player-layout {
            grid-template-columns: 1fr !important;
          }
        }

        .exercise-app-container.fullscreen-active .svg-dial-container {
          width: min(80vw, 70vh, 460px) !important;
          height: min(80vw, 70vh, 460px) !important;
        }

        .exercise-app-container.fullscreen-active .time-display {
          font-size: clamp(3rem, 12cqw, 6rem) !important;
        }

        .exercise-app-container.fullscreen-active .active-step-title {
          font-size: clamp(1.8rem, 6cqw, 3.5rem) !important;
        }

        .exercise-app-container.fullscreen-active .active-step-instruction {
          font-size: clamp(1rem, 3cqw, 1.4rem) !important;
        }

        .exercise-app-container.fullscreen-active .media-container {
          max-height: 380px !important;
        }

        .fs-close-floating-btn {
          position: fixed;
          top: 1.5rem;
          right: 1.5rem;
          background: rgba(0, 0, 0, 0.4);
          color: #ffffff;
          border: 1px solid rgba(255, 255, 255, 0.2);
          padding: 0.5rem 1rem;
          border-radius: 6px;
          cursor: pointer;
          z-index: 10000;
          font-weight: 500;
          display: none;
        }

        .exercise-app-container.fullscreen-active .fs-close-floating-btn {
          display: block;
        }

        .import-export-row {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-top: 1rem;
          border-top: 1px solid var(--border-color);
          padding-top: 1rem;
          flex-wrap: wrap;
          gap: 1rem;
        }
      `}</style>

      {/* Floating full-screen exit button */}
      <button className="fs-close-floating-btn" onClick={toggleFullscreen}>
        ✕ Close Full Screen
      </button>

      {/* Header section */}
      <div className="ex-header">
        <div className="ex-title-group">
          <h1>Exercise Planner & Player</h1>
          <p>Plan customized exercise sets and run them with visual circular timers and speech narration.</p>
        </div>
        
        <div className="ex-header-controls">
          <span className="sync-badge">
            {dbStatus === 'synced' && '☁️ Saved'}
            {dbStatus === 'loading' && '⌛ Loading...'}
            {dbStatus === 'offline' && '🔌 Local storage'}
            {dbStatus === 'error' && '⚠️ Sync error'}
          </span>
          <button className="ex-btn secondary" onClick={() => setTheme(t => t === 'dark' ? 'light' : 'dark')}>
            {theme === 'dark' ? '☀️ Light' : '🌙 Dark'}
          </button>
        </div>
      </div>

      {/* Mode selectors tabs */}
      <div className="ex-tabs">
        <button className={`ex-tab-btn ${activeTab === 'planner' ? 'active' : ''}`} onClick={() => setActiveTab('planner')}>
          📋 Workout Planner
        </button>
        <button className={`ex-tab-btn ${activeTab === 'player' ? 'active' : ''}`} onClick={() => setActiveTab('player')}>
          ▶️ Workout Player
        </button>
      </div>

      {/* MAIN VIEW AREA */}
      {activeTab === 'planner' ? (
        // PLANNER VIEW
        <div className="planner-layout">
          {/* Workouts Sidebar */}
          <div className="workout-sidebar">
            <div className="workout-list-title">My Workout Plans</div>
            {workouts.map((w, idx) => (
              <div 
                key={w.id} 
                className={`workout-card ${activeWorkoutId === w.id ? 'active' : ''}`}
                onClick={() => setActiveWorkoutId(w.id)}
              >
                <div className="workout-info">
                  <span className="workout-name">{w.name}</span>
                  <span className="workout-meta">{w.category} | {w.steps.length} steps</span>
                </div>
                <div className="card-actions">
                  <button className="card-action-btn" title="Move Up" onClick={(e) => { e.stopPropagation(); handleMoveWorkout(idx, -1); }}>
                    ▲
                  </button>
                  <button className="card-action-btn" title="Move Down" onClick={(e) => { e.stopPropagation(); handleMoveWorkout(idx, 1); }}>
                    ▼
                  </button>
                  <button className="card-action-btn" title="Duplicate" onClick={(e) => handleDuplicateWorkout(w, e)}>
                    📄
                  </button>
                  <button className="card-action-btn delete" title="Delete" onClick={(e) => handleDeleteWorkout(w.id, e)}>
                    ✕
                  </button>
                </div>
              </div>
            ))}
            <button className="ex-btn secondary" style={{ marginTop: '0.5rem', width: '100%', justifyContent: 'center' }} onClick={handleAddWorkout}>
              ＋ Create Workout
            </button>
          </div>

          {/* Active Workout Details & Step Editor */}
          {activeWorkout ? (
            <div className="planner-details">
              {/* Workout details editor */}
              <div className="workout-detail-header">
                <div className="workout-name" style={{ fontSize: '1.2rem', color: 'var(--accent)', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.5rem' }}>
                  {editingWorkoutId === activeWorkout.id ? 'Editing Details' : activeWorkout.name}
                </div>

                {editingWorkoutId === activeWorkout.id ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                    <div className="form-row">
                      <div className="form-group">
                        <label className="form-label">Workout Name</label>
                        <input className="form-input" value={editWorkoutName} onChange={(e) => setEditWorkoutName(e.target.value)} />
                      </div>
                      <div className="form-group">
                        <label className="form-label">Category</label>
                        <input className="form-input" value={editWorkoutCategory} onChange={(e) => setEditWorkoutCategory(e.target.value)} />
                      </div>
                    </div>
                    <div className="form-row">
                      <div className="form-group">
                        <label className="form-label">Sets</label>
                        <input className="form-input" type="number" min="1" value={editWorkoutSets} onChange={(e) => setEditWorkoutSets(e.target.value)} />
                      </div>
                      <div className="form-group">
                        <label className="form-label">Reps / Cycles</label>
                        <input className="form-input" type="number" min="1" value={editWorkoutReps} onChange={(e) => setEditWorkoutReps(e.target.value)} />
                      </div>
                      <div className="form-group">
                        <label className="form-label">Rest Between Sets (secs)</label>
                        <input className="form-input" type="number" min="0" value={editWorkoutRest} onChange={(e) => setEditWorkoutRest(e.target.value)} />
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem' }}>
                      <button className="ex-btn" onClick={() => handleSaveWorkoutDetails(activeWorkout.id)}>
                        Save Details
                      </button>
                      <button className="ex-btn secondary" onClick={() => setEditingWorkoutId(null)}>
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem' }}>
                    <div>
                      <div style={{ fontSize: '0.9rem', color: 'var(--text-sub)' }}>
                        Category: <strong style={{ color: 'var(--text-main)' }}>{activeWorkout.category}</strong>
                      </div>
                      <div style={{ display: 'flex', gap: '1.5rem', marginTop: '0.5rem', fontSize: '0.9rem', color: 'var(--text-sub)' }}>
                        <span>Sets: <strong style={{ color: 'var(--text-main)' }}>{activeWorkout.sets}</strong></span>
                        <span>Reps / Cycles: <strong style={{ color: 'var(--text-main)' }}>{activeWorkout.reps}</strong></span>
                        <span>Inter-Set Rest: <strong style={{ color: 'var(--text-main)' }}>{activeWorkout.interSetRest}s</strong></span>
                      </div>
                    </div>
                    <button className="ex-btn secondary" onClick={() => handleStartEdit(activeWorkout)}>
                      Edit Details
                    </button>
                  </div>
                )}
              </div>

              {/* Steps Editor */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div className="workout-list-title">Exercise Steps ({activeWorkout.steps.length})</div>
                  <button className="ex-btn secondary" style={{ padding: '0.35rem 0.75rem', fontSize: '0.75rem' }} onClick={() => handleAddStep(activeWorkout.id)}>
                    ＋ Add Step
                  </button>
                </div>

                <div className="steps-editor-list">
                  {activeWorkout.steps.map((step, idx) => (
                    <div key={step.id} className="step-editor-card">
                      <div className="step-editor-row1">
                        <div className="form-group">
                          <label className="form-label">Step Title</label>
                          <input 
                            className="form-input" 
                            value={step.title} 
                            placeholder="e.g. Quad Stretch" 
                            onChange={(e) => handleUpdateStepField(activeWorkout.id, step.id, 'title', e.target.value)} 
                          />
                        </div>
                        <div className="form-group">
                          <label className="form-label">Type</label>
                          <select 
                            className="form-input" 
                            value={step.type} 
                            onChange={(e) => handleUpdateStepField(activeWorkout.id, step.id, 'type', e.target.value)}
                          >
                            <option value="work">Work (Timer)</option>
                            <option value="prepare">Prepare (Timer)</option>
                            <option value="rest">Rest (Timer)</option>
                            <option value="reps">Reps (Manual Count)</option>
                          </select>
                        </div>
                        {step.type === 'reps' ? (
                          <div className="form-group">
                            <label className="form-label">Reps Count</label>
                            <input 
                              className="form-input" 
                              type="number" 
                              min="1" 
                              value={step.repsCount || 10} 
                              onChange={(e) => handleUpdateStepField(activeWorkout.id, step.id, 'repsCount', Number(e.target.value) || 1)} 
                            />
                          </div>
                        ) : (
                          <div className="form-group">
                            <label className="form-label">Duration (secs)</label>
                            <input 
                              className="form-input" 
                              type="number" 
                              min="1" 
                              value={step.duration || 10} 
                              onChange={(e) => handleUpdateStepField(activeWorkout.id, step.id, 'duration', Number(e.target.value) || 1)} 
                            />
                          </div>
                        )}
                        <div style={{ display: 'flex', gap: '0.4rem', alignSelf: 'end', height: '36px', alignItems: 'center' }}>
                          <div className="step-drag-btn-group">
                            <button className="step-drag-btn" title="Move Step Up" onClick={() => handleMoveStep(activeWorkout.id, idx, -1)}>▲</button>
                            <button className="step-drag-btn" title="Move Step Down" onClick={() => handleMoveStep(activeWorkout.id, idx, 1)}>▼</button>
                          </div>
                          <button className="ex-btn danger" style={{ padding: '0.5rem 0.65rem' }} title="Delete Step" onClick={() => handleDeleteStep(activeWorkout.id, step.id)}>✕</button>
                        </div>
                      </div>

                      <div className="form-row" style={{ marginTop: '0.25rem' }}>
                        <div className="form-group">
                          <label className="form-label">Description / Instructions</label>
                          <input 
                            className="form-input" 
                            value={step.instruction || ''} 
                            placeholder="Detail how to perform this specific step..." 
                            onChange={(e) => handleUpdateStepField(activeWorkout.id, step.id, 'instruction', e.target.value)} 
                          />
                        </div>
                        <div className="form-group">
                          <label className="form-label">Illustration Image or Video URL</label>
                          <input 
                            className="form-input" 
                            value={step.mediaUrl || ''} 
                            placeholder="Paste image link, direct video .mp4, or YouTube URL..." 
                            onChange={(e) => handleUpdateStepField(activeWorkout.id, step.id, 'mediaUrl', e.target.value)} 
                          />
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* JSON export/import footer row */}
              <div className="import-export-row">
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <button className="ex-btn secondary" style={{ fontSize: '0.75rem' }} onClick={handleExportWorkouts}>
                    📥 Export Workouts Backup
                  </button>
                  <label className="ex-btn secondary" style={{ fontSize: '0.75rem', cursor: 'pointer' }}>
                    📤 Import Backup
                    <input type="file" accept=".json" style={{ display: 'none' }} onChange={handleImportWorkouts} />
                  </label>
                </div>
                <button className="ex-btn" onClick={() => syncWorkoutsToDb()}>
                  {isSyncing ? 'Saving Plan...' : 'Save Plan to Database ☁️'}
                </button>
              </div>
            </div>
          ) : (
            <div style={{ textAlign: 'center', padding: '3rem 0', color: 'var(--text-sub)' }}>
              No workout selected. Create a new workout on the left panel!
            </div>
          )}
        </div>
      ) : (
        // PLAYER VIEW
        <div className="player-layout">
          {/* Left panel: Concentric timers visualizer */}
          <div className="player-left">
            <div className="svg-dial-container">
              <svg className="dial-svg" viewBox="0 0 220 220">
                {/* Background track rings */}
                <circle cx="110" cy="110" r="95" stroke="var(--border-color)" strokeWidth="6" fill="none" />
                {activeWorkout.reps > 1 && (
                  <circle cx="110" cy="110" r="82" stroke="var(--border-color)" strokeWidth="4" fill="none" opacity="0.4" />
                )}
                {activeWorkout.sets > 1 && (
                  <circle cx="110" cy="110" r="70" stroke="var(--border-color)" strokeWidth="4" fill="none" opacity="0.4" />
                )}

                {/* Progress Dial Rings */}
                {getConcentricRings().map((ring, idx) => {
                  const circ = 2 * Math.PI * ring.radius;
                  const offset = circ * (ring.progress);
                  return (
                    <circle
                      key={idx}
                      cx="110"
                      cy="110"
                      r={ring.radius}
                      stroke={ring.color}
                      strokeWidth={ring.strokeWidth}
                      strokeLinecap="round"
                      strokeDasharray={circ}
                      strokeDashoffset={offset}
                      fill="none"
                      style={{
                        transition: isPlaying ? 'stroke-dashoffset 0.1s linear' : 'stroke-dashoffset 0.35s ease',
                        filter: ring.glow ? `drop-shadow(0 0 5px ${ring.color})` : 'none'
                      }}
                    />
                  );
                })}
              </svg>

              <div className="dial-center-label">
                {workoutPhase === 'completed' ? (
                  <div className="time-display" style={{ fontSize: '2.2rem', color: 'var(--success)' }}>FINISHED</div>
                ) : workoutPhase === 'reps' ? (
                  <div className="time-display" style={{ fontSize: '2.5rem', color: '#a855f7' }}>
                    {activeStep ? (activeStep.repsCount || 10) : 10}
                    <span style={{ fontSize: '1.1rem', display: 'block', fontWeight: 500, color: 'var(--text-sub)' }}>REPS</span>
                  </div>
                ) : (
                  <div className="time-display">{formatDuration(Math.ceil(stepTimeRemaining))}</div>
                )}
                <span className={`phase-badge ${workoutPhase}`}>
                  {workoutPhase.replace('_', ' ')}
                </span>
              </div>
            </div>
          </div>

          {/* Right panel: Media Illustration & Description controls */}
          <div className="player-right">
            {workoutPhase === 'completed' ? (
              <div className="active-step-info-card" style={{ borderLeft: '4px solid var(--success)', textAlign: 'center' }}>
                <span className="active-workout-name">{activeWorkout.name}</span>
                <h2 className="active-step-title" style={{ color: 'var(--success)' }}>Workout Completed!</h2>
                <p className="active-step-instruction">You have successfully finished all sets and cycles. Great job staying active!</p>
                <div style={{ fontSize: '4rem', marginTop: '1rem' }}>🎉💪🏆</div>
              </div>
            ) : (
              <div className="active-step-info-card" style={{ borderLeft: `4px solid ${getConcentricRings()[0]?.color || 'var(--accent)'}` }}>
                <span className="active-workout-name">{activeWorkout.name}</span>
                <h2 className="active-step-title">{workoutPhase === 'inter_set_rest' ? 'Inter-Set Recovery' : activeStep?.title}</h2>
                
                {/* Illustration Media panel */}
                {workoutPhase !== 'inter_set_rest' && activeStep?.mediaUrl && (
                  <div style={{ marginTop: '0.75rem', marginBottom: '0.75rem' }}>
                    {renderMediaIllustration(activeStep.mediaUrl, activeStep.title)}
                  </div>
                )}

                <p className="active-step-instruction">
                  {workoutPhase === 'inter_set_rest' 
                    ? `Prepare for set ${currentSet + 1}. Rest and restore your breathing.` 
                    : activeStep?.instruction}
                </p>

                {/* Sub totals sets, cycles details */}
                <div className="active-totals-grid">
                  <div className="total-item">
                    <span className="total-val">{currentSet} / {activeWorkout.sets}</span>
                    <span className="total-lbl">Set</span>
                  </div>
                  <div className="total-item" style={{ borderLeft: '1px solid var(--border-color)', borderRight: '1px solid var(--border-color)' }}>
                    <span className="total-val">{currentRep} / {activeWorkout.reps}</span>
                    <span className="total-lbl">Rep Cycle</span>
                  </div>
                  <div className="total-item">
                    <span className="total-val">{currentStepIndex + 1} / {activeWorkout.steps.length}</span>
                    <span className="total-lbl">Step</span>
                  </div>
                </div>
              </div>
            )}

            {/* Next exercise step preview */}
            {workoutPhase !== 'completed' && activeWorkout.steps[currentStepIndex + 1] && (
              <div className="next-preview">
                <span style={{ color: 'var(--text-sub)' }}>Up Next:</span>
                <strong style={{ color: 'var(--accent)' }}>
                  {activeWorkout.steps[currentStepIndex + 1].title} ({activeWorkout.steps[currentStepIndex + 1].type === 'reps' ? `${activeWorkout.steps[currentStepIndex + 1].repsCount} reps` : `${activeWorkout.steps[currentStepIndex + 1].duration}s`})
                </strong>
              </div>
            )}

            {/* Active player buttons */}
            <div className="player-controls-row">
              <button className="ex-btn secondary" title="Previous Step (P)" onClick={skipStepBackward}>
                ◀ Prev Step
              </button>
              <button 
                className="ex-btn" 
                style={{ background: isPlaying ? 'var(--warning)' : 'var(--success)', color: '#ffffff', minWidth: '120px' }}
                onClick={() => setIsPlaying(!isPlaying)}
              >
                {isPlaying ? '⏸ Pause' : '▶ Start'}
              </button>
              <button className="ex-btn secondary" title="Next Step (N)" onClick={skipStepForward}>
                Next Step ▶
              </button>
              <button className="ex-btn secondary" onClick={resetPlayerState}>
                🔄 Reset
              </button>
              <button className="ex-btn secondary" title="Toggle Full Screen (F)" onClick={toggleFullscreen}>
                ⛶ Fullscreen
              </button>
            </div>

            {/* Sound Toggles */}
            <div style={{ display: 'flex', gap: '1.5rem', justifyContent: 'center', marginTop: '0.5rem', fontSize: '0.85rem' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', cursor: 'pointer' }}>
                <input type="checkbox" checked={speechEnabled} onChange={(e) => setSpeechEnabled(e.target.checked)} />
                🗣️ Speech Narrator
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', cursor: 'pointer' }}>
                <input type="checkbox" checked={soundEnabled} onChange={(e) => setSoundEnabled(e.target.checked)} />
                🎵 Sound Beeps
              </label>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
