from pathlib import Path
import os,json,hashlib,base64,math,wave,array,subprocess,time,ctypes
from ctypes import wintypes
import httpx

def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def write(p,d):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
def read_voice_registry(root):
 defaults=read(root/'registry/voices.json')
 local=root/'.local/voices.json'
 if local.exists():defaults.update(read(local))
 return defaults

def store_key(root,key):
 if not key or len(key)<15:raise ValueError('Empty or invalid key')
 import win32crypt
 blob=win32crypt.CryptProtectData(key.encode(),'OSTRO ElevenLabs',None,None,None,0)
 p=root/'.local/elevenlabs.dpapi';p.parent.mkdir(exist_ok=True);p.write_bytes(blob)
def get_key(root):
 if os.environ.get('ELEVENLABS_API_KEY'):return os.environ['ELEVENLABS_API_KEY']
 p=root/'.local/elevenlabs.dpapi'
 if p.exists():
  import win32crypt
  return win32crypt.CryptUnprotectData(p.read_bytes(),None,None,None,0)[1].decode()
 raise RuntimeError('No ElevenLabs credential. Set ELEVENLABS_API_KEY or use voices store-key via stdin.')
def api(root,method,path,**kw):
 key=get_key(root)
 with httpx.Client(timeout=120,follow_redirects=False) as c:r=c.request(method,'https://api.elevenlabs.io'+path,headers={'xi-api-key':key},**kw)
 if 'geo-restriction' in str(r.url)+r.headers.get('location','') or 'Access restricted' in r.text[:10000]:raise RuntimeError('ElevenLabs geographic restriction: authentication and voices_write cannot be verified from this connection.')
 if 'json' not in r.headers.get('content-type',''):raise RuntimeError(f'ElevenLabs returned non-JSON HTTP {r.status_code}; no generation assumed successful.')
 if not r.is_success:
  d=r.json();raise RuntimeError('ElevenLabs HTTP '+str(r.status_code)+': '+json.dumps(d.get('detail',d),ensure_ascii=False)[:600])
 return r.json()
