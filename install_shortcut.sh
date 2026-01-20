#!/bin/bash

# Define paths
APP_NAME="FreeThullu Music Player"
EXEC_NAME="musicplayer-gui"
ICON_NAME="freethullu-icon.png"
DESKTOP_FILE="freethullu.desktop"
ICON_URL="https://raw.githubusercontent.com/thiagofmendonca/cli-music-player/main/musicplayer/assets/frame1.png"

# Find executable
EXEC_PATH=$(which $EXEC_NAME)

if [ -z "$EXEC_PATH" ]; then
    echo "Error: '$EXEC_NAME' not found in PATH."
    echo "Make sure ~/.local/bin is in your PATH."
    exit 1
fi

echo "Found executable at: $EXEC_PATH"

# Setup Directories
# We save the icon in a generic location that is safe
ICON_DIR="$HOME/.local/share/icons"
APP_DIR="$HOME/.local/share/applications"

mkdir -p "$ICON_DIR"
mkdir -p "$APP_DIR"

ICON_FULL_PATH="$ICON_DIR/$ICON_NAME"

# Download Icon
echo "Downloading icon to $ICON_FULL_PATH..."
wget -q -O "$ICON_FULL_PATH" "$ICON_URL"

if [ $? -ne 0 ]; then
    echo "Warning: Failed to download icon. Using generic."
    ICON_ENTRY="Icon=utilities-terminal"
else
    # Use ABSOLUTE path to ensure it works
    ICON_ENTRY="Icon=$ICON_FULL_PATH"
fi

# Create .desktop file
echo "Creating $DESKTOP_FILE..."
cat > "$APP_DIR/$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=$APP_NAME
Comment=A powerful hybrid music player with animated Cthulhu
Exec=$EXEC_PATH
$ICON_ENTRY
Terminal=false
Categories=Audio;Music;Player;
Keywords=music;player;mpv;youtube;
StartupWMClass=FreeThullu Music Player v1.0.6 (GUI)
EOF

# Refresh database and KDE cache
update-desktop-database "$APP_DIR" 2>/dev/null
# Try to force KDE to update icon cache if kbuildsycoca6 exists (KDE 6) or kbuildsycoca5
if command -v kbuildsycoca6 &> /dev/null; then
    kbuildsycoca6 --noincremental
elif command -v kbuildsycoca5 &> /dev/null; then
    kbuildsycoca5 --noincremental
fi

echo "Success! Shortcut created/updated."