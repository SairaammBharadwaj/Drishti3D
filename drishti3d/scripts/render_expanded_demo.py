"""Render the 6:40 subtitle-free extended demo from clean native captures.

Original narration is preserved in sequence. New passages intentionally have
silence pending the user's recording. Existing deliverables are never replaced.
"""
import argparse
import json
import shutil
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'docs/demo/final_video/quality_v2'
CAP=OLD/'captures'
OUT=ROOT/'docs/demo/final_video/expanded_2026_10_02'
ASSETS=OUT/'assets'
SEG=OUT/'segments'
SEG.mkdir(parents=True,exist_ok=True)
FPS=30
VOICE=Path('/home/naveen/Downloads/Drishti3D_SIH26158_4K_Clean_Intro.mp4')
ENC=['-c:v','h264_nvenc','-preset','p7','-tune','hq','-rc','vbr','-cq','12','-b:v','0',
     '-profile:v','high','-level:v','5.1','-pix_fmt','yuv420p','-g','60','-bf','3',
     '-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709','-color_range','tv',
     '-video_track_timescale','15360']

def run(args):
    subprocess.run(args,check=True,stdin=subprocess.DEVNULL)

def probe(p):
    return json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(p)]))

def add(plan,name,source,n,**kw):
    start=sum(s['frames'] for s in plan)
    plan.append(dict(index=len(plan),name=name,source=source,frames=n,start_frame=start,end_frame=start+n,
                     start=start/FPS,end=(start+n)/FPS,**kw))

def plan():
    timeline=json.loads((OLD/'edit-timeline.json').read_text())
    result=[]
    add(result,'intro','brand',360,voice='pending')
    replacements={'calibration':'report-top.png','pipeline':'results-scroll.mp4',
                  'evidence':'hk3-evidence.mp4','alignment':'report-top.png',
                  'safety':'measurement-result.png','accuracy':'@validation.png',
                  'accuracy-scope':'@validation-scope.png','exports':'report-bottom.png',
                  'closing':'brand'}
    for s in timeline:
        if s['index']==42:
            add(result,'code-architecture','@code-architecture.png',270,voice='pending')
            add(result,'code-questions','@code-questions.png',270,voice='pending')
            add(result,'code-refinement','@code-refinement.png',150,voice='pending')
            add(result,'code-refinement-result','@code-refinement-result.png',120,voice='pending')
            add(result,'code-tests','@code-tests.png',270,voice='pending')
            add(result,'benefit-local','hk3-orbit.mp4',210,voice='pending')
            add(result,'benefit-measurement','measurement-result.png',210,voice='pending')
            add(result,'benefit-report','report-scroll.mp4',240,voice='pending')
        source=replacements.get(s['source'],s['source'])
        if s['index']==35: source='@validation-detail.png'
        kw={'original_index':s['index'],'voice':'existing','original_start':s['start']}
        if source=='hk3-full.mp4': kw['half']=0 if s['index']==40 else 1
        if source=='brand': kw['closing']=True
        add(result,f"original-{s['index']:02}",source,s['frames'],**kw)
    assert sum(s['frames'] for s in result)==12000
    (OUT/'edit-timeline.json').write_text(json.dumps(result,indent=2))
    return result

