"""Decode audit, exact frame accounting, and shot contact sheets."""
from pathlib import Path
import json, subprocess, concurrent.futures

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/demo/final_video/narrated'
QA=OUT/'qa';QA.mkdir(exist_ok=True)
video=OUT/'Drishti3D_SIH26158_Final_5m30s.mp4'
timeline=json.loads((OUT/'edit-timeline.json').read_text())

def probe(p):
 return json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(p)]))
result=probe(video)
(QA/'media-info.json').write_text(json.dumps(result,indent=2))
v=next(s for s in result['streams'] if s['codec_type']=='video')
a=next(s for s in result['streams'] if s['codec_type']=='audio')
assert (v['width'],v['height'])==(1920,1080)
assert v['r_frame_rate']=='30/1'
assert int(v['nb_frames'])==9900
assert abs(float(result['format']['duration'])-330)<.05
assert abs(float(a['duration'])-float(v['duration']))<.05
assert sum(s['frames'] for s in timeline)==9900
for i,s in enumerate(timeline):
 assert s['end']>s['start']
 if i:assert abs(s['start']-timeline[i-1]['end'])<.001
 segment=probe(OUT/'segments'/f'{i:02}.mp4')['streams'][0]
 assert int(segment['nb_frames'])==s['frames'], f'Shot {i}: wrong frame count'

def frame(s):
 i=s['index'];t=(s['start']+s['end'])/2
 subprocess.run(['ffmpeg','-y','-hide_banner','-loglevel','error','-ss',str(t),'-i',str(video),'-frames:v','1','-vf',f"scale=480:270,drawbox=x=0:y=0:w=150:h=25:color=black:t=fill,drawtext=fontfile=/usr/share/fonts/TTF/DejaVuSans.ttf:text='Shot {i:02} / {int(t)//60}.{int(t)%60:02}':fontsize=17:x=5:y=4:fontcolor=white",str(QA/f'shot-{i:02}.png')],check=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(frame,timeline))
for group in range(3):
 subprocess.run(['ffmpeg','-y','-hide_banner','-loglevel','error','-start_number',str(group*16),'-i',str(QA/'shot-%02d.png'),'-vf','tile=4x4:padding=5:color=0x223040','-frames:v','1',str(QA/f'contact-{group+1}.jpg')],check=True)
with (QA/'decode-quality.log').open('w') as log:
 subprocess.run(['ffmpeg','-hide_banner','-nostats','-i',str(video),'-vf','freezedetect=n=-60dB:d=3,blackdetect=d=0.2:pix_th=0.01:pic_th=0.98','-af','ebur128=peak=true','-f','null','-'],stderr=log,stdout=subprocess.DEVNULL,check=True)
log=(QA/'decode-quality.log').read_text()
events=[l for l in log.splitlines() if 'freeze_' in l or 'black_start' in l]
(QA/'detected-events.txt').write_text('\n'.join(events)+'\n')
print('Video: 1920x1080, 30 fps, 9,900 frames. Duration: 330.000 s. Audio/video durations agree.')
print('Decode completed. Candidate holds/black frames:',len(events))
print('\n'.join(events))
print(log[-600:])

def stamp(t):return f'{int(t)//60}:{int(t)%60:02}'
rows=['# Final narrated demo — 5:30','', 'Voice: WhatsApp recording, 27 September 2026, 6:21:48 PM.', '',
      'Source audio trimmed from 1.4 to 335.4 seconds. Tempo adjusted by 1.012121× with pitch preserved. Video cuts follow the recorded narration. Original source audio and previous silent export are preserved.', '',
      '| Final time | Scene | Visual cue |','|---|---|---|']
for s in timeline:rows.append(f"| {stamp(s['start'])}–{stamp(s['end'])} | {s['title']} | {s['badge']} |")
(OUT/'FINAL_VIDEO_TIMINGS.md').write_text('\n'.join(rows)+'\n')
