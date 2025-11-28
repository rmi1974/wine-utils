# Docker image to build 32-bit and 64-bit Wine (shared WoW64)
# SPDX-License-Identifier: MIT
FROM fedora:42

# --- Base development dependencies
RUN dnf -y install \
    dnf-plugins-core \
    gcc gcc-c++ make flex bison git filterdiff which file tree curl wget \
    autoconf automake libtool \
    && dnf clean all && rm -rf /var/cache/dnf

# --- Locale (English UTF-8) ---
RUN dnf -y install \
    glibc-langpack-en \
    && dnf clean all && rm -rf /var/cache/dnf
ENV LANG=en_US.UTF-8 \
    LC_ALL=en_US.UTF-8

# --- Python environment tools ---
RUN dnf -y install \
    python3 python3-pip \
    && pip install --no-cache-dir uv \
    && dnf clean all && rm -rf /var/cache/dnf

# --- Runtime X11 support ---
RUN dnf -y install \
    xorg-x11-server-Xvfb \
    xorg-x11-xauth \
    && dnf clean all && rm -rf /var/cache/dnf

# --- Fonts for Wine dialogs ---
RUN dnf -y install \
    dejavu-sans-fonts \
    dejavu-serif-fonts \
    liberation-fonts \
    google-noto-sans-fonts \
    xorg-x11-fonts-Type1 \
    xorg-x11-fonts-misc \
    && dnf clean all && rm -rf /var/cache/dnf

# Rebuild font cache
RUN fc-cache -fv

# --- Build dependencies for Wine ---
RUN dnf -y install \
    alsa-lib alsa-lib.i686 \
    alsa-lib-devel.x86_64 alsa-lib-devel.i686 \
    brotli-devel.x86_64 brotli-devel.i686 \
    bzip2-devel.x86_64 bzip2-devel.i686 \
    cups-libs cups-libs.i686 \
    cups-devel.x86_64 cups-devel.i686 \
    dbus dbus-libs.i686 \
    dbus-devel.x86_64 dbus-devel.i686 \
    egl-wayland-devel.x86_64 egl-wayland-devel.i686 \
    ffmpeg-free-devel \
    fontconfig fontconfig.i686 \
    fontconfig-devel.x86_64 fontconfig-devel.i686 \
    freetype freetype.i686 \
    freetype-devel.x86_64 freetype-devel.i686 \
    glibc-devel.x86_64 glibc-devel.i686 \
    gnutls gnutls.i686 \
    gnutls-devel.x86_64 gnutls-devel.i686 \
    graphite2-devel.x86_64 graphite2-devel.i686 \
    gsm-devel.x86_64 gsm-devel.i686 \
    harfbuzz-devel.x86_64 harfbuzz-devel.i686 \
    jack-audio-connection-kit jack-audio-connection-kit.i686 \
    jack-audio-connection-kit-devel.x86_64 jack-audio-connection-kit-devel.i686 \
    jxrlib jxrlib.i686 \
    jxrlib-devel.x86_64 jxrlib-devel.i686 \
    krb5-libs krb5-libs.i686 \
    krb5-devel.x86_64 krb5-devel.i686 \
    lcms2 lcms2.i686 \
    lcms2-devel.x86_64 lcms2-devel.i686 \
    libavutil-free-devel \
    libavformat-free-devel \
    libavcodec-free-devel \
    libcom_err-devel.x86_64 libcom_err-devel.i686 \
    libexif-devel.x86_64 libexif-devel.i686 \
    libFAudio libFAudio.i686 \
    libFAudio-devel.x86_64 libFAudio-devel.i686 \
    libgcc.i686 \
    libgphoto2 libgphoto2.i686 \
    libgphoto2-devel.x86_64 libgphoto2-devel.i686 \
    libjpeg-turbo libjpeg-turbo.i686 \
    libjpeg-turbo-devel.x86_64 libjpeg-turbo-devel.i686 \
    libnetapi-devel.x86_64 libnetapi-devel.i686 \
    libpcap libpcap.i686 \
    libpcap-devel.x86_64 libpcap-devel.i686 \
    libpng libpng.i686 \
    libpng-devel.x86_64 libpng-devel.i686 \
    libtiff-devel.x86_64 libtiff-devel.i686 \
    libusb1 libusb1.i686 \
    libusb1-devel.x86_64 libusb1-devel.i686 \
    libv4l libv4l.i686 \
    libv4l-devel.x86_64 libv4l-devel.i686 \
    libvkd3d libvkd3d.i686 \
    libvkd3d-devel.x86_64 libvkd3d-devel.i686 \
    libvkd3d-shader-devel.x86_64 libvkd3d-shader-devel.i686 \
    libX11 libX11.i686 \
    libX11-devel.x86_64 libX11-devel.i686 \
    libxkbcommon-devel.x86_64 libxkbcommon-devel.i686 \
    libXcomposite libXcomposite.i686 \
    libXcomposite-devel.x86_64 libXcomposite-devel.i686 \
    libXcursor libXcursor.i686 \
    libXcursor-devel.x86_64 libXcursor-devel.i686 \
    libXext libXext.i686 \
    libXext-devel.x86_64 libXext-devel.i686 \
    libXfixes libXfixes.i686 \
    libXfixes-devel.x86_64 libXfixes-devel.i686 \
    libXi libXi.i686 \
    libXi-devel.x86_64 libXi-devel.i686 \
    libXinerama libXinerama.i686 \
    libXinerama-devel.x86_64 libXinerama-devel.i686 \
    libXrandr libXrandr.i686 \
    libXrandr-devel.x86_64 libXrandr-devel.i686 \
    libXrender libXrender.i686 \
    libXrender-devel.x86_64 libXrender-devel.i686 \
    libXxf86vm libXxf86vm.i686 \
    libXxf86vm-devel.x86_64 libXxf86vm-devel.i686 \
    libxml2 libxml2.i686 \
    libxml2-devel.x86_64 libxml2-devel.i686 \
    libxslt libxslt.i686 \
    libxslt-devel.x86_64 libxslt-devel.i686 \
    mesa-libGL mesa-libGL.i686 \
    mesa-libGL-devel.x86_64 mesa-libGL-devel.i686 \
    mesa-libGLU-devel.x86_64 mesa-libGLU-devel.i686 \
    mesa-vulkan-drivers.x86_64 mesa-vulkan-drivers.i686 \
    mpg123 \
    mpg123-devel.x86_64 mpg123-devel.i686 \
    ncurses ncurses-libs.i686 \
    ncurses-devel.x86_64 ncurses-devel.i686 \
    ocl-icd-devel.x86_64 ocl-icd-devel.i686 \
    openldap-devel.x86_64 openldap-devel.i686 \
    pcsc-lite-devel.x86_64 pcsc-lite-devel.i686 \
    pulseaudio-libs pulseaudio-libs.i686 \
    pulseaudio-libs-devel.x86_64 pulseaudio-libs-devel.i686 \
    sane-backends sane-backends-libs.i686 \
    sane-backends-devel.x86_64 sane-backends-devel.i686 \
    sdl2-compat sdl2-compat.i686 \
    sdl2-compat-devel.x86_64 sdl2-compat-devel.i686 \
    systemd-devel.x86_64 systemd-devel.i686 \
    vulkan-headers \
    vulkan-loader-devel.x86_64 vulkan-loader-devel.i686 \
    wayland-devel.x86_64 wayland-devel.i686 \
    xorg-x11-proto-devel \
    zlib-ng-compat zlib-ng-compat.i686 \
    zlib-ng-compat-devel.x86_64 zlib-ng-compat-devel.i686 \
    && dnf clean all && rm -rf /var/cache/dnf

