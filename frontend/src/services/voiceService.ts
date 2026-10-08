import { pipeline, env } from '@xenova/transformers';

// Enable browser caching for Whisper model assets
env.allowLocalModels = false;
env.useBrowserCache = true;

class VoiceService {
  private transcriber: any = null;
  private mediaRecorder: MediaRecorder | null = null;
  private audioChunks: Blob[] = [];
  private isTranscriberLoading = false;
  private isPrewarmed = false;

  /** Initialize Whisper-Base English Speech-to-Text Pipeline */
  async initSTT() {
    if (this.transcriber || this.isTranscriberLoading) return;
    this.isTranscriberLoading = true;
    try {
      console.log('[VoiceService] Initializing Xenova/whisper-base.en pipeline...');
      this.transcriber = await pipeline('automatic-speech-recognition', 'Xenova/whisper-base.en');
      this.isPrewarmed = true;
      console.log('[VoiceService] Whisper-base.en loaded successfully.');
    } catch (err: any) {
      console.error('[VoiceService] Failed to load whisper-base.en:', err);
    } finally {
      this.isTranscriberLoading = false;
    }
  }

  /** Prewarm STT model in the background on app start */
  async prewarm(): Promise<void> {
    if (this.isPrewarmed || this.isTranscriberLoading) return;
    console.log('[VoiceService] Pre-warming Whisper STT model in background...');
    try {
      await this.initSTT();
    } catch (err) {
      console.warn('[VoiceService] STT pre-warm error:', err);
    }
  }

  isReady(): boolean {
    return !!this.transcriber;
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

      // AudioContext for live visualizer audio metering
      const audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)();
      const source = audioCtx.createMediaStreamSource(stream);
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);

      const bufferLength = analyser.frequencyBinCount;
      const dataArray = new Uint8Array(bufferLength);

      const checkLevel = () => {
        if (!this.mediaRecorder || this.mediaRecorder.state !== 'recording') {
          audioCtx.close();
          return;
        }
        analyser.getByteFrequencyData(dataArray);
        let sum = 0;
        for (let i = 0; i < bufferLength; i++) {
          sum += dataArray[i];
        }
        const avg = sum / bufferLength;
        if (onAudioLevel) onAudioLevel(avg);
        requestAnimationFrame(checkLevel);
      };

      this.mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' });
      this.mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          this.audioChunks.push(event.data);
        }
      };

      this.mediaRecorder.start(100);
      checkLevel();
      return true;
    } catch (err) {
      console.error('[VoiceService] Failed to start microphone recording:', err);
      return false;
    }
  }

  /** Stop Recording, resample to 16kHz Mono Float32Array, and transcribe via Whisper */
  async stopRecordingAndTranscribe(): Promise<string> {
    return new Promise((resolve) => {
      if (!this.mediaRecorder) {
        resolve('');
        return;
      }

      this.mediaRecorder.onstop = async () => {
        try {
          const audioBlob = new Blob(this.audioChunks, { type: 'audio/webm' });
          const arrayBuffer = await audioBlob.arrayBuffer();

          // Decode using AudioContext to raw PCM
          const audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)();
          const audioBuffer = await audioCtx.decodeAudioData(arrayBuffer);

          // Xenova whisper expects 16,000 Hz single-channel Float32Array
          const targetSampleRate = 16000;
          const offlineCtx = new OfflineAudioContext(
            1,
            Math.ceil(audioBuffer.duration * targetSampleRate),
            targetSampleRate
          );

          const source = offlineCtx.createBufferSource();
          source.buffer = audioBuffer;
          source.connect(offlineCtx.destination);
          source.start(0);

          const resampledBuffer = await offlineCtx.startRendering();
          const channelData = resampledBuffer.getChannelData(0);

          // Calculate max amplitude and normalize audio if peak is low
          let maxVal = 0;
          for (let i = 0; i < channelData.length; i++) {
            const abs = Math.abs(channelData[i]);
            if (abs > maxVal) maxVal = abs;
          }
          console.log(`[VoiceService] 16kHz resampled samples: ${channelData.length}, Peak volume: ${maxVal.toFixed(4)}`);

          if (maxVal > 0.001) {
            const scale = Math.min(0.75 / maxVal, 20.0);
            for (let i = 0; i < channelData.length; i++) {
              channelData[i] *= scale;
            }
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
            const text = typeof output === 'string' ? output : output.text || '';
            console.log('[VoiceService] Transcription result:', text);
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
      this.mediaRecorder.stream.getTracks().forEach((track) => track.stop());
    });
  }
}

export const voiceService = new VoiceService();
