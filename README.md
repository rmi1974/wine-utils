# Wine support tools

## buildwine

`buildwine.py` is a script to build Wine variants from source. It supports cross-compiler setups for
non-Intel architectures. Run with '--help' for usage.

By default, `buildwine` always builds shared WoW64 Wine (32-bit and 64-bit), except when cross-compiling (non-Intel).
Note the following defaults:

* building of tests is disabled, enable it by passing `--enable-tests` to the script
* integration of Wine-Mono is disabled, enable it by passing `--enable-mscoree` to the script

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

To better diagnose/debug build failures, pass `--jobs=1` to the script.

### Cross-compiling

Wine currently doesn't build with Yocto/Poky SDK cross-toolchains due to following bugs:

* [Wine Bugzilla #46053]
* [Wine Bugzilla #46079]

Apply the patches.

After that, `configure` needs to be updated due to [Wine Bugzilla #46079].
Since cross-compiling is done, a host-build for running wine tools must exist.

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
./buildwine.py --cross-compile-prefix=$CROSS_COMPILE --disable-mingw --clean
```

---

Links

* [Wine Bugzilla #46053](https://bugs.winehq.org/show_bug.cgi?id=46053)
* [Wine Bugzilla #46079](https://bugs.winehq.org/show_bug.cgi?id=46079)

[//]: # (invisible, for link references)
[Wine Bugzilla #46053]: https://bugs.winehq.org/show_bug.cgi?id=46053
[Wine Bugzilla #46079]: https://bugs.winehq.org/show_bug.cgi?id=46079
