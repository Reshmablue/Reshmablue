/**
 * =============================================================================
 * AI SHOPKEEPER ASSISTANT - VOICE MODULE (voice.js)
 * Web Speech Recognition & Speech Synthesis
 * Supports Telugu (te-IN), Hindi (hi-IN), and English (en-IN)
 * =============================================================================
 */

class VoiceAssistant {
  constructor(options = {}) {
    this.recognition = null;
    this.isListening = false;
    this.selectedLanguage = options.defaultLanguage || "en-IN";
    this.autoSpeak = options.autoSpeak !== undefined ? options.autoSpeak : true;

    // Callbacks
    this.onResult = options.onResult || null;
    this.onStatusChange = options.onStatusChange || null;
    this.onError = options.onError || null;

    // Single-channel audio playback tracking to prevent duplicate simultaneous voices
    this.currentAudio = null;
    this.playbackSessionId = 0;

    // Initialize Speech Recognition
    this.initRecognition();
  }

  initRecognition() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
      console.warn("SpeechRecognition API is not supported in this browser.");
      if (this.onStatusChange) {
        this.onStatusChange("unsupported", "Browser Speech Recognition not supported. Text input is available as fallback.");
      }
      return;
    }

    try {
      this.recognition = new SpeechRecognition();
      this.recognition.continuous = false;
      this.recognition.interimResults = true;
      this.recognition.maxAlternatives = 1;
      this.recognition.lang = this.selectedLanguage;

      this.recognition.onstart = () => {
        this.isListening = true;
        if (this.onStatusChange) {
          this.onStatusChange("listening", `Listening in ${this.getLangLabel(this.selectedLanguage)}... Speak now.`);
        }
      };

      this.recognition.onresult = (event) => {
        let interimTranscript = "";
        let finalTranscript = "";

        for (let i = event.resultIndex; i < event.results.length; ++i) {
          const transcript = event.results[i][0].transcript;
          if (event.results[i].isFinal) {
            finalTranscript += transcript;
          } else {
            interimTranscript += transcript;
          }
        }

        if (this.onResult) {
          this.onResult({
            interim: interimTranscript,
            final: finalTranscript,
            isFinal: !!finalTranscript
          });
        }
      };

      this.recognition.onerror = (event) => {
        this.isListening = false;
        let errMsg = "Microphone error: " + event.error;

        if (event.error === "not-allowed") {
          errMsg = "Microphone permission was denied. Please allow microphone access in your browser settings.";
        } else if (event.error === "no-speech") {
          errMsg = "No speech was detected. Please try speaking again closer to the microphone.";
        } else if (event.error === "network") {
          errMsg = "Network error occurred during speech transcription. Please check internet connection.";
        }

        if (this.onError) {
          this.onError(errMsg, event.error);
        }
        if (this.onStatusChange) {
          this.onStatusChange("error", errMsg);
        }
      };

      this.recognition.onend = () => {
        this.isListening = false;
        if (this.onStatusChange) {
          this.onStatusChange("idle", "Microphone is idle.");
        }
      };

    } catch (err) {
      console.error("Error initializing SpeechRecognition:", err);
    }
  }

  setLanguage(langCode) {
    this.selectedLanguage = langCode;
    if (this.recognition) {
      this.recognition.lang = langCode;
    }
  }

  getLangLabel(langCode) {
    switch (langCode) {
      case "te-IN": return "Telugu (తెలుగు)";
      case "hi-IN": return "Hindi (हिन्दी)";
      case "en-IN":
      default: return "English";
    }
  }

  toggleListening() {
    if (this.isListening) {
      this.stopListening();
    } else {
      this.startListening();
    }
  }

  startListening() {
    if (!this.recognition) {
      if (this.onError) {
        this.onError("Speech recognition is not supported in this browser. Please use Chrome, Edge, or text input.");
      }
      return;
    }

    // Stop synthesis if currently talking
    if (window.speechSynthesis && window.speechSynthesis.speaking) {
      window.speechSynthesis.cancel();
    }

    try {
      this.recognition.lang = this.selectedLanguage;
      this.recognition.start();
    } catch (err) {
      // If already started or aborting
      console.warn("SpeechRecognition start warning:", err);
    }
  }

  stopListening() {
    if (this.recognition && this.isListening) {
      try {
        this.recognition.stop();
      } catch (err) {
        console.warn("SpeechRecognition stop warning:", err);
      }
    }
  }

  /**
   * Speak a given text response using Server-side gTTS with authentic regional accents.
   * Strictly enforces a single audio channel: stops any existing audio, cancels browser synthesis,
   * and prevents Telugu and English from playing concurrently or falling back to English voice.
   */
  speakText(text, metadata = {}, onEndCallback = null) {
    if (typeof metadata === "function") {
      onEndCallback = metadata;
      metadata = {};
    }

    if (!text || !text.trim()) {
      if (onEndCallback) onEndCallback();
      return;
    }

    // Stop any ongoing speech or audio playback immediately
    this.stopSpeaking();

    // Unique session ID to invalidate any lagging promises or events
    const sessionId = this.playbackSessionId;

    // Clean markdown formatting for smooth, clear pronunciation
    const cleanText = text
      .replace(/[*#_`~>]/g, "")
      .replace(/\n+/g, ". ")
      .trim();

    const lang = metadata.language || this.selectedLanguage || "en-IN";

    // 1. Primary Engine: High-fidelity regional audio via Flask /api/tts (gTTS)
    try {
      const audioUrl = `/api/tts?lang=${encodeURIComponent(lang)}&text=${encodeURIComponent(cleanText)}`;
      const audio = new Audio(audioUrl);
      this.currentAudio = audio;

      if (this.onStatusChange) {
        this.onStatusChange("speaking", "Assistant is speaking response...");
      }

      audio.onended = () => {
        if (this.playbackSessionId !== sessionId) return;
        this.currentAudio = null;
        if (this.onStatusChange) {
          this.onStatusChange("idle", "Finished speaking.");
        }
        if (onEndCallback) onEndCallback();
      };

      audio.onerror = (e) => {
        if (this.playbackSessionId !== sessionId) return;
        console.warn("[Voice] Server TTS audio error, checking browser fallback:", e);
        this.currentAudio = null;
        this.fallbackWebSpeech(cleanText, lang, sessionId, onEndCallback);
      };

      const playPromise = audio.play();
      if (playPromise !== undefined) {
        playPromise.catch((err) => {
          if (this.playbackSessionId !== sessionId) return;
          if (err.name === "AbortError") {
            // Cancelled because newer speech started; do nothing
            return;
          }
          console.warn("[Voice] Audio play promise rejected:", err.name, err.message);
          // If autoplay is blocked by browser gesture policy, do NOT trigger English synthesis for Telugu!
          if (err.name === "NotAllowedError") {
            this.currentAudio = null;
            if (this.onStatusChange) {
              this.onStatusChange("idle", "Click '🔊 Read Aloud' to hear spoken response.");
            }
            if (onEndCallback) onEndCallback();
            return;
          }
          this.currentAudio = null;
          this.fallbackWebSpeech(cleanText, lang, sessionId, onEndCallback);
        });
      }
      return;
    } catch (err) {
      if (this.playbackSessionId !== sessionId) return;
      console.warn("[Voice] Server TTS exception:", err);
      this.fallbackWebSpeech(cleanText, lang, sessionId, onEndCallback);
    }
  }

  /**
   * Browser SpeechSynthesis fallback with strict language matching.
   * If user selected Telugu or Hindi and no native voice is installed in the browser,
   * NEVER speak using English voice.
   */
  fallbackWebSpeech(cleanText, lang, sessionId, onEndCallback) {
    if (this.playbackSessionId !== sessionId) return;
    this.currentAudio = null;

    if (!("speechSynthesis" in window)) {
      if (this.onStatusChange) this.onStatusChange("idle", "Speech synthesis not supported in this browser.");
      if (onEndCallback) onEndCallback();
      return;
    }

    const langLower = (lang || "").toLowerCase();
    const isTelugu = langLower.includes("te") || langLower.includes("telugu");
    const isHindi = langLower.includes("hi") || langLower.includes("hindi");

    const voices = window.speechSynthesis.getVoices() || [];
    let matchedVoice = null;

    if (isTelugu) {
      matchedVoice = voices.find(v => v.lang.toLowerCase().startsWith("te"));
      if (!matchedVoice) {
        console.warn("[Voice] No browser Telugu voice installed. Suppressed English voice fallback to prevent duplicate or garbled audio.");
        if (this.onStatusChange) {
          this.onStatusChange("idle", "Telugu speech requires online audio. Text response is displayed.");
        }
        if (onEndCallback) onEndCallback();
        return;
      }
    } else if (isHindi) {
      matchedVoice = voices.find(v => v.lang.toLowerCase().startsWith("hi"));
      if (!matchedVoice) {
        console.warn("[Voice] No browser Hindi voice installed. Suppressed English voice fallback.");
        if (this.onStatusChange) {
          this.onStatusChange("idle", "Hindi speech requires online audio. Text response is displayed.");
        }
        if (onEndCallback) onEndCallback();
        return;
      }
    } else {
      matchedVoice = voices.find(v => v.lang.toLowerCase() === "en-in") ||
                     voices.find(v => v.lang.toLowerCase().startsWith("en-in")) ||
                     voices.find(v => v.lang.toLowerCase().startsWith("en")) ||
                     voices.find(v => v.default);
    }

    try {
      const utterance = new SpeechSynthesisUtterance(cleanText);
      utterance.lang = lang;
      if (matchedVoice) utterance.voice = matchedVoice;
      utterance.rate = 1.0;
      utterance.pitch = 1.0;

      utterance.onend = () => {
        if (this.playbackSessionId !== sessionId) return;
        if (this.onStatusChange) {
          this.onStatusChange("idle", "Finished speaking.");
        }
        if (onEndCallback) onEndCallback();
      };

      utterance.onerror = (e) => {
        if (this.playbackSessionId !== sessionId) return;
        if (this.onStatusChange) {
          this.onStatusChange("idle", "Speech stopped.");
        }
        if (onEndCallback) onEndCallback();
      };

      if (this.onStatusChange) {
        this.onStatusChange("speaking", "Assistant is speaking response...");
      }

      window.speechSynthesis.speak(utterance);
    } catch (e) {
      console.warn("[Voice] Web SpeechSynthesis error:", e);
      if (onEndCallback) onEndCallback();
    }
  }

  isSpeaking() {
    return !!(this.currentAudio && !this.currentAudio.paused) || !!(window.speechSynthesis && window.speechSynthesis.speaking);
  }

  stopSpeaking() {
    // Invalidate active session so pending callbacks are discarded
    this.playbackSessionId = (this.playbackSessionId || 0) + 1;

    if (this.currentAudio) {
      try {
        this.currentAudio.onended = null;
        this.currentAudio.onerror = null;
        this.currentAudio.oncanplay = null;
        this.currentAudio.pause();
        this.currentAudio.currentTime = 0;
        this.currentAudio.src = "";
      } catch (e) {}
      this.currentAudio = null;
    }

    if ("speechSynthesis" in window) {
      try {
        window.speechSynthesis.cancel();
      } catch (e) {}
    }

    if (this.onStatusChange) {
      this.onStatusChange("idle", "Speech stopped.");
    }
  }

  /**
   * Speak an announcement aloud to the user (e.g. during scanning, cart updates, checkout)
   */
  announce(text, language = null) {
    if (!text || !this.autoSpeak) return;
    this.speakText(text, { language: language || this.selectedLanguage });
  }

  /**
   * Welcome the shopkeeper with spoken greeting
   */
  greet(language = null) {
    const lang = language || this.selectedLanguage;
    let greeting = "";
    if (lang === "te-IN") {
      greeting = "నమస్తే! నేను మీ AI షాప్‌కీపర్ అసిస్టెంట్‌ని. ఈ రోజు అమ్మకాలు, లాభం లేదా ఇన్వెంటరీ వివరాలు కావాలంటే నన్ను అడగండి.";
    } else if (lang === "hi-IN") {
      greeting = "नमस्ते! मैं आपका AI शॉपकीपर असिस्टेंट हूँ। आज की बिक्री, मुनाफे या स्टॉक के बारे में मुझसे पूछें।";
    } else {
      greeting = "Namaste! I am your AI Shopkeeper Assistant. Ask me about today's sales, profit, inventory, or product prices.";
    }
    this.speakText(greeting, { language: lang });
    return greeting;
  }

  /**
   * Synthesize a short 1000Hz confirmation beep using Web Audio API on barcode scan
   */
  static playScanBeep() {
    try {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (!AudioContext) return;
      const ctx = new AudioContext();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      osc.frequency.setValueAtTime(1050, ctx.currentTime);
      gain.gain.setValueAtTime(0.2, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.15);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.15);
    } catch (e) {
      // AudioContext policy
    }
  }

  static isSupported() {
    return !!(window.SpeechRecognition || window.webkitSpeechRecognition);
  }

  static isSynthesisSupported() {
    return ("speechSynthesis" in window);
  }
}