def render(s):
    target=SEG/f"{s['index']:02}-{s['name']}.mp4"
    if target.exists():
        v=probe(target)['streams'][0]
        if int(v.get('nb_frames',0))==s['frames']:
            print('CACHED',target.name,flush=True)
            return target
    n=s['frames']; duration=n/FPS; src=s['source']
    prefix=['ffmpeg','-nostdin','-y','-hide_banner','-loglevel','error','-threads','2','-filter_threads','1','-filter_complex_threads','1']
    filters=[]
    if src=='brand':
        # Model pixels remain 1:1. Crop only native viewer chrome for the hero.
        p=CAP/'island-detail.mp4'
        d=float(probe(p)['format']['duration'])
        inputs=['-i',str(p),'-loop','1','-framerate','30','-i',str(ASSETS/'brand-overlay.png')]
        f=f'[0:v]setpts={duration/d:.12f}*PTS,fps=30,crop=2496:1320:624:480,pad=3840:2160:1220:450:color=0x0b151f[model];[model][1:v]overlay=0:0:shortest=1'
        if s.get('closing'): f+=f',fade=t=out:st={duration-.6}:d=0.6'
        else: f+=',fade=t=in:st=0:d=0.35'
        f+=f',trim=end_frame={n},setpts=PTS-STARTPTS,setsar=1[v]'
        middle=['-filter_complex',f,'-map','[v]']
    else:
        if src=='drone':
            inputs=['-ss','180','-i','/home/naveen/Downloads/DJI_1003_1080p.mp4']
            filters=['scale=3840:2160:flags=lanczos','fps=30']
        else:
            p=ASSETS/src[1:] if src.startswith('@') else CAP/src
            v=probe(p)['streams'][0]
            if src.endswith('.png'):
                inputs=['-loop','1','-framerate','30','-i',str(p)]
            else:
                inputs=['-i',str(p)]
                d=float(probe(p)['format']['duration'])
                if 'half' in s:
                    filters += [f'trim=start={s["half"]*d/2}:duration={d/2}','setpts=PTS-STARTPTS']
                    d/=2
                filters += [f'setpts={duration/d:.12f}*PTS','fps=30','tpad=stop_mode=clone:stop_duration=0.1']
            assert v['width']==3840 and v['height'] in (1920,2160)
            if v['height']==1920: filters+=['pad=3840:2160:0:120:color=0x101923']
        filters += [f'trim=end_frame={n}','setpts=PTS-STARTPTS','setsar=1']
        middle=['-vf',','.join(filters)]
    run(prefix+inputs+middle+['-an','-frames:v',str(n)]+ENC+['-movflags','+faststart',str(target)])
    assert int(probe(target)['streams'][0]['nb_frames'])==n
    print('RENDERED',target.name,f'{duration:.3f}s',flush=True)
    return target

def audio():
    p=OUT/'voice-with-recording-slots.wav'
    if p.exists(): return p
    # 9289 original video frames at 30 fps = 14,862,400 audio samples.
    f=('[0:a]aresample=48000,asplit=2[x][y];'
       '[x]atrim=end_sample=14862400,asetpts=PTS-STARTPTS[body];'
       '[y]atrim=start_sample=14862400:end_sample=15840000,asetpts=PTS-STARTPTS[tail];'
       'anullsrc=r=48000:cl=stereo,atrim=end_sample=576000[intro];'
       'anullsrc=r=48000:cl=stereo,atrim=end_sample=2784000[additions];'
       '[intro][body][additions][tail]concat=n=4:v=0:a=1[out]')
    run(['ffmpeg','-nostdin','-y','-hide_banner','-loglevel','error','-threads','2',
         '-i',str(VOICE),'-filter_complex',f,'-map','[out]','-c:a','pcm_s24le',str(p)])
    return p

def assemble(shots):
    files=[SEG/f"{s['index']:02}-{s['name']}.mp4" for s in shots]
    concat=SEG/'concat.txt'
    concat.write_text(''.join(f"file '{p}'\n" for p in files))
    uhd=OUT/'Drishti3D_Extended_4K_No_Subtitles.mp4'
    if not uhd.exists():
        run(['ffmpeg','-nostdin','-y','-hide_banner','-loglevel','error','-f','concat','-safe','0','-i',str(concat),
             '-i',str(audio()),'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','256k',
             '-t','400','-movflags','+faststart',str(uhd)])
    print('4K MASTER COMPLETE',flush=True)
    hd=OUT/'Drishti3D_Extended_1080p_No_Subtitles.mp4'
    if not hd.exists():
        run(['ffmpeg','-nostdin','-y','-hide_banner','-loglevel','error','-threads','2','-filter_threads','1',
             '-i',str(uhd),'-vf','scale=1920:1080:flags=lanczos','-map','0:v:0','-map','0:a:0',
             *ENC,'-c:a','copy','-movflags','+faststart',str(hd)])
    print('1080P DELIVERY COMPLETE',flush=True)
    return uhd,hd

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--only',nargs='*',type=int)
    args=parser.parse_args()
    shots=plan()
    for s in shots:
        if args.only is None or s['index'] in args.only: render(s)
    if args.only is None: assemble(shots)
