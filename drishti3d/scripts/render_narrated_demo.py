"""Reproducible 5:30 edit, anchored to the recorded narration's word times."""
import json, subprocess, concurrent.futures
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/demo/final_video/narrated'
CAP=OUT/'captures'
SEG=OUT/'segments'
SEG.mkdir(parents=True,exist_ok=True)
VOICE=Path('/home/naveen/Downloads/WhatsApp Audio 2026-09-27 at 6.21.48 PM.aac')
FPS=30
SPEED=334/330
FONT='/usr/share/fonts/TTF/DejaVuSans.ttf'
BOLD='/usr/share/fonts/TTF/DejaVuSans-Bold.ttf'
# Narration source times, assets, chapter, supporting on-screen message.
# No existing silent-video timings or baked captions are reused.
shots=[
 (1.4,'drone','01 / THE CAPTURE','One ordinary drone pass','VIDEO + FLIGHT CONTEXT'),
 (10.9,'home.png','02 / DRISHTI3D','From aerial footage to spatial understanding','THE PRODUCT'),
 (16.6,'city-detail.mp4','02 / DRISHTI3D','Explore the reconstruction. Inspect the evidence.','AUSTIN / TRUE COLOUR'),
 (22.4,'austin-orbit.mp4','03 / THE QUESTION','What was actually seen?','OBSERVED GEOMETRY'),
 (29.2,'hk3-evidence.mp4','03 / THE QUESTION','Seen  /  Inferred  /  Measurable','HONG KONG / EVIDENCE VIEW'),
 (36.5,'missions.png','04 / MISSION INPUTS','Video and flight telemetry, together','MISSION LIBRARY'),
 (43.5,'report-top.png','04 / MISSION INPUTS','Camera recovery  /  Scale  /  Alignment','HKISLAND03 / INPUT RECORD'),
 (49.4,'source.png','04 / MISSION INPUTS','Keep the source behind the result','SAVED CAPTURE'),
 (54.5,'setup.png','05 / MISSION SETUP','Create the mission and describe the capture','MISSION SETUP'),
 (61.3,'report-top.png','05 / MISSION SETUP','Capture information stays inspectable','INPUTS + TELEMETRY'),
 (66.0,'calibration','05 / MISSION SETUP','Known calibration or documented estimates','CAMERA CALIBRATION'),
 (71.3,'pipeline','06 / RECONSTRUCTION','Frame screening → Camera recovery → Dense geometry','WORKFLOW OVERVIEW'),
 (80.5,'results-scroll.mp4','06 / RECONSTRUCTION','Geometry, positioning and supporting evidence','SAVED RESULT / INSPECTION'),
 (90.5,'results.png','07 / RECONSTRUCTION RESULTS','More than a point count','AUSTIN / RECONSTRUCTION'),
 (97.3,'results-lower.png','07 / RECONSTRUCTION RESULTS','Registration  /  Reprojection  /  Positioning','QUALITY CONTEXT'),
 (104.0,'report-scroll.mp4','07 / RECONSTRUCTION RESULTS','Strengths and limitations travel with the model','EVIDENCE REPORT'),
 (110.4,'hk3-orbit.mp4','08 / EXPLORE THE GEOMETRY','Coastline detail and recovered flight path','HKISLAND03 / SINGLE PASS'),
 (119.4,'island-detail.mp4','08 / EXPLORE THE GEOMETRY','A closer look at the reconstructed terrain','HKISLAND03 / DETAIL'),
 (126.3,'hk2-orbit.mp4','08 / EXPLORE THE GEOMETRY','Real geometry, presented with its limits','HKISLAND02 / SINGLE PASS'),
 (131.1,'hk3-evidence.mp4','09 / EVIDENCE COLOURS','Green: observed high  /  Amber: observed low  /  Blue: inferred fill','PROVENANCE'),
 (140.3,'evidence','09 / EVIDENCE COLOURS','Every class has a different meaning','OBSERVATION SUPPORT'),
 (147.0,'hk3-evidence.mp4','09 / EVIDENCE COLOURS','Keep observations and inference distinguishable','HKISLAND03 / EVIDENCE'),
 (153.2,'prototype.png','10 / AI-ASSISTED GEOMETRY','AI assistance is a separately labelled layer','RESEARCH PROTOTYPE / RELATIVE SCALE'),
 (161.3,'evidence','10 / AI-ASSISTED GEOMETRY','A useful visualization is not surveyed evidence','LABELLED GEOMETRY'),
 (169.0,'measurement-picked.png','10 / AI-ASSISTED GEOMETRY','Inferred geometry is excluded from measurement by default','OBSERVED GEOMETRY FIRST'),
 (178.0,'report-top.png','11 / POSITIONING CONTEXT','RTK / GPS alignment describes a fit to the input track','POSITIONING'),
 (187.6,'alignment','11 / POSITIONING CONTEXT','Fit residual ≠ independent accuracy','INDEPENDENT REFERENCE REQUIRED'),
 (196.8,'measurement-first.png','12 / MEASUREMENTS','Select observed points in the workspace','DISTANCE TOOL'),
 (203.0,'measurement-picked.png','12 / MEASUREMENTS','Review the endpoints and available support','OBSERVED GEOMETRY'),
 (208.4,'austin-orbit.mp4','12 / MEASUREMENTS','Keep the measurement and its limitations visible','AUSTIN / INTERVAL AND LIMITS'),
 (217.5,'measurement-result.png','13 / MEASUREMENT SAFETY','A click is not a certified answer','EVIDENCE BEFORE RELIANCE'),
 (225.0,'safety','13 / MEASUREMENT SAFETY','Coverage  /  Viewing geometry  /  Independent validation','REQUIREMENTS NEED EVIDENCE'),
 (236.0,'hk2-orbit.mp4','14 / INDEPENDENT VALIDATION','Same-flight LiDAR on two Hong Kong reference flights','HKISLAND02 / SINGLE PASS'),
 (246.45,'hk3-orbit.mp4','14 / INDEPENDENT VALIDATION','Actual reconstructed geometry compared with LiDAR','HKISLAND03 / SINGLE PASS'),
 (252.1,'accuracy','14 / INDEPENDENT VALIDATION','Vertical RMSE: 0.38–0.42 m','HONG KONG / SAME-FLIGHT LIDAR'),
 (257.7,'accuracy','14 / INDEPENDENT VALIDATION','Horizontal placement error: 0.08–0.28 m','HONG KONG / SAME-FLIGHT LIDAR'),
 (263.4,'accuracy-scope','14 / VALIDATION SCOPE','These figures apply to the Hong Kong reference flights only','DATASET-SPECIFIC RESULTS'),
 (273.0,'report-scroll.mp4','15 / REPORT AND EXPORT','Inputs, registration, provenance, warnings and limitations','EVIDENCE REPORT'),
 (283.8,'report-bottom.png','15 / REPORT AND EXPORT','Carry the context beyond the viewer','LIMITATIONS + PERFORMANCE'),
 (289.0,'exports','15 / REPORT AND EXPORT','PLY  /  LAS  /  GLB  /  GeoJSON  /  CSV  /  JSON  /  HTML','EXPORT THE EVIDENCE'),
 (296.6,'hk3-full.mp4','16 / FULL-WINDOW CONTEXT','Place the close-up in the larger flight area','HKISLAND03 / FULL WINDOW'),
 (305.3,'hk3-full.mp4','16 / FULL-WINDOW CONTEXT','The same evidence-aware workflow across the scene','LARGER FLIGHT AREA'),
 (314.8,'city-detail.mp4','17 / DRISHTI3D','What was seen. What was inferred. What can be measured.','EVIDENCE-AWARE 3D'),
 (324.5,'closing','17 / DRISHTI3D','Ordinary drone footage. Evidence-aware 3D.','SIH26158'),
]