def probe_key(root):
 results=[]
 for endpoint in ['/v1/user','/v1/user/subscription','/v2/voices?page_size=100']:
  try:
   d=api(root,'GET',endpoint)
   if endpoint.endswith('subscription'):
    summary={k:d[k] for k in ['tier','status','voice_limit','professional_voice_limit','can_use_instant_voice_cloning','can_use_professional_voice_cloning','character_count','character_limit'] if k in d}
   elif 'voices' in endpoint:summary={'voices_in_page':len(d.get('voices',[])),'has_more':d.get('has_more')}
   else:summary={'user_read':True}
   results.append({'endpoint':endpoint,'status':'ok',**summary})
  except Exception as e:results.append({'endpoint':endpoint,'status':'unverified','reason':str(e)})
 report={'checked_at_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'checks':results,'voice_creation_permission':'unverified_without_authenticated_create_or_explicit_scope_evidence','created_voices':0,'spent_credits':0}
 write(root/'reports/elevenlabs-access.json',report);return report
def pcm(path,ffmpeg):
 r=subprocess.run([str(ffmpeg),'-v','error','-i',str(path),'-f','s16le','-ac','1','-ar','16000','pipe:1'],capture_output=True,check=True)
 a=array.array('h');a.frombytes(r.stdout);return a
def inspect_sample(path,ffmpeg):
 a=pcm(path,ffmpeg);dur=len(a)/16000;rms=math.sqrt(sum(v*v for v in a)/max(1,len(a)))/32768;peak=max((abs(v) for v in a),default=0)/32768
 blocks=[math.sqrt(sum(v*v for v in a[i:i+320])/max(1,len(a[i:i+320])))/32768 for i in range(0,len(a),320)]
 return {'file':str(path),'duration_seconds':round(dur,3),'peak_dbfs':round(20*math.log10(max(peak,1e-9)),2),'rms_dbfs':round(20*math.log10(max(rms,1e-9)),2),'clipped_sample_fraction':sum(abs(v)>=32760 for v in a)/max(1,len(a)),'quiet_block_fraction':sum(v<.006 for v in blocks)/max(1,len(blocks)),'ivc_recommended_duration':60<=dur<=180,'note':'Metrics do not prove one speaker, no music, no room reverb, identity or consent; listen before upload.'}
def create_clone(root,person,ffmpeg,consent,reference,name=None):
 registry=read_voice_registry(root);v=registry[person]
 if v.get('voice_id'):return {'status':'already_created','voice_id':v['voice_id']}
 if not consent or not reference:raise RuntimeError('Record owner consent with --confirm-owner-consent and --consent-reference.')
 inbox=root/v['samples_dir'];inbox.mkdir(parents=True,exist_ok=True)
 files=sorted(p for p in inbox.iterdir() if p.suffix.lower() in ['.mp3','.wav','.m4a','.ogg','.flac','.aac'])
 if not files:raise RuntimeError('No samples in '+v['samples_dir'])
 stats=[inspect_sample(p,ffmpeg) for p in files];duration=sum(s['duration_seconds'] for s in stats)
 if duration<60 or duration>180:raise RuntimeError('Choose 60–180 seconds of clean consistent speech for the IVC starter dataset.')
 if any(s['clipped_sample_fraction']>.001 for s in stats):raise RuntimeError('Samples clip; choose a clean recording.')
 # Clone exactly once. On a timeout, reconcile the account before retrying; do not duplicate slots.
 import contextlib
 with contextlib.ExitStack() as stack:
  multipart=[('files',(p.name,stack.enter_context(p.open('rb')),'application/octet-stream')) for p in files]
  data=api(root,'POST','/v1/voices/add',data={'name':name or 'Project / '+v['name'],'description':'Owner-authorized project voice','remove_background_noise':'false'},files=multipart)
 v.update(voice_id=data['voice_id'],status='verification_required' if data.get('requires_verification') else 'ready',consent_confirmed=True,consent_reference=reference,method='ivc',sample_hashes=[hashlib.sha256(p.read_bytes()).hexdigest() for p in files])
 write(root/'.local/voices.json',registry)
 return {'status':v['status'],'voice_id':v['voice_id']}
def words_from_alignment(d):
 a=d.get('normalized_alignment') or d.get('alignment') or {};words=[];text='';start=None;end=0
 for ch,s,e in zip(a.get('characters',[]),a.get('character_start_times_seconds',[]),a.get('character_end_times_seconds',[])):
  if ch.isspace():
   if text:words.append({'text':text,'start':start,'end':end});text='';start=None
  else:
   if start is None:start=s
   text+=ch;end=e
 if text:words.append({'text':text,'start':start,'end':end})
 return words
def prepare_audio(root,ep,work,ffmpeg):
 voices=read_voice_registry(root);actors={a['id']:a.get('voice_person',a.get('character')) for a in ep['actors']};offset=ep.get('opening_silence',1.0);rate=48000;chunks=[b'\0'*round(offset*rate)*2];timeline=[];calls=hits=0
 cache=root/'.local/tts-cache';cache.mkdir(parents=True,exist_ok=True)
 for i,line in enumerate(ep.get('lines',[])):
  if line.get('cached_audio'):
   audio=root/line['cached_audio'];alignment=read(root/line['cached_alignment']) if line.get('cached_alignment') else {};source='explicit_cached_reference'
  else:
   person=actors[line['speaker']];voice=voices[person]
   if voice['status']!='ready' or not voice.get('voice_id'):raise RuntimeError('No ready, authorized voice for '+person+'. No automatic voice substitution.')
   body={'text':line.get('spoken_text',line['text']),'model_id':ep.get('tts_model','eleven_v4'),'language_code':'ru','voice_settings':{'stability':.5,'similarity_boost':.75},'seed':ep.get('seed',71)+i}
   if line.get('delivery'):body['text']=line['delivery']+'\n'+body['text']
   digest=hashlib.sha256(json.dumps({'body':body,'voice':voice['voice_id']},sort_keys=True,ensure_ascii=False).encode()).hexdigest();audio=cache/(digest+'.mp3');alignfile=cache/(digest+'.json')
   if audio.exists() and alignfile.exists():alignment=read(alignfile);hits+=1
   else:
    alignment=api(root,'POST','/v1/text-to-speech/'+voice['voice_id']+'/with-timestamps?output_format=mp3_44100_192',json=body);audio.write_bytes(base64.b64decode(alignment.pop('audio_base64')));write(alignfile,alignment);calls+=1
   source='library_voice' if voice.get('method')=='existing_library_voice' else 'owner_voice'
  raw=subprocess.run([str(ffmpeg),'-v','error','-i',str(audio),'-f','s16le','-ac','1','-ar',str(rate),'pipe:1'],capture_output=True,check=True).stdout;dur=len(raw)/2/rate
  linewords=words_from_alignment(alignment)
  timeline.append({'id':line['id'],'speaker':line['speaker'],'text':line['text'],'start':offset,'end':offset+dur,'words':[dict(w,start=w['start']+offset,end=w['end']+offset) for w in linewords],'voice_source':source})
  chunks.append(raw);gap=line.get('gap_after',.14);chunks.append(b'\0'*round(gap*rate)*2);offset+=dur+gap
 tail=ep.get('ending_silence',.5);chunks.append(b'\0'*round(tail*rate)*2)
 with wave.open(str(work/'mix.wav'),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(rate);w.writeframes(b''.join(chunks))
 total=offset+tail;mouth={};a=pcm(work/'mix.wav',ffmpeg)
 for line in timeline:
  levels=[]
  for f in range(math.ceil(total*30)):
   t=f/30;block=a[round(t*16000):round((t+1/30)*16000)];rms=math.sqrt(sum(v*v for v in block)/max(1,len(block)))/32768
   levels.append(min(1,max(0,(rms-.008)*10)) if line['start']<=t<line['end'] else 0)
  person=line['speaker'];old=mouth.setdefault(person,[0]*len(levels));mouth[person]=[max(x,y) for x,y in zip(old,levels)]
 data={'duration':total,'lines':timeline,'mouth_fps':30,'mouth':mouth,'tts_new_requests':calls,'tts_cache_hits':hits};write(work/'timeline.json',data);return data
