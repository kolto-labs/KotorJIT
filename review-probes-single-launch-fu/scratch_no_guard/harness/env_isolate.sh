# Strip the real desktop session out of a headless game process's environment.
#
# Every harness script sets DISPLAY to its own Xvfb, but until now nothing
# touched DBUS_SESSION_BUS_ADDRESS or WAYLAND_DISPLAY -- so a wine process
# launched from an interactive KDE/Wayland shell inherited the REAL session bus.
# Wine's file dialogs and some DirectX/DXVK paths can go through
# xdg-desktop-portal for things like screen capture, and a portal call against
# the real session bus registers a session against the real desktop, not the
# throwaway Xvfb one -- invisible here, but it shows up as a stray row in the
# host's own screen-share/remote-desktop panel. Sourced, not run: call
# isolate_desktop_env after exporting DISPLAY and before `wine ...`.
isolate_desktop_env() {
  unset DBUS_SESSION_BUS_ADDRESS WAYLAND_DISPLAY XDG_SESSION_TYPE \
        XDG_SESSION_DESKTOP XDG_CURRENT_DESKTOP XDG_SESSION_PATH \
        XDG_SESSION_CLASS XDG_SESSION_ID QT_WAYLAND_RECONNECT SDL_VIDEODRIVER \
        KONSOLE_DBUS_SERVICE KONSOLE_DBUS_SESSION KONSOLE_DBUS_WINDOW \
        KONSOLE_DBUS_ACTIVATION_COOKIE PROTON_ENABLE_WAYLAND
  # SDL and DXVK both probe Wayland-vs-X11 from these; forcing X11 keeps the
  # child from trying to reach a compositor it has no business talking to.
  export SDL_VIDEODRIVER=x11
}
