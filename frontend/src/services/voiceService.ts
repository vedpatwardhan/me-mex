import { pipeline, env } from '@xenova/transformers';
import { KokoroTTS } from 'kokoro-js';

// Re-enable browser caching now that model assets download cleanly
env.allowLocalModels = false;
env.useBrowserCache = true;

class VoiceService {
  private transcriber: any = null;
  private tts: any = null;
  private mediaRecorder: MediaRecorder | null = null;
  private audioChunks: Blob[] = [];
  private isTranscriberLoading = false;
  private isTTSLoading = false;

  /** Initialize Whisper-Base English Speech-to-Text Pipeline */
  async initSTT() {
    if (this.transcriber || this.isTranscriberLoading) return;
    this.isTranscriberLoading = true;
    try {
      console.log('[VoiceService] Initializing Xenova/whisper-base.en pipeline...');
      this.transcriber = await pipeline('automatic-speech-recognition', 'Xenova/whisper-base.en');
      console.log('[VoiceService] Whisper-base.en loaded successfully.');
    } catch (err: any) {
      console.error('[VoiceService] Failed to load whisper-base.en:', err);
    } finally {
      this.isTranscriberLoading = false;
    }
  }

  /** Initialize Kokoro-82M Text-to-Speech Model */
  async initTTS() {
    if (this.tts || this.isTTSLoading) return;
    this.isTTSLoading = true;
    try {
      console.log('[VoiceService] Loading Kokoro-82M TTS model...');
      this.tts = await KokoroTTS.from_pretrained('onnx-community/Kokoro-82M-v1.0-ONNX', {
        dtype: 'q8',
        device: 'wasm',
      });
      console.log('[VoiceService] Kokoro TTS loaded successfully.');
    } catch (err) {
      console.error('[VoiceService] Failed to load Kokoro TTS:', err);
    } finally {
      this.isTTSLoading = false;
    }
  }

