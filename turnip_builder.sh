#!/bin/bash -e

green='\033[0;32m'
red='\033[0;31m'
nocolor='\033[0m'
deps="meson ninja patchelf unzip curl pip flex bison zip glslang glslangValidator"
workdir="$(pwd)/turnip_workdir"
ndkver="android-ndk-r29"
ndk="$workdir/$ndkver/toolchains/llvm/prebuilt/linux-x86_64/bin"
sdkver="34"
# main = dernière version Mesa disponible, garantit Vulkan 1.4
mesasrc="https://gitlab.freedesktop.org/mesa/mesa/-/archive/main/mesa-main.zip"

clear

run_all(){
        check_deps
        prepare_workdir
        build_lib_for_android
        port_lib_for_adrenotools
}

check_deps(){
        echo "Checking system for required Dependencies ..."
                for deps_chk in $deps;
                        do
                                sleep 0.25
                                if command -v "$deps_chk" >/dev/null 2>&1 ; then
                                        echo -e "$green - $deps_chk found $nocolor"
                                else
                                        echo -e "$red - $deps_chk not found, can't countinue. $nocolor"
                                        deps_missing=1
                                fi;
                        done
                if [ "$deps_missing" == "1" ]
                        then echo "Please install missing dependencies" && exit 1
                fi
        echo "Installing python Mako dependency (if missing) ..." $'\n'
                pip install mako &> /dev/null
}

prepare_workdir(){
        echo "Preparing work directory ..." $'\n'
                mkdir -p "$workdir" && cd "$_"
        echo "Downloading android-ndk ..." $'\n'
                curl https://dl.google.com/android/repository/"$ndkver"-linux.zip --output "$ndkver"-linux.zip &> /dev/null
        echo "Extracting android-ndk ..." $'\n'
                unzip "$ndkver"-linux.zip &> /dev/null
        echo "Downloading mesa source (main / latest) ..." $'\n'
                curl -L "$mesasrc" --output mesa-main.zip
        echo "Extracting mesa source ..." $'\n'
                unzip mesa-main.zip &> /dev/null
                cd mesa-main
}

build_lib_for_android(){
        mkdir -p "$workdir/bin"
        ln -sf "$ndk/clang" "$workdir/bin/cc"
        ln -sf "$ndk/clang++" "$workdir/bin/c++"
        export PATH="$workdir/bin:$ndk:$PATH"
        export CC=clang
        export CXX=clang++
        export AR=llvm-ar
        export RANLIB=llvm-ranlib
        export STRIP=llvm-strip
        export OBJDUMP=llvm-objdump
        export OBJCOPY=llvm-objcopy
        export CFLAGS="-O3"
        export CXXFLAGS="-O3"
        export LDFLAGS="-fuse-ld=lld -Wl,-z,max-page-size=16384 -flto=thin"

        cat <<EOF >"android-aarch64.txt"
[binaries]
ar = '$ndk/llvm-ar'
c = ['ccache', '$ndk/aarch64-linux-android$sdkver-clang']
cpp = ['ccache', '$ndk/aarch64-linux-android$sdkver-clang++', '-fno-exceptions', '-fno-unwind-tables', '-fno-asynchronous-unwind-tables', '--start-no-unused-arguments', '-static-libstdc++', '--end-no-unused-arguments']
c_ld = '$ndk/ld.lld'
cpp_ld = '$ndk/ld.lld'
strip = '$ndk/aarch64-linux-android-strip'
pkg-config = ['env', 'PKG_CONFIG_LIBDIR=$ndk/pkg-config', '/usr/bin/pkg-config']

[host_machine]
system = 'android'
cpu_family = 'aarch64'
cpu = 'armv8'
endian = 'little'
EOF

        cat <<EOF >"native.txt"
[build_machine]
c = ['ccache', 'clang']
cpp = ['ccache', 'clang++']
ar = 'llvm-ar'
strip = 'llvm-strip'
c_ld = 'ld.lld'
cpp_ld = 'ld.lld'
system = 'linux'
cpu_family = 'x86_64'
cpu = 'x86_64'
endian = 'little'
EOF

        meson setup build-android-aarch64 \
                --cross-file "android-aarch64.txt" \
                --native-file "native.txt" \
                -Dbuildtype=release \
                -Db_ndebug=true \
                -Db_lto=true \
                -Db_lto_mode=thin \
                -Dallow-broken-lto=true \
                -Dplatforms=android \
                -Dplatform-sdk-version="$sdkver" \
                -Dandroid-stub=true \
                -Dgallium-drivers= \
                -Dvulkan-drivers=freedreno \
                -Dvulkan-beta=true \
                -Dfreedreno-kmds=kgsl \
                -Dstrip=true \
                -Degl=disabled &> "$workdir/meson_log"

        ninja -C build-android-aarch64 &> "$workdir/ninja_log"

        if ! [ -a "$workdir"/mesa-main/build-android-aarch64/src/freedreno/vulkan/libvulkan_freedreno.so ]; then
                echo -e "$red Build failed! Check meson_log / ninja_log $nocolor" && exit 1
        fi
}

port_lib_for_adrenotools(){
        libname=vulkan.freedreno_a660_final.so
        cp "$workdir"/mesa-main/build-android-aarch64/src/freedreno/vulkan/libvulkan_freedreno.so "$workdir"/$libname
        cd "$workdir"
        patchelf --set-soname $libname $libname
        cat <<EOF > "meta.json"
{
        "schemaVersion": 1,
        "name": "Turnip main - A660 MAX PERF - Vulkan 1.4 - $(date +%Y%m%d)",
        "description": "Release build, -O3 + full LTO, 16KB page-aligned, latest Mesa main, tuned for Adreno 660",
        "author": "custom",
        "packageVersion": "1",
        "vendor": "Mesa",
        "driverVersion": "main-$(date +%Y%m%d)",
        "minApi": $sdkver,
        "libraryName": "$libname"
}
EOF
        zip -9 "$workdir"/turnip_a660_final_adrenotools.zip $libname meta.json &> /dev/null
        if ! [ -a "$workdir"/turnip_a660_final_adrenotools.zip ];
                then echo -e "$red-Packing failed!$nocolor" && exit 1
                else echo -e "$green-All done:$nocolor" && echo "$workdir"/turnip_a660_final_adrenotools.zip
        fi
}

run_all
