"""Run inside Blender on a saved episode. Seek forward/back without state drift."""
from pathlib import Path
import bpy,json,hashlib
work=Path(bpy.context.scene['ostro_work']);root=Path(bpy.context.scene['ostro_root'])
exec(compile((root/'blender/load_animation.py').read_text(encoding='utf-8'),str(root/'blender/load_animation.py'),'exec'))
def digest(t):
 evaluate(t);bpy.context.view_layer.update();out=[]
 def actor_owned(o):
  while o:
   if o.name.startswith('Actor_'):return True
   o=o.parent
  return False
 for o in sorted(bpy.data.objects,key=lambda o:o.name):
  if actor_owned(o):
   out.append((o.name,[round(x,7) for row in o.matrix_world for x in row]))
   if o.type=='MESH' and o.data.shape_keys:out.append((o.name,[(k.name,round(k.value,7)) for k in o.data.shape_keys.key_blocks]))
 return hashlib.sha256(json.dumps(out).encode()).hexdigest()
a=digest(0);digest(.8);b=digest(0);assert a==b,'Animation depends on previous frame'
(work/'determinism.json').write_text(json.dumps({'seek_0_08_0':a==b,'hash':a},indent=2),encoding='utf-8');print('DETERMINISM_OK')
