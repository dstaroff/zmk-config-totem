import subprocess
from os import makedirs
from os.path import curdir, exists, isdir, realpath
from pathlib import Path
from shutil import which
from sys import exit

from click import echo, style
from click.termui import progressbar
from git import Repo


def resolve_container_engine() -> str:
    container_engine: str = ''

    if which('docker') is not None:
        container_engine = 'docker'
    if which('podman') is not None:
        container_engine = 'podman'
    if container_engine:
        echo(f'✅ Found {style(container_engine, bold=True)} as container engine')
        return container_engine

    echo(
        f'❌ This script requires either {style("podman", bold=True)} or {style("docker", bold=True)} to be installed. Please install either, then retry',
        err=True,
    )
    exit(1)


def ensure_zmk_repo(base_dir: Path) -> None:
    zmk_dir: Path = base_dir / 'zmk'

    if exists(zmk_dir) and isdir(zmk_dir):
        echo(f'✅ ZMK git repo directory exists')
        return

    def _pb_update(
        pb,
        op_code: int,
        cur_count: str | float,
        max_count: str | float | None,
        message: str,
    ) -> None:
        if max_count is not None:
            bar.length = int(max_count)

        delta: int = int(cur_count) - pb.pos
        pb.update(delta)

    with progressbar(
        label='⏳ Cloning ZMK git repo:',
        length=100,
        show_percent=True,
    ) as bar:
        Repo.clone_from(
            url='https://github.com/zmkfirmware/zmk.git',
            to_path=zmk_dir,
            progress=lambda op_code, cur_count, max_count, message: _pb_update(
                bar, op_code, cur_count, max_count, message
            ),
        )

    echo(f'✅ Cloned ZMK git repo')


def ensure_build_dir(base_dir: Path) -> None:
    build_dir: Path = base_dir / 'build'

    if exists(build_dir) and isdir(build_dir):
        echo(f'✅ Build directory exists')
        return

    makedirs(build_dir, exist_ok=True)

    echo(f'✅ Created build directory')


def recreate_volume(base_dir: Path, engine: str) -> str:
    volume_name: str = 'zmk-config'

    with progressbar(
        label='⏳ Recreating container volume:',
        length=2,
        show_percent=True,
    ) as bar:
        subprocess.run(
            [engine, 'volume', 'rm', '--force', volume_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
        bar.update(1)

        subprocess.run(
            [
                engine,
                'volume',
                'create',
                '--driver',
                'local',
                '-o',
                'o=bind',
                '-o',
                'type=none',
                '-o',
                f'device={base_dir / "config"}',
                volume_name,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
        bar.update(1)

    echo(f'✅ Recreated container volume: {style(volume_name, bold=True)}')

    return volume_name


def build_image(base_dir: Path, engine: str) -> str:
    image_tag: str = 'zmk-west'

    with progressbar(
        label='⏳ Building container image:',
        length=1,
        show_percent=True,
    ) as bar:
        subprocess.run(
            [
                engine,
                'build',
                '-t',
                image_tag,
                '-f',
                f'{base_dir / "zmk" / ".devcontainer" / "Dockerfile"}',
                f'{base_dir / "zmk" / ".devcontainer"}',
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
        bar.update(1)

    echo(f'✅ Built container image: {style(image_tag, bold=True)}')

    return image_tag


def print_help() -> None:
    echo(
        f'ℹ️ {style("Run following commands if running this script for the first time", fg="blue")}:'
    )
    echo(style('west init -l app/ && west update && west zephyr-export', bold=True))

    echo(
        f'ℹ️ {style("To build the firmware for both halves of the keyboard", fg="blue")}:'
    )
    for side in ['left', 'right']:
        echo(
            style(
                f'west build -s app -d /workspaces/build/{side} -p -b \'seeeduino_xiao_ble\' -- -DZMK_CONFIG=/workspaces/zmk-config -DSHIELD=totem_{side}',
                bold=True,
            )
        )

    echo(
        f'ℹ️ {style("Generated files can be found in", fg="blue")} {style("build/<left|right>/zephyr/zmk.uf2", bold=True)}'
    )


def run_container(
    base_dir: Path, engine: str, image_tag: str, volume_name: str
) -> None:
    subprocess.run(
        [
            engine,
            'run',
            '-it',
            '--rm',
            '--security-opt',
            'label=disable',
            '--workdir',
            '/workspaces/zmk',
            '-v',
            f'{base_dir / "zmk"}:/workspaces/zmk',
            '-v',
            f'{volume_name}:/workspaces/zmk-config',
            '-v',
            f'{base_dir / "build"}:/workspaces/build',
            '-p',
            '3000:3000',
            image_tag,
            '/bin/bash',
        ]
    )


def main():
    container_engine: str = resolve_container_engine()

    config_dir: Path = Path(realpath(curdir))
    ensure_zmk_repo(config_dir)
    ensure_build_dir(config_dir)

    volume_name: str = recreate_volume(config_dir, container_engine)
    image_tag: str = build_image(config_dir, container_engine)

    print_help()
    run_container(config_dir, container_engine, image_tag, volume_name)


if __name__ == '__main__':
    main()
