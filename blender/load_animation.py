"""All pose values are evaluated absolutely from frame time, including seek backwards."""
import bpy,json,math,textwrap
from mathutils import Vector,Quaternion,Euler
from pathlib import Path
from bpy.app.handlers import persistent
scene=bpy.context.scene;data=json.loads(scene['ostro_animation']);ep=data['episode'];timeline=data['timeline'];work=Path(scene['ostro_work'])
actors={a['id']:bpy.data.objects['Actor_'+a['id']] for a in ep['actors']}
rest={}
def descendants(o):
 yield o
 for c in o.children:yield from descendants(c)
for actor in actors.values():
 for o in descendants(actor):rest[o.name]=(o.matrix_basis.copy(),o.scale.copy())
def find(actor,name):return next((o for o in descendants(actor) if o.name.split('.')[0]==name),None)
def smooth(x):x=max(0,min(1,x));return x*x*(3-2*x)
def path(points,t):
 if not points:return None
 if t<=points[0][0]:return Vector(points[0][1])
 for a,b in zip(points,points[1:]):
  if t<=b[0]:return Vector(a[1]).lerp(Vector(b[1]),smooth((t-a[0])/(b[0]-a[0])))
 return Vector(points[-1][1])
def rot(o,x=0,y=0,z=0):
 if not o:return
 base=rest[o.name][0].to_quaternion();o.rotation_mode='QUATERNION';o.rotation_quaternion=base @ Euler((x,y,z),'XYZ').to_quaternion()
def evaluate(t):
 lines=timeline['lines'];current=next((l for l in lines if l['start']<=t<l['end']),None)
 sceneidx=0
 for i,s in enumerate(ep['scenes']):
  start=0 if s['anchor']=='opening' else next(l['start'] for l in lines if l['id']==s['anchor'])
  if t>=start:sceneidx=i
 for i in range(data['scene_count']):
  for o in descendants(bpy.data.objects['Set_'+str(i)]):o.hide_render=i!=sceneidx;o.hide_viewport=i!=sceneidx
 for spec in ep['actors']:
  actor=actors[spec['id']]
  for o in descendants(actor):
   mb,s=rest[o.name];o.matrix_basis=mb
   if o.type=='MESH' and o.data.shape_keys:
    k=o.data.shape_keys.key_blocks.get('MouthOpen')
    if k:k.value=0
  position=path(spec.get('path'),t)
  if position is not None:actor.location=position
  head=find(actor,'Head_Pivot');speak=current and current['speaker']==spec['id']
  # Yaw only: a Pop-style hidden head socket has no anatomical neck to bend.
  rot(head,0,0,.045*math.sin(t*1.3) if speak else 0)
  arm=find(actor,'Arm_R');rot(arm,-.10*math.sin(t*2) if speak else 0,0,0)
  blink=max(0,1-abs(((t+spec.get('blink_offset',0))%4.7)-2.2)/.10)
  for side in ['L','R']:
   eye=find(actor,'Eye_'+side)
   if eye:eye.scale.z=rest[eye.name][1].z*(1-.94*blink)
  levels=timeline['mouth'].get(spec['id'],[]);amount=levels[min(len(levels)-1,int(t*timeline['mouth_fps']))] if levels else 0
  for o in descendants(actor):
   if o.type=='MESH' and o.data.shape_keys:
    k=o.data.shape_keys.key_blocks.get('MouthOpen')
    if k:k.value=amount
 cap=bpy.data.objects.get('Caption');cap.data.body='\n'.join(textwrap.wrap(current['text'],32)) if current else ''
 bpy.data.objects['Caption_card'].hide_render=current is None
 camera=scene.camera;cfg=ep.get('camera',{});pos=path(cfg.get('path'),t)
 if pos is not None:camera.location=pos;camera.rotation_euler=(Vector(cfg.get('look_at',[0,0,1.7]))-pos).to_track_quat('-Z','Y').to_euler()
 scene['ostro_time']=t
@persistent
def ostro_frame(sc):evaluate((sc.frame_current-1)/data['fps'])
for h in list(bpy.app.handlers.frame_change_pre):
 if h.__name__=='ostro_frame':bpy.app.handlers.frame_change_pre.remove(h)
bpy.app.handlers.frame_change_pre.append(ostro_frame);evaluate(0)
if '--contact' in __import__('sys').argv:
 original=scene.render.filepath
 for frame in sorted({1,max(1,scene.frame_end//2),scene.frame_end}):
  scene.frame_set(frame);scene.render.filepath=str(work/f'preview-{frame:04d}.png');bpy.ops.render.render(write_still=True)
 scene.render.filepath=original
