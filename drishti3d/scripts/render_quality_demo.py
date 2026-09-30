"""Native UHD screen edit. The browser image is placed 1:1, never zoomed.

Keeps the approved narration/timeline, preserves v1, uses PNG-origin 4:4:4
capture masters and a single delivery encode. All titles render at UHD size.
"""
import ast
import concurrent.futures
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / 'docs/demo/final_video/narrated'
OUT = ROOT / 'docs/demo/final_video/quality_v2'
CAP = OUT / 'captures'
SEG = OUT / 'segments'
SEG.mkdir(parents=True, exist_ok=True)
FPS = 30
FONT = '/usr/share/fonts/TTF/DejaVuSans.ttf'
BOLD = '/usr/share/fonts/TTF/DejaVuSans-Bold.ttf'
timeline = json.loads((OLD / 'edit-timeline.json').read_text())
# Read only the editorial card data, without executing the old renderer.
tree = ast.parse((ROOT / 'scripts/render_narrated_demo.py').read_text())
cards = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'cards' for t in n.targets))

def run(args):
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL)

def info(path):
    return json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)]))

def draw(text, x, y, size=48, bold=False, color='white', name='text'):
    p = SEG / (name + '.txt')
    p.write_text(text)
    return f"drawtext=fontfile={BOLD if bold else FONT}:textfile='{p}':x={x}:y={y}:fontsize={size}:fontcolor={color}"

def render(s):
    i, n, src = s['index'], s['frames'], s['source']
    duration = n / FPS
    target = SEG / f'{i:02}.mp4'
    if target.exists():
        try:
            v = info(target)['streams'][0]
            if v['width'] == 3840 and int(v['nb_frames']) == n:
                print('CACHED', i, flush=True)
                return
        except (subprocess.CalledProcessError, KeyError):
            pass
    filters = []
    if src in cards:
        inputs = ['-f', 'lavfi', '-i', f'color=c=0x101923:s=3840x2160:r=30:d={duration}']
        heading, items = cards[src]
        filters += [draw('DRISHTI3D  /  EVIDENCE-AWARE RECONSTRUCTION', 180, 380, 34, color='0xa8b8c8', name=f'{i}-eyebrow'),
                    draw(heading, 180, 490, 84, True, name=f'{i}-heading')]
        width = (3480 - (len(items) - 1) * 44) / len(items)
        for j, (number, label, desc) in enumerate(items):
            x = int(180 + j * (width + 44))
            accent = ('0x51cb93', '0xf0b748', '0x658ee8')[j] if src == 'evidence' else '0xe27960'
            filters += [f'drawbox=x={x}:y=800:w={int(width)}:h=560:color=0x192a39:t=fill',
                        f'drawbox=x={x}:y=800:w={int(width)}:h=5:color={accent}:t=fill',
                        draw(number, x + 52, 862, 44, color=accent, name=f'{i}-{j}-number'),
                        draw(label, x + 52, 1000, 70, True, name=f'{i}-{j}-label'),
                        draw(desc, x + 52, 1150, 42, color='0xcbd5df', name=f'{i}-{j}-description')]
            if src == 'accuracy' and j == (0 if i == 34 else 1):
                filters += [f'drawbox=x={x}:y=800:w={int(width)}:h=560:color=0xe27960:t=4']
        if src.startswith('accuracy'):
            filters += [draw('HKisland02 + HKisland03  •  MARS-LVIG  •  Independent same-flight LiDAR', 180, 1480, 40, color='0xa8b8c8', name=f'{i}-scope')]
    elif src == 'drone':
        inputs = ['-ss', '180', '-i', '/home/naveen/Downloads/DJI_1003_1080p.mp4']
        # Only the supplied drone clip is 1080p. Browser captures are native UHD.
        filters += ['scale=3414:1920:flags=lanczos', 'pad=3840:2160:(ow-iw)/2:108:color=0x101923', 'fps=30']
    elif src.endswith('.png'):
        p = CAP / src
        v = info(p)['streams'][0]
        assert (v['width'], v['height']) == (3840, 1920), (src, v['width'], v['height'])
        inputs = ['-loop', '1', '-framerate', '30', '-i', str(p)]
        filters += ['pad=3840:2160:0:108:color=0x101923']
    else:
        p = CAP / src
        metadata = info(p)
        v = metadata['streams'][0]
        assert (v['width'], v['height']) == (3840, 1920), (src, v['width'], v['height'])
        inputs = ['-i', str(p)]
        source_duration = float(metadata['format']['duration'])
        if src == 'hk3-full.mp4':
            offset = source_duration / 2 if i > 0 and timeline[i - 1]['source'] == src else 0
            source_duration /= 2
            filters += [f'trim=start={offset}:duration={source_duration}', 'setpts=PTS-STARTPTS']
        filters += [f'setpts={duration / source_duration:.10f}*PTS', 'fps=30',
                    'tpad=stop_mode=clone:stop_duration=0.1', 'pad=3840:2160:0:108:color=0x101923']
    filters += [f'trim=end_frame={n}', 'setpts=PTS-STARTPTS', 'setsar=1',
                'drawbox=x=0:y=0:w=3840:h=104:color=0x101923:t=fill',
                'drawbox=x=0:y=104:w=3840:h=4:color=0xcf5239:t=fill',
                draw(s['title'], 64, 30, 42, True, name=f'{i}-chapter'),
                draw(s['badge'], 'w-tw-64', 35, 32, color='0xcbd5df', name=f'{i}-badge'),
                'drawbox=x=0:y=2028:w=3840:h=132:color=0x101923:t=fill',
                draw(s['caption'], '(w-tw)/2', 2074, 48, name=f'{i}-caption')]
    if i == 0:
        filters += ['fade=t=in:st=0:d=0.3']
    if i == len(timeline) - 1:
        filters += [f'fade=t=out:st={duration - .5}:d=0.5']
    run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-threads', '3'] + inputs +
        ['-vf', ','.join(filters), '-an', '-frames:v', str(n), '-c:v', 'libx264', '-threads', '6',
         '-preset', 'fast', '-crf', '14', '-pix_fmt', 'yuv420p', '-color_primaries', 'bt709',
         '-color_trc', 'bt709', '-colorspace', 'bt709', '-movflags', '+faststart', str(target)])
    print('RENDERED', i, src, duration, flush=True)