def run(args): subprocess.run(args,check=True,stdout=subprocess.DEVNULL)
def probe(path): return float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',str(path)]))
def textfile(name,text):
 p=SEG/name;p.write_text(text);return p
def draw(text,x,y,size=30,bold=False,color='white',name='label'):
 p=textfile(f'{name}.txt',text)
 return f"drawtext=fontfile={BOLD if bold else FONT}:textfile='{p}':x={x}:y={y}:fontsize={size}:fontcolor={color}"

cards={
 'exports':('TAKE THE EVIDENCE WITH YOU',[('01','PLY / LAS / GLB','Point clouds and 3D geometry'),('02','GeoJSON / CSV','Spatial data and flight trajectory'),('03','JSON / HTML','Reports for analysis and review')]),
 'calibration':('MAKE CAMERA ASSUMPTIONS VISIBLE',[('01','Known calibration','Supply the camera parameters'),('02','Estimated calibration','Keep the assumption in the report')]),
 'pipeline':('FROM VIDEO TO AN INSPECTABLE RESULT', [('01','Screen frames','Select useful views'),('02','Recover cameras','Reconstruct flight geometry'),('03','Build dense geometry','Align and report evidence')]),
 'evidence':('READ THE EVIDENCE BEHIND THE SURFACE',[('01','Observed high','Stronger camera support'),('02','Observed low','Weaker observation support'),('03','Inferred / assisted','Labelled separately')]),
 'alignment':('TWO DIFFERENT QUESTIONS',[('01','Alignment residual','How well does it fit the input track?'),('02','Independent accuracy','How close is it to a separate reference?')]),
 'safety':('REQUIREMENTS NEED EVIDENCE',[('01','Coverage','Was the region observed sufficiently?'),('02','Viewing geometry','Do the camera views support the question?'),('03','Validation','Has accuracy been independently checked?')]),
 'accuracy':('HONG KONG / SINGLE-PASS VALIDATION',[('01','0.38–0.42 m','Vertical RMSE'),('02','0.08–0.28 m','Horizontal placement error')]),
 'accuracy-scope':('KEEP THE VALIDATION IN CONTEXT',[('01','HKisland02 + HKisland03','Same-flight LiDAR reference'),('02','Flight-specific results','Not Austin results or a universal guarantee')]),
 'closing':('DRISHTI3D',[('01','Seen. Inferred. Measurable.','Keep the evidence behind every answer visible.')])
}
manifest=[]
for i,(t,src,title,caption,badge) in enumerate(shots):
 start=round(max(0,(t-1.4)/SPEED)*FPS)
 end=round(((shots[i+1][0]-1.4)/SPEED if i+1<len(shots) else 330)*FPS)
 manifest.append(dict(index=i,start=start/FPS,end=end/FPS,frames=end-start,source=src,title=title,caption=caption,badge=badge))
