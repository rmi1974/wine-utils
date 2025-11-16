# Wine Build Tools

This project provides a modern, containerized environment for building and running a wide range of Wine releases in a **Fedora 42-based Docker environment**.
Unlike many other Wine build projects, this one focuses on rebuilding as many old Wine releases as possible using the same reproducible setup.
It avoids out-of-tree patches and instead applies existing commits to fix or work around build issues with legacy Wine releases.

All builds and runs are performed inside a Docker container.

---

## Quickstart (TL;DR)

```bash
# source env script to use helpers
source ./wine_docker.env

# build the docker image
wine_docker_image_build

# enter the docker container (for building/running Wine)
wine_docker_run

# register llvm-mingw toolchain (see later)
export PATH="$PWD/llvm-mingw-20251104-ucrt-ubuntu-22.04-x86_64/bin:$PATH"

# build a Wine release inside the container
./buildwine.py --version=10.0 --clean

# register Wine bindir path for particular build
export PATH="$PWD/mainline-install-10.0-x86_64/bin:$PATH"

# install/run Wine/app
wineboot
```

## Docker setup using helper aliases
### Source the environment helpers

The file `wine_docker.env` defines shell aliases for building and running the Docker environment.
It must be **sourced**, not executed:

```bash
source ./wine_docker.env
```

This registers two aliases:

`wine_docker_image_build` - builds the Docker image `wine-build-env` using your host user and group IDs
`wine_docker_run` - creates a Docker container from `wine-build-env` image and runs it (home directory and the current working directory are mapped)

### Build the Docker image

```bash
wine_docker_image_build
```

This creates the `wine-build-env` Docker image and configures user mappings so files created inside the container are owned by your host user.

### Run the Docker container

```bash
wine_docker_run
```

This starts an interactive container session with:

* DISPLAY forwarding via X11 for GUI apps
* PulseAudio mounting for sound.
* home directory and current directory mounted for seamless development.

The alias internally runs `xhost +local:docker` to permit local X11 connections.

## Building Wine inside the container

It is recommended to use `buildwine.py` inside the Docker container.
If you run `buildwine.py` without the provided Docker-based build environment, you are on your own.

## Cross-compiling with LLVM MinGW

This is the preferred build mode for this Wine builder project (supported since Wine 6.0).
See project home page [LLVM/Clang/LLD based mingw-w64 toolchain][2] for overview.

### Download and install

Download and unpack `llvm-mingw` release from [LLVM/Clang/LLD mingw-w64 release downloads][3].

```bash
wget https://github.com/mstorsjo/llvm-mingw/releases/download/20251104/llvm-mingw-20251104-ucrt-ubuntu-22.04-x86_64.tar.xz

tar axf llvm-mingw-20251104-ucrt-ubuntu-22.04-x86_64.tar.xz
```

### Register toolchain

Inside the container, prepend the bin directory to `PATH`:

```bash
export PATH=$PWD/llvm-mingw-20251104-ucrt-ubuntu-22.04-x86_64/bin:$PATH
```

```bash
clang -v

clang version 21.1.5 (https://github.com/llvm/llvm-project.git 8e2cd28cd4ba46613a46467b0c91b1cabead26cd)
Target: x86_64-unknown-linux-gnu
Thread model: posix
InstalledDir: /home/rmi1974/projects/wine/llvm-mingw-20251104-ucrt-ubuntu-22.04-x86_64/bin
Found candidate GCC installation: /usr/lib/gcc/x86_64-redhat-linux/15
Selected GCC installation: /usr/lib/gcc/x86_64-redhat-linux/15
Candidate multilib: .;@m64
Candidate multilib: 32;@m32
Selected multilib: .;@m64
```

Now run `buildwine.py` as usual. The `llvm-mingw` toolchain will be automatically detected.

## Common build commands

Build Wine from the current branch HEAD:

```bash
./buildwine.py
```

Build a specific Wine release:

```bash
./buildwine.py --version=8.5
```

Build Wine-Staging variant of a release:

```bash
./buildwine.py --variant=staging --version=9.15
```

Build a custom variant (e.g., for Git bisect):

```bash
./buildwine.py --variant=custom
```

## Behavior and useful buildwine.py flags

- shared WoW64 build by default: 32-bit + 64-bit builds are produced
- tests are disabled by default: enable with `--enable-tests`
- Wine-Mono is disabled on non-release builds (no exact Wine release tag on git checkout): enable with `--enable-mscoree`
- debugging: to diagnose build failures deterministically, use `--jobs=1`

### Building ranges of Wine releases

```bash
# Build Wine 9.[0..22]
for i in 9.{0..22}; do ./buildwine.py --version="$i" --clean || break; done

# Build Wine 1.7.[40..49] using available source tags
for i in $(git -C mainline-src tag | sed -n 's/^wine-\(1\.7\.4[0-9]\)/\1/p' | sort -V); do
  ./buildwine.py --version="$i" --clean || break
done
```

## Running Wine inside the container

After building, applications can be run from inside the same container.
The build script will output the exact Wine install path for each build.
Make note of it. You have to set it explicitly to use a particular Wine build.

```bash
# Wine 10.0 mainline build
export PATH=<basepath>/wine/mainline-install-10.0-x86_64/bin/:$PATH
```

```bash
# Example: run Wine's notepad
wine notepad.exe

# Run a Windows program from your mounted home directory
wine ~/Downloads/SomeSetup.exe
```

If you are doing regression testing be careful with automatic downgrades and upgrades of existing WINEPREFIXes ("prefix recycling").
It may work for a consecutive runs of different Wine releases but may get broken beyond repair.
Restart with fresh `WINEPREFIX` in such cases. Reuse prefixes at own risk.

## Directory layout

The script maintains a separation of sources, build and install artifacts across variants and architectures:

Sources: mainline-src-*, staging-src-*, custom-src, plus git reference mirrors
Builds: mainline-build-*, staging-build-*, custom-build-* for each arch and version
Installs: mainline-install-*, staging-install-*, custom-install-*

---

**Links**

* [How to show missing development packages when building Wine from source][1]
* [LLVM/Clang/LLD based mingw-w64 toolchain][2]
* [LLVM/Clang/LLD mingw-w64 release downloads][3]

[//]: # (invisible, for link references)
[1]: https://gist.github.com/rmi1974/f4393f5df3e34dc8cae35e2974fd9cda
[2]: https://github.com/mstorsjo/llvm-mingw
[3]: https://github.com/mstorsjo/llvm-mingw/releases
