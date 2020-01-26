#!/usr/bin/env python3

# Script to build Wine variants from source, including cross-compile for
# non-Intel architectures. Run with '--help' for usage.

import argparse
import os
import subprocess
import sys
import shutil
import packaging

# Wine project upstream repos
WINE_MAINLINE_GIT_URI = "git://source.winehq.org/git/wine.git"
WINE_STAGING_GIT_URI = "https://github.com/wine-staging/wine-staging.git"

def parse_version(version):
    """Use parse from packaging.version or LooseVersion from distutils.version"""
    global parse_version, Version
    try:
        from packaging.version import Version
        from packaging.version import parse as parse_version
    except ImportError:
        from distutils.version import LooseVersion as parse_version
    return parse_version(version)

def run_command(command, cwd=None, env=None):
    """Run the specified command in a subprocess shell.

    Parameters:
        command (str): Linux shell command.
        cwd (str): Working directory for the command.
        env (str): Custom shell environment for the intermediate shell.
    Returns:
        if executed process exit code is non-zero, raises a CalledProcessError.

    """
    print("[*] Running following command")
    print("'{0}' (cwd='{1}')".format( command, cwd))

    # Some commands involve 'tee' (pipelines) hence prefix with 'pipefail' to capture failure as well
    subprocess.run("set -o pipefail && {0}".format(command), cwd=cwd, env=env, check=True, shell=True,
                    stderr=sys.stderr, stdout=sys.stdout, encoding="utf8")

def git_cherry_pick(source_path, commit_id):
    """ cherry-pick a Git commit into current branch

    Parameters:
        source_path (str): Path to source repository.
        commit_id (str): Commit sha1 of cherry-pick.

    Returns:
        none.

    """

    # FIXME: only works if the commit has no been cherry-picked
    pipe = subprocess.Popen("git branch --contains {0} 2> /dev/null".format(commit_id),
                            cwd=source_path, shell=True, stdout=subprocess.PIPE,
                            encoding="utf8").stdout
    branches = pipe.readline().rstrip(os.linesep)
    pipe.close()

    if branches:
        return

    # FIXME: will generate new sha1
    run_command("git cherry-pick --keep-redundant-commits --strategy=recursive -X theirs -x {0}".format(commit_id), source_path)

def patch_apply(source_path, commit_id, exclude_pattern=""):
    """ Apply a patch from Git commit into current branch using 'patch' tool.
        The heuristics/fuzziness produces much better results with old Wine versions
        than any git merge strategy. Optionally exclude parts of the patch.

    Parameters:
        source_path (str): Path to source repository.
        commit_id (str): Commit sha1 to generate patch from
        exclude_pattern (str): Pattern for 'filterdiff' to exclude files

    Returns:
        none.

    """

    # extract the patch from Git checkout
    pipe = subprocess.Popen("git format-patch -1 {0} 2> /dev/null".format(commit_id),
                            cwd=source_path, shell=True, stdout=subprocess.PIPE,
                            encoding="utf8").stdout
    patchfile = pipe.readline().rstrip(os.linesep)
    pipe.close()

    if not os.path.exists(os.path.normpath(os.path.join(source_path, patchfile))):
        sys.exit("Patch extraction of '{0}' failed, aborting!".format(commit_id))

    # Try to apply the patch.
    run_command("filterdiff -p1 -x '{0}' < {1} | patch -p1".format(exclude_pattern, patchfile), source_path)

    # NOTE: keep .patch files in place for documentation

