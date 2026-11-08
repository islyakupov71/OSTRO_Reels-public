"""Manifest -> editable Blender scene; deterministic animation is embedded as text."""
from pathlib import Path
import bpy,sys,json,math,textwrap,random
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[1]
args=sys.argv[sys.argv.index('--')+1:];epfile,timelinefile,dest=map(Path,args[:3]);smoke='--smoke' in args
ep=json.loads(epfile.read_text(encoding='utf-8-sig'));timeline=json.loads(timelinefile.read_text(encoding='utf-8'));registry=json.loads((ROOT/'registry/characters.json').read_text(encoding='utf-8'));work=dest.parent
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
scene=bpy.context.scene;scene.render.engine='BLENDER_EEVEE_NEXT'
fps=10 if smoke else ep.get('fps',30);duration=min(1.2,timeline['duration']) if smoke else timeline['duration']
scene.render.resolution_x=216 if smoke else ep.get('width',1080);scene.render.resolution_y=384 if smoke else ep.get('height',1920);scene.render.resolution_percentage=100
scene.render.fps=fps;scene.frame_start=1;scene.frame_end=math.ceil(duration*fps);scene.render.image_settings.file_format='PNG';scene.render.filepath=str(work/'frames/######')
(work/'frames').mkdir(exist_ok=True)
scene.world.color=(.2,.2,.2);scene.world.use_nodes=True;scene.world.node_tree.nodes['Background'].inputs[0].default_value=(.35,.35,.35,1);scene.world.node_tree.nodes['Background'].inputs[1].default_value=.35
scene.view_settings.view_transform='AgX'
def color(h):
 a=[int(h.lstrip('#')[i:i+2],16)/255 for i in (0,2,4)];return tuple(v/12.92 if v<.04045 else ((v+.055)/1.055)**2.4 for v in a)
def mat(name,h,rough=.45,emission=False):
 m=bpy.data.materials.new(name);m.diffuse_color=(*color(h),1);m.use_nodes=True;n=m.node_tree.nodes.get('Principled BSDF');n.inputs['Base Color'].default_value=(*color(h),1);n.inputs['Roughness'].default_value=rough
 if emission:n.inputs['Emission Color'].default_value=(*color(h),1);n.inputs['Emission Strength'].default_value=1
 return m
wine=mat('OSTRO wine','#390517');white=mat('OSTRO ivory','#f4f1ed');dark=mat('Stage charcoal','#20242a');gold=mat('OSTRO gold','#a2845e');green=mat('OSTRO green','#162f2c')
def box(name,loc,dims,material,parent=None):
 bpy.ops.mesh.primitive_cube_add(size=1,location=loc);o=bpy.context.object;o.name=name;o.dimensions=dims;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);o.data.materials.append(material)
 bevel=o.modifiers.new('Soft manufactured edge','BEVEL');bevel.width=.05;bevel.segments=3
 if parent:o.parent=parent
 return o
def group(name):
 o=bpy.data.objects.new(name,None);scene.collection.objects.link(o);return o
stages={}
for idx,s in enumerate(ep['scenes']):
 g=group('Set_'+str(idx));stages[idx]=g
 box('Floor_'+str(idx),(0,0,-.12),(40,40,.2),white,g)
 box('Backdrop_'+str(idx),(0,4,2.8),(14,.25,6),wine,g)
 for x in [-5,-2.5,0,2.5,5]:box('Wall panel', (x,3.82,2.8),(.035,.035,5.4),gold,g)
 if s['template'] in ['conference','arena']:
  box('Stage riser',(0,1,.1),(7,3,.3),dark,g);box('Screen',(0,3.6,2.6),(6,.12,3.1),green,g)
  for x in [-3.5,3.5]:
   box('Lighting truss',(x,2.5,2.3),(.14,.14,4.4),dark,g)
   for z in [2.3,2.8,3.3,3.8]:box('Lamp',(x,2.3,z),(.25,.3,.22),gold,g)
 if s['template']=='arena':
  for j in range(3):
   for x in range(-5,6):box('Audience seat',(x*.65,4.7+j*.8,.35+j*.3),(.45,.5,.3),dark,g)
actors={}
for a in ep['actors']:
 before=set(bpy.data.objects);bpy.ops.import_scene.gltf(filepath=str(ROOT/registry[a['character']]['model']));new=set(bpy.data.objects)-before
 wrapper=group('Actor_'+a['id'])
 for o in new:
  if o.parent not in new:m=o.matrix_world.copy();o.parent=wrapper;o.matrix_world=m
 bpy.context.view_layer.update()
 points=[o.matrix_world @ Vector(c) for o in new if o.type=='MESH' for c in o.bound_box];height=max(v.z for v in points)-min(v.z for v in points);wrapper.scale=(3.1/height,)*3
 wrapper.location=a.get('position',[0,0,0]);actors[a['id']]=wrapper
