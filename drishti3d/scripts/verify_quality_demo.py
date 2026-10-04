"""Delivery checks for the UHD remaster, including source-to-export fidelity."""
import concurrent.futures
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/demo/final_video/quality_v2'
QA = OUT / 'qa'
QA.mkdir(exist_ok=True)
OLD = ROOT / 'docs/demo/final_video/narrated/Drishti3D_SIH26158_Final_5m30s.mp4'
UHD = OUT / 'Drishti3D_SIH26158_4K_Remastered.mp4'
HD = OUT / 'Drishti3D_SIH26158_1080p_Remastered.mp4'
timeline = json.loads((OUT / 'edit-timeline.json').read_text())

def probe(p):
    return json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(p)]))

def audiohash(p):
    return subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(p), '-map', '0:a:0', '-c', 'copy', '-f', 'hash', '-hash', 'sha256', '-'], text=True).strip()

audio_hash = audiohash(OLD)
for video, resolution in [(UHD, (3840, 2160)), (HD, (1920, 1080))]:
    metadata = probe(video)
    (QA / (video.stem + '.json')).write_text(json.dumps(metadata, indent=2))
    v = next(s for s in metadata['streams'] if s['codec_type'] == 'video')
    a = next(s for s in metadata['streams'] if s['codec_type'] == 'audio')
    assert (v['width'], v['height']) == resolution
    assert v['r_frame_rate'] == '30/1' and int(v['nb_frames']) == 9900
    assert abs(float(v['duration']) - 330) < .01
    assert abs(float(v['duration']) - float(a['duration'])) < .05
    assert audiohash(video) == audio_hash, 'Narration payload changed'
    print('PASS', video.name, resolution, '9900 frames, 330 s, identical AAC narration', flush=True)

assert sum(s['frames'] for s in timeline) == 9900
for i, s in enumerate(timeline):
    if i:
        assert abs(s['start'] - timeline[i-1]['end']) < .001
    assert int(probe(OUT / 'segments' / f'{i:02}.mp4')['streams'][0]['nb_frames']) == s['frames']
    if s['source'].endswith(('.png', '.mp4')):
        v = probe(OUT / 'captures' / s['source'])['streams'][0]
        assert (v['width'], v['height']) == (3840, 1920), 'Non-native browser capture'

def frame(s):
    i = s['index']
    t = (s['start'] + s['end']) / 2
    subprocess.run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-threads', '2', '-ss', str(t), '-i', str(UHD),
                    '-frames:v', '1', '-vf', f"scale=640:360,drawbox=x=0:y=0:w=230:h=30:color=black:t=fill,drawtext=fontfile=/usr/share/fonts/TTF/DejaVuSans.ttf:text='Shot {i:02} / {int(t)//60}.{int(t)%60:02}':fontsize=20:x=5:y=4:fontcolor=white",
                    str(QA / f'shot-{i:02}.png')], check=True)
    if i in [1, 2, 3, 4, 13, 16, 17, 18, 24, 28, 30, 34, 40]:
        subprocess.run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-threads', '2', '-ss', str(t), '-i', str(UHD),
                        '-frames:v', '1', str(QA / f'native-{i:02}.png')], check=True)

with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    list(pool.map(frame, timeline))
for group in range(3):
    subprocess.run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-start_number', str(group * 16),
                    '-i', str(QA / 'shot-%02d.png'), '-vf', 'tile=4x4:padding=4:color=0x101923', '-frames:v', '1',
                    str(QA / f'contact-{group+1}.jpg')], check=True)