(OUT/'edit-timeline.json').write_text(json.dumps(manifest,indent=2))

def render(s):
 i=s['index'];n=s['frames'];duration=n/FPS;src=s['source'];filters=[]
 target=SEG/f'{i:02}.mp4'
 if target.exists() and abs(probe(target)-duration)<.005: print('Cached',i,flush=True);return
 prefix=['ffmpeg','-y','-hide_banner','-loglevel','error','-threads','2']
 if src in cards:
  inputs=['-f','lavfi','-i',f'color=c=0x101d2a:s=1920x1080:r=30:d={duration}']
  heading,items=cards[src]
  filters += ['drawgrid=w=80:h=80:t=1:c=0x203143@0.4',draw(heading,100,230,46,True,name=f'{i}-heading')]
  width=(1720-(len(items)-1)*30)/len(items)
  for j,(number,label,desc) in enumerate(items):
   x=int(100+j*(width+30))
   filters += [f'drawbox=x={x}:y=375:w={int(width)}:h=310:color=0x1b3043:t=fill',f'drawbox=x={x}:y=375:w=5:h=310:color=0xd65b43:t=fill',draw(number,x+28,407,26,color='0xe49476',name=f'{i}-{j}-n'),draw(label,x+28,482,38,True,name=f'{i}-{j}-l'),draw(desc,x+28,566,22,name=f'{i}-{j}-d')]
   if src=='accuracy' and j==(0 if i==34 else 1):
    filters += [f'drawbox=x={x}:y=375:w={int(width)}:h=310:color=0xe49476:t=3']
  if src.startswith('accuracy'):
   filters += [draw('HKisland02 + HKisland03  •  MARS-LVIG  •  Independent same-flight LiDAR',100,755,24,name=f'{i}-scope')]
  filters += [f"drawbox=x=100:y=850:w=1720:h=3:color=0x31495f:t=fill",f"drawtext=fontfile={FONT}:text='•':x='100+1720*t/{duration}':y=829:fontsize=36:fontcolor=0xe49476"]
  # Editorial cards get a slow camera push; the fixed title and captions below
  # stay readable. Highlight the metric currently being spoken in the voice-over.
  filters += [f"scale=2304:1296:flags=lanczos,zoompan=z='1+0.045*on/{n}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s=1920x1080:fps=30"]
 elif src=='drone':
  inputs=['-ss','180','-i','/home/naveen/Downloads/DJI_1003_1080p.mp4']
  filters += ['scale=1920:1080:flags=lanczos','fps=30']
 elif src.endswith('.png'):
  inputs=['-i',str(CAP/src)]
  filters += [f"scale=2304:1296:flags=lanczos,zoompan=z='1+0.045*on/{n}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d={n}:s=1920x1080:fps=30"]
 else:
  p=CAP/('hk3-orbit.mp4' if src=='hk3-detail' else src)
  inputs=['-i',str(p)]
  if src=='hk3-detail':filters+=['crop=1020:680:440:240','scale=1920:1080:flags=lanczos']
  source_duration=probe(p)
  if src=='hk3-full.mp4':
   offset=source_duration/2 if i>0 and manifest[i-1]['source']==src else 0
   source_duration/=2
   filters += [f'trim=start={offset}:duration={source_duration}','setpts=PTS-STARTPTS']
  filters += [f'setpts={duration/source_duration:.9f}*PTS','fps=30','tpad=stop_mode=clone:stop_duration=0.1']
 filters += [f'trim=end_frame={n}','setpts=PTS-STARTPTS','setsar=1',
  'drawbox=x=0:y=0:w=1920:h=105:color=0x0b1520@0.97:t=fill',
  'drawbox=x=0:y=104:w=1920:h=3:color=0xd65b43:t=fill',
  draw(s['title'],48,34,30,True,name=f'{i}-title'),
  draw(s['badge'],'w-tw-48',40,18,color='0xbbcddd',name=f'{i}-badge'),
  'drawbox=x=0:y=989:w=1920:h=91:color=0x0b1520@0.95:t=fill',
  draw(s['caption'],'(w-tw)/2',1017,27,name=f'{i}-caption')]
 if i==0:filters+=['fade=t=in:st=0:d=0.35']
 if i==len(shots)-1:filters+=[f'fade=t=out:st={duration-.55}:d=0.55']
 run(prefix+inputs+['-vf',','.join(filters),'-an','-frames:v',str(n),'-c:v','libx264','-threads','3','-preset','fast','-crf','17','-pix_fmt','yuv420p',str(target)])
 print('Rendered',i,src,round(duration,2),flush=True)