for name,loc,power,size in [('Key',(-5,-7,9),1300,6),('Fill',(6,-2,6),750,5),('Rim',(0,5,8),1500,4)]:
 l=bpy.data.lights.new(name,'AREA');l.energy=power;l.shape='DISK';l.size=size;o=bpy.data.objects.new(name,l);scene.collection.objects.link(o);o.location=loc;o.rotation_euler=(Vector((0,0,1.7))-o.location).to_track_quat('-Z','Y').to_euler()
d=bpy.data.cameras.new('Camera');cam=bpy.data.objects.new('Camera',d);scene.collection.objects.link(cam);scene.camera=cam;d.type='ORTHO';d.ortho_scale=ep.get('camera',{}).get('scale',7.0);cam.location=ep.get('camera',{}).get('position',[3,-13,6]);cam.rotation_euler=(Vector(ep.get('camera',{}).get('look_at',[0,0,1.7]))-cam.location).to_track_quat('-Z','Y').to_euler()
# Text is camera-aligned. It is never mirrored by scene or actor rotation.
frame=d.view_frame(scene=scene);fw=max(v.x for v in frame)-min(v.x for v in frame);fh=max(v.y for v in frame)-min(v.y for v in frame)
fontpath=ROOT/'assets/brand/Inter-Bold.ttf';font=bpy.data.fonts.load(str(fontpath)) if fontpath.exists() else bpy.data.fonts.get('Bfont')
textmat=mat('Overlay white','#ffffff',emission=True)
def text(name,body,x,y,size):
 cv=bpy.data.curves.new(name,'FONT');cv.body=body;cv.size=size;cv.font=font;cv.align_x='CENTER';cv.align_y='CENTER';cv.space_line=1.12;o=bpy.data.objects.new(name,cv);scene.collection.objects.link(o);o.parent=cam;o.location=(x,y,-5);cv.materials.append(textmat);return o
text('Title','\n'.join(textwrap.wrap(ep['title'],22)),0,fh*.34,fw*.065)
captionmat=mat('Caption wine','#390517',emission=True)
bpy.ops.mesh.primitive_plane_add(size=1);card=bpy.context.object;card.name='Caption_card';card.parent=cam;card.location=(0,-fh*.29,-5.08);card.scale=(fw*.92,fh*.15,1);card.data.materials.append(captionmat)
caption=text('Caption','',0,-fh*.29,fw*.049)
logo=ROOT/'assets/brand/ostro-logo-white.png'
if logo.exists():
 image=bpy.data.images.load(str(logo));image.pack();m=bpy.data.materials.new('Official OSTRO logo');m.use_nodes=True;n=m.node_tree.nodes;n.clear();tex=n.new('ShaderNodeTexImage');tex.image=image;emit=n.new('ShaderNodeEmission');trans=n.new('ShaderNodeBsdfTransparent');mix=n.new('ShaderNodeMixShader');out=n.new('ShaderNodeOutputMaterial');links=m.node_tree.links;links.new(tex.outputs['Color'],emit.inputs['Color']);links.new(tex.outputs['Alpha'],mix.inputs[0]);links.new(trans.outputs[0],mix.inputs[1]);links.new(emit.outputs[0],mix.inputs[2]);links.new(mix.outputs[0],out.inputs[0])
 bpy.ops.mesh.primitive_plane_add(size=1);o=bpy.context.object;o.name='Official_logo';o.parent=cam;o.location=(0,fh*.445,-5.1);o.scale=(fw*.24,fw*.24*image.size[1]/image.size[0],1);o.data.materials.append(m)
animation={'episode':ep,'timeline':timeline,'fps':fps,'scene_count':len(ep['scenes'])}
scene['ostro_animation']=json.dumps(animation,ensure_ascii=False);scene['ostro_root']=str(ROOT);scene['ostro_work']=str(work)
code=(ROOT/'blender/load_animation.py').read_text(encoding='utf-8');t=bpy.data.texts.new('OSTRO_Animation.py');t.write(code)
exec(compile(code,str(ROOT/'blender/load_animation.py'),'exec'),{'__name__':'ostro_build'})
scene.frame_set(1);bpy.ops.wm.save_as_mainfile(filepath=str(dest))
(work/'render.json').write_text(json.dumps({'fps':fps,'frames':scene.frame_end,'width':scene.render.resolution_x,'height':scene.render.resolution_y,'engine':scene.render.engine},indent=2),encoding='utf-8')
print('SCENE_READY',str(dest))