if __name__ == '__main__':
    selected = [s for s in timeline if len(sys.argv) == 1 or str(s['index']) in sys.argv[1:]]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(render, selected))
    if len(selected) != len(timeline):
        sys.exit(0)
    (OUT / 'edit-timeline.json').write_text(json.dumps(timeline, indent=2))
    concat = SEG / 'concat.txt'
    concat.write_text(''.join("file '%s'\n" % (SEG / ('%02d.mp4' % s['index'])) for s in timeline))
    # Reuse the existing synchronized AAC bitstream; no second audio encode.
    run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', str(concat),
         '-i', str(OLD / 'Drishti3D_SIH26158_Final_5m30s.mp4'), '-map', '0:v:0', '-map', '1:a:0',
         '-c', 'copy', '-t', '330', '-movflags', '+faststart', str(OUT / 'Drishti3D_SIH26158_4K_Remastered.mp4')])
    print('4K MASTER COMPLETE', flush=True)
    run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-threads', '4',
         '-i', str(OUT / 'Drishti3D_SIH26158_4K_Remastered.mp4'), '-vf', 'scale=1920:1080:flags=lanczos',
         '-c:v', 'libx264', '-threads', '8', '-preset', 'slow', '-crf', '15', '-pix_fmt', 'yuv420p',
         '-c:a', 'copy', '-movflags', '+faststart', str(OUT / 'Drishti3D_SIH26158_1080p_Remastered.mp4')])
    print('1080P DELIVERY COMPLETE', flush=True)