if __name__=='__main__':
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(render,manifest))
 concat=SEG/'concat.txt';concat.write_text(''.join(f"file '{SEG / f'{i:02}.mp4'}'\n" for i in range(len(shots))))
 run(['ffmpeg','-y','-hide_banner','-loglevel','error','-f','concat','-safe','0','-i',str(concat),'-c','copy',str(OUT/'picture-lock.mp4')])
 # Decode before cutting; ADTS AAC duration estimates are not sample-accurate.
 audiofilter=f'atrim=start=1.4:end=335.4,asetpts=PTS-STARTPTS,atempo={SPEED},highpass=f=65,loudnorm=I=-16:TP=-1.5:LRA=9,aresample=48000,afade=t=in:d=0.08,afade=t=out:st=329.55:d=0.45,apad,atrim=duration=330'
 run(['ffmpeg','-y','-hide_banner','-loglevel','error','-i',str(OUT/'picture-lock.mp4'),'-i',str(VOICE),'-map','0:v:0','-map','1:a:0','-af',audiofilter,'-c:v','copy','-c:a','aac','-b:a','256k','-t','330','-movflags','+faststart',str(OUT/'Drishti3D_SIH26158_Final_5m30s.mp4')])
 print('FINAL',OUT/'Drishti3D_SIH26158_Final_5m30s.mp4',flush=True)
