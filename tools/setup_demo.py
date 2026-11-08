"""Create a neutral procedural model and silent input. No API calls."""
from pathlib import Path
import importlib.util,sys,wave
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('ostro_cli',ROOT/'ostro.py')
cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
directory=ROOT/'.local/demo';directory.mkdir(parents=True,exist_ok=True)
with wave.open(str(directory/'silence.wav'),'wb') as audio:
    audio.setparams((1,2,48000,0,'NONE','not compressed'))
    audio.writeframes(b'\0'*(48000*2*2))
cli.blender('blender/build_demo_character.py')
print('Offline demo ready. No voice accounts or private media were used.')
