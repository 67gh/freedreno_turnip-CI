#!/usr/bin/env bash
# Linux x86_64 -> Android ARM64/KGSL. Run with bash, not sh.
set -Eeuo pipefail
export LC_ALL=C
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
MESA_COMMIT=9cb4a4fb42a8a067cd2250e116c6a605b527a093
MESA_SHA256=a54723117626a3dcd8c36cbaa0a4dfc4bffa1670560978fc8ad17bdbfbd9e01a
NDK_VERSION=android-ndk-r29
NDK_SHA256=4abbbcdc842f3d4879206e9695d52709603e52dd68d3c1fff04b3b5e7a308ecf
API=34
LIBRARY=vulkan.freedreno.so
ARCHIVE=turnip_a660_final_adrenotools.zip
RUN_DIR=''
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
on_error() {
    local status=$? line=$1
    printf 'Build failed (exit %s, line %s). Logs: %s\n' "$status" "$line" "${RUN_DIR:-not created}" >&2
    exit "$status"
}
trap 'on_error "$LINENO"' ERR

download() {
    local url=$1 destination=$2 checksum=$3
    curl --fail --location --retry 3 --connect-timeout 30 --max-time 1800 \
        --silent --show-error "$url" --output "$destination.part"
    printf '%s  %s\n' "$checksum" "$destination.part" | sha256sum --check --status
    mv -- "$destination.part" "$destination"
}
checked_archive() {
    local local_file=$1 url=$2 destination=$3 checksum=$4
    if [[ -n "$local_file" ]]; then
        cp -- "$local_file" "$destination"
        printf '%s  %s\n' "$checksum" "$destination" | sha256sum --check --status
    else
        download "$url" "$destination" "$checksum"
    fi
    python3 "$SCRIPT_DIR/scripts/extract_archive.py" "$destination" "$RUN_DIR" \
        2>&1 | tee "$destination.check.log"
}
preflight() {
    [[ $(uname -s) == Linux && $(uname -m) == x86_64 ]] || fail 'Linux x86_64 is required.'
    local tool missing=0
    for tool in python3 curl sha256sum patchelf pkg-config cc c++ ar strip flex bison glslangValidator; do
        if ! command -v "$tool" >/dev/null 2>&1; then
            printf 'Missing tool: %s\n' "$tool" >&2
            missing=1
        fi
    done
    (( missing == 0 )) || fail 'Install the dependencies listed in README.md.'
    [[ ${JOBS:-4} =~ ^[1-9][0-9]*$ ]] || fail 'JOBS must be a positive integer.'
    [[ "$SCRIPT_DIR" != *"'"* && "$SCRIPT_DIR" != *$'\n'* && "$SCRIPT_DIR" != *'\'* ]] || fail 'Unsupported characters in project path.'
    local patch_files
    patch_files=$(find "$SCRIPT_DIR/patches" -type f ! -name .gitkeep -print)
    [[ -z "$patch_files" ]] || fail 'patches/ contains unapplied files; integrate and review the series explicitly.'
}
prepare() {
    mkdir -p -- "$SCRIPT_DIR/turnip_workdir"
    RUN_DIR=$(mktemp -d "$SCRIPT_DIR/turnip_workdir/run-XXXXXXXX")
    if [[ -n ${GITHUB_OUTPUT:-} ]]; then
        printf 'run_dir=%s\n' "$RUN_DIR" >> "$GITHUB_OUTPUT"
    fi
    printf 'Working directory: %s\n' "$RUN_DIR"
    local native_c native_cpp native_ar native_strip pkgconfig
    native_c=$(command -v cc); native_cpp=$(command -v c++)
    native_ar=$(command -v ar); native_strip=$(command -v strip)
    pkgconfig=$(command -v pkg-config)
    unset CC CXX AR STRIP CFLAGS CXXFLAGS CPPFLAGS LDFLAGS PKG_CONFIG_PATH PKG_CONFIG_LIBDIR
    python3 -m venv "$RUN_DIR/venv"
    "$RUN_DIR/venv/bin/python" -m pip install --disable-pip-version-check \
        meson==1.9.1 ninja==1.13.0 Mako==1.3.10 MarkupSafe==3.0.3 \
        packaging==25.0 PyYAML==6.0.3 2>&1 | tee "$RUN_DIR/python.log"
    export PATH="$RUN_DIR/venv/bin:$PATH"
    checked_archive "${NDK_ARCHIVE:-}" \
        "https://dl.google.com/android/repository/$NDK_VERSION-linux.zip" "$RUN_DIR/ndk.zip" "$NDK_SHA256"
    checked_archive "${MESA_ARCHIVE:-}" \
        "https://gitlab.freedesktop.org/mesa/mesa/-/archive/$MESA_COMMIT/mesa-$MESA_COMMIT.zip" "$RUN_DIR/mesa.zip" "$MESA_SHA256"
    SOURCE="$RUN_DIR/mesa-$MESA_COMMIT"
    NDK="$RUN_DIR/$NDK_VERSION/toolchains/llvm/prebuilt/linux-x86_64/bin"
    [[ -s "$SOURCE/meson.build" && -s "$SOURCE/VERSION" ]] || fail 'Invalid Mesa archive layout.'
    local tool
    for tool in "aarch64-linux-android$API-clang" "aarch64-linux-android$API-clang++" llvm-ar llvm-strip llvm-readelf ld.lld; do
        [[ -x "$NDK/$tool" ]] || fail "NDK tool missing or not executable: $tool"
    done
    "$NDK/aarch64-linux-android$API-clang" --version > "$RUN_DIR/compiler.log"
    mkdir "$RUN_DIR/empty-pkgconfig"
    cat > "$RUN_DIR/android-aarch64.ini" <<EOF
[binaries]
c = '$NDK/aarch64-linux-android$API-clang'
cpp = '$NDK/aarch64-linux-android$API-clang++'
ar = '$NDK/llvm-ar'
strip = '$NDK/llvm-strip'
c_ld = 'lld'
cpp_ld = 'lld'
pkg-config = ['env', 'PKG_CONFIG_LIBDIR=$RUN_DIR/empty-pkgconfig', 'PKG_CONFIG_PATH=', '$pkgconfig']
[host_machine]
system = 'android'
cpu_family = 'aarch64'
cpu = 'armv8'
endian = 'little'
[built-in options]
c_args = ['-O3']
cpp_args = ['-O3']
c_link_args = ['-Wl,-z,max-page-size=16384']
cpp_link_args = ['-static-libstdc++', '-Wl,-z,max-page-size=16384']
EOF
    cat > "$RUN_DIR/native.ini" <<EOF
[binaries]
c = '$native_c'
cpp = '$native_cpp'
ar = '$native_ar'
strip = '$native_strip'
pkg-config = '$pkgconfig'
EOF
}
build() {
    meson setup "$RUN_DIR/build" "$SOURCE" \
        --cross-file "$RUN_DIR/android-aarch64.ini" --native-file "$RUN_DIR/native.ini" \
        --wrap-mode=nofallback -Dbuildtype=release -Db_ndebug=true -Db_lto=false \
        -Dplatforms=android -Dplatform-sdk-version="$API" -Dandroid-stub=true \
        -Dgallium-drivers= -Dvulkan-drivers=freedreno -Dfreedreno-kmds=kgsl \
        -Dvulkan-beta=false -Degl=disabled -Dgbm=disabled -Dglx=disabled \
        -Dllvm=disabled -Dshared-llvm=disabled -Dzstd=disabled \
        -Dbuild-tests=false -Dandroid-libbacktrace=disabled \
        2>&1 | tee "$RUN_DIR/meson.log"
    ninja -C "$RUN_DIR/build" -j "${JOBS:-4}" \
        src/freedreno/vulkan/libvulkan_freedreno.so 2>&1 | tee "$RUN_DIR/ninja.log"
}
package() {
    mkdir "$RUN_DIR/package"
    cp -- "$RUN_DIR/build/src/freedreno/vulkan/libvulkan_freedreno.so" "$RUN_DIR/package/$LIBRARY"
    "$NDK/llvm-strip" --strip-unneeded "$RUN_DIR/package/$LIBRARY"
    patchelf --page-size 16384 --set-soname "$LIBRARY" "$RUN_DIR/package/$LIBRARY"
    "$NDK/llvm-readelf" -h -l -d "$RUN_DIR/package/$LIBRARY" > "$RUN_DIR/elf.log"
    python3 "$SCRIPT_DIR/scripts/package_driver.py" \
        --library "$RUN_DIR/package/$LIBRARY" --version-file "$SOURCE/VERSION" \
        --commit "$MESA_COMMIT" --source-sha256 "$MESA_SHA256" --ndk-sha256 "$NDK_SHA256" \
        --output "$RUN_DIR/$ARCHIVE" --api "$API"
    if [[ -n ${GITHUB_OUTPUT:-} ]]; then
        printf 'package=%s\n' "$RUN_DIR/$ARCHIVE" >> "$GITHUB_OUTPUT"
    fi
    printf 'Build and package checks passed: %s\n' "$RUN_DIR/$ARCHIVE"
}
main() {
    (( $# <= 1 )) || fail 'Too many arguments.'
    case ${1:-} in
        --help) printf '%s\n' 'Usage: bash turnip_builder.sh [--check|--help]' 'JOBS=4; NDK_ARCHIVE/MESA_ARCHIVE: optional checksum-verified local ZIPs.'; return ;;
        --check) preflight; printf 'Host dependency checks passed.\n'; return ;;
        '') ;;
        *) fail "Unknown argument: $1" ;;
    esac
    preflight
    prepare
    build
    package
}
if [[ ${BASH_SOURCE[0]} == "$0" ]]; then
    main "$@"
fi
