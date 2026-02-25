#!/bin/bash

# set projects dir
TARGET_DIR="projects"


mkdir -p "$TARGET_DIR"

while read repo; do
  git clone "$repo" "$TARGET_DIR/$(basename "$repo" .git)"
done < repos.txt