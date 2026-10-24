"""Compile first-party modules before freezing; no source-build fallback."""
import argparse
import ast
import importlib.util
import importlib.machinery
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
TARGETS = {
    'app': ('main', 'ChzzkAutoCategory', 'dist', False),
    'updater': ('updater_app', 'ChzzkAutoUpdater', 'dist-updater', True),
}
SOURCES = {name: ROOT / (name + '.py') for name in (
    'main', 'core', 'api', 'autodetect', 'bridge', 'chzzk_open', 'onboarding',
    'network_policy', 'theme', 'app_icons', 'modern_ui', 'normalization', 'automation', 'scheduling', 'diagnostics', 'release_versions',
    'storage', 'worker', 'process_detect', 'updater', 'version', 'ui_components', 'updater_app', 'steam_lookup', 'activity_stats',
)}


def imported_modules(path):
    names = set()
    tree = ast.parse(path.read_text(encoding='utf-8-sig'))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names.add(node.module)
            for alias in node.names:
                if alias.name == '*':
                    continue
                name = node.module + '.' + alias.name
                try:
                    if importlib.util.find_spec(name) is not None:
                        names.add(name)
                except (ImportError, ModuleNotFoundError, ValueError, AttributeError):
                    pass
    return names


def dependencies(entry):
    local, imports, pending = set(), set(), [entry]
    while pending:
        name = pending.pop()
        if name in local:
            continue
        local.add(name)
        found = imported_modules(SOURCES[name])
        imports.update(found)
        pending.extend(item for item in found if item in SOURCES and item not in local)
    return sorted(local), sorted(imports - local)


def staged_source(name, path, environ=None):
    """Inject build credentials only into ignored Cython staging, never tracked files."""
    source = path.read_text(encoding='utf-8-sig')
    environ = os.environ if environ is None else environ
    credentials = {
        'chzzk_open': {'APP_CLIENT_ID': 'CHZZK_CLIENT_ID', 'APP_CLIENT_SECRET': 'CHZZK_CLIENT_SECRET'},
        'storage': {'APP_STEAM_WEB_API_KEY': 'STEAM_WEB_API'},
    }
    values = {target: environ.get(variable, '').strip()
              for target, variable in credentials.get(name, {}).items()}
    if not values:
        return source
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    for node in reversed(tree.body):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name) and values.get(target.id):
            lines[node.lineno - 1:node.end_lineno] = [f'{target.id} = {values[target.id]!r}\n']
    return ''.join(lines)


def compile_modules(modules, stage, work):
    """Compile first-party modules using short relative source/object paths.

    Cython/setuptools preserve absolute source path components when build_dir and
    build_temp are combined. On Windows that can create /Fo paths longer than
    MAX_PATH (for example, the project path repeated two or three times).
    Running the native build from ``work`` and giving Cython only relative paths
    keeps generated C/object paths short and avoids MSVC C1083.
    """
    from Cython.Build import cythonize
    from Cython.Compiler import Options
    from setuptools import Distribution, Extension

    Options.docstrings = False
    sources_dir = work / 'sources'
    sources_dir.mkdir(parents=True, exist_ok=True)

    for name in modules:
        (sources_dir / (name + '.py')).write_text(staged_source(name, SOURCES[name]), encoding='utf-8')

    previous_cwd = Path.cwd()
    try:
        # IMPORTANT: keep source, generated C, and object paths relative to the
        # per-target work directory. This prevents Windows path duplication such
        # as build/.../objects/Release/C:/Users/.../build/.../generated/C:/Users/...
        os.chdir(work)

        extensions = []
        for name in modules:
            relative_source = Path('sources') / (name + '.py')
            extensions.append(Extension(
                name,
                [str(relative_source)],
                extra_compile_args=['/O2'] if sys.platform == 'win32' else ['-O2', '-g0'],
                extra_link_args=['/DEBUG:NONE'] if sys.platform == 'win32' else ['-s'],
            ))

        extensions = cythonize(
            extensions,
            quiet=True,
            build_dir='generated',
            compiler_directives={
                'language_level': 3,
                'binding': True,
                'annotation_typing': False,
                'embedsignature': False,
                'emit_code_comments': False,
                'linetrace': False,
                'profile': False,
            },
        )

        dist = Distribution({'name': 'chzzk-native', 'ext_modules': extensions})
        command = dist.get_command_obj('build_ext')
        command.build_lib = str(stage)
        command.build_temp = 'objects'
        command.force = True
        command.debug = False
        command.ensure_finalized()
        command.run()
    finally:
        os.chdir(previous_cwd)

    for name in modules:
        spec = importlib.machinery.PathFinder.find_spec(name, [str(stage)])
        if spec is None or not isinstance(spec.loader, importlib.machinery.ExtensionFileLoader):
            raise RuntimeError(f'Native module missing: {name}')


