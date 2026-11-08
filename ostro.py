"""Local Blender video pipeline with an anonymous offline demonstration."""
from pathlib import Path
import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'src'))
from ostro_pipeline.audio import prepare_audio, probe_key, inspect_sample, create_clone, store_key, read_voice_registry

def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

def paths():
    config = load(ROOT / '.local/paths.json') if (ROOT / '.local/paths.json').exists() else {}
    for tool, variable in [('blender', 'BLENDER_EXE'), ('ffmpeg', 'FFMPEG_EXE')]:
        config[tool] = os.environ.get(variable) or config.get(tool) or shutil.which(tool)
    return config

def run(command):
    subprocess.run([str(part) for part in command], check=True, cwd=ROOT)

def blender(script, *arguments, scene=None):
    executable = paths().get('blender')
    if not executable:
        raise RuntimeError('Set BLENDER_EXE or install Blender on PATH.')
    command = [executable, '--background']
    command += [scene] if scene else ['--factory-startup']
    command += ['--python-exit-code', '1', '--python', ROOT / script]
    if arguments:
        command += ['--', *arguments]
    run(command)

def episode_path(value):
    candidate = Path(value)
    return candidate.resolve() if candidate.is_file() else ROOT / 'episodes' / value / 'episode.json'

def validate(episode):
    if episode.get('version') != 1:
        raise ValueError('Unsupported episode version')
    if not episode.get('id') or not episode.get('actors') or not episode.get('scenes'):
        raise ValueError('Episode needs an ID, actors and scenes')
    if min(episode.get('fps', 30), episode.get('width', 1080), episode.get('height', 1920)) <= 0:
        raise ValueError('Render dimensions and FPS must be positive')
    actors = {actor['id'] for actor in episode['actors']}
    if len(actors) != len(episode['actors']):
        raise ValueError('Duplicate actor IDs')
    registry = load(ROOT / 'registry/characters.json')
    for actor in episode['actors']:
        character = registry[actor['character']]
        if not (ROOT / character['model']).is_file():
            raise ValueError('Missing model; run python tools/setup_demo.py for the example')
    lines = episode.get('lines', [])
    line_ids = {line['id'] for line in lines}
    if len(line_ids) != len(lines):
        raise ValueError('Duplicate line IDs')
    for line in lines:
        if line['speaker'] not in actors or not line.get('text', '').strip():
            raise ValueError('Unknown speaker or empty line')
    for scene in episode['scenes']:
        if scene['template'] not in ('studio', 'conference', 'arena'):
            raise ValueError('Unsupported scene template')
        if scene['anchor'] != 'opening' and scene['anchor'] not in line_ids:
            raise ValueError('Unknown scene anchor')
    return episode

def pipeline(file, stage, smoke=False):
    episode = validate(load(file))
    work = ROOT / 'build' / episode['id']
    if stage == 'plan':
        print(json.dumps({'episode': episode['id'], 'stages': ['audio', 'scene', 'preview', 'render', 'mux'],
                          'tts_requests': sum(not line.get('cached_audio') for line in episode.get('lines', [])),
                          'smoke': smoke}, indent=2))
        return
    work.mkdir(parents=True, exist_ok=True)
    journal = {'episode': episode['id'], 'stages': {}}
    started = time.monotonic()
    def step(name, action):
        tick = time.monotonic()
        action()
        journal['stages'][name] = round(time.monotonic() - tick, 3)
        save(work / 'run.json', journal)
    try:
        if stage in ('audio', 'run'):
            step('audio', lambda: prepare_audio(ROOT, episode, work, paths()['ffmpeg']))
        if stage in ('scene', 'run'):
            args = [file, work / 'timeline.json', work / 'scene.blend']
            if smoke:
                args.append('--smoke')
            step('scene', lambda: blender('blender/build_scene.py', *args))
        if stage in ('preview', 'run'):
            step('preview', lambda: blender('blender/load_animation.py', '--contact', scene=work / 'scene.blend'))
        if stage in ('render', 'run'):
            def render():
                run([paths()['blender'], '--background', work / 'scene.blend', '--python-exit-code', '1',
                     '--python', ROOT / 'blender/load_animation.py', '--render-anim'])
            step('render', render)
        if stage in ('mux', 'run'):
            def mux():
                config = load(work / 'render.json')
                output = work / (episode['id'] + '.mp4')
                run([paths()['ffmpeg'], '-hide_banner', '-loglevel', 'error', '-y', '-framerate', config['fps'],
                     '-i', work / 'frames/%06d.png', '-i', work / 'mix.wav', '-map', '0:v:0', '-map', '1:a:0',
                     '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p',
                     '-c:a', 'aac', '-b:a', '192k', '-t', config['frames'] / config['fps'],
                     '-movflags', '+faststart', output])
                print('VIDEO', output)
            step('mux', mux)
        journal['status'] = 'ok'
    except Exception:
        journal['status'] = 'failed'
        raise
    finally:
        journal['elapsed_seconds'] = round(time.monotonic() - started, 3)
        save(work / 'run.json', journal)

def doctor():
    config = paths()
    result = {'tools': {tool: bool(value and Path(value).is_file()) for tool, value in config.items()},
              'characters': len(load(ROOT / 'registry/characters.json')),
              'configured_voices': sum(bool(voice.get('voice_id')) for voice in read_voice_registry(ROOT).values())}
    print(json.dumps(result, indent=2))
    return 0 if all(result['tools'].get(tool) for tool in ('blender', 'ffmpeg')) else 1

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('doctor')
    episode = commands.add_parser('episode')
    episode.add_argument('stage', choices=['plan', 'audio', 'scene', 'preview', 'render', 'mux', 'run'])
    episode.add_argument('episode')
    episode.add_argument('--smoke', action='store_true')
    character = commands.add_parser('characters')
    character.add_argument('action', choices=['rebuild'])
    character.add_argument('person', choices=['demo-host'])
    voices = commands.add_parser('voices')
    voices.add_argument('action', choices=['list', 'probe', 'inspect', 'clone', 'store-key'])
    voices.add_argument('--person')
    voices.add_argument('--sample')
    voices.add_argument('--name')
    voices.add_argument('--confirm-owner-consent', action='store_true')
    voices.add_argument('--consent-reference')
    args = parser.parse_args()
    if args.command == 'doctor':
        raise SystemExit(doctor())
    if args.command == 'episode':
        pipeline(episode_path(args.episode), args.stage, args.smoke)
    elif args.command == 'characters':
        blender('blender/build_demo_character.py')
    elif args.command == 'voices':
        if args.action == 'list':
            print(json.dumps(read_voice_registry(ROOT), ensure_ascii=False, indent=2))
        elif args.action == 'store-key':
            store_key(ROOT, sys.stdin.read().strip())
            print('Key stored locally using Windows DPAPI.')
        elif args.action == 'probe':
            print(json.dumps(probe_key(ROOT), ensure_ascii=False, indent=2))
        elif args.action == 'inspect':
            if not args.sample:
                parser.error('--sample is required')
            print(json.dumps(inspect_sample(Path(args.sample), paths()['ffmpeg']), indent=2))
        elif args.action == 'clone':
            if not args.person:
                parser.error('--person is required')
            print(json.dumps(create_clone(ROOT, args.person, paths()['ffmpeg'], args.confirm_owner_consent,
                                          args.consent_reference, args.name), ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
