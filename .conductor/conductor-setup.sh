#!/bin/zsh

# Symlink all .env* files from repo root to workspace, preserving directory structure

# Symlink root-level .env* files (if any exist)
for f in "$CONDUCTOR_ROOT_PATH"/.env*(.N); do
    ln -sf "$f" .
done

# Symlink .env* files from subdirectories (web/, worker/)
for dir in web worker; do
    if [ -d "$CONDUCTOR_ROOT_PATH/$dir" ]; then
        mkdir -p "$dir"
        for f in "$CONDUCTOR_ROOT_PATH/$dir"/.env*(.N); do
            ln -sf "$f" "$dir/"
        done
    fi
done
