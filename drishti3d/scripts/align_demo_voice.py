"""Local narration transcription with word times for the final video edit."""
import json
from pathlib import Path
from faster_whisper import WhisperModel

out = Path(__file__).resolve().parents[1] / 'docs/demo/final_video/narrated'
out.mkdir(parents=True, exist_ok=True)
source = '/home/naveen/Downloads/WhatsApp Audio 2026-09-27 at 6.21.48 PM.aac'
model = WhisperModel('base.en', device='cpu', compute_type='int8', cpu_threads=6)
segments, info = model.transcribe(source, language='en', beam_size=5, word_timestamps=True, vad_filter=True)
result = []
for s in segments:
    row = {'start': s.start, 'end': s.end, 'text': s.text.strip(),
           'words': [{'start': w.start, 'end': w.end, 'word': w.word, 'probability': w.probability} for w in s.words]}
    result.append(row)
    print(f'{s.start:.2f}–{s.end:.2f} {s.text}', flush=True)
(out / 'transcript.json').write_text(json.dumps(result, indent=2))
