import { pipeline, env } from '@xenova/transformers';
import { KokoroTTS } from 'kokoro-js';

// Configure @xenova/transformers to load remote ONNX CDN models directly and avoid Vite HTML fallback interception
env.allowLocalModels = false;
env.useBrowserCache = true;

class VoiceService {
  private transcriber: any = null;
  private tts: any = null;
  private mediaRecorder: MediaRecorder | null = null;
  private audioChunks: Blob[] = [];
  private isTranscriberLoading = false;
  private isTTSLoading = false;

  /** Initialize Whisper-Tiny Speech-to-Text Pipeline */
  async initSTT() {
    if (this.transcriber || this.isTranscriberLoading) return;
    this.isTranscriberLoading = true;
    try {
      console.log('[VoiceService] Loading Xenova/whisper-tiny model...');
      this.transcriber = await pipeline('automatic-speech-recognition', 'Xenova/whisper-tiny');
      console.log('[VoiceService] Whisper-tiny loaded successfully.');
    } catch (err) {
      console.error('[VoiceService] Failed to load whisper-tiny:', err);
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
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      this.audioChunks = [];
      this.mediaRecorder = new MediaRecorder(stream);

      this.mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          this.audioChunks.push(event.data);
        }
      };

      this.mediaRecorder.start();
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
          const audioBlob = new Blob(this.audioChunks, { type: 'audio/wav' });
          const arrayBuffer = await audioBlob.arrayBuffer();

          // Decode Audio Buffer into 16kHz Float32Array required by Whisper
          const audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)({ sampleRate: 16000 });
          const audioBuffer = await audioCtx.decodeAudioData(arrayBuffer);
          const channelData = audioBuffer.getChannelData(0);

          if (!this.transcriber) {
            await this.initSTT();
          }

          if (this.transcriber) {
            console.log('[VoiceService] Transcribing audio with Whisper-tiny...');
            const output = await this.transcriber(channelData);
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

  /** Convert Response Text to Speech via Kokoro-JS and Play */
  async speakText(text: string, voice: string = 'af_heart'): Promise<void> {
    try {
      if (!this.tts) {
        await this.initTTS();
      }

      if (this.tts) {
        console.log('[VoiceService] Synthesizing speech with Kokoro TTS:', text.slice(0, 60));
        const audio = await this.tts.generate(text, { voice });
        
        // Play Audio Buffer using Web Audio API
        const audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)();
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
