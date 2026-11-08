"""Procedural robot with no reference to a real person's appearance."""
from pathlib import Path
import bpy
ROOT=Path(__file__).resolve().parents[1]
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
def material(name,color):
    value=bpy.data.materials.new(name);value.diffuse_color=(*color,1);return value
shell=material('Teal shell',(.035,.32,.30))
visor=material('Dark visor',(.015,.025,.04))
light=material('Indicator',(.7,.92,.85))
def cube(name,position,scale,mat,parent=None):
    bpy.ops.mesh.primitive_cube_add(size=1,location=position)
    obj=bpy.context.object;obj.name=name;obj.dimensions=scale
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    obj.data.materials.append(mat)
    modifier=obj.modifiers.new('Rounded edges','BEVEL');modifier.width=.08;modifier.segments=3
    if parent:
        world=obj.matrix_world.copy();obj.parent=parent;obj.matrix_world=world
    return obj
cube('Body',(0,0,1.1),(1,.65,1),shell)
for x,side in [(-.28,'L'),(.28,'R')]:
    cube('Foot_'+side,(x,-.03,.27),(.35,.8,.45),shell)
for x,side in [(-.68,'L'),(.68,'R')]:
    cube('Arm_'+side,(x,0,1.1),(.25,.35,.8),shell)
pivot=bpy.data.objects.new('Head_Pivot',None);bpy.context.collection.objects.link(pivot);pivot.location=(0,0,1.8)
cube('Robot_head',(0,0,2.1),(1.2,.85,.8),shell,pivot)
cube('Visor',(0,-.44,2.1),(.98,.08,.49),visor,pivot)
for x,side in [(-.27,'L'),(.27,'R')]:
    cube('Eye_'+side,(x,-.50,2.16),(.17,.045,.13),light,pivot)
cube('Mouth',(0,-.50,1.94),(.3,.045,.05),light,pivot)
target=ROOT/'assets/characters/demo-host.glb';target.parent.mkdir(parents=True,exist_ok=True)
bpy.ops.export_scene.gltf(filepath=str(target),export_format='GLB',export_apply=True)
print('DEMO_CHARACTER_READY')