def verify_analysis(pure, binaries, datas, modules):
    protected = set(modules)
    exposed = protected.intersection(row[0] for row in pure)
    if exposed:
        raise RuntimeError('Protected modules found as Python bytecode: ' + ', '.join(sorted(exposed)))
    native = {Path(row[0]).name.split('.')[0] for row in binaries if row[2] == 'EXTENSION'}
    missing = protected - native
    if missing:
        raise RuntimeError('Missing native modules: ' + ', '.join(sorted(missing)))
    for row in datas:
        path = Path(row[0])
        if path.suffix.lower() in {'.py', '.pyc', '.pyo', '.pyx', '.c', '.cpp', '.pdb'} and path.stem.split('.')[0] in protected:
            raise RuntimeError('Protected source/debug file included: ' + str(path))


def write_spec(target, modules, hidden, stage, work):
    entry, name, _output, onefile = TARGETS[target]
    launcher = stage / 'launch.py'
    launcher.write_text(f'from {entry} import main\nraise SystemExit(main())\n', encoding='utf-8')
    # Copy only the build validator into staging; application .py files stay out.
    validator = stage / '_build_audit.py'
    tree = ast.parse(Path(__file__).read_text(encoding='utf-8'))
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'verify_analysis')
    validator.write_text('from pathlib import Path\n' + ast.unparse(function) + '\n', encoding='utf-8')
    spec = work / (name + '.spec')
    runtime_datas = [(str(ROOT / 'chzzk_auto_category.ico'), '.')] if target == 'app' else []
    from PyInstaller.utils.hooks import collect_data_files
    runtime_datas += collect_data_files('qtawesome')
    hidden = sorted(set(hidden) | {'qtawesome', 'qtpy', 'qtpy.QtCore', 'qtpy.QtGui', 'qtpy.QtWidgets'})
    code = f'''import sys
import json
import os
from pathlib import Path
sys.path.insert(0, {str(stage)!r})
from _build_audit import verify_analysis
a = Analysis([{str(launcher)!r}], pathex=[{str(stage)!r}],
    binaries=[], datas={runtime_datas!r}, hiddenimports={sorted(set(modules + hidden))!r},
    hookspath=[], hooksconfig={{}}, runtime_hooks=[], excludes=[], noarchive=False)
verify_analysis(a.pure, a.binaries, a.datas, {modules!r})
Path({str(work / 'native-audit.json')!r}).write_text(json.dumps(
    {{'target': {target!r}, 'native_modules': {modules!r}, 'python_source_fallback': False}},
    indent=2), encoding='utf-8')
pyz = PYZ(a.pure)
'''
    options = f"name={name!r}, debug=False, strip=False, upx=False, console=False, icon={str(ROOT / 'chzzk_auto_category.ico')!r}"
    if onefile:
        code += f'exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], {options})\n'
    else:
        code += f'exe = EXE(pyz, a.scripts, [], exclude_binaries=True, {options})\n'
        code += f'coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name={name!r})\n'
    spec.write_text(code, encoding='utf-8')
    return spec


def build(target, compile_only=False):
    if not compile_only and (sys.platform != 'win32' or struct.calcsize('P') != 8):
        raise RuntimeError('Release builds require 64-bit Windows Python and MSVC C++ Build Tools.')
    entry, name, output, onefile = TARGETS[target]
    work = ROOT / 'build' / 'protected' / target
    if work.exists():
        shutil.rmtree(work)
    stage = work / 'native'
    stage.mkdir(parents=True)
    modules, hidden = dependencies(entry)
    print('Compiling:', ', '.join(modules), flush=True)
    compile_modules(modules, stage, work)
    spec = write_spec(target, modules, hidden, stage, work)
    if compile_only:
        print('Native compile completed (no Windows EXE):', stage)
        return stage
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
        '--distpath', str(ROOT / output), '--workpath', str(work / 'freeze'), str(spec)],
        cwd=stage, check=True)
    result = ROOT / output / (name + '.exe') if onefile else ROOT / output / name / (name + '.exe')
    if not result.is_file():
        raise RuntimeError('Expected executable was not produced: ' + str(result))
    if target == 'updater':
        destination = ROOT / 'dist' / 'ChzzkAutoCategory'
        if not (destination / 'ChzzkAutoCategory.exe').is_file():
            raise RuntimeError('Build the app first with build.bat.')
        shutil.copy2(result, destination / result.name)
    print('Protected build complete:', result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('target', choices=TARGETS)
    parser.add_argument('--compile-only', action='store_true', help='Compile native modules without packaging (developer verification).')
    args = parser.parse_args()
    try:
        build(args.target, args.compile_only)
    except Exception as exc:
        print('Protected build FAILED:', exc, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
