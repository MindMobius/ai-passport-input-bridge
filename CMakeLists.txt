cmake_minimum_required(VERSION 3.16)

# 固件版本(写进 app descriptor,device.hello 上报给电脑端)。
# 构建脚本在"源码副本"里编译(.git 不在),所以版本由 tools/build_firmware_wsl.sh
# 用 -DPROJECT_VER=<git describe> 注入;裸 idf.py build 时退回 "dev",
# 免得控制台设备信息面板显示一个没有信息量的默认值 "1"。
set(PROJECT_VER "dev" CACHE STRING "Firmware version baked into the app descriptor")

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(FoloToy-AI-Passport)