  /** Start Microphone Audio Recording */
  async startRecording(onAudioLevel?: (level: number) => void): Promise<boolean> {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          sampleRate: 44100,
        },
      });
      this.audioChunks = [];
      this.mediaRecorder = new MediaRecorder(stream, {
        mimeType: MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
          ? 'audio/webm;codecs=opus'
          : undefined,
      });

      this.mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          this.audioChunks.push(event.data);
        }
      };

      // Request data every 250ms so chunks are flushed reliably
      this.mediaRecorder.start(250);
      console.log('[VoiceService] Recording started.');
      return true;
    } catch (err) {
      console.error('[VoiceService] Microphone access denied or failed:', err);
      return false;
    }
  }

  /** Stop Recording and Transcribe with Whisper Tiny */
  async stopRecordingAndTranscribe(): Promise<string> {
    return new Promise((resolve) => {
      if (!this.mediaRecorder) {
        resolve('');
        return;
      }

      this.mediaRecorder.onstop = async () => {
        try {
          const mimeType = this.mediaRecorder?.mimeType || 'audio/webm';
          console.log(`[VoiceService] Stop recording. Total chunks: ${this.audioChunks.length}, mimeType: ${mimeType}`);
          const audioBlob = new Blob(this.audioChunks, { type: mimeType });
          console.log(`[VoiceService] Audio Blob size: ${audioBlob.size} bytes`);

          if (audioBlob.size === 0) {
            console.warn('[VoiceService] Audio Blob is empty!');
            resolve('');
            return;
          }

          const arrayBuffer = await audioBlob.arrayBuffer();

          // 1. Decode recorded audio with default/native AudioContext sample rate
          const defaultCtx = new (window.AudioContext || (window as any).webkitAudioContext)();
          const decodedBuffer = await defaultCtx.decodeAudioData(arrayBuffer);
          console.log(`[VoiceService] Decoded AudioBuffer duration: ${decodedBuffer.duration}s, sampleRate: ${decodedBuffer.sampleRate}, channels: ${decodedBuffer.numberOfChannels}`);
          await defaultCtx.close();

          // 2. Resample to 16kHz OfflineAudioContext as required by Whisper
          const offlineCtx = new OfflineAudioContext(
            decodedBuffer.numberOfChannels,
            Math.ceil(decodedBuffer.duration * 16000),
            16000
          );
          const bufferSource = offlineCtx.createBufferSource();
          bufferSource.buffer = decodedBuffer;
          bufferSource.connect(offlineCtx.destination);
          bufferSource.start();

          const resampledBuffer = await offlineCtx.startRendering();
          const channelData = resampledBuffer.getChannelData(0);

          // Calculate max amplitude and normalize audio if peak is low
          let maxVal = 0;
          for (let i = 0; i < channelData.length; i++) {
            const abs = Math.abs(channelData[i]);
            if (abs > maxVal) maxVal = abs;
          }
          console.log(`[VoiceService] 16kHz resampled Float32Array samples: ${channelData.length}, Peak volume: ${maxVal.toFixed(4)}`);

          // Normalize audio buffer to peak 0.75 if peak volume is low, avoiding over-amplification of noise floor
          if (maxVal > 0.001) {
            const scale = Math.min(0.75 / maxVal, 20.0);
            for (let i = 0; i < channelData.length; i++) {
              channelData[i] *= scale;
            }
            console.log(`[VoiceService] Audio normalized with factor ${scale.toFixed(2)}`);
          }

          if (!this.transcriber) {
            await this.initSTT();
          }

          if (this.transcriber) {
            console.log('[VoiceService] Transcribing audio with Whisper-base.en...');
            const output = await this.transcriber(channelData, {
              language: 'en',
              task: 'transcribe',
              condition_on_previous_text: false,
              return_timestamps: false,
            });
            console.log('[VoiceService] Raw Whisper output:', output);
            const text = typeof output === 'string' ? output : output.text || '';
            console.log('[VoiceService] Transcription:', text);
            resolve(text.trim());
          } else {
            resolve('');
          }
        } catch (err) {
          console.error('[VoiceService] STT transcription failed:', err);
          resolve('');
        }
      };

      this.mediaRecorder.stop();
      // Stop all mic tracks
      this.mediaRecorder.stream.getTracks().forEach((track) => track.stop());
    });
  }

  private isPrewarmed = false;
  private isPrewarming = false;
  private audioCtx: AudioContext | null = null;
  private speechQueue: string[] = [];
  private isPlayingQueue = false;

  /** Prewarm STT and TTS models in the background on app start */
  async prewarm(): Promise<void> {
    if (this.isPrewarmed || this.isPrewarming) return;
    this.isPrewarming = true;
    console.log('[VoiceService] Pre-warming Whisper and Kokoro models in background...');
    try {
      await Promise.all([this.initSTT(), this.initTTS()]);
      this.isPrewarmed = true;
      console.log('[VoiceService] All voice models pre-warmed and ready.');
    } catch (err) {
      console.warn('[VoiceService] Pre-warming error (will retry on demand):', err);
    } finally {
      this.isPrewarming = false;
    }
  }

  isReady(): boolean {
    return !!(this.transcriber && this.tts);
  }

  /** Sanitize text to remove emojis, markdown symbols, and artifacts before TTS */
  cleanTextForSpeech(text: string): string {
    if (!text) return '';
    return text
      // Strip unicode emojis & pictographs
      .replace(/[\p{Extended_Pictographic}\u{1F300}-\u{1F9FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}]/gu, '')
      // Strip markdown links [label](url) -> label
      .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
      // Strip bold / italic asterisks and underscores
      .replace(/[*_#`~>]/g, '')
      // Collapse whitespace
      .replace(/\s+/g, ' ')
      .trim();
  }

  private getAudioContext(): AudioContext {
    if (!this.audioCtx || this.audioCtx.state === 'closed') {
      this.audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)();
    }
    if (this.audioCtx.state === 'suspended') {
      this.audioCtx.resume();
    }
    return this.audioCtx;
  }

  /** Enqueue a sentence chunk to play sequentially as it arrives from a stream */
  enqueueSpeechChunk(sentence: string, voice: string = 'af_heart') {
    const clean = this.cleanTextForSpeech(sentence);
    if (!clean) return;
    this.speechQueue.push(clean);
    this.processSpeechQueue(voice);
  }

  private async processSpeechQueue(voice: string = 'af_heart') {
    if (this.isPlayingQueue || this.speechQueue.length === 0) return;
    this.isPlayingQueue = true;

    while (this.speechQueue.length > 0) {
      const sentence = this.speechQueue.shift();
      if (!sentence) continue;

      try {
        if (!this.tts) await this.initTTS();
        if (this.tts) {
          const audio = await this.tts.generate(sentence, { voice });
          const audioCtx = this.getAudioContext();
          const buffer = audioCtx.createBuffer(1, audio.audio.length, audio.sampling_rate);
          buffer.getChannelData(0).set(audio.audio);

          await new Promise<void>((resolve) => {
            const source = audioCtx.createBufferSource();
            source.buffer = buffer;
            source.connect(audioCtx.destination);
            source.onended = () => resolve();
            source.start(0);
          });
        }
      } catch (err) {
        console.error('[VoiceService] Speech chunk error:', err);
      }
    }

    this.isPlayingQueue = false;
  }

  /** Convert Response Text to Speech via Kokoro-JS and Play */
  async speakText(text: string, voice: string = 'af_heart'): Promise<void> {
    try {
      const clean = this.cleanTextForSpeech(text);
      if (!clean) return;

      if (!this.tts) {
        await this.initTTS();
      }

      if (this.tts) {
        console.log('[VoiceService] Synthesizing speech with Kokoro TTS:', clean.slice(0, 60));
        const audio = await this.tts.generate(clean, { voice });

        // Play Audio Buffer using Web Audio API
        const audioCtx = this.getAudioContext();
        const buffer = audioCtx.createBuffer(1, audio.audio.length, audio.sampling_rate);
        buffer.getChannelData(0).set(audio.audio);

        const source = audioCtx.createBufferSource();
        source.buffer = buffer;
        source.connect(audioCtx.destination);
        source.start(0);
      }
    } catch (err) {
      console.error('[VoiceService] Kokoro TTS playback failed:', err);
    }
  }
}

export const voiceService = new VoiceService();