# Pixel-aligned screenshot comparison; unlike the earlier zoomed edit, no
# geometric registration or compensating scale is needed for this test.
fidelity = []
for s in timeline:
    if not s['source'].endswith('.png'):
        continue
    proc = subprocess.run(['ffmpeg', '-hide_banner', '-threads', '2', '-i', str(OUT / 'segments' / f"{s['index']:02}.mp4"),
                           '-i', str(OUT / 'captures' / s['source']), '-filter_complex',
                           '[0:v]trim=start_frame=30:end_frame=31,setpts=PTS-STARTPTS,crop=3840:1920:0:108,format=yuv420p,settb=1/30[a];[1:v]format=yuv420p,settb=1/30[b];[a][b]ssim',
                           '-frames:v', '1', '-f', 'null', '-'], capture_output=True, text=True, check=True)
    score = float(re.search(r'All:([0-9.]+)', proc.stderr).group(1))
    fidelity.append({'shot': s['index'], 'source': s['source'], 'ssim': score})
    assert score > .99, (s['index'], 'Screenshot fidelity low', score)
(QA / 'screenshot-fidelity.json').write_text(json.dumps(fidelity, indent=2))
print('PASS native screenshot fidelity, minimum SSIM', min(s['ssim'] for s in fidelity), flush=True)

with (QA / 'decode-quality.log').open('w') as log:
    subprocess.run(['ffmpeg', '-hide_banner', '-nostats', '-threads', '4', '-i', str(UHD),
                    '-vf', 'scale=960:540,freezedetect=n=-60dB:d=3,blackdetect=d=0.2:pix_th=0.01:pic_th=0.98',
                    '-af', 'ebur128=peak=true', '-f', 'null', '-'], stdout=subprocess.DEVNULL, stderr=log, check=True)
log = (QA / 'decode-quality.log').read_text()
assert 'black_start' not in log, 'Review black intervals'
holds = []
start = None
for line in log.splitlines():
    m = re.search(r'freeze_start: ([0-9.]+)', line)
    if m:
        start = float(m.group(1))
    m = re.search(r'freeze_end: ([0-9.]+)', line)
    if m and start is not None:
        end = float(m.group(1))
        overlaps = [s for s in timeline if min(end, s['end']) - max(start, s['start']) > 3]
        bad = [s['index'] for s in overlaps if s['source'].endswith('.mp4') or s['source'] == 'drone']
        holds.append({'start': start, 'end': end, 'shots': [s['index'] for s in overlaps], 'unexpected': bad})
        assert not bad, ('Unexpected motion-shot freeze', start, end, bad)
        start = None
(QA / 'intentional-holds.json').write_text(json.dumps(holds, indent=2))
with (QA / 'hd-decode.log').open('w') as log_file:
    subprocess.run(['ffmpeg', '-v', 'error', '-threads', '4', '-i', str(HD), '-f', 'null', '-'], stderr=log_file, check=True)
print('PASS full decode; no black gaps or unexpected motion freezes. Static UI/cards held intentionally.', flush=True)
report = f'''# Quality remaster verification

- Native browser source: 3840 × 1920; UHD output: 3840 × 2160. Browser pixels placed 1:1.
- 1080p delivery derived from the UHD master with Lanczos downsampling.
- Lossless PNG screenshot transport; 4:4:4 high-quality capture intermediates. No JPEG capture.
- No artificial zoom, rotation, motion blur or image sharpening applied to interface footage.
- Three.js sRGB vertex-colour interpretation corrected in the capture session. Geometry unchanged.
- Full screen is inside the title/caption frame; neither overlay hides interface controls.
- 44 shots; 9,900 frames; 30 fps; exactly 330 seconds in both deliveries.
- AAC narration bitstream identical to the prior synchronized edit: {audio_hash}.
- Every screenshot-based shot compared at native pixel alignment. Minimum SSIM: {min(s['ssim'] for s in fidelity):.6f}.
- Both deliveries decoded fully. No black gaps; no unexpected freezes within moving shots.
- Still UI views and explanatory cards are held intentionally; they have not been given fake motion to evade freeze detection.
- Source limitation: opening drone footage was supplied at 1080p; homepage's embedded model image and research assets retain their original source detail.

Contact sheets and selected full-resolution frames are saved alongside this report for visual review.
'''
(QA / 'REVIEW.md').write_text(report)
