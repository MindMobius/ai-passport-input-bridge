#!/usr/bin/env bash
set -euo pipefail

# Build the patched firmware inside WSL, then copy the merged image back to the
# Windows workspace. Set IDF_DIR to override the ESP-IDF checkout location.
PROJECT_DIR="${PROJECT_DIR:-$(pwd)}"
IDF_DIR="${IDF_DIR:-$HOME/esp/esp-idf-5.5.3-jihu}"
BUILD_SRC="${BUILD_SRC:-$HOME/codex-build/passport-wechat-bridge-$(date +%Y%m%d-%H%M%S)}"
BUILD_DIR="${BUILD_DIR:-$BUILD_SRC/build-wechat}"
OUT_DIR="$PROJECT_DIR/build/wechat"

if [[ ! -f "$IDF_DIR/export.sh" ]]; then
  echo "ERROR: ESP-IDF not found at $IDF_DIR" >&2
  exit 2
fi

mkdir -p "$BUILD_SRC"
# Copy only the files needed by the firmware build. This avoids stale Windows
# component caches and unrelated workspace artifacts.
cp -a "$PROJECT_DIR/CMakeLists.txt" "$BUILD_SRC/"
cp -a "$PROJECT_DIR/partitions.csv" "$BUILD_SRC/"
cp -a "$PROJECT_DIR/sdkconfig.defaults" "$BUILD_SRC/"
cp -a "$PROJECT_DIR/main" "$BUILD_SRC/"
cp -a "$PROJECT_DIR/components" "$BUILD_SRC/"
cp -a "$PROJECT_DIR/bootloader_components" "$BUILD_SRC/"
cp -a "$PROJECT_DIR/tools" "$BUILD_SRC/"

cd "$BUILD_SRC"
# shellcheck disable=SC1090
source "$IDF_DIR/export.sh"

idf.py -B "$BUILD_DIR" set-target esp32c3

# espressif/button is public, but this board needs the upstream ADC-glitch
# patch. Set-target downloads the component; overwrite the single patched file
# before the build step, exactly as the upstream project does.
BUTTON_PATCH="$PROJECT_DIR/patches/espressif__button/button_adc.c"
# 兼容旧工作区布局(补丁曾直接放在 managed_components/ 下)
if [[ ! -f "$BUTTON_PATCH" ]]; then
  BUTTON_PATCH="$PROJECT_DIR/managed_components/espressif__button/button_adc.c"
fi
BUTTON_TARGET="$BUILD_SRC/managed_components/espressif__button/button_adc.c"
if [[ -f "$BUTTON_PATCH" && -f "$BUTTON_TARGET" ]]; then
  cp "$BUTTON_PATCH" "$BUTTON_TARGET"
else
  echo "ERROR: button_adc.c patch or downloaded component is missing" >&2
  exit 2
fi

idf.py -B "$BUILD_DIR" build
idf.py -B "$BUILD_DIR" merge-bin -o "$BUILD_DIR/FoloToy-AI-Passport-full.bin"
python3 tools/verify_firmware.py "$BUILD_DIR"

mkdir -p "$OUT_DIR" "$OUT_DIR/segments"
cp "$BUILD_DIR/FoloToy-AI-Passport-full.bin" "$OUT_DIR/"
cp "$BUILD_DIR/flash_args" "$OUT_DIR/" 2>/dev/null || true
cp "$BUILD_DIR/bootloader/bootloader.bin" "$OUT_DIR/segments/bootloader.bin"
cp "$BUILD_DIR/partition_table/partition-table.bin" "$OUT_DIR/segments/partition-table.bin"
cp "$BUILD_DIR/FoloToy-AI-Passport.bin" "$OUT_DIR/segments/FoloToy-AI-Passport.bin"
cp "$BUILD_DIR/flash_args" "$OUT_DIR/segments/flash_args.txt" 2>/dev/null || true
echo "OUTPUT=$OUT_DIR/FoloToy-AI-Passport-full.bin"