def main():

    # Common workspace root path to Wine artifact directories: sources, build, install etc.
    # NOTE: assumes the scripts directory is mapped one level below workspace root path!
    wine_workspace_path = os.path.abspath(os.path.join(os.path.dirname(
                                os.path.realpath(__file__)), os.pardir))

    my_parser = argparse.ArgumentParser(description="Build Wine variants from Wine source tree", allow_abbrev=False)
    # source path
    my_parser.add_argument("--source-path",
                           type=str,
                           default="{0}/mainline-src".format(wine_workspace_path),
                           help="specify the Wine source path (git checkout)")
    # install prefix
    my_parser.add_argument("--install-prefix",
                           type=str,
                           default="{0}/mainline-install".format(wine_workspace_path),
                           help="specify the Wine install path")
    # default Wine variant: mainline
    my_parser.add_argument("--variant",
                           type=str,
                           default="mainline",
                           choices=["mainline", "staging", "custom"],
                           help="specify the Wine variant, possible values: one of [mainline, staging, custom]")
    # default Wine version to build: git HEAD
    my_parser.add_argument("--version",
                           type=str,
                           default="",
                           help="specify the Wine version, should be a valid Wine tag: <major>.<minor>")
    # default number of build jobs
    my_parser.add_argument("--jobs",
                           type=int,
                           default=os.cpu_count(),
                           help="specify the default number of CPU cores used for building Wine")
    # default cross-toolchain: none -> native host toolchain
    my_parser.add_argument("--cross-compile-prefix",
                           type=str,
                           default="",
                           help="specify the cross-toolchain prefix")
    my_parser.add_argument("--disable-mingw",
                           action="store_true",
                           help="do not use the MinGW cross-compiler for building Wine")
    my_parser.add_argument("--enable-mscoree",
                           action="store_true",
                           help="enable Wine-Mono")
    my_parser.add_argument("--enable-tests",
                           action="store_true",
                           help="enable building of Wine tests")
    my_parser.add_argument("--enable-nopic",
                           action="store_true",
                           help="disable building of Wine with position-independent code (PIC), Wine 4.8+ default")
    my_parser.add_argument("--force-autoconf",
                           action="store_true",
                           help="run autoreconf and tools/make_requests all the time")
    my_parser.add_argument("--clean",
                           action="store_true",
                           help="remove build and install directories")
    my_parser.add_argument("--no-configure",
                           action="store_true",
                           help="do not run configure")
    my_parser.add_argument("--no-reset-source",
                           action="store_true",
                           help="do not reset Git source tree to version "
                                "if specified (custom build with patches)")

    args = my_parser.parse_args()

    ##################################################################
    # version/release handling part #1
    dash_version = ""
    wine_version = parse_version(args.version)
    if isinstance(wine_version, Version):
        # prepend dash to encode it into build/install folder names
        dash_version = "-{0}".format(args.version)

    ##################################################################
    # set up various paths for variants: mainline, staging and custom

    # source paths
    wine_mainline_source_path = "{0}/mainline-src{1}".format(wine_workspace_path, dash_version)
    wine_variant_source_path = "{0}/{1}-src{2}".format(wine_workspace_path, args.variant, dash_version)
    wine_staging_patches_path = "{0}/staging-patches{1}".format(wine_workspace_path, dash_version)

    ##################################################################
    # version/release handling part #2
    if not args.version:
        # no version given but we need one to apply fixups on custom builds
        pipe = subprocess.Popen("git describe --abbrev=0 2> /dev/null | sed 's/wine-//'",
                                cwd=wine_variant_source_path, shell=True, stdout=subprocess.PIPE, encoding="utf8").stdout
        wine_version = parse_version(pipe.readline().rstrip(os.linesep))
        pipe.close()

    if not isinstance(wine_version, Version):
        # unknown version schemes not supported
        sys.exit("Invalid Wine version '{0}', aborting!".format(args.version))

    # for exporting variables into current shell environment
    my_env = dict(os.environ.copy())

    ##################################################################
    # default options passed to 'configure'
    configure_options = ""
    # - MinGW cross-compiler, option '--with-mingw' was added with Wine 4.6
    #   LLVM-based MinGW integration and PDB support is usable since Wine 5.0
    if wine_version >= Version("5.0"):
        configure_options += " --without-mingw" if args.disable_mingw else " --with-mingw"
    else:
        args.disable_mingw = True
    # - Wine-Mono disabled by default
    configure_options += " --enable-mscoree" if args.enable_mscoree else " --disable-mscoree"
    # - Tests not built by default
    configure_options += " --enable-tests" if args.enable_tests else " --disable-tests"

    ##################################################################
    # default host and target machine architectures
    pipe = subprocess.Popen("setarch linux64 uname -m", shell=True,
                            stdout=subprocess.PIPE, encoding="utf8").stdout
    wine_host_arch64 = pipe.readline().rstrip(os.linesep)
    pipe.close()
    pipe = subprocess.Popen("setarch linux32 uname -m", shell=True,
                            stdout=subprocess.PIPE, encoding="utf8").stdout
    wine_host_arch32 = pipe.readline().rstrip(os.linesep)
    pipe.close()
    # Default: no cross-compile -> target == host arch
    wine_target_arch64 = wine_host_arch64
    wine_target_arch32 = wine_host_arch32

    ##################################################################
    # cross-compile setup
    wine_cross_compile_options = ""
    if args.cross_compile_prefix:

        wine_cross_compile_options += " --host={0} host_alias={1}".format(
            args.cross_compile_prefix.rstrip("-"), args.cross_compile_prefix.rstrip("-"))
        # Need to set '--with-wine-tools' when cross compiling.
        # The path must point the tools subdirectory of a wine build compiled for the *host* system.
        wine_cross_compile_options += " --with-wine-tools={0}/{1}-build{2}-{3}".format(
            wine_workspace_path, args.variant, dash_version, wine_host_arch64)

        pipe = subprocess.Popen("{0}gcc -dumpmachine | cut -d '-' -f1 2>&1".format(
                                args.cross_compile_prefix),
                                shell=True, stdout=subprocess.PIPE, encoding="utf8").stdout
        wine_target_arch = pipe.readline().rstrip(os.linesep)
        pipe.close()

        if "arm" in wine_target_arch:
            wine_target_arch32 = wine_target_arch
            wine_target_arch64 = ""
            # On 32-bit ARM, the floating point ABI defaults to 'softfp' for compatibility
            # with Windows binaries. This won't work for hardfp toolchains.
            pipe = subprocess.Popen(r"$CC -Q --help=target | grep -m1 -oP '\bmfloat-abi=\s+\K\w+'",
                                    shell=True, stdout=subprocess.PIPE, encoding="utf8").stdout
            cc_opt_floatabi = pipe.readline().rstrip(os.linesep)
            pipe.close()

            pipe = subprocess.Popen(r"$CC -Q --help=target | grep -m1 -oP '\bmfpu=\s+\K\w+'",
                                    shell=True, stdout=subprocess.PIPE, encoding="utf8").stdout
            cc_opt_fpu = pipe.readline().rstrip(os.linesep)
            pipe.close()

            wine_cross_compile_options += " --with-float-abi={0} --with-fpu={1}".format(
                                            cc_opt_floatabi, cc_opt_fpu)

        elif "aarch64" in wine_target_arch:
            wine_target_arch32 = ""
            wine_target_arch64 = wine_target_arch
        else:
            sys.exit("Unsupported target architecture '{0}', aborting!".format(wine_target_arch))

        # Provide full path to cross pkg-config
        # Due to SDK environment script PATH injection, the cross-host pkg-config is found before
        my_env["PKG_CONFIG"] = shutil.which("pkg-config")

    # common CFLAGS
    wine_cflags_common = "-g -O2"
    # Set up target arch specific CFLAGS which are not cross-compile dependent
    wine_cflags_target_arch64 = ""
    wine_cflags_target_arch32 = ""

    if "aarch64" in wine_target_arch64:
        # Wine bug #38719: https://bugs.winehq.org/show_bug.cgi?id=38719
        # 64-bit ARM Windows applications from Windows SDK for Windows 10 crash when accessing TEB/PEB members
        # (AArch64 platform specific register X18 must be reserved for TEB)
        wine_cflags_target_arch64 = "-ffixed-x18"
        # Wine bug #38886: https://bugs.winehq.org/show_bug.cgi?id=38886
        # needs arm64 specific __builtin_ms_va_list
        # https://source.winehq.org/git/wine.git/commit/8fb8cc03c3edb599dd98f369e14a08f899cbff95
        if my_env["CLANGCXX"].strip():
            my_env["CXX"] = my_env["CLANGCXX"]
        if my_env["CLANGCC"].strip():
            my_env["CC"] = my_env["CLANGCC"]
        if my_env["CLANGCPP"].strip():
            my_env["CPP"] = my_env["CLANGCPP"]
    elif "x86_64" in wine_target_arch64:
        if args.enable_nopic:
            wine_cflags_target_arch64 = "-fno-PIC -mcmodel=large"

    if "i386" or "i686" in wine_target_arch32:
        if args.enable_nopic:
            wine_cflags_target_arch32 = "-fno-PIC"

    # if LLVM based MinGW toolchain detected, enable additional features:
    # - generate debug symbols in PDB format
    # - ASLR (dynamicbase)
    if not args.disable_mingw:
        if "aarch64" in wine_host_arch64:
            cc_list = ["aarch64-w64-mingw32-clang", "aarch64-w64-mingw32-gcc"]
        elif "x86_64" in wine_host_arch64:
            cc_list = ["x86_64-w64-mingw32-clang", "amd64-w64-mingw32-clang",
                       "x86_64-pc-mingw32-gcc",  "amd64-pc-mingw32-gcc",
                       "x86_64-w64-mingw32-gcc", "amd64-w64-mingw32-gcc",
                       "x86_64-mingw32msvc-gcc", "amd64-mingw32msvc-gcc"]
        else:
            cc_list = []

        cc_exists = lambda x: shutil.which(x) is not None
        for cc_prog in cc_list:
            if cc_exists(cc_prog) and "clang" in cc_prog:
                # Enable llvm-mingw PDB support
                # https://github.com/mstorsjo/llvm-mingw
                my_env["CROSSCFLAGS"] = "-g -gcodeview -O2"
                my_env["CROSSLDFLAGS"] = "-Wl,-pdb="
                # Enable ASLR support
                # Currently not supported by Wine loader: https://bugs.winehq.org/show_bug.cgi?id=48417
                my_env["CROSSLDFLAGS"] += " -Wl,--dynamicbase"
                break

    # target arch specific build and install paths
    wine_build_target_arch32_path = ""
    wine_build_target_arch64_path = ""
    wine_install_prefix = args.install_prefix

    # target arch specific paths for 32-bit Wine
    if wine_target_arch32:
        wine_build_target_arch32_path = "{0}/{1}-build{2}-{3}".format(
            wine_workspace_path, args.variant, dash_version, wine_target_arch32)
        wine_install_prefix = "{0}/{1}-install{2}-{3}".format(
            wine_workspace_path, args.variant, dash_version, wine_target_arch32)
    # target arch specific paths for 64-bit Wine
    if wine_target_arch64:
        wine_build_target_arch64_path = "{0}/{1}-build{2}-{3}".format(
            wine_workspace_path, args.variant, dash_version, wine_target_arch64)
        # includes shared WoW64 install as well
        wine_install_prefix = "{0}/{1}-install{2}-{3}".format(
            wine_workspace_path, args.variant, dash_version, wine_target_arch64)

    ##################################################################
    # Set up mainline source tree clone. It also needs to be present for Wine-Staging.
    if not os.path.exists(wine_mainline_source_path):

        # local git mirror to speed up checkout and save disk space
        wine_local_clone_source = "{0}/mainline-src-reference-gitmirror".format(wine_workspace_path)
        if not os.path.exists(wine_local_clone_source):
            # create local git mirror for the first time
            run_command("git clone --mirror {0} {1}".format(WINE_MAINLINE_GIT_URI, wine_local_clone_source))
        else:
            # ensure local git mirror is up to date
            run_command("git fetch --all", cwd=wine_local_clone_source)

        # use '--shared' to speed up checkout and save disk space
        run_command("git clone --shared {0} {1}".format(wine_local_clone_source, wine_mainline_source_path))

    # reset mainline source tree when version has been specified
    if args.version and not args.no_reset_source:
        # reset the tree to specific version
        run_command("git reset --hard wine-{0}".format(args.version), wine_mainline_source_path)

    ##################################################################
    # Wine-Staging: set up two source source tree: upstream repo + mainline-patched-with-staging
    if args.variant == "staging":

        if not os.path.exists(wine_staging_patches_path):
            run_command("git clone {0} {1}".format(WINE_STAGING_GIT_URI, wine_staging_patches_path))
        else:
            run_command("git fetch --all", cwd=wine_staging_patches_path)

        if not os.path.exists(wine_variant_source_path):
            run_command("git clone {0} {1}".format(wine_mainline_source_path, wine_variant_source_path))
        else:
            run_command("git fetch --all", cwd=wine_variant_source_path)

        if not args.no_reset_source:
            if args.version:
                # reset source tree to specific version
                run_command("git reset --hard v{0}".format(args.version), wine_staging_patches_path)
                # reset source tree to specific version
                run_command("git reset --hard wine-{0}".format(args.version), wine_variant_source_path)
            else:
                # reset source tree to where upstream points to
                run_command("git reset --hard @{upstream}", wine_staging_patches_path)
                # reset source tree to where upstream points to
                run_command("git reset --hard @{upstream}", wine_variant_source_path)

        # apply staging patches to the clone
        run_command("{0}/patches/patchinstall.sh DESTDIR={1} --backend=git --force-autoconf --all".format(
            wine_staging_patches_path, wine_variant_source_path))

    ##################################################################
    # apply Wine build fixups for older Wine versions

    # ERROR: tools/wrc/parser.y:2840:15: error: ‘YYLEX’ undeclared (first use in this function)
    #        and various other locations with problematic bison directives
    # URL: https://bugs.winehq.org/show_bug.cgi?id=34329
    # GIT: https://source.winehq.org/git/wine.git/commit/8fcac3b2bb8ce4cdbcffc126df779bf1be168882
    # FIXED: wine-1.7.0
    if wine_version >= Version("1.3.30") and wine_version < Version("1.7.0"):
        patch_apply(wine_variant_source_path, "3f98185fb8f88c181877e909ab1b6422fb9bca1e")
        patch_apply(wine_variant_source_path, "8fcac3b2bb8ce4cdbcffc126df779bf1be168882")
        patch_apply(wine_variant_source_path, "bda5a2ffb833b2824325bd9361b30dbaf5f78068")
        patch_apply(wine_variant_source_path, "f86c46f6403fe338a544ab134bdf563c5b0934ae")
        patch_apply(wine_variant_source_path, "ffbe1ca986bd299e1fc894440849914378adbf5c")

    if wine_version >= Version("1.5.10") and wine_version < Version("1.7.0"):
        patch_apply(wine_variant_source_path, "c14e322a92a24e704836c5c12207c694a30e805f")

    # ERROR: err:msidb:get_tablecolumns column 1 out of range (gcc 4.9+ problem, breaks msi installers)
    # URL: https://bugs.winehq.org/show_bug.cgi?id=36139
    # GIT: https://source.winehq.org/git/wine.git/commit/deb274226783ab886bdb44876944e156757efe2b
    # FIXED: wine-1.7.20
    if wine_version >= Version("1.3.30") and wine_version < Version("1.7.20"):
        patch_apply(wine_variant_source_path, "deb274226783ab886bdb44876944e156757efe2b")

    # ERROR: dlls/wineps.drv/psdrv.h:389:5: error: unknown type name ‘PSDRV_DEVMODEA’
    # ERROR: dlls/wineps.drv/init.c:43:14: error: unknown type name ‘PSDRV_DEVMODE’
    # ERROR: dlls/wineps.drv/init.c:605:16: error: ‘cupsGetPPD’ undeclared (first use in this function); did you mean ‘cupsGetFd’?
    # GIT-start: https://source.winehq.org/git/wine.git/commit/d963a8f864a495f7230dc6fe717d71e61ae51d67
    # GIT-end: https://source.winehq.org/git/wine.git/commit/72cfc219f0ba2fc3aea19760558f7820f4883176
    # GIT: https://source.winehq.org/git/wine.git/commit/bdaddc4b7c4b4391b593a5f4ab91b8121c698bef
    if wine_version >= Version("1.3.30") and wine_version < Version("1.5.10"):
        # Way too many patches for fixing this, even across modules. Disable module.
        configure_options += " --disable-wineps.drv"

    # ERROR: dlls/winspool.drv/info.c:779:13: error: ‘cupsGetPPD’ undeclared here (not in a function); did you mean ‘cupsGetFd’?
    # URL: https://bugs.winehq.org/show_bug.cgi?id=40851
    # GIT: https://source.winehq.org/git/wine.git/commit/10065d2acd0a9e1e852a8151c95569b99d1b3294
    # FIXED: wine-1.9.14
    if wine_version >= Version("1.3.30") and wine_version < Version("1.9.14"):
        patch_apply(wine_variant_source_path, "10065d2acd0a9e1e852a8151c95569b99d1b3294", "configure.ac")

    # ERROR: dlls/secur32/schannel_gnutls.c:45:12: error: conflicting types for ‘gnutls_cipher_get_block_size’
    # URL: https://bugs.debian.org/cgi-bin/bugreport.cgi?bug=832275
    # GIT: https://source.winehq.org/git/wine.git/commit/bf5ac531a030bce9e798ab66bc53e84a65ca8fdb
    # FIXED: wine-1.9.13
    if wine_version >= Version("1.7.49") and wine_version < Version("1.9.13"):
        patch_apply(wine_variant_source_path, "bf5ac531a030bce9e798ab66bc53e84a65ca8fdb")

    # ERROR: include/winsock.h:401: warning: "INVALID_SOCKET" redefined
    # GIT: https://source.winehq.org/git/wine.git/commit/28173f06932edd85a64a952120d29b9bb1e762ea
    # FIXED: wine-2.13
    if wine_version >= Version("1.7.6") and wine_version < Version("2.13"):
        patch_apply(wine_variant_source_path, "28173f06932edd85a64a952120d29b9bb1e762ea")

    ##################################################################
    # clean build directories if requested
    if args.clean:

        shutil.rmtree(wine_build_target_arch32_path, ignore_errors=True)
        shutil.rmtree(wine_build_target_arch64_path, ignore_errors=True)

    # always remove install directories
    shutil.rmtree(wine_install_prefix, ignore_errors=True)

    ##################################################################
    # run 'autoreconf' and 'tools/make_requests' if requested
    if args.force_autoconf:

        # update configure scripts
        run_command("autoreconf -f", wine_variant_source_path)
        # update wineserver protocol
        run_command("./tools/make_requests", wine_variant_source_path)

    ##################################################################
    # build and install 64-bit Wine
    if wine_build_target_arch64_path:

        os.makedirs(wine_build_target_arch64_path, exist_ok=True)

        my_env["CFLAGS"] = "{0} {1}".format(wine_cflags_common, wine_cflags_target_arch64)
        my_env["MAKEFLAGS"] = "-j{0} -l{0}".format(args.jobs)

        logfile = "build_{0}.log".format(wine_target_arch64)

        if not args.no_configure:

            run_command("{0}/configure --prefix={1} {2} {3} --enable-win64 2>&1 | tee {4}".format(
                wine_variant_source_path, wine_install_prefix, wine_cross_compile_options,
                configure_options, logfile), wine_build_target_arch64_path, my_env)

        run_command("make 2>&1 | tee -a {0}".format(logfile), wine_build_target_arch64_path, my_env)

        run_command("make install | tee -a {0}".format(logfile), wine_build_target_arch64_path, my_env)

    ##################################################################
    # build and install 32-bit Wine
    if wine_build_target_arch32_path:

        os.makedirs( wine_build_target_arch32_path, exist_ok=True)

        my_env["CFLAGS"] = "{0} {1}".format( wine_cflags_common, wine_cflags_target_arch32)
        my_env["MAKEFLAGS"] = "-j{0} -l{0}".format(args.jobs)

        logfile = "build_{0}.log".format( wine_target_arch32)

        if not args.no_configure:

            run_command("{0}/configure --prefix={1} {2} {3} --with-wine64={4} 2>&1 | tee {5}".format(
                wine_variant_source_path, wine_install_prefix, wine_cross_compile_options,
                configure_options, wine_build_target_arch64_path, logfile), wine_build_target_arch32_path, my_env)

        run_command("make 2>&1 | tee -a {0}".format(logfile), wine_build_target_arch32_path, my_env)

        run_command("make install | tee -a {0}".format(logfile), wine_build_target_arch32_path, my_env)

        # make a lib32 symlink to lib to allow winegcc -m32
        # relative so the prefix can be moved around
        os.symlink("lib", "{0}/lib32".format(wine_install_prefix))

    print(
    """
    Run the following command to register this Wine variant in environment
    ----------------------------------------------------------------------
    export PATH={0}/bin/:$PATH
    ----------------------------------------------------------------------
    """.format( wine_install_prefix))

if __name__== "__main__":
    main()
