#!/usr/bin/python3

# Script to build Wine variants from source, including cross-compile for
# non-Intel architectures. Run with '--help' for usage.

import argparse
import os
import re
import subprocess
import sys
import shutil
import packaging
import tempfile
import stat

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
    """Run the specified command in a subprocess shell and show stdout

    Parameters:
        command (str): Linux shell command.
        cwd (str): Working directory for the command.
        env (str): Custom shell environment for the intermediate shell.
    Returns:
        if executed process exit code is non-zero, raises a CalledProcessError.

    """
    print("[*] Running following command:")
    print("'{0}' (cwd='{1}')".format( command, cwd))

    # Some commands involve 'tee' (pipelines) hence prefix with 'pipefail' to capture failure as well
    subprocess.run("set -o pipefail && {0}".format(command), cwd=cwd, env=env, check=True, shell=True,
                    stderr=sys.stderr, stdout=sys.stdout, encoding="utf8")

def run_command_stdout(command, cwd=None, env=None):
    """Run the specified command in a subprocess shell and return stdout

    Parameters:
        command (str): Linux shell command.
        cwd (str): Working directory for the command.
        env (str): Custom shell environment for the intermediate shell.
    Returns:
        stdout as string
        if executed process exit code is non-zero, raises a CalledProcessError.

    """
    print("[*] Running following command:")
    print("'{0}' (cwd='{1}')".format( command, cwd))

    # Some commands involve 'tee' (pipelines) hence prefix with 'pipefail' to capture failure as well
    return subprocess.run("set -o pipefail && {0}".format(command), stdout=subprocess.PIPE,
                        cwd=cwd, env=env, shell=True, encoding="utf8").stdout.rstrip(os.linesep)

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
    patchfile = run_command_stdout("git format-patch -1 --full-index --binary {0} 2> /dev/null".format(commit_id), source_path)
    if not patchfile or not os.path.exists(os.path.normpath(os.path.join(source_path, patchfile))):
        sys.exit("Patch extraction of '{0}' failed, aborting!".format(commit_id))

    patch_stdout = run_command_stdout("filterdiff -p1 -x '{0}' < {1} | patch -p1 --forward --no-backup-if-mismatch 2>&1".format(
                 exclude_pattern, patchfile), source_path)
    if any(re.findall(r'failed|error:', patch_stdout, re.IGNORECASE)):
        sys.exit("Patch '{0}' failed with output '{1}', aborting!".format(patchfile, patch_stdout))
    # "Reversed (or previously applied) patch detected!  Skipping patch." is not an error

def bin_patch_apply(source_path, commit_id, exclude_pattern=""):
    """ Apply a binary patch from Git commit into current branch using 'git apply'.

    Parameters:
        source_path (str): Path to source repository.
        commit_id (str): Commit sha1 to generate patch from
        exclude_pattern (str): Pattern for 'filterdiff' to exclude files

    Returns:
        none.

    """

    # extract the patch from Git checkout
    patchfile = run_command_stdout("git format-patch -1 --full-index --binary {0} 2> /dev/null".format(commit_id), source_path)
    if not patchfile or not os.path.exists(os.path.normpath(os.path.join(source_path, patchfile))):
        sys.exit("Patch extraction of '{0}' failed, aborting!".format(commit_id))

    patch_stdout = run_command_stdout("filterdiff -p1 -x '{0}' < {1} | git apply 2>&1".format(
                 exclude_pattern, patchfile), source_path)
    if any(re.findall(r'not apply|error:', patch_stdout, re.IGNORECASE)):
        sys.exit("Git apply '{0}' failed with output '{1}', aborting!".format(patchfile, patch_stdout))
    # "Reversed (or previously applied) patch detected!  Skipping patch." is not an error