# --- gstreamer (multilib conflicts workaround) ---
RUN dnf -y install \
    glib2 glib2.i686 \
    glib2-devel.x86_64 \
    libunwind-devel.x86_64 libunwind-devel.i686 \
    elfutils-devel.x86_64 elfutils-devel.i686 \
    sysprof-devel.x86_64 sysprof-devel.i686 \
    pcre2-devel.x86_64 pcre2-devel.i686 \
    libffi-devel.x86_64 libffi-devel.i686 \
    orc-devel.x86_64 orc-devel.i686 \
    libzstd-devel.x86_64 libzstd-devel.i686 \
    gstreamer1 gstreamer1.i686 \
    gstreamer1-devel.x86_64 \
    gstreamer1-plugins-base gstreamer1-plugins-base.i686 \
    gstreamer1-plugins-base-devel.x86_64 gstreamer1-plugins-base-devel.i686
# UGLY HACK to force install i686 devel RPMs that conflict with x86_64 ---
#  - file /usr/share/gir-1.0/GLib-2.0.gir conflicts between attempted installs of glib2-devel-2.84.4-1.fc42.i686 and glib2-devel-2.84.4-1.fc42.x86_64
#  - file /usr/share/gir-1.0/Gst-1.0.gir conflicts between attempted installs of gstreamer1-devel-1.26.7-1.fc42.i686 and gstreamer1-devel-1.26.7-1.fc42.x86_64
RUN dnf download --arch=i686 glib2-devel gstreamer1-devel
RUN rpm -ivh --replacefiles glib2-devel-*.i686.rpm gstreamer1-devel-*.i686.rpm

# --- UnixODBC (multilib conflicts workaround)
#  - file /usr/include/unixodbc.h conflicts between attempted installs of unixODBC-devel-2.3.12-6.fc42.i686 and unixODBC-devel-2.3.12-6.fc42.x86_64
RUN dnf install -y unixODBC-devel unixODBC.i686
RUN dnf download --arch=i686 unixODBC-devel
RUN rpm -ivh --replacefiles unixODBC-devel-*.i686.rpm

# --- NTLM support ---
RUN dnf -y install \
    samba-winbind samba-winbind-clients \
    && dnf clean all && rm -rf /var/cache/dnfll

# --- Prompt customization ---
RUN echo 'export PROMPT_COMMAND="PS1=\"(wine-docker) \u:\w\\$ \""' > /etc/profile.d/prompt.sh

# --- Host user injection ---
ARG USER_ID
ARG GROUP_ID
ARG USER_NAME

RUN groupadd -g $GROUP_ID $USER_NAME \
    && useradd -m -u $USER_ID -g $GROUP_ID -s /bin/bash $USER_NAME

USER $USER_NAME
WORKDIR /home/$USER_NAME

# Force login shell so /etc/profile.d/* is sourced
CMD ["/bin/bash", "-l"]
