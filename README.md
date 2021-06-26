# Wine support tools

## buildwine

`buildwine.py` is a script to build Wine variants from source. It supports cross-compiler setups for
non-Intel architectures. Run with '--help' for usage.

By default, `buildwine` always builds shared WoW64 Wine (32-bit and 64-bit), except when cross-compiling (non-Intel).
Note the following defaults:

* building of tests is disabled, enable it by passing `--enable-tests` to the script
* integration of Wine-Mono is disabled when building from HEAD (no explicit `--version`), enable it by passing `--enable-mscoree` to the script

The script maintains a specific top-level directory structure to separate sources and build artifacts for various variants and host/target architectures.

Sources:

```console
custom-install-x86_64
custom-src
...
mainline-src
mainline-src-1.3.28
...
staging-patches
staging-patches-4.0
staging-src
staging-src-4.0
...
mainline-src-5.5
mainline-src-reference-gitmirror
```

Build directories:

```console
custom-build-i686
custom-build-x86_64
...
mainline-build-1.3.28-i686
mainline-build-1.3.28-x86_64
...
mainline-build-aarch64
mainline-build-arm
...
mainline-build-i686
mainline-build-x86_64
...
staging-build-4.0-i686
staging-build-4.0-x86_64
...
staging-build-i686
staging-build-x86_64
```

Install directories:

```console
custom-install-x86_64
...
mainline-install-1.3.28-x86_64
...
mainline-install-5.5-x86_64
mainline-install-aarch64
mainline-install-x86_64
...
staging-install-4.0-x86_64
staging-install-x86_64
```

Build Wine from current branch HEAD:

```shell
./buildwine.py
```

Build a specific Wine release:

```shell
./buildwine.py --version=5.5
```

Build Wine-Staging variant of a Wine release:

```shell
./buildwine.py --variant=staging --version=4.0
```

Build a custom variant, useful when doing Git bisect:

```shell
./buildwine.py --variant=custom
```

Build a range of Wine releases:

```shell
# build Wine 1.7.[51..53]
for i in 1.7.{51..53} ; do ./buildwine.py --version=$i --clean || break ; done

# build Wine 1.7.[40..49]
for i in `git -C mainline-src tag | sed -n 's/^wine-\(1.7.4[0-9]\)/\1/p' | \
    sort -V` ; do ./buildwine.py --version=$i --clean || break ; done
```

To better diagnose/debug build failures, pass `--jobs=1` to the script.

### Missing development packages

See [How to show missing development packages when building Wine from source][1].

### Cross-compiling using LLVM MinGw toolchain

See project home page [LLVM/Clang/LLD based mingw-w64 toolchain][2] for overview.

Main benefits:

* Wine builtin modules cross-compiled to PE format (no ELF hybrids as with GCC)
* symbol information generated in PDB format which can be used with many Windows debugging tools

Tarballs are available from [LLVM/Clang/LLD mingw-w64 release downloads][3].

Make sure it can be found in path by prepending the `bin` directory from the unpacked tarball to the `PATH` environment variable.

### Cross-compiling using Poky SDK cross-toolchain

For more information on how to create Poky SDK cross-toolchains see [meta-winedev: Yocto layer for Wine cross-development][4].

Wine currently doesn't build with Yocto/Poky SDK cross-toolchains due to following bugs:

* [Wine Bugzilla #46053][5]
* [Wine Bugzilla #46079][6]

Apply the patches.

After that, `configure` needs to be updated. Since cross-compiling is done, a host-build for running wine tools must exist.

```shell
./buildwine.py --clean --force-autoconf
```

Install Poky SDK toolchain(s):

```shell
./build-$MACHINE/tmp/deploy/sdk/*-toolchain-*.sh -d sdk-install -y
```

Register the cross-toolchain in the shell environment.

For 64-bit ARM:

```shell
source sdk-install/environment-setup-aarch64*
```

For 32-bit ARM:

```shell
source sdk-install/environment-setup-armv7*
```

Build Wine for target arch.

```shell
./buildwine.py --cross-compile-prefix=$CROSS_COMPILE --disable-mingw --clean --force-autoconf
```

---

**Links**

* [How to show missing development packages when building Wine from source][1]
* [LLVM/Clang/LLD based mingw-w64 toolchain][2]
* [LLVM/Clang/LLD mingw-w64 release downloads][3]
* [meta-winedev: Yocto layer for Wine cross-development][4]
* [Wine Bugzilla #46053][5]
* [Wine Bugzilla #46079][6]

[//]: # (invisible, for link references)
[1]: https://gist.github.com/rmi1974/f4393f5df3e34dc8cae35e2974fd9cda
[2]: https://github.com/mstorsjo/llvm-mingw
[3]: https://github.com/mstorsjo/llvm-mingw/releases
[4]: https://github.com/rmi1974/meta-winedev
[5]: https://bugs.winehq.org/show_bug.cgi?id=46053
[6]: https://bugs.winehq.org/show_bug.cgi?id=46079