def create_config_wrapper(org_config, arg_filter, output_remove):
    """ Create a shell wrapper in /tmp for pkg-config, freetype-config etc. to fix broken cflags.

    Parameters:
        org_config (str): Path to original pkg-config, freetype-config etc.
        arg_filter (str): Argument pattern to filter output for.
        output_replace (str): Output pattern to remove.

    Returns:
        Full path to new config wrapper script.

    """

    content = """#!/bin/bash
result=`{org_config} "$@"`
if [[ "$@" =~ "{arg_filter}" ]] ; then
  echo "${{result//{output_remove}/}}"
else
  echo "$result"
fi
""".format( org_config=org_config, arg_filter=arg_filter, output_remove=output_remove)

    # Create the wrapper in /tmp/<random>/<org_config> to ensure uniqueness but same basename.
    # It also supports nested 'pkg-config' use-cases. Each created wrapper can call the previous wrapper
    # which at one point calls the original 'pkg-config' from first created wrapper (in sequence).
    # Each wrapper would filter out it's own pattern.
    config_wrapper = os.path.join(tempfile.mkdtemp(), os.path.basename(org_config))
    with open(config_wrapper, 'w') as f:
        f.write( content)
    os.chmod(config_wrapper, os.stat(config_wrapper).st_mode | stat.S_IEXEC)
    return config_wrapper

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
    my_parser.add_argument("--enable-clang",
                           action="store_true",
                           help="Use the clang for building Wine")
    my_parser.add_argument("--disable-mingw",
                           action="store_true",
                           help="do not use the MinGW cross-compiler for building Wine")
    my_parser.add_argument("--enable-mscoree",
                           action="store_true",
                           help="enable Wine-Mono on HEAD builds (default for Wine release builds)")
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
        stdout = run_command_stdout("git describe --abbrev=0 2> /dev/null | sed 's/wine-//'",
                            wine_variant_source_path)
        wine_version = parse_version(stdout)

    if not isinstance(wine_version, Version):
        # unknown version schemes not supported
        sys.exit("Invalid Wine version '{0}', aborting!".format(args.version))

    # for exporting variables into current shell environment
    my_env = dict(os.environ.copy())

    ##################################################################
    # default options passed to 'configure'
    configure_options = ""
    # LLVM-based MinGW integration and PDB support is usable since Wine 5.0
    # Configure fixup required for newer LLVM MinGW 12.x doesn't apply cleanly hence exclude Wine 5.0, 5.1
    # GIT: https://source.winehq.org/git/wine.git/commitdiff/f29d4a43e203303c2d4aaec388f281d01f17764c
    if wine_version <= Version("5.1"):
        args.disable_mingw = True
    # MinGW cross-compiler option '--with-mingw' was added with Wine 4.6
    if wine_version >= Version("4.6"):
        configure_options += " --without-mingw" if args.disable_mingw else " --with-mingw"
    # - Wine-Mono disabled by default on HEAD builds (no explicit version given)
    configure_options += " --enable-mscoree" if args.enable_mscoree or args.version else " --disable-mscoree"
    # - Tests not built by default
    configure_options += " --enable-tests" if args.enable_tests else " --disable-tests"
    # NOTE: 'configure --enable-modulename ' will cause: 'configure:num: WARNING: unrecognized options: --enable-modulename'
    # GIT: https://source.winehq.org/git/wine.git/commitdiff/d92bcec95a55bae2f9bc686bad9b2641a162c548
    # FIXED: wine-1.7.4

    ##################################################################
    # default host and target machine architectures
    wine_host_arch64 = run_command_stdout("setarch linux64 uname -m")
    wine_host_arch32 = run_command_stdout("setarch linux32 uname -m")
    # Default: no cross-compile -> target == host arch
    wine_target_arch64 = wine_host_arch64
    wine_target_arch32 = wine_host_arch32

    # Since Wine 6.8, libraries are installed into architecture-specific subdirectories.
    if wine_version >= Version("6.8"):
        wine_install_arch32_pe_dir = "lib/wine/i386-windows"
        wine_install_arch32_so_dir = "lib/wine/i386-unix"
        wine_install_arch64_pe_dir = "lib/wine/x86_64-windows"
        wine_install_arch64_so_dir = "lib/wine/x86_64-unix"
    else:
        wine_install_arch32_pe_dir = "lib/wine"
        wine_install_arch32_so_dir = "lib/wine"
        wine_install_arch64_pe_dir = "lib64/wine"
        wine_install_arch64_so_dir = "lib64/wine"

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

        wine_target_arch = run_command_stdout("{0}gcc -dumpmachine | cut -d '-' -f1 2>&1".format(
                                args.cross_compile_prefix))

        if "arm" in wine_target_arch:
            wine_target_arch32 = wine_target_arch
            wine_target_arch64 = ""
            wine_install_arch32_pe_dir = "/arm-windows"
            wine_install_arch32_so_dir = "/arm-unix"
            # On 32-bit ARM, the floating point ABI defaults to 'softfp' for compatibility
            # with Windows binaries. This won't work for hardfp toolchains.
            cc_opt_floatabi = run_command_stdout(r"$CC -Q --help=target | grep -m1 -oP '\bmfloat-abi=\s+\K\w+'")
            cc_opt_fpu = run_command_stdout(r"$CC -Q --help=target | grep -m1 -oP '\bmfpu=\s+\K\w+'")
            cc_opt_arch = run_command_stdout(r"$CC -Q --help=target | grep -m1 -oP '\bmarch=\s+\K\w+'")

            wine_cross_compile_options += " --with-float-abi={0}".format(cc_opt_floatabi)
            my_env["EXTRA_TARGETFLAGS"] = "-march={0} -mfpu={1}".format(cc_opt_arch, cc_opt_fpu)

        elif "aarch64" in wine_target_arch:
            wine_target_arch32 = ""
            wine_target_arch64 = wine_target_arch
            wine_install_arch64_pe_dir = "/aarch64-windows"
            wine_install_arch64_so_dir = "/aarch64-unix"
        else:
            sys.exit("Unsupported target architecture '{0}', aborting!".format(wine_target_arch))

    # Provide full path to cross pkg-config
    # Due to SDK environment script PATH injection, the cross-host pkg-config is found before
    my_env["PKG_CONFIG"] = shutil.which("pkg-config")

    # common CFLAGS
    wine_cflags_common = "-O2 -g"
    # Wine 6.21 added dwarf4 debug format support in dbghelp
    if wine_version >= Version("6.21"):
        wine_cflags_common += " -gdwarf-4"

    # Set up target arch specific CFLAGS which are not cross-compile dependent
    wine_cflags_target_arch64 = ""
    wine_cflags_target_arch32 = ""

    # Use clang if requested
    if args.enable_clang:
        # Wine bug #38886: https://bugs.winehq.org/show_bug.cgi?id=38886
        # needs ARM64 specific '__builtin_ms_va_list'
        # https://source.winehq.org/git/wine.git/commit/8fb8cc03c3edb599dd98f369e14a08f899cbff95
        # gcc lacking '__builtin_ms_va_list' support on ARM64:  https://gcc.gnu.org/bugzilla/show_bug.cgi?id=87334

        # CLANGxxx environment variables might be set by cross-compile environments such as Yocto SDK
        my_env["CXX"] = os.getenv('CLANGCXX', 'clang++')
        my_env["CC"] =  os.getenv('CLANGCC', 'clang')
        my_env["CPP"] = os.getenv('CLANGCPP', 'clang -E')

    if "aarch64" in wine_target_arch64:
        # Wine bug #38719: https://bugs.winehq.org/show_bug.cgi?id=38719
        # 64-bit ARM Windows applications from Windows SDK for Windows 10 crash when accessing TEB/PEB members
        # (AArch64 platform specific register X18 must be reserved for TEB)
        wine_cflags_target_arch64 = "-ffixed-x18"

    elif "x86_64" in wine_target_arch64:
        if args.enable_nopic:
            wine_cflags_target_arch64 = "-fno-PIC -mcmodel=large"

    if "i386" or "i686" in wine_target_arch32:
        if args.enable_nopic:
            wine_cflags_target_arch32 = "-fno-PIC"

    if not args.disable_mingw:
        # LLVM based MinGW toolchain settings (https://github.com/mstorsjo/llvm-mingw)
        # - enable ASLR support
        # Currently not supported by Wine loader: https://bugs.winehq.org/show_bug.cgi?id=48417
        my_env["CROSSLDFLAGS"] = " -Wl,--dynamicbase"
        # - generate debug symbols in PDB format
        # GIT: https://source.winehq.org/git/wine.git/commit/83d00d328f58f910a9b197e0a465b110cbdc727c
        if wine_version >= Version("5.9"):
            # Support split debug for cross compiled modules
            my_env["CROSSDEBUG"] = "pdb"
        else:
            my_env["CROSSCFLAGS"] = "-g -gcodeview -O2"
            # Wine 6.21 added dwarf4 debug format support in dbghelp
            if wine_version >= Version("6.21"):
                my_env["CROSSCFLAGS"] = "-gdwarf-4 -O2"
            my_env["CROSSLDFLAGS"] = "-Wl,-pdb="
        # Use clang MSVC mode to emit 'movl %edi,%edi' prologue
        # https://github.com/llvm/llvm-project/blob/main/llvm/lib/Target/X86/X86MCInstLower.cpp#L1386
        #
        # Only enable it on MinGW builds if Wine >= 6.0 to avoid error:
        #
        #    Use configure:10505: checking whether the compiler supports -Wl,-delayload,autoconftest.dll
        #    configure:10516: clang -o conftest -g -gcodeview -O2 -Werror=unknown-warning-option -Wl,-delayload,autoconftest.dll   conftest.c  >&5
        #    /usr/bin/ld: Error: unable to disambiguate: -delayload (did you mean --delayload ?)
        #    clang-13: error: linker command failed with exit code 1 (use -v to see invocation)
        #
        # GIT: https://source.winehq.org/git/wine.git/commitdiff/4b362d016c57c14570efeb9c38dfcc5cf2c0910d
        # FIXED: Wine 6.0
        if wine_version >= Version("6.0"):
            my_env["CROSSCC"] = "clang"

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
            run_command("git fetch --all || true", cwd=wine_local_clone_source)

        # use '--shared' to speed up checkout and save disk space
        run_command("git clone --shared {0} {1}".format(wine_local_clone_source, wine_mainline_source_path))

    # reset mainline source tree when version has been specified
    if args.version and args.variant != "staging" and not args.no_reset_source:
        # reset the tree to specific version
        run_command("git reset --hard wine-{0}".format(args.version), wine_mainline_source_path)
        # removed any untracked files
        run_command("git clean -dxf", wine_mainline_source_path)

    ##################################################################
    # Wine-Staging: set up two source source tree: upstream repo + mainline-patched-with-staging
    if args.variant == "staging":

        if not os.path.exists(wine_staging_patches_path):
            run_command("git clone {0} {1}".format(WINE_STAGING_GIT_URI, wine_staging_patches_path))
        else:
            run_command("git fetch --all || true", cwd=wine_staging_patches_path)

        if not os.path.exists(wine_variant_source_path):
            run_command("git clone {0} {1}".format(wine_mainline_source_path, wine_variant_source_path))
        else:
            run_command("git fetch --all || true", cwd=wine_variant_source_path)

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
    if wine_version >= Version("1.3.28") and wine_version < Version("1.7.0"):
        patch_apply(wine_variant_source_path, "3f98185fb8f88c181877e909ab1b6422fb9bca1e")
        patch_apply(wine_variant_source_path, "8fcac3b2bb8ce4cdbcffc126df779bf1be168882")
        patch_apply(wine_variant_source_path, "bda5a2ffb833b2824325bd9361b30dbaf5f78068")
    # jscript: https://source.winehq.org/git/wine.git/commitdiff/9ebdd111264cfa646dd5219b5874166eb59217c1
    if wine_version >= Version("1.1.10") and wine_version < Version("1.7.0"):
        patch_apply(wine_variant_source_path, "ffbe1ca986bd299e1fc894440849914378adbf5c")
    # vbscript: https://source.winehq.org/git/wine.git/commitdiff/80bcaf8d7ba68aea7090cac2a18e4e7a13147e88
    if wine_version >= Version("1.3.28") and wine_version < Version("1.7.0"):
        patch_apply(wine_variant_source_path, "f86c46f6403fe338a544ab134bdf563c5b0934ae")
    # wbemprox: https://source.winehq.org/git/wine.git/commitdiff/f6be21103b441180c8557aa6bc2845e5428271a4
    if wine_version >= Version("1.5.7") and wine_version < Version("1.7.0"):
        patch_apply(wine_variant_source_path, "c14e322a92a24e704836c5c12207c694a30e805f")

    # ERROR: err:msidb:get_tablecolumns column 1 out of range (gcc 4.9+ problem, breaks msi installers)
    # URL: https://bugs.winehq.org/show_bug.cgi?id=36139
    # GIT: https://source.winehq.org/git/wine.git/commit/deb274226783ab886bdb44876944e156757efe2b
    # FIXED: wine-1.7.20
    # NOTE: wine-1.3.22 reformatted code: 'maxcount*sizeof(*colinfo)' -> 'maxcount * sizeof(*colinfo)'
    # https://source.winehq.org/git/wine.git/commitdiff/1ae309f98194f56b3734943cd63d8a798319fb34
    if wine_version >= Version("1.3.28") and wine_version < Version("1.7.20"):
        patch_apply(wine_variant_source_path, "deb274226783ab886bdb44876944e156757efe2b")

    # ERROR: dlls/wineps.drv/psdrv.h:389:5: error: unknown type name ‘PSDRV_DEVMODEA’
    # ERROR: dlls/wineps.drv/init.c:43:14: error: unknown type name ‘PSDRV_DEVMODE’
    # ERROR: dlls/wineps.drv/init.c:605:16: error: ‘cupsGetPPD’ undeclared (first use in this function); did you mean ‘cupsGetFd’?
    # GIT-start: https://source.winehq.org/git/wine.git/commit/d963a8f864a495f7230dc6fe717d71e61ae51d67
    # GIT-end: https://source.winehq.org/git/wine.git/commit/72cfc219f0ba2fc3aea19760558f7820f4883176
    # GIT: https://source.winehq.org/git/wine.git/commit/bdaddc4b7c4b4391b593a5f4ab91b8121c698bef
    if wine_version >= Version("1.3.28") and wine_version < Version("1.5.2"):
        # Way too many patches for fixing this, even across modules. Disable module.
        configure_options += " --disable-wineps.drv"
    if wine_version >= Version("1.5.2") and wine_version < Version("1.5.7"):
        patch_apply(wine_variant_source_path, "bdaddc4b7c4b4391b593a5f4ab91b8121c698bef")

    # ERROR: dlls/winspool.drv/info.c:779:13: error: ‘cupsGetPPD’ undeclared here (not in a function); did you mean ‘cupsGetFd’?
    # URL: https://bugs.winehq.org/show_bug.cgi?id=40851
    # GIT: https://source.winehq.org/git/wine.git/commit/10065d2acd0a9e1e852a8151c95569b99d1b3294
    # REBASE-FIX needed due to: https://source.winehq.org/git/wine.git/commitdiff/cf0e96c6d0edc3a22b8ee5ac423d9b6b652ce0e5
    # FIXED: wine-1.9.14
    if wine_version >= Version("1.3.28") and wine_version < Version("1.7.12"):
        patch_apply(wine_variant_source_path, "2ac0c877f591be14815902b527f314a915eee147")
    if wine_version >= Version("1.7.12") and wine_version < Version("1.9.14"):
        patch_apply(wine_variant_source_path, "10065d2acd0a9e1e852a8151c95569b99d1b3294")

    # ERROR: dlls/secur32/schannel_gnutls.c:45:12: error: conflicting types for ‘gnutls_cipher_get_block_size’
    # URL: https://bugs.debian.org/cgi-bin/bugreport.cgi?bug=832275
    # GIT: https://source.winehq.org/git/wine.git/commit/bf5ac531a030bce9e798ab66bc53e84a65ca8fdb
    # FIXED: wine-1.9.13
    if wine_version >= Version("1.7.46") and wine_version < Version("1.9.13"):
        patch_apply(wine_variant_source_path, "bf5ac531a030bce9e798ab66bc53e84a65ca8fdb")

    # ERROR: include/winsock.h:401: warning: "INVALID_SOCKET" redefined
    # GIT: https://source.winehq.org/git/wine.git/commit/28173f06932edd85a64a952120d29b9bb1e762ea
    # FIXED: wine-2.13
    # wpcap code introduced by: https://source.winehq.org/git/wine.git/commitdiff/fa67586811765d88d3b4108b3e5b4e51bb07868f
    if wine_version >= Version("1.7.25") and wine_version < Version("2.13"):
        patch_apply(wine_variant_source_path, "28173f06932edd85a64a952120d29b9bb1e762ea")

    # wine-1.5.30-x86_64/bin/wine:
    #       error while loading shared libraries: libwine.so.1: cannot open shared object file: No such file or directory
    # URL: https://bugs.winehq.org/show_bug.cgi?id=33560
    # GIT: https://source.winehq.org/git/wine.git/commitdiff/ce4b6451aabbe83809c7483c748cfa009cc090d6
    # FIXED: wine-1.5.31
    if wine_version >= Version("1.5.30") and wine_version < Version("1.5.31"):
        patch_apply(wine_variant_source_path, "ce4b6451aabbe83809c7483c748cfa009cc090d6")

    # ERROR: rm -f fonts && ln -s ../mainline-build-1.9.5-x86_64/fonts fonts
    #        rm: cannot remove 'fonts': Is a directory
    # URL: https://bugs.winehq.org/show_bug.cgi?id=40253
    # GIT: https://source.winehq.org/git/wine.git/commitdiff/c6d6dcee47eb97fd75e389434d4136de2f31414c
    # FIXED: wine-1.9.6
    if wine_version >= Version("1.9.5") and wine_version < Version("1.9.6"):
        patch_apply(wine_variant_source_path, "c6d6dcee47eb97fd75e389434d4136de2f31414c")

    # ERROR: gstreamer-1.0 base plugins 32-bit development files not found, gstreamer support disabled
    # GIT: https://source.winehq.org/git/wine.git/commitdiff/20d41d9e2810696ca38598abcef6da8e77f9aae7
    # FIXED: wine-2.10
    if wine_version >= Version("1.4") and wine_version < Version("2.10"):
        patch_apply(wine_variant_source_path, "20d41d9e2810696ca38598abcef6da8e77f9aae7")

    # configure: Don't use X_PRE_LIBS.
    # GIT: https://source.winehq.org/git/wine.git/commitdiff/bb50d6fd9512a9a05306c56112bbcdc6de6c8d65
    # FIXED: wine-1.7.2
    if wine_version >= Version("1.5.17") and wine_version < Version("1.7.2"):
        patch_apply(wine_variant_source_path, "bb50d6fd9512a9a05306c56112bbcdc6de6c8d65")

    # ERROR: configure: libOSMesa 64-bit development files not found (or too old)
    # GIT: https://source.winehq.org/git/wine.git/commitdiff/f625707ffc38c58cc296c8a27ac6c2b3e1c38249
    # REBASE-FIX needed due to: https://source.winehq.org/git/wine.git/commitdiff/cf0e96c6d0edc3a22b8ee5ac423d9b6b652ce0e5
    # FIXED: wine-2.7
    if wine_version >= Version("1.6") and wine_version < Version("1.7.12"):
        patch_apply(wine_variant_source_path, "324305bb282aa4d4de471c43d5c129d2bdd97711")
    if wine_version >= Version("1.7.12") and wine_version < Version("2.7"):
        # stable > 2.0.4 already has cherry-pick
        if wine_version not in [Version("2.0.5")]:
            patch_apply(wine_variant_source_path, "f625707ffc38c58cc296c8a27ac6c2b3e1c38249")

    # backport for prelink support
    # winegcc: Set the LDDLLFLAGS according to the target platform.
    # GIT: https://source.winehq.org/git/wine.git/commitdiff/2374cd52a72d685d4f7ddb88456a846e6396415f
    # FIXED: wine-1.7.1
    if wine_version >= Version("1.5.30") and wine_version < Version("1.7.1"):
        patch_apply(wine_variant_source_path, "2374cd52a72d685d4f7ddb88456a846e6396415f")
    # configure: WARNING: prelink not found, base address of core dlls won't be set correctly.
    # GIT: https://source.winehq.org/git/wine.git/commitdiff/a35f9a13a80fa93c251e12402a73a38a89ec397f
    # FIXED: wine-1.7.54
    if wine_version >= Version("1.5.30") and wine_version < Version("1.7.54"):
        patch_apply(wine_variant_source_path, "a35f9a13a80fa93c251e12402a73a38a89ec397f")

    # Fix build failure ('major' undefined) in glibc 2.28.
    # ERROR: server/fd.c:922:9: warning: implicit declaration of function ‘major’ [-Wimplicit-function-declaration]
    #                  922 |     if (major(dev) == FLOPPY_MAJOR) return 1;
    #        /usr/bin/ld: fd.o: in function `is_device_removable':
    #         server/fd.c:922: undefined reference to `major'
    #         collect2: error: ld returned 1 exit status
    # GIT: https://source.winehq.org/git/wine.git/commitdiff/ca8a08606d3f0900b3f4aa8f2e6547882a22dba8
    # FIXED: wine-1.9.10
    if wine_version >= Version("1.7.44") and wine_version < Version("1.9.10"):
        patch_apply(wine_variant_source_path, "ca8a08606d3f0900b3f4aa8f2e6547882a22dba8")
    # REBASE-FIX needed for ca8a08606d3f0900b3f for older Wine versions
    if wine_version < Version("1.7.44"):
        patch_apply(wine_variant_source_path, "4f862879c86aedef6d81982d4f828a3109b2192f")

    # Fix build failure for glibc 2.30+
    # ERROR: dlls/ntdll/directory.c:145:19: error: conflicting types for ‘getdents64’
    #         145 | static inline int getdents64( int fd, char *de, unsigned int size )
    #        In file included from /usr/include/dirent.h:404,
    #             from dlls/ntdll/directory.c:29:
    #        /usr/include/bits/dirent_ext.h:29:18: note: previous declaration of ‘getdents64’ was here
    #   29 | extern __ssize_t getdents64 (int __fd, void *__buffer, size_t __length)
    # make[1]: *** [Makefile:393: directory.o] Error 1
    # GIT: https://source.winehq.org/git/wine.git/commitdiff/12fc123338f7af601d3fe76b168a644fcd7e1362
    # Smaller custom fix needed due to change buried in large rework commit.
    # FIXED: wine-1.9.10
    # Intermediate fixup because d189f95d71f1246a doesn't apply cleanly on older Wine versions
    # GIT: https://source.winehq.org/git/wine.git/commitdiff/606c88a348fa240359a25aa5a3659a0b41ee0cb4
    if wine_version >= Version("1.5.11"):
        if wine_version < Version("1.5.23"):
            patch_apply(wine_variant_source_path, "606c88a348fa240359a25aa5a3659a0b41ee0cb4")
        # Intermediate fixup because d189f95d71f1246a doesn't apply cleanly on older Wine versions
        # GIT: https://source.winehq.org/git/wine.git/commitdiff/3ae113a957d396d400a88259634e2870368f307b
        if wine_version < Version("1.7.26"):
            patch_apply(wine_variant_source_path, "3ae113a957d396d400a88259634e2870368f307b")
        if wine_version < Version("1.9.10"):
            patch_apply(wine_variant_source_path, "d189f95d71f1246a8683b14c5b64b0ec5308492f")
    else:
        patch_apply(wine_variant_source_path, "cba95b7eb3986b201dfca5a3e6d9065edecb8188")


    # Freetype 2.8.1 build failures
    # ERROR: ../tools/sfnt2fon/sfnt2fon -o coure.fon .../mainline-src-2.17/fonts/courier.ttf -d 128 13,1252,8
    #        Error: Cannot open face .../mainline-src-2.17/fonts/courier.ttf
    # GIT: https://source.winehq.org/git/wine.git/commitdiff/40166848a7944383a4cfdaac9b18bd03fbb2b4f9
    #      https://source.winehq.org/git/wine.git/commitdiff/7ea82a02079d1600191743cc2c148955efe725fb
    #      https://source.winehq.org/git/wine.git/commitdiff/d82321006de92dcd74465c905121618a76eae76a
    #      https://source.winehq.org/git/wine.git/commitdiff/89e79d8144308a24676ef069d567a14655985b0c
    # FIXED: wine-2.18
    if wine_version >= Version("1.7.12") and wine_version < Version("2.18"):
        # stable > 2.0.2 already has cherry-pick
        if wine_version not in [Version("2.0.3"), Version("2.0.4"), Version("2.0.5")]:
            patch_apply(wine_variant_source_path, "89e79d8144308a24676ef069d567a14655985b0c")
    if wine_version < Version("2.18"):
        if wine_version < Version("1.5.16"):
            patch_apply(wine_variant_source_path, "8ef70039d366bf45900c7e7999767be2ccf9704c")
            patch_apply(wine_variant_source_path, "7cd8dc6bf2b0d81338db9a6d13669b2f31da33d8")
        # stable > 2.0.2 already has cherry-pick
        if wine_version not in [Version("2.0.3"), Version("2.0.4"), Version("2.0.5")]:
            patch_apply(wine_variant_source_path, "d82321006de92dcd74465c905121618a76eae76a")
    if wine_version >= Version("1.7.12") and wine_version < Version("2.18"):
        patch_apply(wine_variant_source_path, "7ea82a02079d1600191743cc2c148955efe725fb")
        # stable > 2.0.2 already has cherry-pick
        if wine_version not in [Version("2.0.3"), Version("2.0.4"), Version("2.0.5")]:
            bin_patch_apply(wine_variant_source_path, "40166848a7944383a4cfdaac9b18bd03fbb2b4f9")
    # REBASE-FIX needed for 7ea82a02079d16 and 40166848a7944383a for older Wine versions
    # Apply prerequisite patches on older Wine versions because a326e29144b74c0b3a doesn't apply cleanly
    if wine_version < Version("1.4-rc1"):
        bin_patch_apply(wine_variant_source_path, "3e6199904f4fc2bf1612f210e07e18435a46a38f")
        bin_patch_apply(wine_variant_source_path, "5d2b9eb9d3e15c3787571000e6a75673a42a0c49")
        bin_patch_apply(wine_variant_source_path, "a926bfdb061ffcdc3c6f88b29fca614f9f12fa78")
        bin_patch_apply(wine_variant_source_path, "4b71072b861cc396c4c50806db034f98869e2cc1")
    if wine_version < Version("1.5.2"):
        if wine_version != Version("1.4.1"):
            # Wine 1.4.1 has this as cherry-pick:
            # https://source.winehq.org/git/wine.git/commitdiff/1823a4ae52b970436943760f028e2c154fd9985d
            bin_patch_apply(wine_variant_source_path, "4f819f8efcd08e29a1a7650300e204839b43af2c")
        bin_patch_apply(wine_variant_source_path, "fc42bfe60f3a29c4ce0ed47eb03cc3125be904fd")
    if wine_version < Version("1.5.16"):
        bin_patch_apply(wine_variant_source_path, "679385fd1cd2c405ac0d3745863d827293a3b445")
        bin_patch_apply(wine_variant_source_path, "673617ee4eb15aa778859d3bcc227e8d8a514e01")
    if wine_version < Version("1.5.18"):
        bin_patch_apply(wine_variant_source_path, "e070173ac6316cd9afc2755087d8e6b95b6cdafe")
        bin_patch_apply(wine_variant_source_path, "1a6e9d4a50ec4a1a5464ca9c3bb02921d50eb777")
    if wine_version < Version("1.5.20"):
        bin_patch_apply(wine_variant_source_path, "9d71d29f26a6f89d4e603c60e355d2ed39153b7f")
    if wine_version < Version("1.5.25"):
        bin_patch_apply(wine_variant_source_path, "1b17f0fd5ded290a332260cad963dac53c08609f")
    if wine_version < Version("1.5.28"):
        bin_patch_apply(wine_variant_source_path, "6eaa345261fad0e0a0e04f265ce6f731302ed674")
        bin_patch_apply(wine_variant_source_path, "c4408e0b621b99115247386e7095231be7e1045d")
    if wine_version < Version("1.5.31"):
        patch_apply(wine_variant_source_path, "d29f6c41eb13e647a311091956af3131633e7eda")
        bin_patch_apply(wine_variant_source_path, "3f0e3ef6b4f422d0528d8031bbad3727face17dd")
        bin_patch_apply(wine_variant_source_path, "8e2cd615c3dc884dc76bd75a77d35fc1fcaf8217")
    if wine_version < Version("1.6-rc2"):
        bin_patch_apply(wine_variant_source_path, "121f82bff7665794be6fee841ddfda6973cc7c46")
        bin_patch_apply(wine_variant_source_path, "2fd3ec7d068ef925e5720222e92cfda4f6badd2a")
    if wine_version < Version("1.6-rc5"):
        bin_patch_apply(wine_variant_source_path, "74b2cb58f7f1192d6b0a7c1bc31a64eb92ccaa86")
        bin_patch_apply(wine_variant_source_path, "66f641896b8056a818b06f07055d1161c36941c1")
        bin_patch_apply(wine_variant_source_path, "eb29e639e579535009a4626fede64e3cf34e7009")
        bin_patch_apply(wine_variant_source_path, "994f74fb46285130cc63784449176c748cfdfaaf")
        bin_patch_apply(wine_variant_source_path, "7983df22cfd97399575652e72c90203597a818a7")
        bin_patch_apply(wine_variant_source_path, "80a17baf20da4620394f8832f6221edf45b7a0f0")
    # REBASE-FIX for 7ea82a02079d16 and 40166848a7944383a for older Wine versions

    if wine_version < Version("1.7.12"):
        bin_patch_apply(wine_variant_source_path, "a326e29144b74c0b3a0261142892192b99607141")

    # wpcap: Fix compilation with recent pcap/pcap.h versions.
    # ERROR: In file included from .../include/winsock2.h:50,
    #        from ... dlls/wpcap/wpcap.c:27:
    #        .../include/ws2def.h:60:19: error: redefinition of ‘struct sockaddr_storage’
    # GIT: https://source.winehq.org/git/wine.git/commitdiff/40c9b46500c3606e966d5404d45b68a48609b6ea
    # FIXED: wine-4.3
    if wine_version >= Version("1.7.25") and wine_version < Version("4.3"):
        patch_apply(wine_variant_source_path, "40c9b46500c3606e966d5404d45b68a48609b6ea")

    # loader/preloader build failure with GCC 10.x optimizing wld_memset() into a memset(3) call.
    # ERROR:  /usr/bin/ld: preloader.o: in function `wld_memset':
    #          .../loader/preloader.c:455: undefined reference to `memset'
    #          collect2: error: ld returned 1 exit status
    #          make[1]: *** [Makefile:335: wine64-preloader] Error 1
    # GIT: https://source.winehq.org/git/wine.git/commitdiff/a6fdf73233d3df4435680d921f68089630bc9c64
    # FIXED: wine-1.5.21
    if wine_version < Version("1.5.21"):
        patch_apply(wine_variant_source_path, "a6fdf73233d3df4435680d921f68089630bc9c64")

    # /usr/bin/ld: ios.o: relocation R_X86_64_32 against symbol `basic_streambuf_char_overflow'
    #          can not be used when making a shared object; recompile with -fPIC
    #       make[1]: *** [Makefile:338: msvcp90.dll.so] Error 2
    # GIT: https://source.winehq.org/git/wine.git/commitdiff/72999eac5b315102d3d7d48aaf6d687ca8ec8d96
    #      https://source.winehq.org/git/wine.git/commitdiff/07a9909ccaea1e9626731c4b259f555877d50bb2
    if wine_version < Version("1.3.35"):
        patch_apply(wine_variant_source_path, "07a9909ccaea1e9626731c4b259f555877d50bb2")
        patch_apply(wine_variant_source_path, "72999eac5b315102d3d7d48aaf6d687ca8ec8d96")

    # libxml2 fixes
    #  ../dlls/msxml3/mxwriter.c:412:60: error: invalid use of incomplete typedef â€˜xmlBufâ€™ {aka â€˜struct _xmlBufâ€™}
    #    412 |                                          This->buffer->conv->use/sizeof(WCHAR));
    #    make[1]: *** [Makefile:215: mxwriter.o] Error 1
    # GIT: https://source.winehq.org/git/wine.git/commitdiff/a4b24978e9dc2e54057552fc2efffbd58cc25d0a
    #      https://source.winehq.org/git/wine.git/commitdiff/197d41156a1a237eb2073524ec36006d6a26ceaa
    #      https://source.winehq.org/git/wine.git/commitdiff/b0f704daaf633d8c713c9212a2ab5dd8a4457e7a
    #      https://source.winehq.org/git/wine.git/commitdiff/d80ee5b3ae36275f813b096576b5beecea2c2d60
    #      https://source.winehq.org/git/wine.git/commitdiff/fda8c2177d01c767c020864370cf9dfaf7b6755d
    #      https://source.winehq.org/git/wine.git/commitdiff/35c7c694294d5461b84e18b17b65a99068050e8b
    if wine_version < Version("1.3.35"):
        patch_apply(wine_variant_source_path, "a4b24978e9dc2e54057552fc2efffbd58cc25d0a")
        patch_apply(wine_variant_source_path, "197d41156a1a237eb2073524ec36006d6a26ceaa")
        patch_apply(wine_variant_source_path, "b0f704daaf633d8c713c9212a2ab5dd8a4457e7a")
        patch_apply(wine_variant_source_path, "d80ee5b3ae36275f813b096576b5beecea2c2d60")
        patch_apply(wine_variant_source_path, "fda8c2177d01c767c020864370cf9dfaf7b6755d")
        patch_apply(wine_variant_source_path, "35c7c694294d5461b84e18b17b65a99068050e8b")

    # ERROR: 'err:msi:MSI_OpenDatabaseW unknown flag (nil)' ... 'err:msi:msi_apply_patch_package
    # Fixup for GCC 9.x/10.x/MinGW
    # GIT: https://source.winehq.org/git/wine.git/commitdiff/cce9a5f124ae6d3fffcc7772cab6523f09a1e3d1
    # FIXED: wine-4.20
    # MSI changes in Wine 1.7.38 and 1.7.39 make patch/rebase way too much effort hence skip fix below
    if wine_version >= Version("1.7.40") and wine_version < Version("4.20"):
        patch_apply(wine_variant_source_path, "cce9a5f124ae6d3fffcc7772cab6523f09a1e3d1")

    # GCC/LLVM Clang 10.x compat fixes: lld-link: error: duplicate symbol: xxx
    # GIT: https://source.winehq.org/git/wine.git/commitdiff/5740b735cdb44fb89a41f3090dcc3dabf360ab41
    #      https://source.winehq.org/git/wine.git/commitdiff/fba65a153759dd60f470fe9a787f074cbf0f7ea8
    #      https://source.winehq.org/git/wine.git/commitdiff/e402fdf364fc76838ba4e11a11fef3c552110639
    #      https://source.winehq.org/git/wine.git/commitdiff/93888fbb3e4d973f5878a0aab16a9d64fb73a764
    #      https://source.winehq.org/git/wine.git/commitdiff/388348ddbf7d138fed3a6fe48bf6666a95ef3528
    #      https://source.winehq.org/git/wine.git/commitdiff/da21c305164c3e585e29e20242afc5a31f91989f
    #      https://source.winehq.org/git/wine.git/commitdiff/44e69405adcdc98d6b0777e6c0acb2697d776ef8
    #      https://source.winehq.org/git/wine.git/commitdiff/4a91eb362666b3af549c48b95e093051756628e0
    #      https://source.winehq.org/git/wine.git/commitdiff/cc7f698b8245a48669d248569e7589ff824f2c70
    #      https://source.winehq.org/git/wine.git/commitdiff/bc51c5d589de709e1d393b58b0cc5985c78061ac
    #      https://source.winehq.org/git/wine.git/commitdiff/453980e13015e20dd551531be69b3361b63f22b1
    #      https://source.winehq.org/git/wine.git/commitdiff/c13d58780f78393571dfdeb5b4952e3dcd7ded90
    if wine_version == Version("5.0"):
        patch_apply(wine_variant_source_path, "5740b735cdb44fb89a41f3090dcc3dabf360ab41")
        patch_apply(wine_variant_source_path, "fba65a153759dd60f470fe9a787f074cbf0f7ea8")
        patch_apply(wine_variant_source_path, "e402fdf364fc76838ba4e11a11fef3c552110639")
        patch_apply(wine_variant_source_path, "93888fbb3e4d973f5878a0aab16a9d64fb73a764")
        patch_apply(wine_variant_source_path, "388348ddbf7d138fed3a6fe48bf6666a95ef3528")
        patch_apply(wine_variant_source_path, "da21c305164c3e585e29e20242afc5a31f91989f")
        patch_apply(wine_variant_source_path, "44e69405adcdc98d6b0777e6c0acb2697d776ef8")
        patch_apply(wine_variant_source_path, "4a91eb362666b3af549c48b95e093051756628e0")
        patch_apply(wine_variant_source_path, "cc7f698b8245a48669d248569e7589ff824f2c70")
        patch_apply(wine_variant_source_path, "bc51c5d589de709e1d393b58b0cc5985c78061ac")
        patch_apply(wine_variant_source_path, "453980e13015e20dd551531be69b3361b63f22b1")
        patch_apply(wine_variant_source_path, "c13d58780f78393571dfdeb5b4952e3dcd7ded90")

    # ERROR: /usr/bin/ld: chain.o:../dlls/crypt32/crypt32_private.h:155: multiple definition of `hInstance';
    #        cert.o:../dlls/crypt32/crypt32_private.h:155: first defined here
    # Fixup for GCC 10.x: https://gcc.gnu.org/gcc-10/porting_to.html#c
    # Pass '-fcommon' to CFLAGS to avoid applying a dozen commits to various components starting with
    # GIT: https://source.winehq.org/git/wine.git/commit/5740b735cdb44fb89a41f3090dcc3dabf360ab41
    if wine_version < Version("5.1"):
        wine_cflags_common += " -fcommon"

    # mpg123: Fix compilation with clang.
    # GIT: https://source.winehq.org/git/wine.git/commitdiff/981306c1f01112719850439a74e13693dfa6d3a4
    if wine_version == Version("6.20"):
        patch_apply(wine_variant_source_path, "981306c1f01112719850439a74e13693dfa6d3a4")

    # opencl: Fix compilation on MSVC targets.
    # GIT: https://source.winehq.org/git/wine.git/commitdiff/a91d6e9eae71a0ed0ddeac3d571704fd3e47b3c5
    if wine_version >= Version("6.5") and wine_version < Version("6.19"):
        patch_apply(wine_variant_source_path, "a91d6e9eae71a0ed0ddeac3d571704fd3e47b3c5")

    # ERROR: tools/wrc/wrc -u -o dlls/gdi32/gdi32.res -m64 --nostdinc --po-dir=po -Idlls/gdi32 \
    #        -I/usr/lib64/glib-2.0/include -I/usr/include/sysprof-4 -I/usr/include/libxml2 -D__WINESRC__ \
    #        -pthread -D_GDI32_ -D_UCRT .../dlls/gdi32/gdi32.rc
    #        tools/wrc/wrc: invalid option -- 'p'
    #        tools/wrc/wrc: invalid option -- 't'
    # URL: https://bugs.winehq.org/show_bug.cgi?id=50811
    # GIT: https://source.winehq.org/git/wine.git/commitdiff/4f04994ef47b5077e13c1b770ed0f818f59adcd5
    # FIXED: wine-6.6
    if wine_version <= Version("6.5"):
        # needed for erroneous FREETYPE_CFLAGS
        my_env["PKG_CONFIG"] = create_config_wrapper(my_env["PKG_CONFIG"], "--cflags freetype2", "-pthread")
        # needed for erroneous FONTCONFIG_CFLAGS
        # NOTE: The second wrapper will call the first wrapper which in turn will call the original pkg-config
        my_env["PKG_CONFIG"] = create_config_wrapper(my_env["PKG_CONFIG"], "--cflags fontconfig", "-pthread")
        # needed for erroneous FREETYPEINCL
        if wine_version < Version("1.5.2"):
            # original config tool is provided with full path so wrapper doesn't create a recursion
            wrapper_path = os.path.dirname( create_config_wrapper(shutil.which("freetype-config"), "--cflags", "-pthread"))
            # inject wrapper into PATH
            my_env["PATH"] = "{0}:{1}".format(wrapper_path, my_env["PATH"])

    # ERROR: winebuild: llvm-mingw-20211002-ucrt-ubuntu-18.04-x86_64/bin/x86_64-w64-mingw32-dlltool failed with status 1
    #        make: *** [Makefile:1843: dlls/advpack/libadvpack.delay.a] Error 1
    # GIT: https://source.winehq.org/git/wine.git/commitdiff/f29d4a43e203303c2d4aaec388f281d01f17764c
    # FIXED: wine-5.3
    if wine_version == Version("5.2"):
        patch_apply(wine_variant_source_path, "f29d4a43e203303c2d4aaec388f281d01f17764c")

    # ERROR: /usr/bin/ld: dlls/dnsapi/libresolv.o: in function `resolv_query':
    #        .../dlls/dnsapi/libresolv.c:897: undefined reference to `ns_initparse'
    #       /usr/bin/ld: .../dlls/dnsapi/libresolv.c:769: undefined reference to `ns_parserr'
    # URL: https://bugs.winehq.org/show_bug.cgi?id=51635
    # GIT: https://source.winehq.org/git/wine.git/commitdiff/a3bbf5137707abb548ff642826992b7069bef1de
    # FIXED: wine-6.16
    if wine_version >= Version("6.6") and wine_version < Version("6.16"):
        patch_apply(wine_variant_source_path, "a3bbf5137707abb548ff642826992b7069bef1de")

    # ERROR: ../../tools/winegcc/winegcc -o ntdll.dll.so -B../../tools/winebuild -m64 -fasynchronous-unwind-tables -shared
    #        mainline-src-1.7.45/dlls/ntdll/ntdll.spec \
    #        ...
    #        /usr/bin/ld: signal_x86_64.o: in function `libunwind_virtual_unwind':
    #        mainline-src-1.7.45/dlls/ntdll/signal_x86_64.c:1554: undefined reference to `_Ux86_64_getcontext'
    # GIT: https://source.winehq.org/git/wine.git/commitdiff/36a9f9dd05c3b9df77c44c91663e9bd6cae1c848
    if wine_version == Version("1.7.45"):
        patch_apply(wine_variant_source_path, "36a9f9dd05c3b9df77c44c91663e9bd6cae1c848")

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

        # Copy the PDB files into install DESTDIR.
        run_command("find {0} -type f -name '*.pdb' -exec cp -v '{{}}' '{1}/{2}' \;".format(
            wine_build_target_arch64_path, wine_install_prefix, wine_install_arch64_pe_dir))

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

        # Make a lib32 symlink to lib to allow 'winegcc -m32'.
        # Since Wine 6.8, libraries are installed into architecture-specific subdirectories.
        if wine_version < Version("6.8"):
            os.symlink("lib", "{0}/lib32".format(wine_install_prefix))

        # Copy the PDB files into install DESTDIR.
        run_command("find {0} -type f -name '*.pdb' -exec cp -v '{{}}' '{1}/{2}' \;".format(
            wine_build_target_arch32_path, wine_install_prefix, wine_install_arch32_pe_dir))

    print(
    """
    Run the following command to register this Wine variant in environment
    ----------------------------------------------------------------------
    export PATH={0}/bin/:$PATH
    ----------------------------------------------------------------------
    """.format( wine_install_prefix))

if __name__== "__main__":
    main()
